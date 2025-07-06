"""
TimeRangeクラスの単体テスト（実装に合わせて修正版）

すべてのメソッドとプロパティを網羅的にテストします。
"""

import pytest

from domain.value_objects.time_range import TimeRange


class TestTimeRange:
    """TimeRange値オブジェクトのテスト"""

    def test_init_with_valid_values(self):
        """有効な値で初期化できることを確認"""
        time_range = TimeRange(start=10.0, end=20.0)
        assert time_range.start == 10.0
        assert time_range.end == 20.0

    def test_init_with_start_greater_than_end_raises_error(self):
        """開始時間が終了時間より大きい場合エラーになることを確認"""
        with pytest.raises(ValueError, match="End time must be greater than or equal to start time"):
            TimeRange(start=20.0, end=10.0)

    def test_init_with_negative_start_raises_error(self):
        """開始時間が負の場合エラーになることを確認"""
        with pytest.raises(ValueError, match="Start time cannot be negative"):
            TimeRange(start=-1.0, end=10.0)

    def test_init_with_equal_start_and_end(self):
        """開始時間と終了時間が同じ場合も有効であることを確認"""
        time_range = TimeRange(start=10.0, end=10.0)
        assert time_range.start == 10.0
        assert time_range.end == 10.0
        assert time_range.is_empty

    def test_duration_property(self):
        """durationプロパティが正しく計算されることを確認"""
        time_range = TimeRange(start=10.0, end=25.5)
        assert time_range.duration == 15.5

    def test_is_empty_property(self):
        """is_emptyプロパティが正しく判定されることを確認"""
        assert TimeRange(start=10.0, end=10.0).is_empty is True
        assert TimeRange(start=10.0, end=10.001).is_empty is False

    def test_contains_time(self):
        """contains(time)メソッドが正しく判定することを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 範囲内
        assert time_range.contains(15.0) is True
        # 境界値
        assert time_range.contains(10.0) is True
        assert time_range.contains(20.0) is True
        # 範囲外
        assert time_range.contains(5.0) is False
        assert time_range.contains(25.0) is False

    def test_overlaps(self):
        """overlapsメソッドが正しく判定することを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 重なる
        assert time_range.overlaps(TimeRange(start=5.0, end=15.0)) is True
        assert time_range.overlaps(TimeRange(start=15.0, end=25.0)) is True
        assert time_range.overlaps(TimeRange(start=5.0, end=25.0)) is True
        # 境界で接触（実装は < と > なので重ならない）
        assert time_range.overlaps(TimeRange(start=20.0, end=30.0)) is False
        assert time_range.overlaps(TimeRange(start=0.0, end=10.0)) is False
        # 重ならない
        assert time_range.overlaps(TimeRange(start=25.0, end=30.0)) is False
        assert time_range.overlaps(TimeRange(start=0.0, end=5.0)) is False

    def test_intersection(self):
        """intersectionメソッドが正しく交差範囲を返すことを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 部分的な重なり
        result = time_range.intersection(TimeRange(start=5.0, end=15.0))
        assert result is not None
        assert result.start == 10.0
        assert result.end == 15.0

        # 完全に含む
        result = time_range.intersection(TimeRange(start=12.0, end=18.0))
        assert result is not None
        assert result.start == 12.0
        assert result.end == 18.0

        # 重ならない
        result = time_range.intersection(TimeRange(start=25.0, end=30.0))
        assert result is None

    def test_union(self):
        """unionメソッドが正しく結合範囲を返すことを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 重なる範囲
        result = time_range.union(TimeRange(start=15.0, end=25.0))
        assert result is not None
        assert result.start == 10.0
        assert result.end == 25.0

        # 隣接する範囲（gap_tolerance以内）
        result = time_range.union(TimeRange(start=20.0, end=30.0))
        assert result is not None
        assert result.start == 10.0
        assert result.end == 30.0

        # 離れた範囲（gap_tolerance以上）
        result = time_range.union(TimeRange(start=30.0, end=40.0))
        assert result is None

    def test_is_adjacent(self):
        """is_adjacentメソッドが正しく隣接を判定することを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 隣接する（終了と開始が一致）
        assert time_range.is_adjacent(TimeRange(start=20.0, end=30.0)) is True
        assert time_range.is_adjacent(TimeRange(start=0.0, end=10.0)) is True

        # 隣接しない
        assert time_range.is_adjacent(TimeRange(start=21.0, end=30.0)) is False
        assert time_range.is_adjacent(TimeRange(start=0.0, end=9.0)) is False
        assert time_range.is_adjacent(TimeRange(start=15.0, end=25.0)) is False

    def test_split_at(self):
        """split_atメソッドが正しく分割することを確認"""
        time_range = TimeRange(start=10.0, end=30.0)

        # 中間で分割
        left, right = time_range.split_at(20.0)
        assert left is not None
        assert left.start == 10.0
        assert left.end == 20.0
        assert right is not None
        assert right.start == 20.0
        assert right.end == 30.0

        # 境界で分割
        left, right = time_range.split_at(10.0)
        assert left is None  # 開始点で分割すると左はNone
        assert right is not None
        assert right.start == 10.0
        assert right.end == 30.0

        left, right = time_range.split_at(30.0)
        assert left is not None
        assert left.start == 10.0
        assert left.end == 30.0
        assert right is None  # 終了点で分割すると右はNone

    def test_split_at_invalid_point_returns_tuple(self):
        """無効な分割点ではタプルを返すことを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 範囲外の点で分割（エラーではなくタプルを返す）
        left, right = time_range.split_at(5.0)
        assert left is None
        assert right == time_range  # 元の範囲が返される

        left, right = time_range.split_at(25.0)
        assert left == time_range  # 元の範囲が返される
        assert right is None

    def test_with_padding(self):
        """with_paddingメソッドが正しくパディングを追加することを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 両側にパディング（引数は start_padding, end_padding の2つ）
        padded = time_range.with_padding(2.0, 3.0)
        assert padded.start == 8.0
        assert padded.end == 23.0

        # 開始時間が0未満にならないことを確認
        time_range2 = TimeRange(start=1.0, end=5.0)
        padded2 = time_range2.with_padding(2.0, 2.0)
        assert padded2.start == 0.0  # 負にならない
        assert padded2.end == 7.0

        # 異なるパディング
        padded3 = time_range.with_padding(1.0, 5.0)
        assert padded3.start == 9.0
        assert padded3.end == 25.0

    def test_with_padding_negative_values(self):
        """負のパディングでも動作することを確認"""
        time_range = TimeRange(start=10.0, end=20.0)

        # 負のパディングで縮小
        padded = time_range.with_padding(-2.0, -3.0)
        assert padded.start == 12.0
        assert padded.end == 17.0

        # 大きすぎる負のパディングでも動作する（endがstartより小さくなる可能性）
        try:
            padded2 = time_range.with_padding(-15.0, -15.0)
            # endがstartより小さくなるのでエラーになるはず
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "End time must be greater than or equal to start time" in str(e)

    def test_to_tuple(self):
        """to_tupleメソッドが正しくタプルを返すことを確認"""
        time_range = TimeRange(start=10.5, end=20.5)
        result = time_range.to_tuple()
        assert result == (10.5, 20.5)
        assert isinstance(result, tuple)

    def test_from_tuple(self):
        """from_tupleクラスメソッドが正しくインスタンスを作成することを確認"""
        time_range = TimeRange.from_tuple((10.5, 20.5))
        assert time_range.start == 10.5
        assert time_range.end == 20.5

    def test_from_tuple_edge_cases(self):
        """タプル変換のエッジケースを確認"""
        # 1要素のタプルはIndexError
        with pytest.raises(IndexError):
            TimeRange.from_tuple((10.0,))

        # 3つの要素があっても最初の2つが使われる
        time_range = TimeRange.from_tuple((10.0, 20.0, 30.0))
        assert time_range.start == 10.0
        assert time_range.end == 20.0

        # リストでも動作する（インデックスアクセスができればOK）
        time_range2 = TimeRange.from_tuple([10.0, 20.0])
        assert time_range2.start == 10.0
        assert time_range2.end == 20.0

    def test_merge_ranges(self):
        """merge_rangesクラスメソッドが正しく範囲をマージすることを確認"""
        ranges = [
            TimeRange(start=0.0, end=10.0),
            TimeRange(start=5.0, end=15.0),  # 重なる
            TimeRange(start=20.0, end=30.0),  # 離れている
            TimeRange(start=15.0, end=20.0),  # 隣接
        ]

        merged = TimeRange.merge_ranges(ranges)

        assert len(merged) == 1
        assert merged[0].start == 0.0
        assert merged[0].end == 30.0

    def test_merge_ranges_with_gaps(self):
        """ギャップのある範囲のマージを確認"""
        ranges = [
            TimeRange(start=0.0, end=10.0),
            TimeRange(start=20.0, end=30.0),
            TimeRange(start=40.0, end=50.0),
        ]

        # gap_threshold=5.0の場合、ギャップが10あるのでマージされない
        merged = TimeRange.merge_ranges(ranges, gap_threshold=5.0)
        assert len(merged) == 3

        # gap_threshold=15.0の場合、全てマージされる
        # gap=10 < threshold=15 なので全てが結合される
        merged2 = TimeRange.merge_ranges(ranges, gap_threshold=15.0)
        assert len(merged2) == 1
        assert merged2[0].start == 0.0
        assert merged2[0].end == 50.0

    def test_merge_ranges_empty_list(self):
        """空のリストのマージを確認"""
        merged = TimeRange.merge_ranges([])
        assert merged == []

    def test_comparison_operators(self):
        """比較演算子の動作を確認"""
        # TimeRangeクラスに比較演算子（< > <= >=）は実装されていない
        # dataclassのデフォルトで==は動作する
        t1 = TimeRange(start=10.0, end=20.0)
        t2 = TimeRange(start=10.0, end=20.0)
        t3 = TimeRange(start=10.0, end=30.0)

        # 等価性のみテスト
        assert t1 == t2
        assert not t1 == t3

    def test_repr(self):
        """__repr__メソッドが正しい文字列を返すことを確認"""
        time_range = TimeRange(start=10.5, end=20.5)
        assert repr(time_range) == "TimeRange(start=10.5, end=20.5)"

    def test_str(self):
        """__str__メソッドが正しい文字列を返すことを確認"""
        time_range = TimeRange(start=10.5, end=20.5)
        # 実装は "10.50s - 20.50s" 形式
        assert str(time_range) == "10.50s - 20.50s"

    def test_immutability(self):
        """TimeRangeオブジェクトが不変であることを確認"""
        time_range = TimeRange(start=10.0, end=20.0)
        with pytest.raises(AttributeError):
            time_range.start = 15.0
        with pytest.raises(AttributeError):
            time_range.end = 25.0

    def test_hash(self):
        """ハッシュ可能であることを確認"""
        t1 = TimeRange(start=10.0, end=20.0)
        t2 = TimeRange(start=10.0, end=20.0)
        t3 = TimeRange(start=10.0, end=30.0)

        # 同じ値なら同じハッシュ
        assert hash(t1) == hash(t2)
        # 異なる値なら（通常は）異なるハッシュ
        assert hash(t1) != hash(t3)

        # セットに追加できることを確認
        time_set = {t1, t2, t3}
        assert len(time_set) == 2  # t1とt2は同じなので1つになる
