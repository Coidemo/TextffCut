"""
ドメインエンティティ

ビジネスロジックの中核となるエンティティを定義します。
エンティティは同一性を持ち、ライフサイクルを通じて追跡されます。
"""

from .text_difference import TextDifference
from .transcription import (
    Char,
    TranscriptionResult,
    TranscriptionSegment,
    Word,
)
from .video_segment import VideoSegment

__all__ = [
    "TranscriptionResult",
    "TranscriptionSegment",
    "Word",
    "Char",
    "VideoSegment",
    "TextDifference",
]
