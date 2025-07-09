"""
シンプルなテキスト処理ゲートウェイ

レガシーコードを使わず、ドメイン層のユースケースを直接使用する実装。
"""

from domain.entities import TextDifference, TranscriptionResult
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.use_cases.time_range_calculator import TimeRangeCalculator
from domain.value_objects import TimeRange
from use_cases.interfaces import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class SimpleTextProcessorGateway(ITextProcessorGateway):
    """
    シンプルなテキスト処理ゲートウェイ

    レガシーコードに依存せず、クリーンな実装を提供。
    """

    def __init__(self):
        """初期化"""
        self._detector = TextDifferenceDetector()
        self._calculator = TimeRangeCalculator()

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
        """
        logger.info(f"差分検出開始: 元{len(original_text)}文字, 編集{len(edited_text)}文字")

        # 正規化処理
        if not skip_normalization:
            import re

            # 全角スペースを半角に変換
            normalized_original = original_text.replace("　", " ")
            normalized_edited = edited_text.replace("　", " ")

            # 改行を統一
            normalized_original = normalized_original.replace("\r\n", "\n").replace("\r", "\n")
            normalized_edited = normalized_edited.replace("\r\n", "\n").replace("\r", "\n")

            # 連続する空白（スペース、タブ、改行）を1つに
            normalized_original = re.sub(r"\s+", " ", normalized_original)
            normalized_edited = re.sub(r"\s+", " ", normalized_edited)

            # 前後の空白を削除
            normalized_original = normalized_original.strip()
            normalized_edited = normalized_edited.strip()

            logger.info(f"正規化後: 元{len(normalized_original)}文字, 編集{len(normalized_edited)}文字")
        else:
            normalized_original = original_text
            normalized_edited = edited_text

        return self._detector.detect_differences(normalized_original, normalized_edited)

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
        # TimeRangeCalculatorを使用して時間範囲を計算
        time_tuples = self._calculator.calculate_time_ranges(differences, transcription)

        # TimeRangeオブジェクトに変換
        time_ranges = [TimeRange(start=start, end=end) for start, end in time_tuples]

        return time_ranges

    def get_time_ranges(
        self, text_difference: TextDifference, transcription_result: TranscriptionResult
    ) -> list[TimeRange]:
        """
        差分から時間範囲を取得（インターフェース準拠）

        Args:
            text_difference: テキスト差分
            transcription_result: 文字起こし結果

        Returns:
            共通部分の時間範囲リスト
        """
        return self.get_time_ranges_from_differences(text_difference, transcription_result)

    def get_time_ranges_tuples(
        self, differences: TextDifference, transcription: TranscriptionResult
    ) -> list[tuple[float, float]]:
        """
        差分情報から時間範囲のタプルを取得（後方互換性）

        Args:
            differences: 差分情報
            transcription: 文字起こし結果

        Returns:
            時間範囲のタプルリスト
        """
        time_ranges = self.get_time_ranges_from_differences(differences, transcription)
        return [(tr.start, tr.end) for tr in time_ranges]

    def normalize_text(self, text: str) -> str:
        """
        テキストを正規化

        Args:
            text: 正規化するテキスト

        Returns:
            正規化されたテキスト
        """
        # 全角半角の統一など
        import unicodedata

        return unicodedata.normalize("NFKC", text)

    def split_into_sentences(self, text: str) -> list[str]:
        """
        テキストを文に分割

        Args:
            text: 分割するテキスト

        Returns:
            文のリスト
        """
        # 句点で分割
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in "。！？":
                sentences.append(current.strip())
                current = ""

        if current.strip():
            sentences.append(current.strip())

        return sentences

    def find_differences_with_separator(
        self,
        source_text: str,
        target_text: str,
        transcription_result: TranscriptionResult,
        separator: str,
        skip_normalization: bool = False,
    ) -> TextDifference:
        """
        セパレータ付きテキストの差分検出

        Args:
            source_text: 元のテキスト
            target_text: 対象テキスト
            transcription_result: 文字起こし結果
            separator: セパレータ
            skip_normalization: 正規化をスキップするか

        Returns:
            差分情報
        """
        # セパレータで分割
        sections = self.split_text_by_separator(target_text, separator)

        # 各セクションを結合（セパレータなしで）
        combined_text = "".join(sections)

        logger.info(f"セパレータで{len(sections)}個のセクションに分割")
        logger.info(f"結合後のテキスト長: {len(combined_text)}文字")

        # セパレータを除外したテキストで差分検出
        return self.find_differences(source_text, combined_text, skip_normalization)

    def split_text_by_separator(self, text: str, separator: str) -> list[str]:
        """
        テキストをセパレータで分割

        Args:
            text: 分割するテキスト
            separator: セパレータ

        Returns:
            分割されたテキストのリスト
        """
        return [section.strip() for section in text.split(separator) if section.strip()]

    def remove_boundary_markers(self, text: str) -> str:
        """
        境界調整マーカーを削除

        Args:
            text: マーカーを削除するテキスト

        Returns:
            マーカーを削除したテキスト
        """
        # マーカーパターン: [<数値], [数値>]
        import re

        text = re.sub(r"\[<[\d.]+\]", "", text)
        text = re.sub(r"\[[\d.]+>\]", "", text)
        return text

    def extract_existing_markers(self, text: str) -> dict[str, dict[str, float]]:
        """
        既存のマーカー情報を抽出

        Args:
            text: マーカーを抽出するテキスト

        Returns:
            マーカー情報の辞書
        """
        import re

        markers = {}

        # パターン: [<開始値]テキスト[終了値>]
        pattern = r"\[<([\d.]+)\]([^[]+)\[([\d.]+)>\]"

        for match in re.finditer(pattern, text):
            start_val = float(match.group(1))
            content = match.group(2)
            end_val = float(match.group(3))

            markers[content] = {"start": start_val, "end": end_val}

        return markers

    def adjust_boundaries(
        self, video_path: str, time_ranges: list[tuple[float, float]], adjustments: dict[str, dict[str, float]]
    ) -> list[tuple[float, float]]:
        """
        境界を調整

        Args:
            video_path: 動画ファイルパス
            time_ranges: 時間範囲のリスト
            adjustments: 調整値の辞書

        Returns:
            調整された時間範囲のリスト
        """
        # 簡易実装：調整値を適用
        adjusted = []

        for i, (start, end) in enumerate(time_ranges):
            # 調整値があれば適用
            key = f"range_{i}"
            if key in adjustments:
                adj = adjustments[key]
                start += adj.get("start", 0)
                end += adj.get("end", 0)

            adjusted.append((start, end))

        return adjusted

    def apply_boundary_adjustments(self, text: str, time_ranges: list[TimeRange]) -> tuple[str, list[TimeRange]]:
        """
        境界調整マーカーを適用

        Args:
            text: マーカーを含むテキスト
            time_ranges: 元の時間範囲

        Returns:
            マーカーを除去したテキストと調整後の時間範囲
        """
        # マーカーを抽出
        markers = self.extract_existing_markers(text)

        # マーカーを削除
        cleaned_text = self.remove_boundary_markers(text)

        # 時間範囲を調整
        adjusted_ranges = []
        for i, time_range in enumerate(time_ranges):
            # TODO: マーカー情報に基づいて調整
            adjusted_ranges.append(time_range)

        return cleaned_text, adjusted_ranges

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
        results = []
        full_text = transcription_result.text

        # 大文字小文字を考慮
        search_text = full_text if case_sensitive else full_text.lower()
        search_query = query if case_sensitive else query.lower()

        # すべての出現位置を検索
        start = 0
        while True:
            pos = search_text.find(search_query, start)
            if pos == -1:
                break

            # 時間範囲を計算
            # TODO: より正確な実装が必要
            if transcription_result.segments:
                # 簡易実装：位置から時間を推定
                text_progress = pos / len(full_text)
                total_duration = transcription_result.segments[-1].end
                estimated_time = total_duration * text_progress

                # 前後0.5秒の範囲
                time_range = TimeRange(
                    start=max(0, estimated_time - 0.5), end=min(total_duration, estimated_time + 0.5)
                )

                matched_text = full_text[pos : pos + len(query)]
                results.append((matched_text, time_range))

            start = pos + 1

        return results
