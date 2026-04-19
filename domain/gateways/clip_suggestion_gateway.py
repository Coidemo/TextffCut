"""
AI切り抜き候補生成ゲートウェイのインターフェース
"""

from abc import ABC, abstractmethod
from typing import Any

from domain.entities.clip_suggestion import (
    TopicDetectionRequest,
    TopicDetectionResult,
)


class ClipSuggestionGatewayInterface(ABC):
    """AI切り抜き候補生成ゲートウェイのインターフェース"""

    @abstractmethod
    def detect_topics(self, request: TopicDetectionRequest, format_mode: str = "chunk_30s") -> TopicDetectionResult:
        """話題の時間範囲を検出する（テキスト編集は行わない）"""
        pass

    @abstractmethod
    def judge_segment_relevance(
        self,
        title: str,
        segments: list[dict],
    ) -> list[int]:
        """各セグメントが切り抜きに必要かAIに判定させる。

        Args:
            title: 話題のタイトル
            segments: [{"index": int, "text": str, "start": float, "end": float}]

        Returns:
            除外すべきセグメントのインデックスリスト
        """
        pass

    @abstractmethod
    def evaluate_clip_quality(
        self,
        title: str,
        transcribed_text: str,
        audio_issues: list[str] | None = None,
    ) -> dict:
        """出来上がり音声の品質をAIに判定させる。

        Args:
            title: クリップのタイトル
            transcribed_text: 出来上がり音声の文字起こしテキスト
            audio_issues: 音響分析で検出された問題のリスト

        Returns:
            {"ok": bool, "issues": list[str], "fix_suggestions": list[str],
             "scores": {"hook": int, "completeness": int, "compactness": int,
                        "ending": int, "title_relevance": int}}
        """
        pass

    @abstractmethod
    def select_best_clip(
        self,
        title: str,
        candidates_text: str,
    ) -> int:
        """複数候補の出来上がりテキストから最良を選定する。

        Args:
            title: 話題のタイトル
            candidates_text: 候補一覧のフォーマット済みテキスト

        Returns:
            選定された候補番号（1始まり）
        """
        pass

    @abstractmethod
    def trim_clips(
        self,
        title: str,
        clips_text: str,
        max_duration: float,
    ) -> list[int]:
        """デュレーション超過時に削除すべきクリップを選定する。

        Args:
            title: クリップのタイトル
            clips_text: クリップ一覧と出来上がりテキストのフォーマット済み文字列
            max_duration: 目標最大秒数

        Returns:
            削除すべきクリップのインデックスリスト
        """
        pass

    @abstractmethod
    def refine_topic_boundary(
        self,
        title: str,
        all_segments: list[dict],
        extension_candidates: list[dict],
    ) -> dict:
        """話題範囲の適切な終了位置を判定する。

        Args:
            title: 話題のタイトル
            all_segments: 話題の全セグメント [{"index": int, "text": str, "start": float, "end": float}]
            extension_candidates: 後続10セグメント

        Returns:
            {"action": "keep" | "trim" | "extend",
             "end_segment_index": int,
             "is_complete": bool,
             "reason": str}
        """
        pass

    @abstractmethod
    def find_core_and_conclusion(
        self,
        title: str,
        segments: list[dict],
    ) -> dict:
        """骨子（核心の主張）と結び（まとめ）のセグメント位置を特定する。

        Args:
            title: 話題のタイトル
            segments: [{"idx": int, "text": str}]

        Returns:
            {"core": [{"start": int, "end": int, "summary": str}],
             "conclusion": [{"start": int, "end": int, "summary": str}]}
        """
        pass

    @property
    @abstractmethod
    def client(self) -> Any:
        """OpenAIクライアントを返す（タイトル画像・アンカー検出等で使用）。"""
        pass

    @property
    @abstractmethod
    def api_key(self) -> str | None:
        """APIキーを返す（SRT生成でWhisper APIに使用）。"""
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        pass
