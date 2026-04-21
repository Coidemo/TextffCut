"""Phase 3.6 フィラー音声切除のユニットテスト。"""

from __future__ import annotations

from unittest.mock import MagicMock

from use_cases.ai.filler_audio_removal import (
    apply_filler_removal,
    subtract_filler_ranges,
)


def _span(start: float, end: float, text: str = "あの") -> object:
    """FillerSpanのモック。"""
    s = MagicMock()
    s.time_start = start
    s.time_end = end
    s.filler_text = text
    return s


# ---------------------------------------------------------------------------
# subtract_filler_ranges: 数学的正しさ
# ---------------------------------------------------------------------------


class TestSubtractFillerRanges:
    def test_no_fillers_returns_unchanged(self):
        ranges = [(0.0, 10.0)]
        assert subtract_filler_ranges(ranges, []) == [(0.0, 10.0)]

    def test_filler_outside_range_no_op(self):
        ranges = [(5.0, 10.0)]
        fillers = [(0.0, 2.0), (12.0, 14.0)]
        assert subtract_filler_ranges(ranges, fillers) == [(5.0, 10.0)]

    def test_filler_in_middle_splits(self):
        ranges = [(0.0, 10.0)]
        fillers = [(4.0, 5.0)]
        assert subtract_filler_ranges(ranges, fillers) == [(0.0, 4.0), (5.0, 10.0)]

    def test_filler_at_start_shortens(self):
        ranges = [(0.0, 10.0)]
        fillers = [(0.0, 2.0)]
        assert subtract_filler_ranges(ranges, fillers) == [(2.0, 10.0)]

    def test_filler_at_end_shortens(self):
        ranges = [(0.0, 10.0)]
        fillers = [(8.0, 10.0)]
        assert subtract_filler_ranges(ranges, fillers) == [(0.0, 8.0)]

    def test_filler_covers_entire_range_removes(self):
        ranges = [(5.0, 8.0)]
        fillers = [(0.0, 10.0)]
        assert subtract_filler_ranges(ranges, fillers) == []

    def test_multiple_fillers_cumulative(self):
        ranges = [(0.0, 10.0)]
        fillers = [(2.0, 3.0), (6.0, 7.0)]
        result = subtract_filler_ranges(ranges, fillers)
        assert result == [(0.0, 2.0), (3.0, 6.0), (7.0, 10.0)]

    def test_short_filler_ignored(self):
        """デフォルトの 0.15s 閾値未満は切除しない。"""
        ranges = [(0.0, 10.0)]
        fillers = [(4.0, 4.1)]  # 0.1s
        assert subtract_filler_ranges(ranges, fillers) == [(0.0, 10.0)]

    def test_custom_min_duration(self):
        ranges = [(0.0, 10.0)]
        fillers = [(4.0, 4.2)]  # 0.2s
        # 0.3s 閾値なら無視、0.1s 閾値なら切除
        assert subtract_filler_ranges(ranges, fillers, min_filler_duration=0.3) == [(0.0, 10.0)]
        assert subtract_filler_ranges(ranges, fillers, min_filler_duration=0.1) == [
            (0.0, 4.0),
            (4.2, 10.0),
        ]

    def test_multiple_ranges_each_gets_subtracted(self):
        ranges = [(0.0, 5.0), (10.0, 15.0)]
        fillers = [(2.0, 3.0), (12.0, 13.0)]
        result = subtract_filler_ranges(ranges, fillers)
        assert result == [(0.0, 2.0), (3.0, 5.0), (10.0, 12.0), (13.0, 15.0)]

    def test_filler_spans_two_ranges_partial(self):
        """1つのfillerが複数のrange境界にまたがる。"""
        ranges = [(0.0, 5.0), (5.0, 10.0)]
        fillers = [(4.0, 6.0)]  # 2つのrangeにまたがる
        result = subtract_filler_ranges(ranges, fillers)
        assert result == [(0.0, 4.0), (6.0, 10.0)]


# ---------------------------------------------------------------------------
# apply_filler_removal: FillerMap からの高レベルAPI
# ---------------------------------------------------------------------------


class TestApplyFillerRemoval:
    def test_empty_map_returns_unchanged(self):
        ranges = [(0.0, 10.0)]
        new_ranges, count = apply_filler_removal(ranges, {})
        assert new_ranges == [(0.0, 10.0)]
        assert count == 0

    def test_filler_in_range_is_removed(self):
        ranges = [(0.0, 10.0)]
        filler_map = {0: [_span(3.0, 3.5)]}
        new_ranges, count = apply_filler_removal(ranges, filler_map)
        assert new_ranges == [(0.0, 3.0), (3.5, 10.0)]
        assert count == 1

    def test_filler_outside_range_ignored(self):
        """range外のfillerはカウントしない（collect内で弾かれる）。"""
        ranges = [(5.0, 10.0)]
        filler_map = {0: [_span(0.0, 1.0)]}  # range外
        new_ranges, count = apply_filler_removal(ranges, filler_map)
        assert new_ranges == [(5.0, 10.0)]
        assert count == 0

    def test_short_filler_not_counted(self):
        """閾値未満のfillerはカウントも切除もされない。"""
        ranges = [(0.0, 10.0)]
        filler_map = {0: [_span(3.0, 3.1)]}  # 0.1s
        new_ranges, count = apply_filler_removal(ranges, filler_map)
        assert new_ranges == [(0.0, 10.0)]
        assert count == 0

    def test_multiple_seg_fillers_all_applied(self):
        ranges = [(0.0, 20.0)]
        filler_map = {
            0: [_span(2.0, 2.5), _span(5.0, 5.5)],
            1: [_span(10.0, 10.5)],
        }
        new_ranges, count = apply_filler_removal(ranges, filler_map)
        assert new_ranges == [(0.0, 2.0), (2.5, 5.0), (5.5, 10.0), (10.5, 20.0)]
        assert count == 3


# ---------------------------------------------------------------------------
# エッジケース
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_ranges(self):
        assert subtract_filler_ranges([], [(1.0, 2.0)]) == []

    def test_zero_duration_filler(self):
        """長さ0のfillerは無視される（min_duration 閾値以下）。"""
        ranges = [(0.0, 10.0)]
        fillers = [(5.0, 5.0)]
        assert subtract_filler_ranges(ranges, fillers) == [(0.0, 10.0)]

    def test_identical_boundaries_not_treated_as_overlap(self):
        """fillerの終了=rangeの開始 ちょうどの場合は重ならない扱い。"""
        ranges = [(5.0, 10.0)]
        fillers = [(3.0, 5.0)]  # filler_end == range_start
        assert subtract_filler_ranges(ranges, fillers, min_filler_duration=0.1) == [(5.0, 10.0)]
