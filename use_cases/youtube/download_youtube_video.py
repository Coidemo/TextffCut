"""
YouTube 動画ダウンロードユースケース

作者の許可を得た動画のダウンロードを実行します。
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

from domain.value_objects.file_path import FilePath
from use_cases.base import BaseUseCase
from use_cases.exceptions import UseCaseError
from use_cases.interfaces.youtube_download_gateway import (
    IYouTubeDownloadGateway,
    VideoInfo,
    DownloadProgress,
)

logger = logging.getLogger(__name__)


@dataclass
class DownloadYouTubeVideoInput:
    """YouTube 動画ダウンロードの入力"""
    
    url: str
    progress_callback: Optional[Callable[[DownloadProgress], None]] = None


@dataclass
class DownloadYouTubeVideoOutput:
    """YouTube 動画ダウンロードの出力"""
    
    file_path: FilePath
    video_info: VideoInfo


class DownloadYouTubeVideo(BaseUseCase[DownloadYouTubeVideoInput, DownloadYouTubeVideoOutput]):
    """
    YouTube 動画ダウンロードユースケース
    
    作者の許可を得た動画をダウンロードし、
    ローカルのvideosフォルダに保存します。
    """

    def __init__(self, youtube_gateway: IYouTubeDownloadGateway):
        """
        初期化

        Args:
            youtube_gateway: YouTube ダウンロードゲートウェイ
        """
        super().__init__()
        self.youtube_gateway = youtube_gateway

    def execute(self, input_data: DownloadYouTubeVideoInput) -> DownloadYouTubeVideoOutput:
        """
        YouTube 動画をダウンロード

        Args:
            input_data: 入力データ（URL、進捗コールバック）

        Returns:
            ダウンロード結果（ファイルパス、動画情報）

        Raises:
            UseCaseError: ダウンロードに失敗した場合
        """
        try:
            # URLの検証
            if not self.youtube_gateway.validate_url(input_data.url):
                raise UseCaseError(
                    "無効なYouTube URLです。正しいURLを入力してください。",
                    details={"url": input_data.url}
                )

            # 動画情報の取得
            logger.info(f"動画情報を取得中: {input_data.url}")
            video_info = self.youtube_gateway.get_video_info(input_data.url)
            
            # サイズチェック（2GB以上は警告）
            if video_info.estimated_size > 2 * 1024 * 1024 * 1024:
                size_gb = video_info.estimated_size / (1024 * 1024 * 1024)
                logger.warning(f"動画サイズが大きいです: {size_gb:.1f}GB")

            # ダウンロード実行
            logger.info(f"動画をダウンロード中: {video_info.title}")
            file_path = self.youtube_gateway.download_video(
                input_data.url,
                input_data.progress_callback
            )

            logger.info(f"ダウンロード完了: {file_path}")
            
            return DownloadYouTubeVideoOutput(
                file_path=file_path,
                video_info=video_info
            )

        except ValueError as e:
            raise UseCaseError(
                "入力値が不正です",
                details={"error": str(e)}
            )
        except RuntimeError as e:
            raise UseCaseError(
                "ダウンロードに失敗しました",
                details={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"予期しないエラーが発生しました: {e}")
            raise UseCaseError(
                "予期しないエラーが発生しました",
                details={"error": str(e)}
            )


@dataclass
class GetVideoInfoInput:
    """動画情報取得の入力"""
    
    url: str


class GetVideoInfo(BaseUseCase[GetVideoInfoInput, VideoInfo]):
    """
    動画情報取得ユースケース
    
    ダウンロード前に動画の情報を取得します。
    """

    def __init__(self, youtube_gateway: IYouTubeDownloadGateway):
        """
        初期化

        Args:
            youtube_gateway: YouTube ダウンロードゲートウェイ
        """
        super().__init__()
        self.youtube_gateway = youtube_gateway

    def execute(self, input_data: GetVideoInfoInput) -> VideoInfo:
        """
        動画情報を取得

        Args:
            input_data: 入力データ（URL）

        Returns:
            動画情報

        Raises:
            UseCaseError: 情報取得に失敗した場合
        """
        try:
            # URLの検証
            if not self.youtube_gateway.validate_url(input_data.url):
                raise UseCaseError(
                    "無効なYouTube URLです。正しいURLを入力してください。",
                    details={"url": input_data.url}
                )

            # 動画情報の取得
            return self.youtube_gateway.get_video_info(input_data.url)

        except ValueError as e:
            raise UseCaseError(
                "入力値が不正です",
                details={"error": str(e)}
            )
        except RuntimeError as e:
            raise UseCaseError(
                "動画情報の取得に失敗しました",
                details={"error": str(e)}
            )
        except Exception as e:
            logger.error(f"予期しないエラーが発生しました: {e}")
            raise UseCaseError(
                "予期しないエラーが発生しました",
                details={"error": str(e)}
            )