"""
テキスト差分検出ユースケース
"""

from dataclasses import dataclass

from domain.entities import TextDifference, TranscriptionResult
from domain.value_objects import TimeRange
from use_cases.base import UseCase
from use_cases.exceptions import InvalidTextFormatError, TextProcessingError
from use_cases.interfaces import ITextProcessorGateway


@dataclass
class FindDifferencesRequest:
    """差分検出リクエスト"""

    original_text: str
    edited_text: str
    transcription_result: TranscriptionResult
    skip_normalization: bool = False


@dataclass
class FindDifferencesResponse:
    """差分検出レスポンス"""

    text_difference: TextDifference
    time_ranges: list[TimeRange]
    removed_count: int
    remaining_count: int

    @property
    def has_changes(self) -> bool:
        """変更があるかどうか"""
        return self.text_difference.has_changes

    @property
    def removal_rate(self) -> float:
        """削除率（0.0-1.0）"""
        total = self.removed_count + self.remaining_count
        return self.removed_count / total if total > 0 else 0.0


class FindTextDifferencesUseCase(UseCase[FindDifferencesRequest, FindDifferencesResponse]):
    """
    テキストの差分を検出し、対応する時間範囲を特定するユースケース

    元のテキストと編集後のテキストを比較し、
    残された部分（共通部分）の時間範囲を返します。
    """

    def __init__(self, text_processor_gateway: ITextProcessorGateway):
        super().__init__()
        self.gateway = text_processor_gateway

    def validate_request(self, request: FindDifferencesRequest) -> None:
        """リクエストのバリデーション"""
        # テキストの検証
        if not request.original_text and not request.edited_text:
            raise InvalidTextFormatError("Both original and edited text are empty")

        # 文字起こし結果の検証
        if not request.transcription_result.segments:
            raise TextProcessingError("Transcription result has no segments")

        # 元のテキストと文字起こし結果の整合性チェック
        transcribed_text = request.transcription_result.text
        if not self._texts_match(request.original_text, transcribed_text):
            self.logger.warning(
                "Original text does not match transcription result. "
                "This may cause inaccurate time range calculation."
            )

    def execute(self, request: FindDifferencesRequest) -> FindDifferencesResponse:
        """差分検出の実行"""
        self.logger.info("Starting text difference detection")

        try:
            # 差分の検出
            text_difference = self.gateway.find_differences(
                original_text=request.original_text,
                edited_text=request.edited_text,
                transcription_result=request.transcription_result,
                skip_normalization=request.skip_normalization,
            )

            # 時間範囲の取得
            time_ranges = self.gateway.get_time_ranges(
                text_difference=text_difference, transcription_result=request.transcription_result
            )

            # 統計情報の計算
            removed_count = text_difference.deleted_count
            remaining_count = len(time_ranges)

            self.logger.info(
                f"Difference detection completed. " f"Removed: {removed_count}, Remaining: {remaining_count}"
            )

            # 結果の検証
            if not time_ranges and request.edited_text:
                self.logger.warning(
                    "No time ranges found for edited text. " "This may indicate a problem with word-level timestamps."
                )

            return FindDifferencesResponse(
                text_difference=text_difference,
                time_ranges=time_ranges,
                removed_count=removed_count,
                remaining_count=remaining_count,
            )

        except TextProcessingError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to find differences: {str(e)}")
            raise TextProcessingError(f"Failed to find text differences: {str(e)}", cause=e)

    def _texts_match(self, text1: str, text2: str) -> bool:
        """テキストが大体一致しているか確認（正規化して比較）"""
        # 簡易的な正規化
        norm1 = text1.strip().replace("\n", " ").replace("  ", " ")
        norm2 = text2.strip().replace("\n", " ").replace("  ", " ")

        # 完全一致または部分一致をチェック
        return norm1 == norm2 or norm1 in norm2 or norm2 in norm1
