"""
Duration Value Object

時間の長さを表現する不変オブジェクト
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Duration:
    """時間の長さを表現するValue Object"""

    seconds: float

    def __post_init__(self):
        """
        バリデーション

        Raises:
            ValueError: 負の値の場合
        """
        if self.seconds < 0:
            raise ValueError(f"Duration cannot be negative: {self.seconds}")

    @classmethod
    def from_milliseconds(cls, milliseconds: float) -> "Duration":
        """ミリ秒から作成"""
        return cls(milliseconds / 1000.0)

    @classmethod
    def from_minutes(cls, minutes: float) -> "Duration":
        """分から作成"""
        return cls(minutes * 60.0)

    @classmethod
    def from_hours(cls, hours: float) -> "Duration":
        """時間から作成"""
        return cls(hours * 3600.0)

    @property
    def milliseconds(self) -> float:
        """ミリ秒で取得"""
        return self.seconds * 1000.0

    @property
    def minutes(self) -> float:
        """分で取得"""
        return self.seconds / 60.0

    @property
    def hours(self) -> float:
        """時間で取得"""
        return self.seconds / 3600.0

    def add(self, other: "Duration") -> "Duration":
        """他のDurationを加算"""
        return Duration(self.seconds + other.seconds)

    def subtract(self, other: "Duration") -> "Duration":
        """他のDurationを減算"""
        result = self.seconds - other.seconds
        return Duration(max(0, result))  # 負の値にならないように

    def multiply(self, factor: float) -> "Duration":
        """指定倍率で乗算"""
        return Duration(self.seconds * factor)

    def format(self) -> str:
        """HH:MM:SS.mmm 形式でフォーマット"""
        hours = int(self.seconds // 3600)
        minutes = int((self.seconds % 3600) // 60)
        seconds = self.seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

    def __str__(self) -> str:
        """文字列表現"""
        return self.format()

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"Duration(seconds={self.seconds:.3f})"

    def __eq__(self, other) -> bool:
        """等価比較"""
        if not isinstance(other, Duration):
            return False
        return abs(self.seconds - other.seconds) < 0.001  # 1ms未満の差は同じとみなす

    def __lt__(self, other) -> bool:
        """小なり比較"""
        if not isinstance(other, Duration):
            return NotImplemented
        return self.seconds < other.seconds

    def __le__(self, other) -> bool:
        """小なりイコール比較"""
        return self < other or self == other
