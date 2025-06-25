"""
無音削除による時間マッピングを管理

無音削除により動画の時間が詰まるため、元動画の時間を
無音削除後の時間にマッピングする機能を提供。
"""

from dataclasses import dataclass

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimeMapping:
    """時間マッピング情報"""

    original_start: float
    original_end: float
    mapped_start: float
    mapped_end: float


class TimeMapper:
    """無音削除による時間マッピングを管理"""

    def __init__(self, original_ranges: list[tuple[float, float]], kept_ranges: list[tuple[float, float]]):
        """
        Args:
            original_ranges: 元の時間範囲（差分検出結果）
            kept_ranges: 無音削除後の時間範囲
        """
        self.mappings: list[TimeMapping] = []
        self._build_mapping(original_ranges, kept_ranges)

    def _build_mapping(self, original_ranges: list[tuple[float, float]], kept_ranges: list[tuple[float, float]]):
        """マッピングテーブルを構築"""
        current_time = 0.0

        # original_rangesとkept_rangesの対応を確認
        if len(original_ranges) != len(kept_ranges):
            logger.info(f"Range count mismatch: original={len(original_ranges)}, kept={len(kept_ranges)}")
            logger.info("無音削除により範囲が分割されました")

        # kept_rangesを基準にマッピングを構築
        for i, kept_range in enumerate(kept_ranges):
            # 各範囲の長さ
            kept_duration = kept_range[1] - kept_range[0]

            # マッピング情報を作成
            mapping = TimeMapping(
                original_start=kept_range[0],  # 元動画での開始時間
                original_end=kept_range[1],  # 元動画での終了時間
                mapped_start=current_time,  # 無音削除後の開始時間
                mapped_end=current_time + kept_duration,  # 無音削除後の終了時間
            )
            self.mappings.append(mapping)

            logger.debug(
                f"Mapping {i}: [{kept_range[0]:.2f}-{kept_range[1]:.2f}] -> "
                f"[{current_time:.2f}-{current_time + kept_duration:.2f}]"
            )

            current_time += kept_duration

    def map_time(self, original_time: float) -> float | None:
        """元動画の時間を無音削除後の時間に変換"""
        for mapping in self.mappings:
            if mapping.original_start <= original_time <= mapping.original_end:
                # 範囲内の相対位置を計算
                original_duration = mapping.original_end - mapping.original_start
                if original_duration > 0:
                    relative_pos = (original_time - mapping.original_start) / original_duration
                else:
                    relative_pos = 0.0

                # マッピング後の時間を計算
                mapped_duration = mapping.mapped_end - mapping.mapped_start
                mapped_time = mapping.mapped_start + relative_pos * mapped_duration

                logger.debug(f"Mapped time: {original_time:.2f} -> {mapped_time:.2f}")
                return mapped_time

        # 範囲外の場合はNone
        logger.debug(f"Time {original_time:.2f} is out of range")
        return None

    def map_range(self, start: float, end: float) -> tuple[float, float] | None:
        """時間範囲をマッピング"""
        mapped_start = self.map_time(start)
        mapped_end = self.map_time(end)

        if mapped_start is not None and mapped_end is not None:
            logger.debug(f"Mapped range: [{start:.2f}-{end:.2f}] -> [{mapped_start:.2f}-{mapped_end:.2f}]")
            return (mapped_start, mapped_end)

        logger.warning(f"Failed to map range: [{start:.2f}-{end:.2f}]")
        return None

    def map_range_to_segments(self, start: float, end: float) -> list[tuple[float, float]]:
        """時間範囲を複数のセグメントにマッピング（無音削除で分割される場合）

        Args:
            start: 元動画の開始時間
            end: 元動画の終了時間

        Returns:
            マッピング後の時間範囲のリスト（分割される場合は複数）
        """
        segments = []

        for mapping in self.mappings:
            # この範囲と重なる部分があるか確認
            if mapping.original_end <= start or mapping.original_start >= end:
                continue  # 重ならない

            # 重なる部分の計算
            overlap_start = max(start, mapping.original_start)
            overlap_end = min(end, mapping.original_end)

            # 重なる部分をマッピング
            if overlap_start < overlap_end:
                # 元の範囲内での相対位置
                start_ratio = (overlap_start - mapping.original_start) / (mapping.original_end - mapping.original_start)
                end_ratio = (overlap_end - mapping.original_start) / (mapping.original_end - mapping.original_start)

                # マッピング後の位置
                mapped_duration = mapping.mapped_end - mapping.mapped_start
                mapped_start = mapping.mapped_start + start_ratio * mapped_duration
                mapped_end = mapping.mapped_start + end_ratio * mapped_duration

                segments.append((mapped_start, mapped_end))
                logger.debug(
                    f"Segment: [{overlap_start:.2f}-{overlap_end:.2f}] -> [{mapped_start:.2f}-{mapped_end:.2f}]"
                )

        if segments:
            logger.info(f"Range [{start:.2f}-{end:.2f}] mapped to {len(segments)} segments")
        else:
            logger.warning(f"No segments found for range [{start:.2f}-{end:.2f}]")

        return segments

    def get_total_mapped_duration(self) -> float:
        """マッピング後の総時間を取得"""
        if not self.mappings:
            return 0.0

        last_mapping = self.mappings[-1]
        return last_mapping.mapped_end
