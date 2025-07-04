"""
Video Entity

動画関連のエンティティ
"""

from dataclasses import dataclass
from typing import Optional

from ..value_objects import FilePath, TimeRange


@dataclass
class VideoInfo:
    """動画情報"""

    file_path: FilePath
    duration: float
    fps: float
    width: int
    height: int
    codec: str = "h264"
    bitrate: int | None = None

    def __post_init__(self):
        """バリデーション"""
        if self.duration <= 0:
            raise ValueError(f"Duration must be positive: {self.duration}")
        if self.fps <= 0:
            raise ValueError(f"FPS must be positive: {self.fps}")
        if self.width <= 0 or self.height <= 0:
            raise ValueError(f"Width and height must be positive: {self.width}x{self.height}")

    @property
    def aspect_ratio(self) -> float:
        """アスペクト比を取得"""
        return self.width / self.height

    @property
    def total_frames(self) -> int:
        """総フレーム数を取得"""
        return int(self.duration * self.fps)

    @property
    def resolution_name(self) -> str:
        """解像度の一般的な名称を取得"""
        if self.width >= 3840:
            return "4K"
        elif self.width >= 1920:
            return "Full HD"
        elif self.width >= 1280:
            return "HD"
        else:
            return "SD"

    def time_to_frame(self, time: float) -> int:
        """時刻をフレーム番号に変換"""
        return int(time * self.fps)

    def frame_to_time(self, frame: int) -> float:
        """フレーム番号を時刻に変換"""
        return frame / self.fps


@dataclass
class Clip:
    """動画クリップ"""

    id: str
    source_path: FilePath
    time_range: TimeRange
    title: str | None = None

    @property
    def start(self) -> float:
        """開始時刻"""
        return self.time_range.start

    @property
    def end(self) -> float:
        """終了時刻"""
        return self.time_range.end

    @property
    def duration(self) -> float:
        """継続時間"""
        return self.time_range.duration

    def shift(self, offset: float) -> "Clip":
        """クリップを時間的にシフト"""
        return Clip(
            id=self.id, source_path=self.source_path, time_range=self.time_range.shift(offset), title=self.title
        )

    def trim(self, new_range: TimeRange) -> Optional["Clip"]:
        """
        クリップをトリミング

        Args:
            new_range: 新しい時間範囲

        Returns:
            トリミングされたクリップ、範囲外の場合None
        """
        intersection = self.time_range.intersect(new_range)
        if intersection is None:
            return None

        return Clip(id=self.id, source_path=self.source_path, time_range=intersection, title=self.title)
