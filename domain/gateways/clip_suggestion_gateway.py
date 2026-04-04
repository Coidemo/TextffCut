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
    def check_connection(self) -> bool:
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        pass
