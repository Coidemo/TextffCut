"""
YouTube ダウンロードのViewModel

YouTube動画ダウンロードの状態を管理します。
"""

from dataclasses import dataclass
from typing import Any

from presentation.view_models.base import BaseViewModel


@dataclass
class YouTubeDownloadViewModel(BaseViewModel):
    """
    YouTube ダウンロードのViewModel

    ダウンロード状態、進捗、動画情報などを管理します。
    """

    # URL入力
    url: str = ""

    # 動画情報
    has_video_info: bool = False
    video_title: str = ""
    video_duration: int = 0  # 秒
    video_uploader: str = ""
    estimated_size_mb: float = 0.0

    # ダウンロード状態
    is_downloading: bool = False
    download_complete: bool = False
    downloaded_file_path: str | None = None

    # 進捗情報
    progress_percent: float = 0.0
    downloaded_mb: float = 0.0
    total_mb: float = 0.0
    download_speed_mbps: float = 0.0
    eta_seconds: int = 0

    # UI状態
    is_loading: bool = False
    loading_message: str = ""
    has_error: bool = False
    error_message: str | None = None

    @property
    def duration_text(self) -> str:
        """動画時間のテキスト表現"""
        if self.video_duration == 0:
            return "不明"

        hours = self.video_duration // 3600
        minutes = (self.video_duration % 3600) // 60
        seconds = self.video_duration % 60

        if hours > 0:
            return f"{hours}時間{minutes}分{seconds}秒"
        elif minutes > 0:
            return f"{minutes}分{seconds}秒"
        else:
            return f"{seconds}秒"

    @property
    def eta_text(self) -> str:
        """残り時間のテキスト表現"""
        if self.eta_seconds <= 0:
            return "計算中..."

        if self.eta_seconds < 60:
            return f"{self.eta_seconds}秒"
        elif self.eta_seconds < 3600:
            minutes = self.eta_seconds // 60
            return f"{minutes}分"
        else:
            hours = self.eta_seconds // 3600
            minutes = (self.eta_seconds % 3600) // 60
            return f"{hours}時間{minutes}分"

    @property
    def can_download(self) -> bool:
        """ダウンロード可能かどうか"""
        return bool(self.url) and not self.is_downloading and not self.download_complete

    def set_video_info(
        self,
        title: str,
        duration: int,
        uploader: str,
        estimated_size: int,
    ) -> None:
        """動画情報を設定"""
        self.has_video_info = True
        self.video_title = title
        self.video_duration = duration
        self.video_uploader = uploader
        self.estimated_size_mb = estimated_size / (1024 * 1024)
        self.notify()

    def update_progress(
        self,
        percent: float,
        downloaded_mb: float,
        total_mb: float,
        speed_mbps: float,
        eta_seconds: int,
    ) -> None:
        """進捗情報を更新"""
        self.progress_percent = percent
        self.downloaded_mb = downloaded_mb
        self.total_mb = total_mb
        self.download_speed_mbps = speed_mbps
        self.eta_seconds = eta_seconds
        self.notify()

    def set_downloading(self, downloading: bool) -> None:
        """ダウンロード状態を設定"""
        self.is_downloading = downloading
        if not downloading:
            self.progress_percent = 0.0
            self.downloaded_mb = 0.0
            self.total_mb = 0.0
            self.download_speed_mbps = 0.0
            self.eta_seconds = 0
        self.notify()

    def set_download_complete(self, file_path: str) -> None:
        """ダウンロード完了を設定"""
        self.download_complete = True
        self.downloaded_file_path = file_path
        self.is_downloading = False
        self.progress_percent = 100.0
        self.notify()

    def set_loading(self, message: str) -> None:
        """ローディング状態を設定"""
        self.is_loading = True
        self.loading_message = message
        self.notify()

    def clear_loading(self) -> None:
        """ローディング状態をクリア"""
        self.is_loading = False
        self.loading_message = ""
        self.notify()

    def set_error(self, message: str) -> None:
        """エラーを設定"""
        self.has_error = True
        self.error_message = message
        self.notify()

    def clear_error(self) -> None:
        """エラーをクリア"""
        self.has_error = False
        self.error_message = None
        self.notify()

    def reset(self) -> None:
        """状態をリセット"""
        self.url = ""
        self.has_video_info = False
        self.video_title = ""
        self.video_duration = 0
        self.video_uploader = ""
        self.estimated_size_mb = 0.0
        self.is_downloading = False
        self.download_complete = False
        self.downloaded_file_path = None
        self.progress_percent = 0.0
        self.downloaded_mb = 0.0
        self.total_mb = 0.0
        self.download_speed_mbps = 0.0
        self.eta_seconds = 0
        self.clear_loading()
        self.clear_error()
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """ViewModelを辞書形式に変換"""
        return {
            "url": self.url,
            "has_video_info": self.has_video_info,
            "video_title": self.video_title,
            "duration_text": self.duration_text,
            "is_downloading": self.is_downloading,
            "download_complete": self.download_complete,
            "progress_percent": self.progress_percent,
            "has_error": self.has_error,
        }

    def validate(self) -> str | None:
        """ViewModelの妥当性を検証"""
        if self.is_downloading and not self.url:
            return "URLが設定されていません"
        return None
