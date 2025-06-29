"""
時間長の値オブジェクト

時間の長さを表す不変オブジェクト。
"""

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class Duration:
    """時間長を表す値オブジェクト（秒単位）"""
    seconds: float
    
    def __post_init__(self):
        """バリデーション"""
        if self.seconds < 0:
            raise ValueError("Duration cannot be negative")
    
    @property
    def minutes(self) -> float:
        """分単位の時間"""
        return self.seconds / 60
    
    @property
    def hours(self) -> float:
        """時間単位の時間"""
        return self.seconds / 3600
    
    @property
    def milliseconds(self) -> float:
        """ミリ秒単位の時間"""
        return self.seconds * 1000
    
    @property
    def is_zero(self) -> bool:
        """ゼロかどうか"""
        return self.seconds == 0
    
    def to_timecode(self, fps: float = 30.0) -> str:
        """タイムコード形式（HH:MM:SS:FF）に変換"""
        total_frames = int(self.seconds * fps)
        frames = total_frames % int(fps)
        seconds = int(self.seconds) % 60
        minutes = int(self.seconds // 60) % 60
        hours = int(self.seconds // 3600)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}:{frames:02d}"
    
    def to_srt_timecode(self) -> str:
        """SRTタイムコード形式（HH:MM:SS,mmm）に変換"""
        milliseconds = int((self.seconds % 1) * 1000)
        seconds = int(self.seconds) % 60
        minutes = int(self.seconds // 60) % 60
        hours = int(self.seconds // 3600)
        
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
    
    def to_human_readable(self) -> str:
        """人間が読みやすい形式に変換"""
        if self.seconds < 1:
            return f"{self.milliseconds:.0f}ms"
        elif self.seconds < 60:
            return f"{self.seconds:.1f}s"
        elif self.seconds < 3600:
            minutes = int(self.seconds // 60)
            seconds = self.seconds % 60
            return f"{minutes}m {seconds:.1f}s"
        else:
            hours = int(self.seconds // 3600)
            minutes = int((self.seconds % 3600) // 60)
            seconds = self.seconds % 60
            return f"{hours}h {minutes}m {seconds:.1f}s"
    
    def add(self, other: Union["Duration", float]) -> "Duration":
        """時間を加算"""
        if isinstance(other, Duration):
            return Duration(self.seconds + other.seconds)
        return Duration(self.seconds + other)
    
    def subtract(self, other: Union["Duration", float]) -> "Duration":
        """時間を減算"""
        if isinstance(other, Duration):
            result = self.seconds - other.seconds
        else:
            result = self.seconds - other
        
        return Duration(max(0, result))  # 負の値を防ぐ
    
    def multiply(self, factor: float) -> "Duration":
        """時間を乗算"""
        return Duration(self.seconds * factor)
    
    def divide(self, divisor: float) -> "Duration":
        """時間を除算"""
        if divisor == 0:
            raise ValueError("Cannot divide by zero")
        return Duration(self.seconds / divisor)
    
    @classmethod
    def from_milliseconds(cls, milliseconds: float) -> "Duration":
        """ミリ秒から作成"""
        return cls(milliseconds / 1000)
    
    @classmethod
    def from_minutes(cls, minutes: float) -> "Duration":
        """分から作成"""
        return cls(minutes * 60)
    
    @classmethod
    def from_hours(cls, hours: float) -> "Duration":
        """時間から作成"""
        return cls(hours * 3600)
    
    @classmethod
    def from_timecode(cls, timecode: str, fps: float = 30.0) -> "Duration":
        """タイムコード形式から作成"""
        parts = timecode.split(':')
        if len(parts) != 4:
            raise ValueError("Timecode must be in HH:MM:SS:FF format")
        
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
        frames = int(parts[3])
        
        total_seconds = hours * 3600 + minutes * 60 + seconds + frames / fps
        return cls(total_seconds)
    
    def __add__(self, other: Union["Duration", float]) -> "Duration":
        """加算演算子"""
        return self.add(other)
    
    def __sub__(self, other: Union["Duration", float]) -> "Duration":
        """減算演算子"""
        return self.subtract(other)
    
    def __mul__(self, factor: float) -> "Duration":
        """乗算演算子"""
        return self.multiply(factor)
    
    def __truediv__(self, divisor: float) -> "Duration":
        """除算演算子"""
        return self.divide(divisor)
    
    def __lt__(self, other: "Duration") -> bool:
        """小なり比較"""
        return self.seconds < other.seconds
    
    def __le__(self, other: "Duration") -> bool:
        """小なりイコール比較"""
        return self.seconds <= other.seconds
    
    def __gt__(self, other: "Duration") -> bool:
        """大なり比較"""
        return self.seconds > other.seconds
    
    def __ge__(self, other: "Duration") -> bool:
        """大なりイコール比較"""
        return self.seconds >= other.seconds
    
    def __str__(self) -> str:
        """文字列表現"""
        return self.to_human_readable()
    
    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"Duration(seconds={self.seconds})"