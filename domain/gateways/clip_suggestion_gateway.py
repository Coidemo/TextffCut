"""
AI切り抜き候補生成ゲートウェイのインターフェース
"""

from abc import ABC, abstractmethod

from domain.entities.clip_suggestion import (
    TopicDetectionRequest,
    TopicDetectionResult,
)


class ClipSuggestionGatewayInterface(ABC):
    """AI切り抜き候補生成ゲートウェイのインターフェース"""

    @abstractmethod
    def detect_topics(self, request: TopicDetectionRequest) -> TopicDetectionResult:
        """話題の時間範囲を検出する（テキスト編集は行わない）"""
        pass

    @abstractmethod
    def select_best_variant(
        self, topic_title: str, variants: list[dict]
    ) -> int | None:
        """複数のクリップパターンからベストを選定する。

        Args:
            topic_title: 話題のタイトル
            variants: パターンのリスト（各要素にlabel, text, duration）

        Returns:
            選定されたvariantのインデックス（0始まり）。選定できない場合はNone。
        """
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
    def review_naturalness(
        self,
        title: str,
        segments_text: list[str],
        cut_issues: list[dict],
    ) -> list[dict]:
        """カット後のテキストと音声特徴を見て自然さをレビューする。

        Args:
            title: 話題のタイトル
            segments_text: カット後の各クリップのテキスト
            cut_issues: ピッチ分析で検出された問題のリスト

        Returns:
            修正提案のリスト [{"action": "extend"|"keep"|"remove", "index": int, "reason": str}]
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
            {"ok": bool, "issues": list[str], "fix_suggestions": list[str]}
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
    def check_connection(self) -> bool:
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        pass
