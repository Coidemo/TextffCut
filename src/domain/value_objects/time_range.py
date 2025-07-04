"""
TimeRange Value Object

時間範囲を表現する不変オブジェクト
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class TimeRange:
    """時間範囲を表現するValue Object"""

    start: float
    end: float

    def __post_init__(self):
        """
        バリデーション

        Raises:
            ValueError: 不正な時間範囲の場合
        """
        if self.start < 0:
            raise ValueError(f"Start time cannot be negative: {self.start}")
        if self.end < self.start:
            raise ValueError(f"End time must be after start time: start={self.start}, end={self.end}")

    @property
    def duration(self) -> float:
        """継続時間を取得"""
        return self.end - self.start

    def overlaps(self, other: "TimeRange") -> bool:
        """
        他の時間範囲と重なっているか確認

        Args:
            other: 比較対象の時間範囲

        Returns:
            重なっている場合True
        """
        return self.start < other.end and other.start < self.end

    def contains(self, time: float) -> bool:
        """
        指定時刻が範囲内に含まれているか確認

        Args:
            time: 確認する時刻

        Returns:
            含まれている場合True
        """
        return self.start <= time <= self.end

    def merge(self, other: "TimeRange") -> Optional["TimeRange"]:
        """
        他の時間範囲とマージ（重なっているか隣接している場合のみ）

        Args:
            other: マージ対象の時間範囲

        Returns:
            マージされた時間範囲、マージできない場合None
        """
        if self.overlaps(other) or self.end == other.start or other.end == self.start:
            return TimeRange(start=min(self.start, other.start), end=max(self.end, other.end))
        return None

    def intersect(self, other: "TimeRange") -> Optional["TimeRange"]:
        """
        他の時間範囲との交差部分を取得

        Args:
            other: 交差を求める時間範囲

        Returns:
            交差部分の時間範囲、交差しない場合None
        """
        if not self.overlaps(other):
            return None

        return TimeRange(start=max(self.start, other.start), end=min(self.end, other.end))

    def shift(self, offset: float) -> "TimeRange":
        """
        時間範囲をシフト

        Args:
            offset: シフト量（秒）

        Returns:
            シフトされた新しい時間範囲
        """
        return TimeRange(start=self.start + offset, end=self.end + offset)

    def expand(self, amount: float) -> "TimeRange":
        """
        時間範囲を両端に拡張

        Args:
            amount: 拡張量（秒）

        Returns:
            拡張された新しい時間範囲
        """
        new_start = max(0, self.start - amount)
        new_end = self.end + amount
        return TimeRange(start=new_start, end=new_end)

    def format_time(self, time: float) -> str:
        """
        時刻を HH:MM:SS.mmm 形式にフォーマット

        Args:
            time: フォーマットする時刻（秒）

        Returns:
            フォーマットされた時刻文字列
        """
        hours = int(time // 3600)
        minutes = int((time % 3600) // 60)
        seconds = time % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    def __str__(self) -> str:
        """文字列表現"""
        return f"{self.format_time(self.start)} - {self.format_time(self.end)}"

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"TimeRange(start={self.start:.3f}, end={self.end:.3f})"
