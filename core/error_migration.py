"""
エラークラス移行用モジュール

既存のエラークラスから新しいエラー階層への移行をサポート。
"""

import warnings

# 新しいエラークラス
from .error_handling import (
    AlignmentError,
    ConfigurationError,
    ExternalSystemError,
    FFmpegError,
    FileValidationError,
    InsufficientMemoryError,
    ProcessingError,
    TextffCutError,
    TranscriptionError,
    ValidationError,
    VideoProcessingError,
    WhisperError,
    WordsFieldMissingError,
)

# 既存のエラークラス（後方互換性のため）
try:
    from utils.exceptions import (
        ConfigurationError as OldConfigurationError,  # noqa: F401
    )
    from utils.exceptions import (
        FFmpegError as OldFFmpegError,  # noqa: F401
    )
    from utils.exceptions import (
        FileNotFoundError as OldFileNotFoundError,  # noqa: F401
    )
    from utils.exceptions import (
        MemoryError as OldMemoryError,  # noqa: F401
    )
    from utils.exceptions import (
        TextffCutError as OldTextffCutError,
    )
    from utils.exceptions import (
        TranscriptionError as OldTranscriptionError,  # noqa: F401
    )
    from utils.exceptions import (
        VideoProcessingError as OldVideoProcessingError,  # noqa: F401
    )
    from utils.exceptions import (
        WhisperError as OldWhisperError,  # noqa: F401
    )

    UTILS_EXCEPTIONS_AVAILABLE = True
except ImportError:
    UTILS_EXCEPTIONS_AVAILABLE = False

try:
    from core.exceptions import (  # noqa: F401
        AlignmentError as CoreAlignmentError,
    )
    from core.exceptions import (
        AlignmentValidationError,  # noqa: F401
        CacheError,  # noqa: F401
        RetryExhaustedError,  # noqa: F401
        SubprocessError,  # noqa: F401
        TranscriptionValidationError,  # noqa: F401
    )
    from core.exceptions import (
        ProcessingError as CoreProcessingError,  # noqa: F401
    )
    from core.exceptions import (
        WordsFieldMissingError as CoreWordsFieldMissingError,  # noqa: F401
    )

    CORE_EXCEPTIONS_AVAILABLE = True
except ImportError:
    CORE_EXCEPTIONS_AVAILABLE = False


class ErrorMigration:
    """エラークラスの移行ヘルパー"""

    # 旧エラークラスから新エラークラスへのマッピング
    ERROR_MAPPING: dict[str, type[TextffCutError]] = {
        # utils.exceptions からの移行
        "TextffCutError": TextffCutError,
        "TranscriptionError": TranscriptionError,
        "VideoProcessingError": VideoProcessingError,
        "FileNotFoundError": FileValidationError,
        "FFmpegError": FFmpegError,
        "WhisperError": WhisperError,
        "MemoryError": InsufficientMemoryError,
        "ConfigurationError": ConfigurationError,
        # core.exceptions からの移行
        "ProcessingError": ProcessingError,
        "TranscriptionValidationError": ValidationError,
        "WordsFieldMissingError": WordsFieldMissingError,
        "AlignmentError": AlignmentError,
        "AlignmentValidationError": ValidationError,
        "SubprocessError": ExternalSystemError,
        "CacheError": ProcessingError,
        "RetryExhaustedError": ProcessingError,
    }

    @classmethod
    def convert_error(cls, old_error: Exception) -> TextffCutError:
        """
        旧エラーを新しいエラークラスに変換

        Args:
            old_error: 変換元のエラー

        Returns:
            新しいエラークラスのインスタンス
        """
        error_type_name = type(old_error).__name__

        # マッピングから新しいエラークラスを取得
        new_error_class = cls.ERROR_MAPPING.get(error_type_name, TextffCutError)

        # エラーメッセージと詳細を抽出
        message = str(old_error)
        details = {}

        # 旧エラーから属性を抽出
        if hasattr(old_error, "details"):
            details = old_error.details
        elif hasattr(old_error, "__dict__"):
            details = {k: v for k, v in old_error.__dict__.items() if not k.startswith("_")}

        # 新しいエラーインスタンスを作成
        return new_error_class(message=message, details=details, cause=old_error)

    @classmethod
    def create_compatibility_wrapper(cls, old_error_class: type[Exception]) -> type[Exception]:
        """
        後方互換性のためのラッパークラスを作成

        Args:
            old_error_class: ラップする旧エラークラス

        Returns:
            ラッパークラス
        """

        class CompatibilityWrapper(TextffCutError):
            def __init__(self, *args, **kwargs) -> None:
                warnings.warn(
                    f"{old_error_class.__name__} is deprecated. "
                    f"Use {self.__class__.__bases__[0].__name__} instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                super().__init__(*args, **kwargs)

        CompatibilityWrapper.__name__ = old_error_class.__name__
        CompatibilityWrapper.__qualname__ = old_error_class.__qualname__

        return CompatibilityWrapper


# 後方互換性のためのエイリアス（非推奨）
def create_compatibility_aliases() -> dict[str, type[Exception]]:
    """後方互換性のためのエイリアスを作成"""
    aliases = {}

    # utils.exceptions のエイリアス
    if UTILS_EXCEPTIONS_AVAILABLE:
        aliases["TextffCutError"] = ErrorMigration.create_compatibility_wrapper(OldTextffCutError)
        # 他のエイリアスも必要に応じて追加

    # core.exceptions のエイリアス
    if CORE_EXCEPTIONS_AVAILABLE:
        # 必要に応じて追加
        pass

    return aliases


# 移行支援関数
def migrate_exception_handling(func):
    """
    デコレータ: 旧エラーを新エラーに自動変換

    使用例:
        @migrate_exception_handling
        def some_function():
            # 旧エラーをraiseしても新エラーに変換される
            raise OldTranscriptionError("エラー")
    """

    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TextffCutError:
            # 既に新しいエラーの場合はそのまま
            raise
        except Exception as e:
            # 旧エラーを新エラーに変換
            new_error = ErrorMigration.convert_error(e)
            raise new_error from e

    return wrapper
