"""
並列文字起こしユースケース
"""

from dataclasses import dataclass
from typing import Optional, Callable

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath, Duration
from use_cases.base import UseCase
from use_cases.exceptions import TranscriptionError
from use_cases.interfaces import ITranscriptionGateway, IVideoProcessorGateway


@dataclass
class ParallelTranscribeRequest:
    """並列文字起こしリクエスト"""
    video_path: FilePath
    model_size: str = "medium"
    language: Optional[str] = None
    chunk_duration: float = 600.0  # 10分
    num_workers: int = 2
    min_chunk_duration: float = 60.0  # 最小チャンク時間（1分）
    progress_callback: Optional[Callable[[str], None]] = None
    
    def __post_init__(self):
        """パスの検証とパラメータの調整"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))
        
        # パラメータの範囲チェック
        self.chunk_duration = max(self.min_chunk_duration, self.chunk_duration)
        self.num_workers = max(1, min(8, self.num_workers))  # 1-8の範囲


class ParallelTranscribeUseCase(UseCase[ParallelTranscribeRequest, TranscriptionResult]):
    """
    大きな動画を並列で文字起こしするユースケース
    
    動画をチャンクに分割し、複数のワーカーで並列処理します。
    """
    
    def __init__(
        self,
        transcription_gateway: ITranscriptionGateway,
        video_gateway: IVideoProcessorGateway
    ):
        super().__init__()
        self.transcription_gateway = transcription_gateway
        self.video_gateway = video_gateway
    
    def validate_request(self, request: ParallelTranscribeRequest) -> None:
        """リクエストのバリデーション"""
        # ファイルの存在確認
        if not request.video_path.exists:
            raise TranscriptionError(
                f"Video file not found: {request.video_path}"
            )
        
        # チャンク時間の確認
        if request.chunk_duration < request.min_chunk_duration:
            raise TranscriptionError(
                f"Chunk duration ({request.chunk_duration}s) must be at least "
                f"{request.min_chunk_duration}s"
            )
    
    def execute(self, request: ParallelTranscribeRequest) -> TranscriptionResult:
        """並列文字起こしの実行"""
        self.logger.info(
            f"Starting parallel transcription for: {request.video_path.name} "
            f"with {request.num_workers} workers"
        )
        
        # 動画情報の取得
        video_info = self._get_video_info(request.video_path)
        total_duration = Duration(seconds=video_info['duration'])
        
        # 並列処理が必要かチェック
        if total_duration.seconds <= request.chunk_duration:
            self.logger.info(
                f"Video duration ({total_duration.seconds:.1f}s) is less than "
                f"chunk duration ({request.chunk_duration}s). "
                "Using single transcription."
            )
            # 通常の文字起こしにフォールバック
            return self.transcription_gateway.transcribe(
                video_path=request.video_path,
                model_size=request.model_size,
                language=request.language,
                progress_callback=request.progress_callback
            )
        
        # 進捗通知
        if request.progress_callback:
            request.progress_callback(
                f"Starting parallel transcription with {request.num_workers} workers..."
            )
        
        try:
            # 並列文字起こしの実行
            result = self.transcription_gateway.transcribe_parallel(
                video_path=request.video_path,
                model_size=request.model_size,
                language=request.language,
                chunk_duration=request.chunk_duration,
                num_workers=request.num_workers,
                progress_callback=request.progress_callback
            )
            
            # 検証
            if not result.segments:
                raise TranscriptionError("No segments found in transcription result")
            
            # 結果の統計
            self.logger.info(
                f"Parallel transcription completed. "
                f"Total duration: {result.duration:.1f}s, "
                f"Segments: {len(result.segments)}, "
                f"Processing time: {result.processing_time:.1f}s"
            )
            
            # 処理時間の効率を計算
            speedup = total_duration.seconds / result.processing_time
            self.logger.info(f"Processing speed: {speedup:.1f}x realtime")
            
            return result
            
        except TranscriptionError:
            raise
        except Exception as e:
            self.logger.error(f"Parallel transcription failed: {str(e)}")
            raise TranscriptionError(
                f"Failed to transcribe video in parallel: {str(e)}",
                cause=e
            )
    
    def _get_video_info(self, video_path: FilePath) -> dict:
        """動画情報を取得"""
        try:
            return self.video_gateway.get_video_info(video_path)
        except Exception as e:
            raise TranscriptionError(
                f"Failed to get video information: {str(e)}",
                cause=e
            )