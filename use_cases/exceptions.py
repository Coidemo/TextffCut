"""
ユースケース層の例外定義
"""

from typing import Optional
from .base import UseCaseError


class TranscriptionError(UseCaseError):
    """文字起こし関連のエラー"""
    pass


class CacheNotFoundError(TranscriptionError):
    """キャッシュが見つからない"""
    pass


class ModelNotAvailableError(TranscriptionError):
    """指定されたモデルが利用できない"""
    pass


class TextProcessingError(UseCaseError):
    """テキスト処理関連のエラー"""
    pass


class InvalidTextFormatError(TextProcessingError):
    """テキスト形式が不正"""
    pass


class VideoProcessingError(UseCaseError):
    """動画処理関連のエラー"""
    pass


class AudioExtractionError(VideoProcessingError):
    """音声抽出エラー"""
    pass


class SilenceDetectionError(VideoProcessingError):
    """無音検出エラー"""
    pass


class SegmentCombineError(VideoProcessingError):
    """セグメント結合エラー"""
    pass


class ExportError(UseCaseError):
    """エクスポート関連のエラー"""
    pass


class InvalidExportFormatError(ExportError):
    """エクスポート形式が不正"""
    pass


class FileWriteError(ExportError):
    """ファイル書き込みエラー"""
    def __init__(self, message: str, path: str, cause: Optional[Exception] = None):
        super().__init__(message, cause)
        self.path = path