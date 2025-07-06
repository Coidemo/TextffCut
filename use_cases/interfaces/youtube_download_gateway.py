"""
YouTube ダウンロードゲートウェイのインターフェース

YouTube動画のダウンロード機能を抽象化します。
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from domain.value_objects.file_path import FilePath


@dataclass
class VideoInfo:
    """動画情報"""

    title: str
    duration: int  # 秒
    uploader: str
    description: str
    thumbnail: str
    estimated_size: int  # バイト
    formats: int  # 利用可能なフォーマット数


@dataclass
class DownloadProgress:
    """ダウンロード進捗"""

    status: str  # downloading, finished, error
    percent: float
    downloaded_bytes: int
    total_bytes: int
    speed: float  # バイト/秒
    eta: int  # 残り秒数


class IYouTubeDownloadGateway(ABC):
    """YouTube ダウンロードゲートウェイのインターフェース"""

    @abstractmethod
    def validate_url(self, url: str) -> bool:
        """
        YouTube URLの妥当性を検証

        Args:
            url: 検証するURL

        Returns:
            有効なYouTube URLかどうか
        """
        pass

    @abstractmethod
    def get_video_info(self, url: str) -> VideoInfo:
        """
        動画情報を取得

        Args:
            url: YouTube URL

        Returns:
            動画情報

        Raises:
            ValueError: URLが無効な場合
            RuntimeError: 動画情報の取得に失敗した場合
        """
        pass

    @abstractmethod
    def download_video(
        self,
        url: str,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> FilePath:
        """
        動画をダウンロード

        Args:
            url: YouTube URL
            progress_callback: 進捗コールバック関数

        Returns:
            ダウンロードしたファイルのパス

        Raises:
            ValueError: URLが無効な場合
            RuntimeError: ダウンロードに失敗した場合
        """
        pass
