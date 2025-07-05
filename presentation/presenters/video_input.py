"""
動画入力Presenter

動画ファイルの選択と情報取得のビジネスロジックを管理します。
"""

import logging
from pathlib import Path

from domain.value_objects import FilePath
from presentation.view_models.video_input import VideoInfo, VideoInputViewModel

from .base import BasePresenter

logger = logging.getLogger(__name__)


class VideoInputPresenter(BasePresenter[VideoInputViewModel]):
    """
    動画入力のPresenter

    動画ファイルの一覧取得、選択、情報取得などの処理を行います。
    """

    def __init__(self, view_model: VideoInputViewModel, file_gateway, video_gateway):
        """
        初期化

        Args:
            view_model: 管理するViewModel
            file_gateway: ファイル操作ゲートウェイ
            video_gateway: 動画処理ゲートウェイ
        """
        super().__init__(view_model)
        self.file_gateway = file_gateway
        self.video_gateway = video_gateway
        self.videos_dir = "videos"  # TODO: 設定から取得

    def initialize(self) -> None:
        """初期化処理"""
        logger.info("Initializing VideoInputPresenter")
        self.refresh_video_list()
        self._is_initialized = True

    def refresh_video_list(self) -> None:
        """動画ファイル一覧を更新"""

        def _refresh():
            try:
                # ディレクトリが存在することを確認
                if not self.file_gateway.exists(FilePath(self.videos_dir)):
                    self.file_gateway.create_directory(FilePath(self.videos_dir))
                    logger.info(f"Created videos directory: {self.videos_dir}")

                # ファイル一覧を取得
                patterns = ["*" + ext for ext in self.view_model.supported_extensions]
                files = []

                for pattern in patterns:
                    matched_files = self.file_gateway.list_files(FilePath(self.videos_dir), pattern)
                    files.extend(matched_files)

                # ファイル名のみを抽出して重複を排除してソート
                # FilePathオブジェクトからpathを取得
                file_names = sorted(list(set(Path(f.path).name for f in files)))

                # ViewModelを更新
                self.view_model.video_files = file_names
                self.view_model.clear_error()

                logger.info(f"Found {len(file_names)} video files")

            except Exception as e:
                self.handle_error(e, "動画ファイル一覧の取得に失敗しました")

        # ローディング状態を管理しながら実行
        self.execute_with_loading(_refresh, "is_refreshing")

    def select_video(self, filename: str | None) -> None:
        """
        動画を選択

        Args:
            filename: 選択する動画ファイル名（Noneで選択解除）
        """
        if filename is None:
            self.view_model.clear_selection()
            return

        # ファイル名の検証
        if filename not in self.view_model.video_files:
            self.view_model.set_error(f"ファイル '{filename}' は利用可能なファイル一覧に存在しません")
            return

        def _load_video_info():
            try:
                # 動画ファイルのフルパス
                video_path = Path(self.videos_dir) / filename

                # 動画情報を取得
                metadata = self.video_gateway.get_video_info(str(video_path))

                if metadata:
                    # VideoInfoに変換
                    video_info = VideoInfo(
                        duration=metadata.get("duration", 0.0),
                        fps=metadata.get("fps", 0.0),
                        width=metadata.get("width", 0),
                        height=metadata.get("height", 0),
                        codec=metadata.get("codec", "unknown"),
                        file_size=metadata.get("file_size", 0),
                    )

                    # ViewModelを更新
                    self.view_model.selected_file = filename
                    self.view_model.video_info = video_info
                    self.view_model.clear_error()

                    logger.info(f"Selected video: {filename} (duration: {video_info.duration}s)")
                else:
                    raise ValueError("動画情報の取得に失敗しました")

            except Exception as e:
                self.view_model.selected_file = filename
                self.view_model.video_info = None
                self.handle_error(e, "動画情報の取得に失敗しました")

        # ローディング状態を管理しながら実行
        self.execute_with_loading(_load_video_info)

    def toggle_show_all_files(self) -> None:
        """すべてのファイルを表示するかどうかを切り替え"""
        self.view_model.show_all_files = not self.view_model.show_all_files
        self.view_model.notify()

        # ファイル一覧を更新
        if self.view_model.show_all_files:
            # すべての拡張子を含める
            self.view_model.supported_extensions = [".*"]
        else:
            # デフォルトの拡張子に戻す
            self.view_model.supported_extensions = [".mp4", ".mov", ".avi", ".mkv"]

        self.refresh_video_list()

    def get_selected_video_path(self) -> Path | None:
        """
        選択された動画のフルパスを取得

        Returns:
            動画のフルパス（未選択の場合はNone）
        """
        if not self.view_model.selected_file:
            return None

        return Path(self.videos_dir) / self.view_model.selected_file

    def is_valid_selection(self) -> bool:
        """
        現在の選択が有効かどうか

        Returns:
            有効な場合True
        """
        if not self.view_model.is_ready:
            return False

        # 追加の検証
        error = self.validate_state()
        return error is None
