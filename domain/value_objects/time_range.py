"""
時間範囲の値オブジェクト

開始時刻と終了時刻のペアを表す不変オブジェクト。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TimeRange:
    """時間範囲を表す値オブジェクト"""

    start: float
    end: float

    def __post_init__(self):
        """バリデーション"""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be greater than or equal to start time")

    @property
    def duration(self) -> float:
        """継続時間"""
        return self.end - self.start

    @property
    def is_empty(self) -> bool:
        """空の範囲かどうか"""
        return self.duration == 0

    def contains(self, time: float) -> bool:
        """指定された時刻が範囲内に含まれるか"""
        return self.start <= time <= self.end

    def overlaps(self, other: "TimeRange") -> bool:
        """他の時間範囲と重なっているか"""
        return self.start < other.end and self.end > other.start

    def intersection(self, other: "TimeRange") -> Optional["TimeRange"]:
        """他の時間範囲との交差部分を取得"""
        if not self.overlaps(other):
            return None

        return TimeRange(start=max(self.start, other.start), end=min(self.end, other.end))

    def union(self, other: "TimeRange", gap_tolerance: float = 0.001) -> Optional["TimeRange"]:
        """他の時間範囲との結合（隣接または重複している場合のみ）"""
        if not self.overlaps(other) and not self.is_adjacent(other, gap_tolerance):
            return None

        return TimeRange(start=min(self.start, other.start), end=max(self.end, other.end))

    def is_adjacent(self, other: "TimeRange", tolerance: float = 0.001) -> bool:
        """他の時間範囲と隣接しているか"""
        return abs(self.end - other.start) <= tolerance or abs(other.end - self.start) <= tolerance

    def split_at(self, time: float) -> tuple[Optional["TimeRange"], Optional["TimeRange"]]:
        """指定された時刻で分割"""
        if not self.contains(time):
            return (self, None) if time > self.end else (None, self)

        if time == self.start:
            return (None, self)
        if time == self.end:
            return (self, None)

        return (TimeRange(self.start, time), TimeRange(time, self.end))

    def with_padding(self, start_padding: float, end_padding: float) -> "TimeRange":
        """パディングを追加した新しい時間範囲を作成"""
        return TimeRange(start=max(0, self.start - start_padding), end=self.end + end_padding)

    def to_tuple(self) -> tuple[float, float]:
        """タプル形式に変換（既存コードとの互換性）"""
        return (self.start, self.end)

    @classmethod
    def from_tuple(cls, time_tuple: tuple[float, float]) -> "TimeRange":
        """タプルから作成（既存コードとの互換性）"""
        return cls(start=time_tuple[0], end=time_tuple[1])

    @classmethod
    def merge_ranges(cls, ranges: list["TimeRange"], gap_threshold: float = 0.1) -> list["TimeRange"]:
        """隣接する時間範囲をマージ"""
        if not ranges:
            return []

        # 開始時間でソート
        sorted_ranges = sorted(ranges, key=lambda r: r.start)
        merged = [sorted_ranges[0]]

        for range_ in sorted_ranges[1:]:
            last_merged = merged[-1]

            # 隣接または重複している場合はマージ
            if last_merged.overlaps(range_) or last_merged.is_adjacent(range_, gap_threshold):
                new_range = last_merged.union(range_, gap_threshold)
                if new_range:
                    merged[-1] = new_range
            else:
                merged.append(range_)

        return merged

    def __str__(self) -> str:
        """文字列表現"""
        return f"{self.start:.2f}s - {self.end:.2f}s"

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"TimeRange(start={self.start}, end={self.end})"
