"""
統一エラーハンドリングシステム

プロジェクト全体で一貫したエラー処理を提供する。
"""

import logging
import traceback
from datetime import datetime
from enum import Enum
from typing import Any


class ErrorSeverity(Enum):
    """エラーの重要度"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """エラーカテゴリ"""

    VALIDATION = "validation"
    PROCESSING = "processing"
    RESOURCE = "resource"
    CONFIGURATION = "configuration"
    EXTERNAL = "external"
    SYSTEM = "system"


class TextffCutError(Exception):
    """
    TextffCut基底エラークラス

    すべてのプロジェクト固有エラーの基底クラス。
    統一されたエラー情報の構造を提供する。
    """

    # デフォルト値
    error_code: str = "UNKNOWN_ERROR"
    severity: ErrorSeverity = ErrorSeverity.ERROR
    category: ErrorCategory = ErrorCategory.SYSTEM
    user_message: str = "エラーが発生しました"
    recoverable: bool = False

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
        user_message: str | None = None,
    ):
        """
        エラーを初期化

        Args:
            message: 開発者向けの詳細メッセージ
            details: 追加の詳細情報
            cause: 原因となった例外
            user_message: ユーザー向けメッセージ（Noneの場合はデフォルト使用）
        """
        self.message = message
        self.details = details or {}
        self.cause = cause
        self.timestamp = datetime.now()

        if user_message:
            self.user_message = user_message

        # 原因がある場合は詳細に追加
        if cause:
            self.details["cause_type"] = type(cause).__name__
            self.details["cause_message"] = str(cause)

        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """エラー情報を辞書形式に変換"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "user_message": self.user_message,
            "severity": self.severity.value,
            "category": self.category.value,
            "recoverable": self.recoverable,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }

    def get_log_message(self) -> str:
        """ログ用メッセージを生成"""
        parts = [f"[{self.error_code}]", f"[{self.severity.value.upper()}]", self.message]

        if self.details:
            parts.append(f"Details: {self.details}")

        return " ".join(parts)


# 検証エラー
class ValidationError(TextffCutError):
    """入力検証エラー"""

    error_code = "VALIDATION_ERROR"
    severity = ErrorSeverity.WARNING
    category = ErrorCategory.VALIDATION
    user_message = "入力値が正しくありません"
    recoverable = True


class FileValidationError(ValidationError):
    """ファイル検証エラー"""

    error_code = "FILE_VALIDATION_ERROR"
    user_message = "ファイルが見つからないか、アクセスできません"


class ParameterValidationError(ValidationError):
    """パラメータ検証エラー"""

    error_code = "PARAMETER_VALIDATION_ERROR"
    user_message = "パラメータが正しくありません"


# 処理エラー
class ProcessingError(TextffCutError):
    """処理エラー"""

    error_code = "PROCESSING_ERROR"
    severity = ErrorSeverity.ERROR
    category = ErrorCategory.PROCESSING
    user_message = "処理中にエラーが発生しました"


class TranscriptionError(ProcessingError):
    """文字起こしエラー"""

    error_code = "TRANSCRIPTION_ERROR"
    user_message = "文字起こし処理でエラーが発生しました"


class VideoProcessingError(ProcessingError):
    """動画処理エラー"""

    error_code = "VIDEO_PROCESSING_ERROR"
    user_message = "動画処理でエラーが発生しました"


class AlignmentError(ProcessingError):
    """アライメントエラー"""

    error_code = "ALIGNMENT_ERROR"
    user_message = "アライメント処理でエラーが発生しました"


class ExportError(ProcessingError):
    """エクスポートエラー"""

    error_code = "EXPORT_ERROR"
    user_message = "エクスポート処理でエラーが発生しました"


# リソースエラー
class ResourceError(TextffCutError):
    """リソース関連エラー"""

    error_code = "RESOURCE_ERROR"
    severity = ErrorSeverity.ERROR
    category = ErrorCategory.RESOURCE
    user_message = "リソースへのアクセスでエラーが発生しました"


class InsufficientMemoryError(ResourceError):
    """メモリ不足エラー"""

    error_code = "INSUFFICIENT_MEMORY_ERROR"
    severity = ErrorSeverity.CRITICAL
    user_message = "メモリが不足しています。他のアプリケーションを終了してください"


class DiskSpaceError(ResourceError):
    """ディスク容量不足エラー"""

    error_code = "DISK_SPACE_ERROR"
    severity = ErrorSeverity.CRITICAL
    user_message = "ディスク容量が不足しています"


