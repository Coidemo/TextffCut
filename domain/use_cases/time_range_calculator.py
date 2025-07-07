"""
時間範囲計算のユースケース

テキストの位置情報から音声/動画の時間範囲を計算する。
"""

from dataclasses import dataclass

from domain.entities.text_difference import DifferenceType, TextDifference
from domain.entities.transcription import TranscriptionResult
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimeRangeWithText:
    """テキスト付き時間範囲"""

    start: float
    end: float
    text: str


class TimeRangeCalculator:
    """
    時間範囲計算ユースケース

    テキストの差分情報と文字起こし結果から時間範囲を計算する。
    """

    def calculate_time_ranges(
        self, differences: TextDifference, transcription_result: TranscriptionResult
    ) -> list[tuple[float, float]]:
        """
        差分情報から時間範囲を計算

        Args:
            differences: テキスト差分情報
            transcription_result: 文字起こし結果

        Returns:
            時間範囲のタプルリスト
        """
        time_ranges = []

        # 変更されていない部分（UNCHANGED）の時間範囲を計算
        for diff_type, text, _ in differences.differences:
            if diff_type == DifferenceType.UNCHANGED and text.strip():
                # このテキストがtranscription内のどこにあるか探す
                ranges = self._find_text_time_ranges(text, transcription_result)
                time_ranges.extend(ranges)

        # 重複を除去して並び替え
        time_ranges = self._merge_overlapping_ranges(time_ranges)

        logger.info(f"計算された時間範囲: {len(time_ranges)}個")
        return time_ranges

    def _find_text_time_ranges(
        self, target_text: str, transcription_result: TranscriptionResult
    ) -> list[tuple[float, float]]:
        """
        指定テキストの時間範囲を検索

        Args:
            target_text: 検索対象テキスト
            transcription_result: 文字起こし結果

        Returns:
            時間範囲のリスト
        """
        ranges = []

        # 全体テキストを結合（スペースなし）
        full_text = transcription_result.text

        # テキストの位置を検索
        position = full_text.find(target_text)
        if position == -1:
            logger.warning(f"テキストが見つかりません: {target_text[:50]}...")
            return ranges

        # デバッグ情報
        logger.info(f"=== テキスト位置デバッグ ===")
        logger.info(f"検索テキスト: {target_text[:50]}...")
        logger.info(f"検索テキスト長: {len(target_text)}文字")
        logger.info(f"全体テキスト内の位置: {position}")
        logger.info(f"全体テキスト長: {len(full_text)}文字")

        # 位置から時間範囲を計算
        current_pos = 0
        start_time = None
        end_time = None
        target_start = position
        target_end = position + len(target_text)

        for segment in transcription_result.segments:
            segment_text = segment.text
            segment_len = len(segment_text)

            # このセグメントが対象範囲と重なるか確認
            segment_start = current_pos
            segment_end = current_pos + segment_len

            # 開始位置がこのセグメント内にある
            if start_time is None and target_start >= segment_start and target_start < segment_end:
                # セグメント内での相対位置から時間を推定
                relative_pos = (target_start - segment_start) / segment_len
                start_time = segment.start + (segment.end - segment.start) * relative_pos
                logger.info(f"  開始位置検出: セグメント{segment.id if hasattr(segment, 'id') else '?'} "
                           f"({segment.start:.2f}-{segment.end:.2f}秒), "
                           f"相対位置: {relative_pos:.2f}, 計算開始時間: {start_time:.2f}秒")

            # 終了位置がこのセグメント内にある
            if target_end > segment_start and target_end <= segment_end:
                # セグメント内での相対位置から時間を推定
                relative_pos = (target_end - segment_start) / segment_len
                end_time = segment.start + (segment.end - segment.start) * relative_pos
                logger.info(f"  終了位置検出: セグメント{segment.id if hasattr(segment, 'id') else '?'} "
                           f"({segment.start:.2f}-{segment.end:.2f}秒), "
                           f"相対位置: {relative_pos:.2f}, 計算終了時間: {end_time:.2f}秒")

                # 範囲が確定したら追加
                if start_time is not None:
                    ranges.append((start_time, end_time))
                    logger.info(f"  → 時間範囲確定: {start_time:.2f}秒 - {end_time:.2f}秒")
                break

            # 対象範囲がこのセグメント全体を含む場合
            if target_start <= segment_start and target_end >= segment_end:
                if start_time is None:
                    start_time = segment.start
                # 次のセグメントも確認するため継続

            current_pos += segment_len

        # 最後まで到達した場合
        if start_time is not None and end_time is None:
            # 最後のセグメントの終了時間を使用
            end_time = transcription_result.segments[-1].end
            ranges.append((start_time, end_time))

        return ranges

    def _merge_overlapping_ranges(self, ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
        """
        重複する時間範囲をマージ

        Args:
            ranges: 時間範囲のリスト

        Returns:
            マージ後の時間範囲
        """
        if not ranges:
            return []

        # 開始時間でソート
        sorted_ranges = sorted(ranges, key=lambda x: x[0])

        merged = [sorted_ranges[0]]

        for current in sorted_ranges[1:]:
            last = merged[-1]

            # 重複または隣接している場合はマージ
            if current[0] <= last[1]:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)

        return merged

    def calculate_with_word_timestamps(
        self, differences: TextDifference, transcription_result: TranscriptionResult
    ) -> list[tuple[float, float]]:
        """
        単語レベルのタイムスタンプを使った精密な計算

        Args:
            differences: テキスト差分情報
            transcription_result: 文字起こし結果

        Returns:
            時間範囲のタプルリスト
        """
        # 単語レベルのタイムスタンプがない場合は通常の計算
        if not transcription_result.has_word_level_timestamps:
            logger.info("単語レベルのタイムスタンプがないため、セグメントベースで計算")
            return self.calculate_time_ranges(differences, transcription_result)

        # TODO: 単語レベルの実装
        logger.warning("単語レベルのタイムスタンプ計算は未実装")
        return self.calculate_time_ranges(differences, transcription_result)
