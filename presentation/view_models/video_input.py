"""
動画入力ViewModel

動画ファイルの選択と情報表示に関するデータを管理します。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .base import BaseViewModel


@dataclass
class VideoInfo:
    """動画情報"""

    duration: float  # 秒単位
    fps: float
    width: int
    height: int
    codec: str
    file_size: int  # バイト単位

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "duration": self.duration,
            "fps": self.fps,
            "width": self.width,
            "height": self.height,
            "codec": self.codec,
            "file_size": self.file_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VideoInfo":
        """辞書から作成"""
        return cls(
            duration=data.get("duration", 0.0),
            fps=data.get("fps", 0.0),
            width=data.get("width", 0),
            height=data.get("height", 0),
            codec=data.get("codec", ""),
            file_size=data.get("file_size", 0),
        )


@dataclass
class VideoInputViewModel(BaseViewModel):
    """
    動画入力のViewModel

    動画ファイルの選択、動画情報の表示、エラー状態などを管理します。
    """

    # 選択された動画ファイル
    selected_file: str | None = None

    # 利用可能な動画ファイル一覧
    video_files: list[str] = field(default_factory=list)

    # 選択された動画の情報
    video_info: VideoInfo | None = None

    # UI状態
    is_loading: bool = False
    is_refreshing: bool = False

    # エラー情報
    error_message: str | None = None
    error_details: dict[str, Any] | None = None

    # フィルタ設定
    show_all_files: bool = False
    supported_extensions: list[str] = field(default_factory=lambda: [".mp4", ".mov", ".avi", ".mkv"])

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "selected_file": self.selected_file,
            "video_files": self.video_files,
            "video_info": self.video_info.to_dict() if self.video_info else None,
            "is_loading": self.is_loading,
            "is_refreshing": self.is_refreshing,
            "error_message": self.error_message,
            "error_details": self.error_details,
            "show_all_files": self.show_all_files,
            "supported_extensions": self.supported_extensions,
        }

    def validate(self) -> str | None:
        """ViewModelの妥当性を検証"""
        if self.selected_file and self.selected_file not in self.video_files:
            return f"選択されたファイル '{self.selected_file}' が利用可能なファイル一覧に存在しません"

        if self.video_info and self.video_info.duration <= 0:
            return "動画の長さが無効です"

        return None

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """辞書からViewModelを更新"""
        # 基本フィールドの更新
        for key in [
            "selected_file",
            "video_files",
            "is_loading",
            "is_refreshing",
            "error_message",
            "error_details",
            "show_all_files",
            "supported_extensions",
        ]:
            if key in data:
                setattr(self, key, data[key])

        # VideoInfoの更新
        if "video_info" in data and data["video_info"]:
            self.video_info = VideoInfo.from_dict(data["video_info"])
        elif "video_info" in data and data["video_info"] is None:
            self.video_info = None

        self.notify()

    def clear_selection(self) -> None:
        """選択をクリア"""
        self.selected_file = None
        self.video_info = None
        self.error_message = None
        self.error_details = None
        self.notify()

    def set_error(self, message: str, details: dict[str, Any] | None = None) -> None:
        """エラー情報を設定"""
        self.error_message = message
        self.error_details = details
        self.is_loading = False
        self.is_refreshing = False
        self.notify()

    def clear_error(self) -> None:
        """エラー情報をクリア"""
        self.error_message = None
        self.error_details = None
        self.notify()

    @property
    def has_selection(self) -> bool:
        """動画が選択されているか"""
        return self.selected_file is not None

    @property
    def is_ready(self) -> bool:
        """処理可能な状態か"""
        return self.has_selection and self.video_info is not None and not self.is_loading

    @property
    def is_valid(self) -> bool:
        """有効な選択状態か"""
        return (
            self.has_selection
            and self.video_info is not None
            and self.video_info.duration > 0
            and not self.is_loading
            and self.error_message is None
        )

    @property
    def file_path(self) -> Path | None:
        """選択されたファイルのパス"""
        if self.selected_file:
            # VideoInputPresenterと同じディレクトリを想定
            return Path("./videos") / self.selected_file
        return None

    @property
    def duration(self) -> float:
        """動画の長さ（秒）"""
        if self.video_info:
            return self.video_info.duration
        return 0.0

    @property
    def duration_text(self) -> str:
        """動画の長さをテキスト形式で取得"""
        if not self.video_info:
            return "不明"

        duration = self.video_info.duration
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)

        if hours > 0:
            return f"{hours}時間{minutes}分{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"

    @property
    def file_size_text(self) -> str:
        """ファイルサイズをテキスト形式で取得"""
        if not self.video_info:
            return "不明"

        size = self.video_info.file_size
        if size >= 1024 * 1024 * 1024:  # GB
            return f"{size / (1024 * 1024 * 1024):.1f} GB"
        elif size >= 1024 * 1024:  # MB
            return f"{size / (1024 * 1024):.1f} MB"
        elif size >= 1024:  # KB
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size} B"
