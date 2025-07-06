"""
YouTube ダウンロードのPresenter

YouTube動画のダウンロード処理を管理します。
"""

import logging

from domain.interfaces.error_handler import IErrorHandler
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.base import BasePresenter
from presentation.view_models.youtube_download import YouTubeDownloadViewModel
from use_cases.youtube.download_youtube_video import (
    DownloadYouTubeVideo,
    DownloadYouTubeVideoInput,
    GetVideoInfo,
    GetVideoInfoInput,
)

logger = logging.getLogger(__name__)


class YouTubeDownloadPresenter(BasePresenter[YouTubeDownloadViewModel]):
    """
    YouTube ダウンロードのPresenter

    YouTube動画のダウンロード処理とUI更新を管理します。
    """

    def __init__(
        self,
        view_model: YouTubeDownloadViewModel,
        session_manager: SessionManager,
        download_use_case: DownloadYouTubeVideo,
        get_info_use_case: GetVideoInfo,
        error_handler: IErrorHandler,
    ):
        """
        初期化

        Args:
            view_model: YouTubeダウンロードViewModel
            session_manager: セッション管理
            download_use_case: ダウンロードユースケース
            get_info_use_case: 動画情報取得ユースケース
            error_handler: エラーハンドラー
        """
        super().__init__(view_model)
        self.session_manager = session_manager
        self.download_use_case = download_use_case
        self.get_info_use_case = get_info_use_case
        self.error_handler = error_handler

    def initialize(self) -> None:
        """初期化処理"""
        logger.info("YouTubeDownloadPresenter.initialize called")
        self.view_model.reset()

    def validate_url(self, url: str) -> bool:
        """
        URLの妥当性を検証

        Args:
            url: YouTube URL

        Returns:
            有効なURLかどうか
        """
        if not url:
            self.view_model.set_error("URLを入力してください")
            return False

        # 簡易的なURL検証（詳細はゲートウェイで行う）
        if not (url.startswith("https://") or url.startswith("http://")):
            self.view_model.set_error("有効なURLを入力してください")
            return False

        if "youtube.com" not in url and "youtu.be" not in url:
            self.view_model.set_error("YouTube URLを入力してください")
            return False

        self.view_model.clear_error()
        return True

    def get_video_info(self, url: str) -> None:
        """
        動画情報を取得

        Args:
            url: YouTube URL
        """
        if not self.validate_url(url):
            return

        try:
            self.view_model.set_loading("動画情報を取得中...")

            input_data = GetVideoInfoInput(url=url)
            video_info = self.get_info_use_case.execute(input_data)

            self.view_model.set_video_info(
                title=video_info.title,
                duration=video_info.duration,
                uploader=video_info.uploader,
                estimated_size=video_info.estimated_size,
            )

            self.view_model.clear_loading()
            logger.info(f"動画情報を取得しました: {video_info.title}")

        except Exception as e:
            self.handle_error(e, "動画情報取得")

    def start_download(self, url: str) -> None:
        """
        ダウンロードを開始

        Args:
            url: YouTube URL
        """
        if not self.validate_url(url):
            return

        if self.view_model.is_downloading:
            self.view_model.set_error("既にダウンロード中です")
            return

        try:
            self.view_model.set_downloading(True)
            self.view_model.set_loading("ダウンロードを開始しています...")

            # 進捗コールバック
            def progress_callback(progress):
                self.view_model.update_progress(
                    percent=progress.percent,
                    downloaded_mb=progress.downloaded_bytes / (1024 * 1024),
                    total_mb=progress.total_bytes / (1024 * 1024),
                    speed_mbps=(progress.speed / (1024 * 1024)) if progress.speed else 0,
                    eta_seconds=progress.eta,
                )
                # 進捗をログに出力（デバッグ用）
                if progress.percent % 10 < 1:  # 10%ごとにログ出力
                    logger.info(f"ダウンロード進捗: {progress.percent:.1f}%")

            input_data = DownloadYouTubeVideoInput(url=url, progress_callback=progress_callback)

            result = self.download_use_case.execute(input_data)

            # ダウンロード完了
            self.view_model.set_download_complete(str(result.file_path))

            # セッションに保存
            self.session_manager.set("downloaded_video_path", str(result.file_path))
            self.session_manager.set(
                "video_info",
                {
                    "title": result.video_info.title,
                    "duration": result.video_info.duration,
                    "uploader": result.video_info.uploader,
                },
            )

            logger.info(f"ダウンロード完了: {result.file_path}")

        except Exception as e:
            self.handle_error(e, "ダウンロード")
        finally:
            self.view_model.set_downloading(False)
            self.view_model.clear_loading()

    def cancel_download(self) -> None:
        """ダウンロードをキャンセル"""
        # TODO: ダウンロードのキャンセル機能を実装
        self.view_model.set_downloading(False)
        self.view_model.clear_loading()
        self.view_model.set_error("ダウンロードをキャンセルしました")

    def handle_error(self, error: Exception, context: str) -> None:
        """
        エラーをハンドリング

        Args:
            error: 発生したエラー
            context: エラーのコンテキスト
        """
        logger.error(f"{context}でエラーが発生しました: {error}", exc_info=True)
        error_info = self.error_handler.handle_error(error, context=context, raise_after=False)
        error_message = error_info.get("user_message", str(error)) if error_info else str(error)
        self.view_model.set_error(f"{context}: {error_message}")
        self.view_model.set_downloading(False)
        self.view_model.clear_loading()

    def reset(self) -> None:
        """状態をリセット"""
        self.view_model.reset()
