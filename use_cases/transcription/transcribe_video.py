"""
動画文字起こしユースケース
"""

from collections.abc import Callable
from dataclasses import dataclass

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath
from use_cases.base import UseCase
from use_cases.exceptions import ModelNotAvailableError, TranscriptionError
from use_cases.interfaces import ITranscriptionGateway


@dataclass
class TranscribeVideoRequest:
    """動画文字起こしリクエスト"""

    video_path: FilePath
    model_size: str = "medium"
    language: str | None = None
    use_cache: bool = True
    skip_alignment: bool = False
    progress_callback: Callable[[str], None] | None = None

    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))


class TranscribeVideoUseCase(UseCase[TranscribeVideoRequest, TranscriptionResult]):
    """
    動画の文字起こしを実行するユースケース

    キャッシュがある場合は利用し、なければ新規に文字起こしを実行します。
    """

    def __init__(self, transcription_gateway: ITranscriptionGateway):
        super().__init__()
        self.gateway = transcription_gateway

    def validate_request(self, request: TranscribeVideoRequest) -> None:
        """リクエストのバリデーション"""
        # ファイルの存在確認
        if not request.video_path.exists:
            raise TranscriptionError(f"Video file not found: {request.video_path}")

        # ファイル拡張子の確認
        valid_extensions = [".mp4", ".avi", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"]
        if not request.video_path.validate_extension(valid_extensions):
            raise TranscriptionError(f"Invalid video/audio format: {request.video_path.extension}")

        # モデルサイズの確認
        available_models = self.gateway.get_available_models()
        if request.model_size not in available_models:
            raise ModelNotAvailableError(
                f"Model '{request.model_size}' is not available. " f"Available models: {', '.join(available_models)}"
            )

    def execute(self, request: TranscribeVideoRequest) -> TranscriptionResult:
        """文字起こしの実行"""
        self.logger.info(f"Starting transcription for: {request.video_path.name} " f"with model: {request.model_size}")

        # キャッシュの確認
        if request.use_cache:
            cached_result = self._try_load_cache(request)
            if cached_result:
                self.logger.info("Using cached transcription result")
                return cached_result

        # 進捗通知
        if request.progress_callback:
            request.progress_callback("Starting transcription...")

        try:
            # 文字起こしの実行
            result = self.gateway.transcribe(
                video_path=request.video_path,
                model_size=request.model_size,
                language=request.language,
                use_cache=request.use_cache,
                progress_callback=request.progress_callback,
            )

            # 検証
            if not result.segments:
                raise TranscriptionError("No segments found in transcription result")

            # キャッシュへの保存（ゲートウェイ内で処理される）
            self.logger.info(
                f"Transcription completed successfully. "
                f"Duration: {result.duration:.1f}s, "
                f"Segments: {len(result.segments)}"
            )

            return result

        except TranscriptionError:
            # TranscriptionErrorはそのまま再スロー
            raise
        except Exception as e:
            # その他のエラーはラップ
            self.logger.error(f"Transcription failed: {str(e)}")
            raise TranscriptionError(f"Failed to transcribe video: {str(e)}", cause=e)

    def _try_load_cache(self, request: TranscribeVideoRequest) -> TranscriptionResult | None:
        """キャッシュの読み込みを試行"""
        try:
            return self.gateway.load_from_cache(video_path=request.video_path, model_size=request.model_size)
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {str(e)}")
            return None
