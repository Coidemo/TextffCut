"""
TimeRangeCalculatorLCSの単体テスト
"""

import pytest
from domain.use_cases.time_range_calculator_lcs import TimeRangeCalculatorLCS, TimeRangeWithText
from domain.entities.text_difference import DifferenceType
from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.value_objects.lcs_match import DifferenceBlock


class TestTimeRangeCalculatorLCS:
    """TimeRangeCalculatorLCSのテスト"""

    @pytest.fixture
    def calculator(self):
        return TimeRangeCalculatorLCS()

    @pytest.fixture
    def sample_blocks(self):
        """サンプルの差分ブロック"""
        chars1 = [
            CharacterWithTimestamp("こ", 0.0, 0.2, "seg1", 0, 0),
            CharacterWithTimestamp("ん", 0.2, 0.4, "seg1", 1, 1),
            CharacterWithTimestamp("に", 0.4, 0.6, "seg1", 2, 2),
        ]

        chars2 = [
            CharacterWithTimestamp("ち", 0.6, 0.8, "seg1", 3, 3),
            CharacterWithTimestamp("は", 0.8, 1.0, "seg1", 4, 4),
        ]

        blocks = [
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="こんに",
                start_time=0.0,
                end_time=0.6,
                char_positions=chars1,
                original_start_pos=0,
                original_end_pos=2,
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="削除",
                start_time=0.6,
                end_time=0.8,
                char_positions=[],
                original_start_pos=3,
                original_end_pos=3,
            ),
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="ちは",
                start_time=0.8,
                end_time=1.2,
                char_positions=chars2,
                original_start_pos=4,
                original_end_pos=5,
            ),
            DifferenceBlock(
                type=DifferenceType.ADDED,
                text="追加",
                start_time=None,
                end_time=None,
                char_positions=[],
                original_start_pos=None,
                original_end_pos=None,
            ),
        ]

        return blocks

    def test_calculate_from_blocks_basic(self, calculator, sample_blocks):
        """基本的な時間範囲計算"""
        ranges = calculator.calculate_from_blocks(sample_blocks)

        # UNCHANGEDブロックのみが時間範囲になる
        assert len(ranges) == 2

        assert ranges[0].start == 0.0
        assert ranges[0].end == 0.6
        assert ranges[0].text == "こんに"

        assert ranges[1].start == 0.8
        assert ranges[1].end == 1.2
        assert ranges[1].text == "ちは"

    def test_calculate_from_blocks_include_deleted(self, calculator, sample_blocks):
        """削除部分を含む時間範囲計算"""
        ranges = calculator.calculate_from_blocks(sample_blocks, include_deleted=True)

        # UNCHANGEDとDELETEDブロックが含まれる
        assert len(ranges) == 3

        # 削除部分のテキストには[削除]プレフィックスが付く
        deleted_range = [r for r in ranges if "[削除]" in r.text][0]
        assert deleted_range.start == 0.6
        assert deleted_range.end == 0.8
        assert "[削除] 削除" in deleted_range.text

    def test_calculate_from_blocks_empty(self, calculator):
        """空のブロックリスト"""
        ranges = calculator.calculate_from_blocks([])
        assert ranges == []

    def test_merge_adjacent_ranges_basic(self, calculator):
        """基本的な隣接範囲のマージ"""
        ranges = [
            TimeRangeWithText(start=0.0, end=1.0, text="最初"),
            TimeRangeWithText(start=1.05, end=2.0, text="次"),  # 0.05秒のギャップ
            TimeRangeWithText(start=2.5, end=3.0, text="最後"),  # 0.5秒のギャップ
        ]

        merged = calculator.merge_adjacent_ranges(ranges, gap_threshold=0.1)

        # 最初の2つはマージされ、最後は別
        assert len(merged) == 2

        assert merged[0].start == 0.0
        assert merged[0].end == 2.0
        assert "最初 次" in merged[0].text

        assert merged[1].start == 2.5
        assert merged[1].end == 3.0
        assert merged[1].text == "最後"

    def test_merge_adjacent_ranges_no_merge(self, calculator):
        """マージなしの場合"""
        ranges = [
            TimeRangeWithText(start=0.0, end=1.0, text="A"),
            TimeRangeWithText(start=2.0, end=3.0, text="B"),  # 1秒のギャップ
            TimeRangeWithText(start=4.0, end=5.0, text="C"),  # 1秒のギャップ
        ]

        merged = calculator.merge_adjacent_ranges(ranges, gap_threshold=0.1)

        # マージされない
        assert len(merged) == 3
        assert all(m.text in ["A", "B", "C"] for m in merged)

    def test_merge_adjacent_ranges_all_merge(self, calculator):
        """全てマージされる場合"""
        ranges = [
            TimeRangeWithText(start=0.0, end=1.0, text="A"),
            TimeRangeWithText(start=1.0, end=2.0, text="B"),  # 0秒のギャップ（連続）
            TimeRangeWithText(start=2.0, end=3.0, text="C"),  # 0秒のギャップ（連続）
        ]

        merged = calculator.merge_adjacent_ranges(ranges, gap_threshold=0.1)

        # 全てマージされる
        assert len(merged) == 1
        assert merged[0].start == 0.0
        assert merged[0].end == 3.0
        assert "A B C" in merged[0].text

    def test_merge_adjacent_ranges_empty(self, calculator):
        """空の範囲リスト"""
        merged = calculator.merge_adjacent_ranges([])
        assert merged == []

    def test_calculate_total_duration(self, calculator):
        """合計時間の計算"""
        ranges = [
            TimeRangeWithText(start=0.0, end=1.5, text="A"),
            TimeRangeWithText(start=2.0, end=4.0, text="B"),
            TimeRangeWithText(start=5.0, end=5.5, text="C"),
        ]

        total = calculator.calculate_total_duration(ranges)

        # 1.5 + 2.0 + 0.5 = 4.0
        assert total == pytest.approx(4.0)

    def test_find_gaps_basic(self, calculator):
        """基本的なギャップ検出"""
        ranges = [
            TimeRangeWithText(start=1.0, end=2.0, text="A"),
            TimeRangeWithText(start=3.0, end=4.0, text="B"),
        ]

        gaps = calculator.find_gaps(ranges, total_duration=5.0)

        # 3つのギャップ：開始前、中間、終了後
        assert len(gaps) == 3

        assert gaps[0] == (0.0, 1.0)  # 開始前
        assert gaps[1] == (2.0, 3.0)  # 中間
        assert gaps[2] == (4.0, 5.0)  # 終了後

    def test_find_gaps_no_ranges(self, calculator):
        """範囲がない場合のギャップ"""
        gaps = calculator.find_gaps([], total_duration=10.0)

        # 全体が1つのギャップ
        assert len(gaps) == 1
        assert gaps[0] == (0.0, 10.0)

    def test_find_gaps_no_gaps(self, calculator):
        """ギャップがない場合"""
        ranges = [
            TimeRangeWithText(start=0.0, end=5.0, text="A"),
            TimeRangeWithText(start=5.0, end=10.0, text="B"),
        ]

        gaps = calculator.find_gaps(ranges, total_duration=10.0)

        # ギャップなし
        assert len(gaps) == 0

    def test_validate_ranges_valid(self, calculator):
        """妥当な範囲の検証"""
        ranges = [
            TimeRangeWithText(start=0.0, end=1.0, text="A"),
            TimeRangeWithText(start=2.0, end=3.0, text="B"),
        ]

        is_valid, errors = calculator.validate_ranges(ranges, total_duration=5.0)

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_ranges_negative_start(self, calculator):
        """負の開始時間"""
        ranges = [
            TimeRangeWithText(start=-1.0, end=1.0, text="A"),
        ]

        is_valid, errors = calculator.validate_ranges(ranges)

        assert is_valid is False
        assert len(errors) == 1
        assert "負の値" in errors[0]

    def test_validate_ranges_invalid_order(self, calculator):
        """開始時間と終了時間の順序エラー"""
        ranges = [
            TimeRangeWithText(start=2.0, end=1.0, text="A"),
        ]

        is_valid, errors = calculator.validate_ranges(ranges)

        assert is_valid is False
        assert len(errors) == 1
        assert "開始時間以前" in errors[0]

    def test_validate_ranges_exceeds_duration(self, calculator):
        """動画時間を超える範囲"""
        ranges = [
            TimeRangeWithText(start=0.0, end=15.0, text="A"),
        ]

        is_valid, errors = calculator.validate_ranges(ranges, total_duration=10.0)

        assert is_valid is False
        assert len(errors) == 1
        assert "動画の長さを超えています" in errors[0]

    def test_validate_ranges_overlap(self, calculator):
        """範囲の重複"""
        ranges = [
            TimeRangeWithText(start=0.0, end=2.0, text="A"),
            TimeRangeWithText(start=1.0, end=3.0, text="B"),  # 重複
        ]

        is_valid, errors = calculator.validate_ranges(ranges)

        assert is_valid is False
        assert len(errors) == 1
        assert "重複" in errors[0]

    def test_validate_ranges_empty(self, calculator):
        """空の範囲リストは妥当"""
        is_valid, errors = calculator.validate_ranges([])

        assert is_valid is True
        assert len(errors) == 0
