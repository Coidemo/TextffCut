"""
テキスト処理ゲートウェイインターフェース
"""

from typing import Protocol

from domain.entities import TextDifference, TranscriptionResult
from domain.value_objects import TimeRange


class ITextProcessorGateway(Protocol):
    """テキスト処理機能へのゲートウェイ"""

    def find_differences(
        self,
        original_text: str,
        edited_text: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        テキストの差分を検出

        Args:
            original_text: 元のテキスト
            edited_text: 編集後のテキスト
            skip_normalization: 正規化をスキップするか

        Returns:
            差分情報

        Raises:
            TextProcessingError: 差分検出失敗
        """
        ...

    def get_time_ranges(
        self, text_difference: TextDifference, transcription_result: TranscriptionResult
    ) -> list[TimeRange]:
        """
        差分から時間範囲を取得

        Args:
            text_difference: テキスト差分
            transcription_result: 文字起こし結果

        Returns:
            共通部分の時間範囲リスト
        """
        ...


    def normalize_text(self, text: str) -> str:
        """
        テキストを正規化

        Args:
            text: 正規化するテキスト

        Returns:
            正規化されたテキスト
        """
        ...

    def search_text(
        self, query: str, transcription_result: TranscriptionResult, case_sensitive: bool = False
    ) -> list[tuple[str, TimeRange]]:
        """
        文字起こし結果からテキストを検索

        Args:
            query: 検索クエリ
            transcription_result: 文字起こし結果
            case_sensitive: 大文字小文字を区別するか

        Returns:
            マッチしたテキストと時間範囲のリスト
        """
        ...
