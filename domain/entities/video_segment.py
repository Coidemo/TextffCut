"""
動画セグメントのドメインエンティティ

動画の一部分を表すエンティティ。
無音削除や切り抜きで使用される。
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from uuid import uuid4


@dataclass
class VideoSegment:
    """動画セグメントエンティティ"""
    id: str
    start: float
    end: float
    is_silence: bool = False
    metadata: Optional[dict] = None
    
    def __post_init__(self):
        """バリデーション"""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be greater than start time")
    
    @property
    def duration(self) -> float:
        """セグメントの継続時間"""
        return self.end - self.start
    
    @property
    def time_range(self) -> Tuple[float, float]:
        """時間範囲のタプル"""
        return (self.start, self.end)
    
    def overlaps_with(self, other: "VideoSegment") -> bool:
        """他のセグメントと重なっているか確認"""
        return self.start < other.end and self.end > other.start
    
    def contains(self, time: float) -> bool:
        """指定された時刻がセグメント内に含まれるか確認"""
        return self.start <= time <= self.end
    
    def merge_with(self, other: "VideoSegment") -> "VideoSegment":
        """他のセグメントとマージ（隣接または重複している場合）"""
        if not self.overlaps_with(other) and abs(self.end - other.start) > 0.001 and abs(other.end - self.start) > 0.001:
            raise ValueError("Segments must be adjacent or overlapping to merge")
        
        return VideoSegment(
            id=str(uuid4()),
            start=min(self.start, other.start),
            end=max(self.end, other.end),
            is_silence=self.is_silence and other.is_silence,
            metadata={**(self.metadata or {}), **(other.metadata or {})}
        )
    
    def split_at(self, time: float) -> Tuple["VideoSegment", "VideoSegment"]:
        """指定された時刻でセグメントを分割"""
        if not self.contains(time):
            raise ValueError(f"Split time {time} is outside segment range [{self.start}, {self.end}]")
        
        if time == self.start or time == self.end:
            raise ValueError("Cannot split at segment boundaries")
        
        first = VideoSegment(
            id=str(uuid4()),
            start=self.start,
            end=time,
            is_silence=self.is_silence,
            metadata=self.metadata.copy() if self.metadata else None
        )
        
        second = VideoSegment(
            id=str(uuid4()),
            start=time,
            end=self.end,
            is_silence=self.is_silence,
            metadata=self.metadata.copy() if self.metadata else None
        )
        
        return first, second
    
    def with_padding(self, start_padding: float, end_padding: float) -> "VideoSegment":
        """パディングを追加した新しいセグメントを作成"""
        return VideoSegment(
            id=str(uuid4()),
            start=max(0, self.start - start_padding),
            end=self.end + end_padding,
            is_silence=self.is_silence,
            metadata={
                **(self.metadata or {}),
                "original_start": self.start,
                "original_end": self.end,
                "start_padding": start_padding,
                "end_padding": end_padding
            }
        )
    
    @classmethod
    def from_time_range(cls, time_range: Tuple[float, float], is_silence: bool = False) -> "VideoSegment":
        """時間範囲タプルからセグメントを作成"""
        return cls(
            id=str(uuid4()),
            start=time_range[0],
            end=time_range[1],
            is_silence=is_silence
        )
    
    @classmethod
    def merge_segments(cls, segments: list["VideoSegment"], gap_threshold: float = 0.1) -> list["VideoSegment"]:
        """隣接するセグメントをマージ"""
        if not segments:
            return []
        
        # 開始時間でソート
        sorted_segments = sorted(segments, key=lambda s: s.start)
        merged = [sorted_segments[0]]
        
        for segment in sorted_segments[1:]:
            last_merged = merged[-1]
            
            # 隣接または重複している場合はマージ
            if last_merged.end >= segment.start - gap_threshold:
                merged[-1] = last_merged.merge_with(segment)
            else:
                merged.append(segment)
        
        return merged