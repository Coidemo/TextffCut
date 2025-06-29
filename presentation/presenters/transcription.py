"""
文字起こしのPresenter

文字起こし機能のビジネスロジックを担当します。
"""

import logging
from typing import Optional, List, Callable, Any
from pathlib import Path
from presentation.presenters.base import BasePresenter
from presentation.view_models.transcription import TranscriptionViewModel, TranscriptionCache
from use_cases.interfaces.file_gateway import IFileGateway
from use_cases.interfaces.transcription_gateway import ITranscriptionGateway
from use_cases.transcription.transcribe_video import TranscribeVideoUseCase, TranscribeVideoRequest
from use_cases.transcription.load_cache import LoadTranscriptionCacheUseCase, LoadCacheRequest
from domain.value_objects.file_path import FilePath
from core.error_handling import ErrorHandler


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
        error_handler: ErrorHandler
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
        """
        super().__init__(view_model)
        self.transcribe_use_case = transcribe_use_case
        self.load_cache_use_case = load_cache_use_case
        self.file_gateway = file_gateway
        self.transcription_gateway = transcription_gateway
        self.error_handler = error_handler
    
    def initialize(self) -> None:
        """初期化処理"""
        # 必要に応じて初期化処理を実装
        pass
    
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
            
            # Gateway経由でキャッシュ一覧を取得
            cache_list = self.transcription_gateway.get_available_caches(str(self.view_model.video_path))
            
            # ViewModelのフォーマットに変換
            self.view_model.available_caches = [
                TranscriptionCache(
                    file_path=Path(cache["file_path"]),
                    mode=cache["mode"],
                    model_size=cache["model_size"],
                    modified_time=cache["modified_time"],
                    is_api=cache["is_api"]
                )
                for cache in cache_list
            ]
            
        except Exception as e:
            logger.warning(f"キャッシュ一覧の取得に失敗: {e}")
            self.view_model.available_caches = []
    
    def set_processing_mode(self, use_api: bool) -> None:
        """
        処理モードを設定
        
        Args:
            use_api: APIモードを使用するか
        """
        self.view_model.use_api = use_api
        
        # モデルサイズをモードに応じて設定
        if use_api:
            self.view_model.model_size = "whisper-1"
        else:
            self.view_model.model_size = "medium"
        
        # 料金を更新
        self._update_cost_estimation()
        
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
            # キャッシュ読み込みユースケースを実行
            request = LoadCacheRequest(
                video_path=FilePath(str(self.view_model.video_path))
            )
            
            result = self.load_cache_use_case.execute(request)
            
            if result:
                self.view_model.transcription_result = result
                self.view_model.notify()
                return True
            else:
                self.view_model.set_error("キャッシュの読み込みに失敗しました")
                return False
                
        except Exception as e:
            self.handle_error(e, "キャッシュ読み込み")
            return False
    
    def start_transcription(self, progress_callback: Optional[Callable[[float, str], None]] = None) -> bool:
        """
        文字起こしを開始
        
        Args:
            progress_callback: 進捗コールバック
            
        Returns:
            成功したかどうか
        """
        if not self.view_model.is_ready_to_run:
            self.view_model.set_error("実行に必要な情報が不足しています")
            return False
        
        try:
            self.view_model.start_processing()
            
            # 進捗コールバックのラッパー（TranscribeVideoRequestはstatus文字列のみを受け取る）
            def wrapped_progress(status: str) -> None:
                # キャンセルチェック
                if self.view_model.is_cancelled:
                    raise InterruptedError("処理がキャンセルされました")
                
                # 進捗率は推定値を使用
                progress = 0.5  # 実際の進捗が取れない場合は50%固定
                
                # ViewModelを更新
                self.view_model.update_progress(progress, status)
                
                # 元のコールバックも呼び出し（元の形式で）
                if progress_callback:
                    progress_callback(progress, status)
            
            # 文字起こしユースケースを実行
            request = TranscribeVideoRequest(
                video_path=FilePath(str(self.view_model.video_path)),
                model_size=self.view_model.model_size,
                language="ja",
                progress_callback=wrapped_progress
            )
            
            result = self.transcribe_use_case.execute(request)
            
            if result:
                self.view_model.complete_processing(result)
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
                self.view_model.set_error(
                    error_info["user_message"],
                    error_info.get("details")
                )
            else:
                self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")
        except Exception:
            # エラーハンドリング自体が失敗した場合
            self.view_model.set_error(f"{context}でエラーが発生しました: {str(error)}")
    
    def get_transcription_result(self) -> Optional[Any]:
        """
        文字起こし結果を取得
        
        Returns:
            文字起こし結果（TranscriptionResult）
        """
        return self.view_model.transcription_result