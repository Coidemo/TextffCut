"""
文字起こしのPresenter

文字起こし機能のビジネスロジックを担当します。
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from domain.interfaces.error_handler import IErrorHandler
from domain.value_objects.file_path import FilePath
from infrastructure.ui.session_manager import SessionManager
from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter
from presentation.presenters.base import BasePresenter
from presentation.view_models.transcription import TranscriptionCache, TranscriptionViewModel
from use_cases.interfaces.file_gateway import IFileGateway
from use_cases.interfaces.transcription_gateway import ITranscriptionGateway
from use_cases.transcription.load_cache import LoadCacheRequest, LoadTranscriptionCacheUseCase
from use_cases.transcription.transcribe_video import TranscribeVideoRequest, TranscribeVideoUseCase

logger = logging.getLogger(__name__)


class TranscriptionPresenter(BasePresenter[TranscriptionViewModel]):
    """
    文字起こしのPresenter

    ViewModelの状態管理とユースケースの実行を担当します。
    """

    def __init__(
        self,
        view_model: TranscriptionViewModel,
        transcribe_use_case: TranscribeVideoUseCase,
        load_cache_use_case: LoadTranscriptionCacheUseCase,
        file_gateway: IFileGateway,
        transcription_gateway: ITranscriptionGateway,
        error_handler: IErrorHandler,
        session_manager: SessionManager,
    ):
        """
        初期化

        Args:
            view_model: 文字起こしViewModel
            transcribe_use_case: 文字起こしユースケース
            load_cache_use_case: キャッシュ読み込みユースケース
            file_gateway: ファイルゲートウェイ
            transcription_gateway: 文字起こしゲートウェイ
            error_handler: エラーハンドラー
            session_manager: セッション管理
        """
        super().__init__(view_model)
        self.transcribe_use_case = transcribe_use_case
        self.load_cache_use_case = load_cache_use_case
        self.file_gateway = file_gateway
        self.transcription_gateway = transcription_gateway
        self.error_handler = error_handler
        self.session_manager = session_manager

    def initialize(self) -> None:
        """初期化処理"""
        # SessionManagerから実行フラグを復元
        should_run = self.session_manager.get("transcription_should_run", False)
        logger.info(f"initialize - should_run from SessionManager: {should_run}")
        if should_run:
            self.view_model.should_run = True
            logger.info("should_runをTrueに設定")
            # フラグをクリア（一度だけ実行）
            self.session_manager.set("transcription_should_run", False)

        # MLX利用可能性を設定
        from utils.environment import MLX_AVAILABLE

        self.view_model.mlx_whisper_available = MLX_AVAILABLE
        if MLX_AVAILABLE:
            self.view_model.available_models = ["large-v3", "large-v3-turbo", "medium", "small", "base"]
        else:
            self.view_model.available_models = ["medium", "small", "base"]

        # 保存されたモデルサイズを復元
        saved_model = self.session_manager.get("model_size", None)
        if saved_model and saved_model in self.view_model.available_models:
            self.view_model.model_size = saved_model

        # 保存されたAPIキーを読み込む
        from utils.api_key_manager import api_key_manager

        saved_key = api_key_manager.load_api_key()
        if saved_key:
            self.view_model.api_key = saved_key
            logger.info("初期化時: 保存されたAPIキーを読み込みました")

    def initialize_with_video(self, video_path: Path) -> None:
        """
        動画ファイルで初期化

        Args:
            video_path: 動画ファイルパス
        """
        try:
            self.view_model.video_path = video_path

            # 動画情報を取得
            video_info = self.transcription_gateway.get_video_info(str(video_path))
            self.view_model.video_duration_minutes = video_info.duration / 60

            # 時間のフォーマット
            from utils.time_utils import format_time

            self.view_model.video_duration_text = format_time(video_info.duration)

            # 利用可能なキャッシュを取得
            self._load_available_caches()

            self.view_model.notify()

        except Exception as e:
            self.handle_error(e, "動画情報の取得")

    def _load_available_caches(self) -> None:
        """利用可能なキャッシュを読み込む"""
        try:
            if not self.view_model.video_path:
                return

            logger.info(f"キャッシュを検索中: {self.view_model.video_path}")

            # Gateway経由でキャッシュ一覧を取得
            cache_list = self.transcription_gateway.get_available_caches(str(self.view_model.video_path))

            logger.info(f"キャッシュが見つかりました: {len(cache_list)}個")

            # ViewModelのフォーマットに変換
            self.view_model.available_caches = [
                TranscriptionCache(
                    file_path=Path(cache["file_path"]),
                    mode=cache["mode"],
                    model_size=cache["model_size"],
                    modified_time=cache["modified_time"],
                    is_api=cache["is_api"],
                    actual_filename=cache.get("actual_filename"),
                )
                for cache in cache_list
            ]

            logger.info(f"ViewModelに設定されたキャッシュ数: {len(self.view_model.available_caches)}")

        except Exception as e:
            logger.warning(f"キャッシュ一覧の取得に失敗: {e}")
            logger.exception("詳細なエラー情報:")
            self.view_model.available_caches = []

    def set_processing_mode(self, use_api: bool) -> None:
        """
        処理モードを設定

        Args:
            use_api: APIモードを使用するか
        """
        logger.info(f"set_processing_mode呼び出し - use_api: {use_api}")

        self.view_model.use_api = use_api

        # モデルサイズをモードに応じて設定
        if use_api:
            self.view_model.model_size = "whisper-1"

            # APIモードの場合、保存されたAPIキーを読み込む
            from utils.api_key_manager import api_key_manager

            saved_key = api_key_manager.load_api_key()
            if saved_key:
                self.view_model.api_key = saved_key
                logger.info("保存されたAPIキーを読み込みました")
            else:
                self.view_model.api_key = None
                logger.warning("保存されたAPIキーが見つかりません")
        else:
            saved = self.session_manager.get("model_size", None)
            if saved and saved in self.view_model.available_models:
                self.view_model.model_size = saved
            else:
                self.view_model.model_size = self.view_model.available_models[0]

        # SessionManagerに保存（DIコンテナが参照できるように）
        self.session_manager.set("use_api", use_api)
        self.session_manager.set("api_key", self.view_model.api_key)
        self.session_manager.set("model_size", self.view_model.model_size)

        logger.info(f"SessionManagerに設定を保存 - use_api: {use_api}")

        # 料金を更新
        self._update_cost_estimation()

        self.view_model.notify()

    def set_model_size(self, model_size: str) -> None:
        """モデルサイズを設定"""
        logger.info(f"set_model_size: {model_size}")
        self.view_model.model_size = model_size
        self.session_manager.set("model_size", model_size)
        self.view_model.notify()

    def set_api_key(self, api_key: str) -> None:
        """
        APIキーを設定

        Args:
            api_key: OpenAI APIキー
        """
        self.view_model.api_key = api_key
        self.view_model.notify()

    def select_cache(self, cache: TranscriptionCache) -> None:
        """
        キャッシュを選択

        Args:
            cache: 選択するキャッシュ
        """
        self.view_model.selected_cache = cache
        self.view_model.use_cache = True
        self.view_model.notify()

    def load_selected_cache(self) -> bool:
        """
        選択されたキャッシュを読み込む

        Returns:
            成功したかどうか
        """
        if not self.view_model.selected_cache:
            return False

        try:
            # Gateway経由でキャッシュを読み込む
            logger.info(f"キャッシュファイルから読み込み: {self.view_model.selected_cache.file_path}")

            # LoadCacheRequestを作成
            # actual_filenameがある場合はそれを使用、なければmodel_sizeを使用
            cache_model_size = (
                self.view_model.selected_cache.actual_filename
                if self.view_model.selected_cache.actual_filename
                else self.view_model.selected_cache.model_size
            )

            request = LoadCacheRequest(
                video_path=FilePath(str(self.view_model.video_path)), model_size=cache_model_size
            )

            # ユースケース経由でキャッシュを読み込む
            result = self.load_cache_use_case.execute(request)

            if result:
                # ドメインエンティティをアダプターでラップ
                adapter = TranscriptionResultAdapter(result)

                # ViewModelにアダプターを設定
                self.view_model.transcription_result = adapter
                self.view_model.notify()

                # SessionManagerにドメインエンティティを保存
                self.session_manager.set_transcription_result(result)

                return True
            else:
                self.view_model.set_error("キャッシュの読み込みに失敗しました")
                return False

        except Exception as e:
            self.handle_error(e, "キャッシュ読み込み")
            return False

    def start_transcription(self, progress_callback: Callable[[float, str], None] | None = None) -> bool:
        """
        文字起こしを開始

        Args:
            progress_callback: 進捗コールバック

        Returns:
            成功したかどうか
        """
        logger.info(f"start_transcription開始 - is_ready_to_run: {self.view_model.is_ready_to_run}")
        logger.info(
            f"APIモード: {self.view_model.use_api}, APIキー: {'設定済み' if self.view_model.api_key else '未設定'}"
        )

        if not self.view_model.is_ready_to_run:
            self.view_model.set_error("実行に必要な情報が不足しています")
            return False

        try:
            logger.info("start_processing呼び出し")
            self.view_model.start_processing()

            # 進捗コールバックのラッパー
            # レガシーコードはprogress_callback(progress: float, status: str)の形式で呼び出す
            def wrapped_progress(progress: float, status: str = "") -> None:
                # キャンセルチェック
                if self.view_model.is_cancelled:
                    raise InterruptedError("処理がキャンセルされました")

                # 引数が1つの場合はstatusとして扱う（後方互換性）
                if isinstance(progress, str):
                    status = progress
                    progress = 0.5

                # ViewModelを更新
                self.view_model.update_progress(progress, status)

                # 元のコールバックも呼び出し
                if progress_callback:
                    progress_callback(progress, status)

            # バッチサイズは自動最適化されるため、手動設定は削除
            
            # 文字起こしユースケースを実行
            logger.info(
                f"TranscribeVideoRequest作成 - video_path: {self.view_model.video_path}, model_size: {self.view_model.model_size}"
            )
            request = TranscribeVideoRequest(
                video_path=FilePath(str(self.view_model.video_path)),
                model_size=self.view_model.model_size,
                language="ja",
                progress_callback=wrapped_progress,
            )

            logger.info("transcribe_use_case.execute呼び出し")
            logger.info(f"transcribe_use_case: {self.transcribe_use_case}")
            logger.info(f"transcribe_use_case.__class__: {self.transcribe_use_case.__class__}")
            result = self.transcribe_use_case.execute(request)

            if result:
                # ドメインエンティティをアダプターでラップ
                adapter = TranscriptionResultAdapter(result)

                # ViewModelにアダプターを設定
                self.view_model.transcription_result = adapter
                self.view_model.is_processing = False
                self.view_model.notify()

                # SessionManagerにドメインエンティティを保存
                self.session_manager.set_transcription_result(result)

                return True
            else:
                self.view_model.set_error("文字起こしに失敗しました")
                return False

        except InterruptedError:
            self.view_model.reset_processing_state()
            self.view_model.status_message = "処理がキャンセルされました"
            self.view_model.notify()
            return False

        except Exception as e:
            self.handle_error(e, "文字起こし処理")
            return False

    def cancel_transcription(self) -> None:
        """文字起こしをキャンセル"""
        self.view_model.cancel_processing()

    def _update_cost_estimation(self) -> None:
        """料金推定を更新"""
        if not self.view_model.use_api or self.view_model.video_duration_minutes == 0:
            self.view_model.estimated_cost_usd = 0
            self.view_model.estimated_cost_jpy = 0
            return

        try:
            # 料金計算（$0.006/分）
            OPENAI_COST_PER_MINUTE = 0.006
            cost_usd = self.view_model.video_duration_minutes * OPENAI_COST_PER_MINUTE
            cost_jpy = cost_usd * 150  # 為替レート

            self.view_model.estimated_cost_usd = cost_usd
            self.view_model.estimated_cost_jpy = cost_jpy

        except Exception as e:
            logger.warning(f"料金計算エラー: {e}")

    def handle_error(self, error: Exception, context: str) -> None:
        """
        エラーをハンドリング

        Args:
            error: エラー
            context: コンテキスト
        """
        try:
            error_info = self.error_handler.handle_error(error, context=context, raise_after=False)
            if error_info:
                self.view_model.set_error(error_info["user_message"], error_info.get("details"))
            else:
                self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")
        except Exception:
            # エラーハンドリング自体が失敗した場合
            self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")

    def get_transcription_result(self) -> Any | None:
        """
        文字起こし結果を取得

        Returns:
            文字起こし結果（TranscriptionResult）
        """
        return self.view_model.transcription_result

    def get_video_path(self) -> Path | None:
        """
        動画パスを取得

        Returns:
            動画ファイルパス
        """
        # SessionManagerから取得
        video_path_str = self.session_manager.get_video_path()
        if video_path_str:
            return Path(video_path_str)

        # ViewModelから取得
        return self.view_model.video_path

    def clear_result(self) -> None:
        """文字起こし結果をクリア"""
        logger.info("文字起こし結果をクリア")

        # ViewModelをクリア
        self.view_model.transcription_result = None

        # SessionManagerからもクリア
        self.session_manager.set_transcription_result(None)

        # 通知
        self.view_model.notify()