# 外部システムエラー
class ExternalSystemError(TextffCutError):
    """外部システムエラー"""

    error_code = "EXTERNAL_SYSTEM_ERROR"
    severity = ErrorSeverity.ERROR
    category = ErrorCategory.EXTERNAL
    user_message = "外部システムでエラーが発生しました"


class FFmpegError(ExternalSystemError):
    """FFmpegエラー"""

    error_code = "FFMPEG_ERROR"
    user_message = "動画処理システムでエラーが発生しました"


class ExternalServiceError(ExternalSystemError):
    """外部サービスエラー（APIなど）"""

    error_code = "EXTERNAL_SERVICE_ERROR"
    user_message = "外部サービスでエラーが発生しました"


class WhisperError(ExternalSystemError):
    """Whisperエラー"""

    error_code = "WHISPER_ERROR"
    user_message = "音声認識システムでエラーが発生しました"


class APIError(ExternalSystemError):
    """APIエラー"""

    error_code = "API_ERROR"
    user_message = "APIへのアクセスでエラーが発生しました"
    recoverable = True


# 設定エラー
class ConfigurationError(TextffCutError):
    """設定エラー"""

    error_code = "CONFIGURATION_ERROR"
    severity = ErrorSeverity.ERROR
    category = ErrorCategory.CONFIGURATION
    user_message = "設定にエラーがあります"


# 特殊なエラー
class WordsFieldMissingError(ProcessingError):
    """
    wordsフィールド欠落エラー

    文字起こし結果にwordsフィールドがない場合の重要なエラー。
    検索や切り抜き機能に必須のため、特別扱いする。
    """

    error_code = "WORDS_FIELD_MISSING"
    severity = ErrorSeverity.ERROR
    user_message = "文字位置情報が欠落しています。アライメント処理が必要です"
    recoverable = True


class ErrorHandler:
    """統一エラーハンドラー"""

    def __init__(self, logger: logging.Logger | None = None):
        """
        エラーハンドラーを初期化

        Args:
            logger: 使用するロガー（Noneの場合はデフォルトロガー使用）
        """
        self.logger = logger or logging.getLogger(__name__)

    def handle_error(
        self, error: Exception, context: str, raise_after: bool = True, log_traceback: bool = True
    ) -> dict[str, Any] | None:
        """
        エラーを統一的に処理

        Args:
            error: 処理するエラー
            context: エラーが発生したコンテキスト
            raise_after: 処理後に例外を再発生させるか
            log_traceback: トレースバックをログに含めるか

        Returns:
            エラー情報の辞書（raise_after=Falseの場合）
        """
        # TextffCutErrorの場合
        if isinstance(error, TextffCutError):
            error_info = error.to_dict()
            error_info["context"] = context

            # ログ出力
            log_message = f"[{context}] {error.get_log_message()}"

            if error.severity == ErrorSeverity.CRITICAL:
                self.logger.critical(log_message)
            elif error.severity == ErrorSeverity.ERROR:
                self.logger.error(log_message)
            elif error.severity == ErrorSeverity.WARNING:
                self.logger.warning(log_message)
            else:
                self.logger.info(log_message)

            # トレースバックをログに追加
            if log_traceback and error.severity in [ErrorSeverity.ERROR, ErrorSeverity.CRITICAL]:
                self.logger.debug(f"Traceback:\n{traceback.format_exc()}")

        # その他の例外の場合
        else:
            error_info = {
                "error_code": "UNEXPECTED_ERROR",
                "message": str(error),
                "user_message": "システムエラーが発生しました",
                "severity": ErrorSeverity.ERROR.value,
                "category": ErrorCategory.SYSTEM.value,
                "recoverable": False,
                "context": context,
                "error_type": type(error).__name__,
            }

            self.logger.error(f"[{context}] Unexpected error: {error}", exc_info=True)

        if raise_after:
            raise error
        else:
            return error_info

    @staticmethod
    def format_user_message(error: Exception) -> str:
        """
        ユーザー向けメッセージを生成

        Args:
            error: エラーオブジェクト

        Returns:
            ユーザー向けメッセージ
        """
        if isinstance(error, TextffCutError):
            return error.user_message
        else:
            return "システムエラーが発生しました"

    @staticmethod
    def is_recoverable(error: Exception) -> bool:
        """
        エラーが回復可能かチェック

        Args:
            error: エラーオブジェクト

        Returns:
            回復可能な場合True
        """
        if isinstance(error, TextffCutError):
            return error.recoverable
        return False

    @staticmethod
    def get_error_code(error: Exception) -> str:
        """
        エラーコードを取得

        Args:
            error: エラーオブジェクト

        Returns:
            エラーコード
        """
        if isinstance(error, TextffCutError):
            return error.error_code
        return "UNEXPECTED_ERROR"
