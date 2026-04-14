"""
AI切り抜き候補のドメインエンティティ

3段階パイプライン:
1. TopicRange: AIが指定した話題の時間範囲
2. ClipVariant: 機械的に生成されたトリミングパターン
3. ClipSuggestion: 最終的な切り抜き候補（FCPXML出力用）
"""

import uuid
from dataclasses import dataclass, field


@dataclass
class TopicRange:
    """AIが指定した話題の時間範囲"""

    id: str
    title: str
    segment_start_index: int
    segment_end_index: int
    score: int
    category: str
    reasoning: str
    keywords: list[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        title: str,
        segment_start_index: int,
        segment_end_index: int,
        score: int = 0,
        category: str = "",
        reasoning: str = "",
        keywords: list[str] | None = None,
    ) -> "TopicRange":
        return cls(
            id=str(uuid.uuid4()),
            title=title,
            segment_start_index=segment_start_index,
            segment_end_index=segment_end_index,
            score=score,
            category=category,
            reasoning=reasoning,
            keywords=keywords or [],
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "segment_start_index": self.segment_start_index,
            "segment_end_index": self.segment_end_index,
            "score": self.score,
            "category": self.category,
            "reasoning": self.reasoning,
            "keywords": self.keywords,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TopicRange":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data["title"],
            segment_start_index=data["segment_start_index"],
            segment_end_index=data["segment_end_index"],
            score=data.get("score", 0),
            category=data.get("category", ""),
            reasoning=data.get("reasoning", ""),
            keywords=data.get("keywords", []),
        )


@dataclass
class ClipVariant:
    """機械的に生成されたトリミングパターン"""

    id: str
    topic_id: str
    text: str  # フィラー削除済みの原文テキスト
    time_ranges: list[tuple[float, float]]
    total_duration: float
    quality_score: float  # 機械的な品質スコア
    label: str  # パターンの説明（例: "フル版", "前半トリム", "コア部分のみ"）

    @classmethod
    def create(
        cls,
        topic_id: str,
        text: str,
        time_ranges: list[tuple[float, float]],
        quality_score: float = 0.0,
        label: str = "",
    ) -> "ClipVariant":
        total = sum(end - start for start, end in time_ranges)
        return cls(
            id=str(uuid.uuid4()),
            topic_id=topic_id,
            text=text,
            time_ranges=time_ranges,
            total_duration=total,
            quality_score=quality_score,
            label=label,
        )


@dataclass
class ClipSuggestion:
    """最終的な切り抜き候補（FCPXML出力用）"""

    id: str
    title: str
    text: str
    time_ranges: list[tuple[float, float]]
    total_duration: float
    score: int
    category: str
    reasoning: str
    keywords: list[str] = field(default_factory=list)
    variant_label: str = ""
    topic_start_time: float | None = None
    topic_end_time: float | None = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "time_ranges": self.time_ranges,
            "total_duration": self.total_duration,
            "score": self.score,
            "category": self.category,
            "reasoning": self.reasoning,
            "keywords": self.keywords,
            "variant_label": self.variant_label,
        }
        if self.topic_start_time is not None:
            d["topic_start_time"] = self.topic_start_time
        if self.topic_end_time is not None:
            d["topic_end_time"] = self.topic_end_time
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ClipSuggestion":
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            title=data["title"],
            text=data.get("text", ""),
            time_ranges=data.get("time_ranges", []),
            total_duration=data.get("total_duration", 0.0),
            score=data.get("score", 0),
            category=data.get("category", ""),
            reasoning=data.get("reasoning", ""),
            keywords=data.get("keywords", []),
            variant_label=data.get("variant_label", ""),
            topic_start_time=data.get("topic_start_time"),
            topic_end_time=data.get("topic_end_time"),
        )


@dataclass
class TopicDetectionRequest:
    """話題範囲検出リクエスト"""

    transcription_segments: list[dict]
    num_candidates: int = 5
    min_duration: int = 30
    max_duration: int = 60
    prompt_path: str | None = None


@dataclass
class TopicDetectionResult:
    """話題範囲検出結果"""

    topics: list[TopicRange]
    model_used: str
    processing_time: float
    token_usage: dict = field(default_factory=dict)
    estimated_cost_usd: float = 0.0
