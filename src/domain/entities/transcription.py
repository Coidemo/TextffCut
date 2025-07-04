"""
Transcription Entity

文字起こし結果を表現するエンティティ
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..value_objects import TimeRange


@dataclass
class TranscriptionSegment:
    """文字起こしの1セグメント"""

    id: str
    text: str
    start: float
    end: float
    confidence: float = 1.0
    speaker: str | None = None

    def __post_init__(self):
        """バリデーション"""
        if self.start < 0:
            raise ValueError(f"Start time cannot be negative: {self.start}")
        if self.end < self.start:
            raise ValueError(f"End time must be after start time: start={self.start}, end={self.end}")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confidence must be between 0 and 1: {self.confidence}")

    @property
    def time_range(self) -> TimeRange:
        """時間範囲を取得"""
        return TimeRange(start=self.start, end=self.end)

    @property
    def duration(self) -> float:
        """継続時間を取得"""
        return self.end - self.start

    def contains_time(self, time: float) -> bool:
        """指定時刻がセグメント内に含まれるか確認"""
        return self.start <= time <= self.end

    def overlaps(self, other: "TranscriptionSegment") -> bool:
        """他のセグメントと重なっているか確認"""
        return self.time_range.overlaps(other.time_range)


@dataclass
class TranscriptionResult:
    """文字起こし結果全体"""

    id: str = field(default_factory=lambda: str(uuid4()))
    language: str = "ja"
    segments: list[TranscriptionSegment] = field(default_factory=list)
    original_audio_path: str = ""
    model_size: str = "large-v2"
    processing_time: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def text(self) -> str:
        """全セグメントのテキストを結合"""
        return " ".join(seg.text for seg in self.segments)

    @property
    def duration(self) -> float:
        """全体の継続時間"""
        if not self.segments:
            return 0.0
        return max(seg.end for seg in self.segments)

    @property
    def segment_count(self) -> int:
        """セグメント数"""
        return len(self.segments)

    @property
    def average_confidence(self) -> float:
        """平均信頼度"""
        if not self.segments:
            return 0.0
        return sum(seg.confidence for seg in self.segments) / len(self.segments)

    def get_segment_at_time(self, time: float) -> TranscriptionSegment | None:
        """指定時刻のセグメントを取得"""
        for segment in self.segments:
            if segment.contains_time(time):
                return segment
        return None

    def get_segments_in_range(self, time_range: TimeRange) -> list[TranscriptionSegment]:
        """指定時間範囲内のセグメントを取得"""
        result = []
        for segment in self.segments:
            if segment.time_range.overlaps(time_range):
                result.append(segment)
        return result

    def merge_continuous_segments(self, max_gap: float = 0.1) -> "TranscriptionResult":
        """
        連続するセグメントをマージ

        Args:
            max_gap: マージする最大ギャップ（秒）

        Returns:
            マージされた新しいTranscriptionResult
        """
        if not self.segments:
            return TranscriptionResult(
                id=self.id,
                language=self.language,
                original_audio_path=self.original_audio_path,
                model_size=self.model_size,
                processing_time=self.processing_time,
                metadata=self.metadata.copy(),
            )

        merged_segments = []
        current_segment = None

        for segment in sorted(self.segments, key=lambda s: s.start):
            if current_segment is None:
                # 最初のセグメント
                current_segment = TranscriptionSegment(
                    id=segment.id,
                    text=segment.text,
                    start=segment.start,
                    end=segment.end,
                    confidence=segment.confidence,
                    speaker=segment.speaker,
                )
            elif segment.start - current_segment.end <= max_gap:
                # マージ可能
                current_segment = TranscriptionSegment(
                    id=current_segment.id,
                    text=current_segment.text + " " + segment.text,
                    start=current_segment.start,
                    end=segment.end,
                    confidence=(current_segment.confidence + segment.confidence) / 2,
                    speaker=current_segment.speaker if current_segment.speaker == segment.speaker else None,
                )
            else:
                # マージ不可、新しいセグメント開始
                merged_segments.append(current_segment)
                current_segment = TranscriptionSegment(
                    id=segment.id,
                    text=segment.text,
                    start=segment.start,
                    end=segment.end,
                    confidence=segment.confidence,
                    speaker=segment.speaker,
                )

        if current_segment:
            merged_segments.append(current_segment)

        return TranscriptionResult(
            id=self.id,
            language=self.language,
            segments=merged_segments,
            original_audio_path=self.original_audio_path,
            model_size=self.model_size,
            processing_time=self.processing_time,
            metadata=self.metadata.copy(),
        )
