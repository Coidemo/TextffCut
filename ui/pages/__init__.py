"""
UIページコントローラー

main.pyのリファクタリングで分離されたページコントローラーを提供します。
各ページは独立したモジュールとして実装され、単一の責任を持ちます。
"""

from .transcription_page import TranscriptionPageController
from .text_editing_page import TextEditingPageController
from .processing_page import ProcessingPageController

__all__ = [
    "TranscriptionPageController",
    "TextEditingPageController", 
    "ProcessingPageController",
]