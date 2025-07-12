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

        # 外部AIサービスを使用する新しい実装ではセッション復元は不要
        # if self.session_manager:
        #     saved_state = self.session_manager.get("buzz_clip_state")
        #     if saved_state:
        #         self._restore_state(saved_state)

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

        # 外部AIサービスを使用する新しい実装ではセッション保存は不要
        # if self.session_manager:
        #     self._save_state()

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
    
    def _format_segments(self, segments: list[dict[str, Any]]) -> str:
        """セグメントをフォーマット"""
        formatted_lines = []
        for seg in segments:
            time_str = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
            formatted_lines.append(f"{time_str} {seg['text']}")
        return "\n".join(formatted_lines)
    
    def _get_system_prompt(self) -> str:
        """システムプロンプトを取得"""
        return """あなたは「保存したくなる」「誰かに教えたくなる」ショート動画を特定する専門家です。
長い会話から、視聴者が「これは役立つ！」「あるある！」と思う部分を見つけることが得意です。

以下の基準で切り抜き候補を選んでください：

1. 実用性（すぐに実践できる具体的なアドバイスや解決策）
2. 共感性（「あるある」「それな！」と思える日常の悩みや疑問）  
3. 明快さ（断定的で分かりやすい主張、「なるほど！」という気づき）
4. 現代性（AI、リモートワークなど現代的な話題やツール）
5. 完結性（問題提起→原因分析→解決策の流れが30-40秒で完結）

特に以下のような内容を優先してください：
- 仕事や人間関係の悩みへの具体的な解決策
- 日常の「あるある」や素朴な疑問への答え
- すぐに試せるライフハックや仕事術
- 「そういう考え方があったのか！」という新しい視点

各候補に0-20のスコアを付けて、スコアの高い順に返してください。"""
    
    def _create_user_prompt(self, segments_text: str) -> str:
        """ユーザープロンプトを作成"""
        prompt = f"""以下の動画の文字起こし結果から、{self.view_model.min_duration}〜{self.view_model.max_duration}秒の「保存したくなる」切り抜きショート動画の候補を{self.view_model.num_candidates}個選んでください。

【文字起こし結果】
{segments_text}

【編集ルール】※違反は不採用
1. 引用厳守：文字起こし結果の文字のみ使用（一切の追加禁止）
2. フィラー削除：「あの」「その」「えっと」「まあ」などを削る
3. 大胆カット：本筋に関係ない例示・補足説明・挨拶は削除
4. 重複削除：同じ内容の繰り返しは1回に圧縮
5. 数字・単位：原文のまま（95パー→ 95パー）
6. 語尾：重複語尾は1回に圧縮しつつ原文を保持

【選定基準】  
- 各候補は{self.view_model.min_duration}〜{self.view_model.max_duration}秒の長さ（約150-250文字目安）
- 「これは保存したい！」「誰かに教えたい！」と思える内容
- 断定的で分かりやすい主張
- 読後に「行動」か「気づき」が残る形で締める

【構成パターン】（どれか1つを選択）
A. Q→A型：問題提起→解決策→行動提案
B. 主張型：主張→理由→提案／未来予測
C. Tips型：結論→具体例の列挙（「〜すると」「〜とか」で並列）

- タイトルは「〇〇する方法」「〇〇の理由」など実用的に
- スコア（0-20）で評価"""
        
        if self.view_model.selected_categories:
            prompt += f"\n\n優先カテゴリ: {', '.join(self.view_model.selected_categories)}"
        
        prompt += """

【出力形式】
JSON形式で以下の構造で出力してください：
{
  "clips": [
    {
      "title": "タイトル案",
      "text": "切り抜き部分のテキスト",
      "start_time": 開始時間（秒）,
      "end_time": 終了時間（秒）,
      "score": バズスコア（0-20）,
      "category": "カテゴリ（仕事術/人間関係/ライフハック/日常の疑問/新しい視点/その他）",
      "reasoning": "選定理由",
      "keywords": ["キーワード1", "キーワード2"]
    }
  ]
}

【セルフ検品フェーズ】（全案に必ず実行）
① 時間…{self.view_model.min_duration}〜{self.view_model.max_duration}秒内か
② 引用違反…原文にない語彙・語順変更がないか
③ フィラー残存…「えー」「あの」等を取り除いたか
④ 余談残り…挨拶や無関係な例示が残っていないか
⑤ 構成…A〜Cいずれかに適合しているか
→ 1つでもNG項目があれば該当案を再生成せよ。"""
        
        return prompt

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
        
        """# 以下は旧実装のコード（コメントアウト）
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
        """

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
        
        """# 以下は旧実装のコード（コメントアウト）
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
        """

    def _find_available_buzz_caches(self, video_path: str | Path, transcription_model: str = None) -> list[Path]:
        """利用可能なバズクリップキャッシュを探す"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のbuzz_clips/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "buzz_clips"

        if not cache_dir.exists():
            return []

        # バズクリップのキャッシュファイルを検索
        cache_files = []
        if transcription_model:
            # 特定のモデルに紐づいたキャッシュを探す
            cache_file = cache_dir / f"{transcription_model}.json"
            if cache_file.exists():
                cache_files.append(cache_file)
        else:
            # すべてのバズクリップキャッシュを探す
            for cache_file in cache_dir.glob("*.json"):
                cache_files.append(cache_file)

        # 更新時刻でソート（新しい順）
        cache_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return cache_files
