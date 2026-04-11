"""
バズクリップ生成のPresenter
"""

import json
import logging
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.presenters.base import BasePresenter
from presentation.view_models.buzz_clip import BuzzClipViewModel
from use_cases.ai.generate_buzz_clips import (
    GenerateBuzzClipsRequest,
    GenerateBuzzClipsUseCase,
)

logger = logging.getLogger(__name__)


class BuzzClipPresenter(BasePresenter[BuzzClipViewModel]):
    """
    バズクリップ生成のPresenter

    バズクリップ生成機能のビジネスロジックとViewの橋渡しを行います。
    """

    def __init__(
        self,
        view_model: BuzzClipViewModel,
        generate_buzz_clips_use_case: GenerateBuzzClipsUseCase | None = None,
        session_manager: Any = None,
    ):
        """
        初期化

        Args:
            view_model: ViewModel
            generate_buzz_clips_use_case: バズクリップ生成ユースケース（外部AIサービス版では不要）
            session_manager: セッション管理
        """
        super().__init__(view_model)
        self.generate_buzz_clips_use_case = generate_buzz_clips_use_case
        self.session_manager = session_manager

    def initialize(self) -> None:
        """初期化処理"""
        logger.info("BuzzClipPresenter initialized")

    def set_generation_params(
        self, num_candidates: int, min_duration: int, max_duration: int, categories: list[str]
    ) -> None:
        """
        生成パラメータを設定

        Args:
            num_candidates: 候補数
            min_duration: 最小時間（秒）
            max_duration: 最大時間（秒）
            categories: カテゴリリスト
        """
        self.view_model.num_candidates = num_candidates
        self.view_model.min_duration = min_duration
        self.view_model.max_duration = max_duration
        self.view_model.selected_categories = categories

    def generate_buzz_clips(
        self,
        transcription_segments: list[dict[str, Any]],
        video_path: str | Path | None = None,
        transcription_model: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        save_cache: bool = True,
        append_to_existing: bool = False,
    ) -> bool:
        """
        バズクリップを生成

        Args:
            transcription_segments: 文字起こしセグメント
            video_path: 動画ファイルパス（キャッシュ保存用）
            transcription_model: 文字起こしモデル名（キャッシュ紐付け用）
            progress_callback: 進捗コールバック
            save_cache: キャッシュに保存するか
            append_to_existing: 既存の候補に追加するか

        Returns:
            成功したかどうか
        """
        logger.info(f"Starting buzz clip generation with {len(transcription_segments)} segments")
        logger.info(f"Transcription model: {transcription_model}")
        logger.info(f"Append to existing: {append_to_existing}")

        # 既存の候補を保持（追加モードの場合）
        existing_candidates = []
        if append_to_existing and self.view_model.candidates:
            existing_candidates = list(self.view_model.candidates)
            logger.info(f"Keeping {len(existing_candidates)} existing candidates")

        # キャッシュから読み込みを試行（追加モードでない場合のみ）
        if not append_to_existing and video_path and self.load_from_cache(video_path, transcription_model):
            logger.info("Loaded buzz clips from cache")
            # セッションに保存
            if self.session_manager:
                self._save_state()
            return True

        try:
            # 生成開始
            self.view_model.start_generation()

            if progress_callback:
                progress_callback(0.1, "文字起こし結果を準備中...")

            # 全テキストを結合
            full_text = "\n".join([seg["text"] for seg in transcription_segments])

            # リクエストを作成（既存候補を含める）
            request = GenerateBuzzClipsRequest(
                transcription_text=full_text,
                transcription_segments=transcription_segments,
                num_candidates=self.view_model.num_candidates,
                min_duration=self.view_model.min_duration,
                max_duration=self.view_model.max_duration,
                categories=self.view_model.selected_categories or None,
                existing_candidates=existing_candidates if append_to_existing else None,
            )

            if progress_callback:
                progress_callback(0.2, "AIによる分析を実行中...")

            # ユースケースを実行
            logger.info("Calling use case execute method")
            response = self.generate_buzz_clips_use_case.execute(request)
            logger.info(
                f"Use case response: success={response.success}, candidates={len(response.candidates) if response.candidates else 0}"
            )

            if not response.success:
                logger.error(f"Buzz clip generation failed: {response.error_message}")
                self.view_model.set_error(response.error_message or "生成に失敗しました")
                return False

            if progress_callback:
                progress_callback(0.9, "結果を処理中...")

            # 結果を設定（追加モードの場合は既存と結合）
            if append_to_existing and existing_candidates:
                all_candidates = existing_candidates + response.candidates
                logger.info(
                    f"Merging {len(existing_candidates)} existing + {len(response.candidates)} new = {len(all_candidates)} total candidates"
                )
            else:
                all_candidates = response.candidates

            logger.info(f"Setting {len(all_candidates)} candidates to view model")
            self.view_model.complete_generation(
                candidates=all_candidates,
                processing_time=response.processing_time,
                model_used=response.model_used,
                token_usage=response.usage,
            )
            logger.info(f"View model now has {len(self.view_model.candidates)} candidates")

            # セッションに保存
            if self.session_manager:
                self._save_state()

            if progress_callback:
                progress_callback(1.0, "完了")

            logger.info(f"Generated {len(response.candidates)} buzz clip candidates")

            # キャッシュに保存
            if save_cache and video_path:
                self.save_to_cache(video_path, transcription_model)
                logger.info("Saved buzz clips to cache")

            return True

        except Exception as e:
            logger.error(f"Error generating buzz clips: {e}")
            self.view_model.set_error(str(e))
            return False

    def reset(self) -> None:
        """状態をリセット"""
        self.view_model.reset()

        # セッションからも削除
        if self.session_manager:
            self.session_manager.set("buzz_clip_state", None)

    def generate_prompt_for_external_ai(self, transcription_segments: list[dict[str, Any]]) -> str:
        """外部AIサービス用のプロンプトを生成"""
        logger.info("Generating prompt for external AI service")

        from utils.prompt_loader import PromptLoader

        loader = PromptLoader()
        prompt = loader.load_buzz_clip_prompt(transcription_segments)

        return prompt

    def get_cache_path(self, video_path: str | Path, transcription_model: str = None) -> Path:
        """キャッシュファイルのパスを取得"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のbuzz_clips/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "buzz_clips"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 文字起こしモデルに紐づけたファイル名（シンプルに）
        if transcription_model:
            filename = f"{transcription_model}.json"
        else:
            # モデル名が不明な場合はデフォルト
            filename = "default.json"
        return cache_dir / filename

    def save_to_cache(self, video_path: str | Path, transcription_model: str = None) -> None:
        """結果をキャッシュに保存（外部AIサービス版では使用しない）"""
        # 外部AIサービスを使用する新しい実装ではキャッシュ保存は不要
        logger.info("save_to_cache called but skipped in external AI service mode")
        return

    def load_from_cache(
        self, video_path: str | Path, transcription_model: str = None, auto_adjust_params: bool = True
    ) -> bool:
        """キャッシュから結果を読み込み（外部AIサービス版では使用しない）

        Args:
            video_path: 動画ファイルパス
            transcription_model: 文字起こしモデル名
            auto_adjust_params: キャッシュのパラメータに自動調整するか
        """
        # 外部AIサービスを使用する新しい実装ではキャッシュ読み込みは不要
        logger.info("load_from_cache called but skipped in external AI service mode")
        return False
