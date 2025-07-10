"""
LCSベースの時間範囲計算ユースケース

差分ブロックから時間範囲を計算し、隣接する範囲をマージする。
"""

from typing import List, Optional, Tuple
from dataclasses import dataclass
from domain.value_objects.time_range import TimeRange
from domain.entities.text_difference import DifferenceType
from domain.value_objects.lcs_match import DifferenceBlock
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimeRangeWithText:
    """テキスト付き時間範囲"""

    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        """継続時間"""
        return self.end - self.start


class TimeRangeCalculatorLCS:
    """
    LCSベースの時間範囲計算ユースケース

    差分ブロックから切り抜き用の時間範囲を計算する。
    """

    def calculate_from_blocks(
        self, blocks: List[DifferenceBlock], include_deleted: bool = False
    ) -> List[TimeRangeWithText]:
        """
        差分ブロックから時間範囲を計算

        Args:
            blocks: 差分ブロックのリスト
            include_deleted: 削除部分も含めるか（デバッグ用）

        Returns:
            時間範囲のリスト
        """
        time_ranges = []

        for block in blocks:
            # UNCHANGEDブロックから時間範囲を作成
            if block.type == DifferenceType.UNCHANGED:
                if block.start_time is not None and block.end_time is not None:
                    time_range = TimeRangeWithText(start=block.start_time, end=block.end_time, text=block.text)
                    time_ranges.append(time_range)

            # デバッグ用：削除部分も表示
            elif include_deleted and block.type == DifferenceType.DELETED:
                if block.start_time is not None and block.end_time is not None:
                    time_range = TimeRangeWithText(
                        start=block.start_time, end=block.end_time, text=f"[削除] {block.text}"
                    )
                    time_ranges.append(time_range)

        logger.info(f"差分ブロックから{len(time_ranges)}個の時間範囲を作成しました")
        return time_ranges

    def merge_adjacent_ranges(
        self, ranges: List[TimeRangeWithText], gap_threshold: float = 0.1
    ) -> List[TimeRangeWithText]:
        """
        近接した範囲をマージ

        Args:
            ranges: 時間範囲のリスト
            gap_threshold: マージする最大ギャップ（秒）

        Returns:
            マージされた時間範囲のリスト
        """
        if not ranges:
            return []

        # 開始時間でソート
        sorted_ranges = sorted(ranges, key=lambda r: r.start)

        merged = []
        current = sorted_ranges[0]

        for next_range in sorted_ranges[1:]:
            # 隣接判定
            gap = next_range.start - current.end

            if 0 <= gap <= gap_threshold:
                # マージ
                merged_text = current.text
                if not merged_text.endswith(next_range.text):
                    merged_text = f"{current.text} {next_range.text}"

                current = TimeRangeWithText(start=current.start, end=next_range.end, text=merged_text)
            else:
                # マージしない
                merged.append(current)
                current = next_range

        # 最後の範囲を追加
        merged.append(current)

        logger.info(f"時間範囲をマージ: {len(ranges)}個 → {len(merged)}個")
        return merged

    def calculate_total_duration(self, ranges: List[TimeRangeWithText]) -> float:
        """
        時間範囲の合計時間を計算

        Args:
            ranges: 時間範囲のリスト

        Returns:
            合計時間（秒）
        """
        total = sum(r.duration for r in ranges)
        logger.info(f"合計時間: {total:.2f}秒")
        return total

    def find_gaps(self, ranges: List[TimeRangeWithText], total_duration: float) -> List[Tuple[float, float]]:
        """
        時間範囲のギャップを特定

        Args:
            ranges: 時間範囲のリスト（ソート済み）
            total_duration: 動画の総時間

        Returns:
            ギャップの時間範囲のリスト
        """
        if not ranges:
            return [(0.0, total_duration)] if total_duration > 0 else []

        gaps = []
        sorted_ranges = sorted(ranges, key=lambda r: r.start)

        # 最初のギャップ
        if sorted_ranges[0].start > 0:
            gaps.append((0.0, sorted_ranges[0].start))

        # 中間のギャップ
        for i in range(len(sorted_ranges) - 1):
            gap_start = sorted_ranges[i].end
            gap_end = sorted_ranges[i + 1].start

            if gap_end > gap_start:
                gaps.append((gap_start, gap_end))

        # 最後のギャップ
        if sorted_ranges[-1].end < total_duration:
            gaps.append((sorted_ranges[-1].end, total_duration))

        logger.info(f"ギャップを検出: {len(gaps)}個")
        return gaps

    def validate_ranges(
        self, ranges: List[TimeRangeWithText], total_duration: Optional[float] = None
    ) -> Tuple[bool, List[str]]:
        """
        時間範囲の妥当性を検証

        Args:
            ranges: 時間範囲のリスト
            total_duration: 動画の総時間（指定時は範囲チェック）

        Returns:
            (妥当性, エラーメッセージのリスト)
        """
        errors = []

        if not ranges:
            return True, []

        # 各範囲の検証
        for i, range_item in enumerate(ranges):
            if range_item.start < 0:
                errors.append(f"範囲{i+1}: 開始時間が負の値です ({range_item.start})")

            if range_item.end <= range_item.start:
                errors.append(f"範囲{i+1}: 終了時間が開始時間以前です " f"({range_item.start} → {range_item.end})")

            if total_duration is not None and range_item.end > total_duration:
                errors.append(
                    f"範囲{i+1}: 終了時間が動画の長さを超えています " f"({range_item.end} > {total_duration})"
                )

        # 重複チェック
        sorted_ranges = sorted(ranges, key=lambda r: r.start)
        for i in range(len(sorted_ranges) - 1):
            if sorted_ranges[i].end > sorted_ranges[i + 1].start:
                errors.append(f"範囲{i+1}と{i+2}が重複しています")

        is_valid = len(errors) == 0
        if not is_valid:
            logger.warning(f"時間範囲の検証エラー: {len(errors)}件")

        return is_valid, errors
