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
    def detect_topics(self, request: TopicDetectionRequest, format_mode: str = "chunk_30s") -> TopicDetectionResult:
        """話題の時間範囲を検出する（テキスト編集は行わない）"""
        pass

    @abstractmethod
    def select_best_variant(self, topic_title: str, variants: list[dict]) -> int | None:
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
    def select_clip_segments(
        self,
        title: str,
        segments: list[dict],
        min_duration: float,
        max_duration: float,
        num_variants: int = 2,
    ) -> list[list[int]]:
        """話題のセグメント一覧から、ショート動画に使うセグメントのindexリストを返す。

        Args:
            title: 話題のタイトル
            segments: [{"index": int, "text": str, "start": float, "end": float}]
            min_duration: 目標最小秒数
            max_duration: 目標最大秒数
            num_variants: 生成するバリアント数

        Returns:
            バリアントごとのindexリスト [[28,29,36,...], [24,28,29,36,...]]
            各リストはindex昇順。空リスト=失敗。
        """
        pass

    @abstractmethod
    def classify_segment_essentiality(
        self,
        title: str,
        segments: list[dict],
    ) -> list[dict]:
        """各セグメントを essential/supportive/redundant に分類する。

        Args:
            title: 話題のタイトル
            segments: [{"index": int, "text": str, "start": float, "end": float}]

        Returns:
            [{"index": int, "role": "essential"|"supportive"|"redundant", "reason": str}]
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
    def compute_embeddings(self, texts: list[str]) -> list[list[float]]:
        """テキストリストのembeddingベクトルを返す。"""
        pass

    @abstractmethod
    def judge_filler_context(
        self,
        candidates: list[dict],
    ) -> list[bool]:
        """フィラー候補が実際にフィラーかどうかをAIに判定させる。

        Args:
            candidates: [{"filler": "なんか", "context": "前後30文字のテキスト"}]

        Returns:
            各候補がフィラーかどうか（True=フィラー、False=文法的用法）
        """
        pass

    @abstractmethod
    def verify_topic_completeness(
        self,
        title: str,
        range_segments: list[dict],
        extension_candidates: list[dict],
    ) -> int:
        """話題の論点が完結しているか検証し、追加すべきセグメント数を返す。

        Args:
            title: 話題のタイトル
            range_segments: 現在の範囲内セグメント（最後の5件）
            extension_candidates: 範囲直後のセグメント（拡張候補、最大5件）

        Returns:
            追加すべきセグメント数（0=完結済み）
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
    def validate_clip_candidates(
        self,
        title: str,
        candidates: list[dict],
        original_text: str = "",
    ) -> list[bool]:
        """各候補テキストが話題の趣旨を保っているか検証する。

        Args:
            title: 話題のタイトル
            candidates: [{"index": 0, "text": "候補テキスト", "duration": 30.0}]
            original_text: 話題の全テキスト（フィラー除去済み）。空文字の場合は従来動作。

        Returns:
            各候補の有効性（True=趣旨保持、False=不適切）
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

    @abstractmethod
    def check_connection(self) -> bool:
        pass

    @abstractmethod
    def get_available_models(self) -> list[str]:
        pass
