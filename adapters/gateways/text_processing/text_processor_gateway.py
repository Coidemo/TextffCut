"""
テキスト処理ゲートウェイの実装

既存のTextProcessorクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

from uuid import uuid4

from adapters.converters.text_converter import TextConverter
from adapters.converters.transcription_converter import TranscriptionConverter
from core.text_processor import TextDifference as LegacyTextDifference
from core.text_processor import TextProcessor as LegacyTextProcessor
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from core.transcription import TranscriptionSegment as LegacyTranscriptionSegment
from domain.entities import TextDifference, TranscriptionResult, TranscriptionSegment
from domain.entities.text_difference import DifferenceType
from domain.value_objects import TimeRange
from use_cases.interfaces import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class TextProcessorGatewayAdapter(ITextProcessorGateway):
    """
    テキスト処理ゲートウェイのアダプター実装

    既存のTextProcessorクラスをラップし、ドメイン層のインターフェースに適合させます。
    """

    def __init__(self):
        """初期化"""
        self._legacy_processor = LegacyTextProcessor()
        self._text_converter = TextConverter()
        self._transcription_converter = TranscriptionConverter()

    def find_differences(
        self, original_text: str, edited_text: str, skip_normalization: bool = False
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
            TextProcessingError: 差分検出に失敗
        """
        try:
            # レガシーメソッドを呼び出し
            legacy_diff = self._legacy_processor.find_differences(
                original=original_text, edited=edited_text, skip_normalization=skip_normalization
            )

            # ドメインエンティティに変換
            domain_diff = self._text_converter.legacy_difference_to_domain(legacy_diff)

            # 差分の統計情報をログ出力
            unchanged_count = sum(1 for d in domain_diff.differences if d[0] == DifferenceType.UNCHANGED)
            added_count = sum(1 for d in domain_diff.differences if d[0] == DifferenceType.ADDED)
            deleted_count = sum(1 for d in domain_diff.differences if d[0] == DifferenceType.DELETED)

            logger.info(
                f"Text differences found: {unchanged_count} unchanged, " f"{added_count} added, {deleted_count} deleted"
            )

            return domain_diff

        except Exception as e:
            logger.error(f"Failed to find text differences: {e}")
            from use_cases.exceptions import TextProcessingError

            raise TextProcessingError(f"Failed to find text differences: {str(e)}", cause=e)

    def get_time_ranges_from_differences(
        self, differences: TextDifference, transcription: TranscriptionResult
    ) -> list[TimeRange]:
        """
        差分情報から時間範囲を取得

        Args:
            differences: 差分情報
            transcription: 文字起こし結果

        Returns:
            時間範囲のリスト
        """
        try:
            # ドメインエンティティをレガシー形式に変換
            legacy_transcription = self._convert_to_legacy_transcription(transcription)
            legacy_diff = self._convert_to_legacy_difference(differences)

            # レガシーメソッドを呼び出し
            time_ranges_tuples = legacy_diff.get_time_ranges(legacy_transcription)

            # タプルをドメインのTimeRangeに変換
            domain_ranges = self._text_converter.time_ranges_to_domain(time_ranges_tuples)

            logger.info(f"Extracted {len(domain_ranges)} time ranges from differences")

            return domain_ranges

        except Exception as e:
            logger.error(f"Failed to get time ranges: {e}")
            from use_cases.exceptions import TextProcessingError

            raise TextProcessingError(f"Failed to get time ranges from differences: {str(e)}", cause=e)

    def adjust_boundaries(
        self,
        text: str,
        time_ranges: list[TimeRange],
        transcription_segments: list[TranscriptionSegment],
        markers: list[str] | None = None,
    ) -> list[TranscriptionSegment]:
        """
        マーカーを使用して境界を調整

        Args:
            text: 調整対象のテキスト
            time_ranges: 時間範囲
            transcription_segments: 文字起こしセグメント
            markers: 境界マーカー

        Returns:
            調整済みのセグメント
        """
        try:
            # デフォルトマーカー
            if markers is None:
                markers = ["<<", ">>"]

            # ドメインエンティティをレガシー形式に変換
            legacy_segments = self._convert_to_legacy_segments(transcription_segments)
            legacy_time_ranges = self._text_converter.domain_to_time_ranges(time_ranges)

            # レガシーメソッドを呼び出し
            # TextProcessorにはadjust_boundariesメソッドがないので、
            # 直接的な境界調整は行わず、セグメントをそのまま返す
            # TODO: 実際の境界調整ロジックの実装

            # 簡易実装：マーカーで区切られた部分を検出してセグメントを調整
            adjusted_segments = self._simple_boundary_adjustment(text, time_ranges, transcription_segments, markers)

            logger.info(f"Adjusted {len(adjusted_segments)} segments")

            return adjusted_segments

        except Exception as e:
            logger.error(f"Failed to adjust boundaries: {e}")
            from use_cases.exceptions import TextProcessingError

            raise TextProcessingError(f"Failed to adjust boundaries: {str(e)}", cause=e)

    def normalize_text(self, text: str, preserve_newlines: bool = False) -> str:
        """
        テキストを正規化

        Args:
            text: 正規化するテキスト
            preserve_newlines: 改行を保持するか

        Returns:
            正規化されたテキスト
        """
        try:
            return self._legacy_processor.normalize_text(text, preserve_newlines)
        except Exception as e:
            logger.error(f"Failed to normalize text: {e}")
            return text  # エラー時は元のテキストを返す

    def split_into_sentences(self, text: str, language: str = "ja") -> list[str]:
        """
        テキストを文に分割

        Args:
            text: 分割するテキスト
            language: 言語コード

        Returns:
            文のリスト
        """
        try:
            # 日本語の場合
            if language == "ja":
                # 句点、感嘆符、疑問符で分割
                import re

                sentences = re.split(r"[。！？]+", text)
                # 空文字列を除外
                return [s.strip() for s in sentences if s.strip()]
            else:
                # 英語の場合
                # ピリオド、感嘆符、疑問符で分割
                import re

                sentences = re.split(r"[.!?]+", text)
                return [s.strip() for s in sentences if s.strip()]
        except Exception as e:
            logger.error(f"Failed to split text: {e}")
            # エラー時は全体を1文として返す
            return [text]

    def split_text_by_separator(self, text: str, separator: str) -> list[str]:
        """
        区切り文字でテキストを分割

        Args:
            text: 分割するテキスト
            separator: 区切り文字

        Returns:
            分割されたテキストのリスト
        """
        try:
            # 区切り文字で分割
            sections = text.split(separator)
            # 空文字列を除外してトリミング
            return [s.strip() for s in sections if s.strip()]
        except Exception as e:
            logger.error(f"Failed to split text by separator: {e}")
            return [text]

    def remove_boundary_markers(self, text: str) -> str:
        """
        境界調整マーカーを削除

        Args:
            text: マーカーを削除するテキスト

        Returns:
            マーカーを削除したテキスト
        """
        try:
            import re

            # [<数値] と [数値>] のパターンを削除
            text = re.sub(r"\[<[\d.]+\]", "", text)
            text = re.sub(r"\[[\d.]+>\]", "", text)
            return text
        except Exception as e:
            logger.error(f"Failed to remove boundary markers: {e}")
            return text

    def extract_existing_markers(self, text: str) -> dict:
        """
        既存の境界調整マーカーを抽出

        Args:
            text: マーカーを抽出するテキスト

        Returns:
            マーカー情報の辞書
        """
        try:
            import re

            markers = {}

            # [<数値]text[数値>]のパターンを検索
            pattern = r"\[<([\d.]+)\]([^[]+)\[([\d.]+)>\]"
            matches = re.finditer(pattern, text)

            for match in matches:
                start_val = float(match.group(1))
                text_content = match.group(2)
                end_val = float(match.group(3))
                markers[text_content] = {"start": start_val, "end": end_val}

            return markers
        except Exception as e:
            logger.error(f"Failed to extract markers: {e}")
            return {}

    def find_differences_with_separator(
        self,
        source_text: str,
        target_text: str,
        transcription_result: TranscriptionResult,
        separator: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        区切り文字と文脈指定を考慮して差分を検出

        Args:
            source_text: 元のテキスト
            target_text: 編集後のテキスト
            transcription_result: 文字起こし結果
            separator: 区切り文字
            skip_normalization: 正規化をスキップするか

        Returns:
            差分情報
        """
        try:
            # レガシーの文字起こし結果に変換
            legacy_transcription = self._convert_to_legacy_transcription(transcription_result)

            # レガシーメソッドを呼び出して時間範囲を取得
            time_ranges_tuples = self._legacy_processor.find_differences_with_separator(
                source_text, target_text, legacy_transcription, separator, skip_normalization
            )

            # 結果からTextDifferenceを構築
            # ここでは時間範囲から逆算して差分情報を作成
            differences = []
            for start_time, end_time in time_ranges_tuples:
                # 時間範囲に対応するテキストを推定（簡易実装）
                differences.append(
                    (
                        DifferenceType.UNCHANGED,
                        "",  # テキストは空にする（時間範囲のみ重要）
                        TimeRange(start=start_time, end=end_time),
                    )
                )

            return TextDifference(
                id=str(uuid4()), original_text=source_text, edited_text=target_text, differences=differences
            )

        except Exception as e:
            logger.error(f"Failed to find differences with separator: {e}")
            from use_cases.exceptions import TextProcessingError

            raise TextProcessingError(f"Failed to find differences with separator: {str(e)}", cause=e)

    def get_time_ranges(
        self, diff_result: TextDifference, transcription_result: TranscriptionResult
    ) -> list[TimeRange]:
        """
        差分結果から時間範囲を取得

        Args:
            diff_result: 差分結果
            transcription_result: 文字起こし結果

        Returns:
            時間範囲のリスト
        """
        # get_time_ranges_from_differencesメソッドを使用
        return self.get_time_ranges_from_differences(diff_result, transcription_result)

    # ===== ヘルパーメソッド =====

    def _convert_to_legacy_transcription(self, transcription: TranscriptionResult) -> LegacyTranscriptionResult:
        """ドメインの文字起こし結果をレガシー形式に変換"""
        # TranscriptionConverterの逆変換を利用
        legacy_dict = self._transcription_converter.domain_to_legacy_dict(transcription)

        # 辞書からレガシーオブジェクトを作成
        segments = []
        for seg_dict in legacy_dict["segments"]:
            # words と chars はそのまま辞書形式で保持
            # LegacyTranscriptionSegmentは辞書形式のwords/charsを期待している
            words = seg_dict.get("words")
            chars = seg_dict.get("chars")

            segment = LegacyTranscriptionSegment(
                start=seg_dict["start"],
                end=seg_dict["end"],
                text=seg_dict["text"],
                words=words,
                chars=chars,
            )
            segments.append(segment)

        return LegacyTranscriptionResult(
            language=legacy_dict["language"],
            segments=segments,
            original_audio_path=legacy_dict["original_audio_path"],
            model_size=legacy_dict["model_size"],
            processing_time=legacy_dict.get("processing_time", 0.0),
        )

    def _convert_to_legacy_segments(self, segments: list[TranscriptionSegment]) -> list[LegacyTranscriptionSegment]:
        """ドメインのセグメントをレガシー形式に変換"""
        legacy_segments = []

        for segment in segments:
            # Wordsの変換
            words = None
            if segment.words:
                words = [
                    {"word": w.word, "start": w.start, "end": w.end, "confidence": w.confidence} for w in segment.words
                ]

            # Charsの変換
            chars = None
            if segment.chars:
                chars = [
                    {"char": c.char, "start": c.start, "end": c.end, "confidence": c.confidence} for c in segment.chars
                ]

            legacy_segment = LegacyTranscriptionSegment(
                start=segment.start, end=segment.end, text=segment.text, words=words, chars=chars
            )
            legacy_segments.append(legacy_segment)

        return legacy_segments

    def _convert_to_legacy_difference(self, differences: TextDifference) -> LegacyTextDifference:
        """ドメインの差分情報をレガシー形式に変換"""
        from core.text_processor import TextPosition as LegacyTextPosition

        # 共通部分の位置情報を変換
        common_positions = []
        added_positions = []
        added_chars = set()

        # differencesから各タイプを抽出
        current_pos = 0
        for diff_type, text, _ in differences.differences:
            if diff_type == DifferenceType.UNCHANGED:
                # 元のテキストから位置を見つける
                pos_in_original = differences.original_text.find(text, current_pos)
                if pos_in_original != -1:
                    pos = LegacyTextPosition(start=pos_in_original, end=pos_in_original + len(text), text=text)
                    common_positions.append(pos)
                    current_pos = pos_in_original + len(text)
            elif diff_type == DifferenceType.ADDED:
                # 追加された文字を収集
                added_chars.update(text)
                # 編集後のテキストから位置を見つける
                pos_in_edited = differences.edited_text.find(text)
                if pos_in_edited != -1:
                    pos = LegacyTextPosition(start=pos_in_edited, end=pos_in_edited + len(text), text=text)
                    added_positions.append(pos)

        return LegacyTextDifference(
            original_text=differences.original_text,
            edited_text=differences.edited_text,
            common_positions=common_positions,
            added_chars=added_chars,
            added_positions=added_positions if added_positions else None,
        )

    def _simple_boundary_adjustment(
        self, text: str, time_ranges: list[TimeRange], segments: list[TranscriptionSegment], markers: list[str]
    ) -> list[TranscriptionSegment]:
        """
        簡易的な境界調整実装

        マーカーで区切られた部分を検出し、対応するセグメントを調整します。
        """
        # TODO: 実際の境界調整ロジックの実装
        # 現在は入力をそのまま返す
        return segments
