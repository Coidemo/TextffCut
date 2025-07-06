"""
VideoSegmentクラスの単体テスト

すべてのメソッドとプロパティを網羅的にテストします。
"""

import pytest

from domain.entities.video_segment import VideoSegment


class TestVideoSegment:
    """VideoSegmentエンティティのテスト"""

    def test_init_with_valid_values(self):
        """有効な値で初期化できることを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0, is_silence=False, metadata={"source": "test"})
        assert segment.id == "seg1"
        assert segment.start == 10.0
        assert segment.end == 20.0
        assert segment.is_silence is False
        assert segment.metadata == {"source": "test"}

    def test_init_with_invalid_time_range_raises_error(self):
        """無効な時間範囲でエラーになることを確認"""
        with pytest.raises(ValueError, match="End time must be greater than start time"):
            VideoSegment(
                id="seg1",
                start=20.0,
                end=10.0,  # 開始時間より前
            )

    def test_init_with_negative_start_raises_error(self):
        """負の開始時間でエラーになることを確認"""
        with pytest.raises(ValueError, match="Start time cannot be negative"):
            VideoSegment(
                id="seg1",
                start=-1.0,
                end=10.0,
            )

    def test_duration_property(self):
        """durationプロパティが正しく計算されることを確認"""
        segment = VideoSegment(
            id="seg1",
            start=10.0,
            end=25.5,
        )
        assert segment.duration == 15.5

    def test_time_range_property(self):
        """time_rangeプロパティが正しいタプルを返すことを確認"""
        segment = VideoSegment(
            id="seg1",
            start=10.0,
            end=20.0,
        )
        time_range = segment.time_range
        assert isinstance(time_range, tuple)
        assert time_range == (10.0, 20.0)

    def test_overlaps_with_segment(self):
        """overlaps_withメソッドが他のセグメントとの重なりを正しく判定することを確認"""
        segment1 = VideoSegment(id="seg1", start=10.0, end=20.0)
        segment2 = VideoSegment(id="seg2", start=15.0, end=25.0)
        segment3 = VideoSegment(id="seg3", start=25.0, end=30.0)

        # 重なる
        assert segment1.overlaps_with(segment2) is True
        assert segment2.overlaps_with(segment1) is True

        # 重ならない
        assert segment1.overlaps_with(segment3) is False
        assert segment3.overlaps_with(segment1) is False

    def test_contains_time(self):
        """containsメソッドが時刻を正しく判定することを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)

        # 範囲内
        assert segment.contains(15.0) is True
        # 境界値
        assert segment.contains(10.0) is True
        assert segment.contains(20.0) is True
        # 範囲外
        assert segment.contains(5.0) is False
        assert segment.contains(25.0) is False

    def test_merge_with_adjacent_segments(self):
        """merge_withメソッドが隣接するセグメントを正しくマージすることを確認"""
        segment1 = VideoSegment(id="seg1", start=10.0, end=20.0, is_silence=False)
        segment2 = VideoSegment(id="seg2", start=20.0, end=30.0, is_silence=False)

        merged = segment1.merge_with(segment2)
        assert merged.start == 10.0
        assert merged.end == 30.0
        assert merged.is_silence is False

    def test_merge_with_overlapping_segments(self):
        """merge_withメソッドが重なるセグメントを正しくマージすることを確認"""
        segment1 = VideoSegment(id="seg1", start=10.0, end=20.0, is_silence=True)
        segment2 = VideoSegment(id="seg2", start=15.0, end=25.0, is_silence=True)

        merged = segment1.merge_with(segment2)
        assert merged.start == 10.0
        assert merged.end == 25.0
        assert merged.is_silence is True  # 両方がTrueの場合のみTrue

    def test_merge_with_non_adjacent_segments_raises_error(self):
        """merge_withメソッドが離れたセグメントでエラーになることを確認"""
        segment1 = VideoSegment(id="seg1", start=10.0, end=20.0)
        segment2 = VideoSegment(id="seg2", start=30.0, end=40.0)

        with pytest.raises(ValueError, match="Segments must be adjacent or overlapping to merge"):
            segment1.merge_with(segment2)

    def test_split_at(self):
        """split_atメソッドが正しくセグメントを分割することを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=30.0, is_silence=True)

        first, second = segment.split_at(20.0)

        assert first.start == 10.0
        assert first.end == 20.0
        assert first.is_silence is True

        assert second.start == 20.0
        assert second.end == 30.0
        assert second.is_silence is True

    def test_split_at_boundary(self):
        """split_atメソッドが境界値でエラーになることを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)

        with pytest.raises(ValueError, match="Cannot split at segment boundaries"):
            segment.split_at(10.0)

        with pytest.raises(ValueError, match="Cannot split at segment boundaries"):
            segment.split_at(20.0)

    def test_split_at_invalid_point_raises_error(self):
        """split_atメソッドが無効な分割点でエラーになることを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)

        with pytest.raises(ValueError, match="Split time .* is outside segment range"):
            segment.split_at(5.0)

        with pytest.raises(ValueError, match="Split time .* is outside segment range"):
            segment.split_at(25.0)

    def test_with_padding(self):
        """with_paddingメソッドが正しくパディングを追加することを確認"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)

        padded = segment.with_padding(2.0, 3.0)
        assert padded.start == 8.0
        assert padded.end == 23.0
        assert padded.metadata["original_start"] == 10.0
        assert padded.metadata["original_end"] == 20.0
        assert padded.metadata["start_padding"] == 2.0
        assert padded.metadata["end_padding"] == 3.0

    def test_with_padding_clamps_to_zero(self):
        """with_paddingメソッドが開始時間を0未満にしないことを確認"""
        segment = VideoSegment(id="seg1", start=1.0, end=5.0)

        padded = segment.with_padding(5.0, 2.0)
        assert padded.start == 0.0  # 負にならない
        assert padded.end == 7.0

    def test_from_time_range(self):
        """from_time_rangeクラスメソッドが正しく動作することを確認"""
        segment = VideoSegment.from_time_range((10.0, 20.0), is_silence=True)

        assert segment.start == 10.0
        assert segment.end == 20.0
        assert segment.is_silence is True
        assert segment.id is not None  # UUIDが生成される

    def test_from_time_range_with_defaults(self):
        """from_time_rangeクラスメソッドのデフォルト値を確認"""
        segment = VideoSegment.from_time_range((10.0, 20.0))

        assert segment.start == 10.0
        assert segment.end == 20.0
        assert segment.is_silence is False  # デフォルト

    def test_merge_segments(self):
        """merge_segmentsクラスメソッドが正しくセグメントをマージすることを確認"""
        segments = [
            VideoSegment(id="seg1", start=0.0, end=10.0),
            VideoSegment(id="seg2", start=5.0, end=15.0),  # 重なる
            VideoSegment(id="seg3", start=20.0, end=30.0),  # 離れている
            VideoSegment(id="seg4", start=29.9, end=40.0),  # ほぼ隣接
        ]

        merged = VideoSegment.merge_segments(segments, gap_threshold=0.1)

        assert len(merged) == 2
        assert merged[0].start == 0.0
        assert merged[0].end == 15.0
        assert merged[1].start == 20.0
        assert merged[1].end == 40.0  # gap_threshold以内なのでマージされる

    def test_merge_segments_empty_list(self):
        """merge_segmentsクラスメソッドが空のリストを正しく処理することを確認"""
        merged = VideoSegment.merge_segments([])
        assert merged == []

    def test_immutability(self):
        """VideoSegmentの属性が変更可能であることを確認（dataclassのデフォルト）"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)
        # dataclassのデフォルトでは変更可能
        segment.start = 15.0
        assert segment.start == 15.0

    def test_hash(self):
        """VideoSegmentがハッシュ可能でないことを確認（可変オブジェクト）"""
        segment = VideoSegment(id="seg1", start=10.0, end=20.0)
        # dataclassのデフォルトではhash=Falseなのでハッシュ不可
        with pytest.raises(TypeError, match="unhashable type"):
            hash(segment)
