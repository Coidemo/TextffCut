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
        generate_buzz_clips_use_case: GenerateBuzzClipsUseCase,
        session_manager: Any = None,
    ):
        """
        初期化

        Args:
            view_model: ViewModel
            generate_buzz_clips_use_case: バズクリップ生成ユースケース
            session_manager: セッション管理
        """
        super().__init__(view_model)
        self.generate_buzz_clips_use_case = generate_buzz_clips_use_case
        self.session_manager = session_manager

    def initialize(self) -> None:
        """初期化処理"""
        logger.info("BuzzClipPresenter initialized")

        # セッションから状態を復元
        if self.session_manager:
            saved_state = self.session_manager.get("buzz_clip_state")
            if saved_state:
                self._restore_state(saved_state)

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

        # セッションに保存
        if self.session_manager:
            self._save_state()

    def generate_buzz_clips(
        self,
        transcription_segments: list[dict[str, Any]],
        video_path: str | Path | None = None,
        transcription_model: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        save_cache: bool = True,
    ) -> bool:
        """
        バズクリップを生成

        Args:
            transcription_segments: 文字起こしセグメント
            video_path: 動画ファイルパス（キャッシュ保存用）
            transcription_model: 文字起こしモデル名（キャッシュ紐付け用）
            progress_callback: 進捗コールバック
            save_cache: キャッシュに保存するか

        Returns:
            成功したかどうか
        """
        logger.info(f"Starting buzz clip generation with {len(transcription_segments)} segments")
        logger.info(f"Transcription model: {transcription_model}")

        # キャッシュから読み込みを試行
        if video_path and self.load_from_cache(video_path, transcription_model):
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

            # リクエストを作成
            request = GenerateBuzzClipsRequest(
                transcription_text=full_text,
                transcription_segments=transcription_segments,
                num_candidates=self.view_model.num_candidates,
                min_duration=self.view_model.min_duration,
                max_duration=self.view_model.max_duration,
                categories=self.view_model.selected_categories or None,
            )

            if progress_callback:
                progress_callback(0.2, "AIによる分析を実行中...")

            # ユースケースを実行
            response = self.generate_buzz_clips_use_case.execute(request)

            if not response.success:
                logger.error(f"Buzz clip generation failed: {response.error_message}")
                self.view_model.set_error(response.error_message or "生成に失敗しました")
                return False

            if progress_callback:
                progress_callback(0.9, "結果を処理中...")

            # 結果を設定
            self.view_model.complete_generation(
                candidates=response.candidates,
                processing_time=response.processing_time,
                model_used=response.model_used,
                token_usage=response.usage,
            )

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

    def _save_state(self) -> None:
        """状態をセッションに保存"""
        if not self.session_manager:
            return

        state = {
            "num_candidates": self.view_model.num_candidates,
            "min_duration": self.view_model.min_duration,
            "max_duration": self.view_model.max_duration,
            "selected_categories": self.view_model.selected_categories,
            "candidates": [c.to_dict() for c in self.view_model.candidates],
            "total_processing_time": self.view_model.total_processing_time,
            "model_used": self.view_model.model_used,
            "token_usage": self.view_model.token_usage,
        }

        self.session_manager.set("buzz_clip_state", state)

    def _restore_state(self, state: dict[str, Any]) -> None:
        """セッションから状態を復元"""
        self.view_model.num_candidates = state.get("num_candidates", 5)
        self.view_model.min_duration = state.get("min_duration", 30)
        self.view_model.max_duration = state.get("max_duration", 40)
        self.view_model.selected_categories = state.get("selected_categories", [])
        self.view_model.total_processing_time = state.get("total_processing_time", 0.0)
        self.view_model.model_used = state.get("model_used", "")
        self.view_model.token_usage = state.get("token_usage", {})

        # 候補を復元
        candidates = []
        for candidate_dict in state.get("candidates", []):
            # created_atの処理
            created_at = candidate_dict.get("created_at")
            if created_at and isinstance(created_at, str):
                # ISO形式の文字列からdatetimeに変換
                created_at = datetime.fromisoformat(created_at)
            elif not created_at:
                # created_atがない場合は現在時刻を使用
                created_at = datetime.now()

            candidate = BuzzClipCandidate(
                id=candidate_dict["id"],
                title=candidate_dict["title"],
                text=candidate_dict["text"],
                start_time=candidate_dict["start_time"],
                end_time=candidate_dict["end_time"],
                duration=candidate_dict["duration"],
                score=candidate_dict["score"],
                category=candidate_dict["category"],
                reasoning=candidate_dict["reasoning"],
                keywords=candidate_dict["keywords"],
                created_at=created_at,
            )
            candidates.append(candidate)

        if candidates:
            self.view_model.candidates = candidates

    def get_cache_path(self, video_path: str | Path, transcription_model: str = None) -> Path:
        """キャッシュファイルのパスを取得"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のtranscriptions/サブフォルダ（文字起こしと同じ場所）
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"
        cache_dir.mkdir(parents=True, exist_ok=True)

        # 文字起こしモデルに紐づけたファイル名
        if transcription_model:
            filename = f"{transcription_model}_buzz_{self.view_model.num_candidates}_{self.view_model.min_duration}_{self.view_model.max_duration}.json"
        else:
            # モデル名が不明な場合はデフォルト
            filename = f"buzz_{self.view_model.num_candidates}_{self.view_model.min_duration}_{self.view_model.max_duration}.json"
        return cache_dir / filename

    def save_to_cache(self, video_path: str | Path, transcription_model: str = None) -> None:
        """結果をキャッシュに保存"""
        if not self.view_model.candidates:
            return

        cache_path = self.get_cache_path(video_path, transcription_model)

        cache_data = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "transcription_model": transcription_model,  # 紐づいている文字起こしモデル
            "parameters": {
                "num_candidates": self.view_model.num_candidates,
                "min_duration": self.view_model.min_duration,
                "max_duration": self.view_model.max_duration,
                "selected_categories": self.view_model.selected_categories,
            },
            "results": {
                "candidates": [c.to_dict() for c in self.view_model.candidates],
                "total_processing_time": self.view_model.total_processing_time,
                "model_used": self.view_model.model_used,
                "token_usage": self.view_model.token_usage,
            },
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved buzz clip cache to {cache_path}")

    def load_from_cache(
        self, video_path: str | Path, transcription_model: str = None, auto_adjust_params: bool = True
    ) -> bool:
        """キャッシュから結果を読み込み

        Args:
            video_path: 動画ファイルパス
            transcription_model: 文字起こしモデル名
            auto_adjust_params: キャッシュのパラメータに自動調整するか
        """
        # まず、利用可能なキャッシュを探す
        if auto_adjust_params:
            cache_files = self._find_available_buzz_caches(video_path, transcription_model)
            if cache_files:
                # 最新のキャッシュを選択
                cache_path = cache_files[0]
                logger.info(f"Found buzz clip cache: {cache_path}")
            else:
                logger.info("No buzz clip cache found")
                return False
        else:
            cache_path = self.get_cache_path(video_path, transcription_model)
            if not cache_path.exists():
                logger.info(f"Cache file does not exist: {cache_path}")
                return False

        try:
            with open(cache_path, encoding="utf-8") as f:
                cache_data = json.load(f)

            # パラメータが一致するか確認
            params = cache_data.get("parameters", {})
            logger.info(f"Cache params: {params}")
            logger.info(
                f"Current params: num_candidates={self.view_model.num_candidates}, min_duration={self.view_model.min_duration}, max_duration={self.view_model.max_duration}, selected_categories={self.view_model.selected_categories}"
            )

            if auto_adjust_params:
                # パラメータをキャッシュに合わせて更新
                self.view_model.num_candidates = params.get("num_candidates", 5)
                self.view_model.min_duration = params.get("min_duration", 30)
                self.view_model.max_duration = params.get("max_duration", 40)
                self.view_model.selected_categories = params.get("selected_categories", [])
                logger.info("Auto-adjusted parameters to match cache")
            else:
                # 通常のパラメータチェック
                if (
                    params.get("num_candidates") != self.view_model.num_candidates
                    or params.get("min_duration") != self.view_model.min_duration
                    or params.get("max_duration") != self.view_model.max_duration
                    or params.get("selected_categories") != self.view_model.selected_categories
                ):
                    logger.info("Cache parameters do not match current settings")
                    return False

            # 結果を復元
            results = cache_data.get("results", {})
            candidates = []
            for candidate_dict in results.get("candidates", []):
                # datetimeの変換
                created_at = datetime.fromisoformat(candidate_dict["created_at"])
                candidate = BuzzClipCandidate(
                    id=candidate_dict["id"],
                    title=candidate_dict["title"],
                    text=candidate_dict["text"],
                    start_time=candidate_dict["start_time"],
                    end_time=candidate_dict["end_time"],
                    duration=candidate_dict["duration"],
                    score=candidate_dict["score"],
                    category=candidate_dict["category"],
                    reasoning=candidate_dict["reasoning"],
                    keywords=candidate_dict["keywords"],
                    created_at=created_at,
                )
                candidates.append(candidate)

            self.view_model.complete_generation(
                candidates=candidates,
                processing_time=results.get("total_processing_time", 0.0),
                model_used=results.get("model_used", ""),
                token_usage=results.get("token_usage", {}),
            )

            logger.info(f"Loaded {len(candidates)} buzz clips from cache")
            return True

        except Exception as e:
            logger.error(f"Failed to load buzz clip cache: {e}")
            return False

    def _find_available_buzz_caches(self, video_path: str | Path, transcription_model: str = None) -> list[Path]:
        """利用可能なバズクリップキャッシュを探す"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のtranscriptions/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"

        if not cache_dir.exists():
            return []

        # バズクリップのキャッシュファイルを検索
        cache_files = []
        if transcription_model:
            # 特定のモデルに紐づいたキャッシュを探す
            pattern = f"{transcription_model}_buzz_*.json"
        else:
            # すべてのバズクリップキャッシュを探す
            pattern = "*_buzz_*.json"

        for cache_file in cache_dir.glob(pattern):
            cache_files.append(cache_file)

        # 更新時刻でソート（新しい順）
        cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return cache_files
