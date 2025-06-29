"""
ドメインエンティティ

ビジネスロジックの中核となるエンティティを定義します。
エンティティは同一性を持ち、ライフサイクルを通じて追跡されます。
"""

from .transcription import (
    TranscriptionResult,
    TranscriptionSegment,
    Word,
    Char,
)
from .video_segment import VideoSegment
from .text_difference import TextDifference

__all__ = [
    "TranscriptionResult",
    "TranscriptionSegment",
    "Word",
    "Char",
    "VideoSegment",
    "TextDifference",
]
