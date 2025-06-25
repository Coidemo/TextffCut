"""
タイムライン編集機能のテスト
"""

import pytest

from core.timeline_processor import TimelineProcessor, TimelineSegment
from services.timeline_editing_service import TimelineEditingService


class TestTimelineSegment:
    """TimelineSegmentクラスのテスト"""

    def test_segment_creation(self):
        """セグメントの作成テスト"""
        segment = TimelineSegment(id="test_1", start=10.5, end=20.3, text="テストテキスト")

        assert segment.id == "test_1"
        assert segment.start == 10.5
        assert segment.end == 20.3
        assert segment.text == "テストテキスト"
        assert segment.duration() == pytest.approx(9.8)

    def test_segment_to_frames(self):
        """フレーム変換テスト"""
        segment = TimelineSegment(id="test_1", start=1.0, end=2.0, text="テスト")

        # 30fps
        start_frame, end_frame = segment.to_frames(30.0)
        assert start_frame == 30
        assert end_frame == 60

        # 60fps
        start_frame, end_frame = segment.to_frames(60.0)
        assert start_frame == 60
        assert end_frame == 120

    def test_adjust_start(self):
        """開始時間調整テスト"""
        segment = TimelineSegment(id="test_1", start=5.0, end=10.0, text="テスト")

        # 正の調整
        assert segment.adjust_start(1.0)
        assert segment.start == 6.0

        # 負の調整（0未満にならない）
        assert segment.adjust_start(-10.0)
        assert segment.start == 0.0

        # 最小長チェック
        segment.end = 0.05
        assert not segment.adjust_start(0.1, min_duration=0.1)

    def test_adjust_end(self):
        """終了時間調整テスト"""
        segment = TimelineSegment(id="test_1", start=5.0, end=10.0, text="テスト")

        # 正の調整
        assert segment.adjust_end(1.0, max_duration=20.0)
        assert segment.end == 11.0

        # 最大長制限
        assert segment.adjust_end(20.0, max_duration=15.0)
        assert segment.end == 15.0

        # 最小長チェック
        segment.start = 14.9
        assert not segment.adjust_end(-0.1, max_duration=20.0, min_duration=0.2)

    def test_set_time_range(self):
        """時間範囲設定テスト"""
        segment = TimelineSegment(id="test_1", start=0.0, end=0.0, text="テスト")

        # 正常な設定
        assert segment.set_time_range(5.0, 10.0, max_duration=20.0)
        assert segment.start == 5.0
        assert segment.end == 10.0

        # 無効な範囲
        assert not segment.set_time_range(-1.0, 10.0, max_duration=20.0)
        assert not segment.set_time_range(5.0, 25.0, max_duration=20.0)
        assert not segment.set_time_range(10.0, 5.0, max_duration=20.0)

    def test_segment_serialization(self):
        """シリアライズ・デシリアライズテスト"""
        original = TimelineSegment(
            id="test_1", start=10.5, end=20.3, text="テストテキスト", waveform_data=[0.1, 0.2, 0.3]
        )

        # 辞書に変換
        data = original.to_dict()
        assert data["id"] == "test_1"
        assert data["start"] == 10.5
        assert data["end"] == 20.3
        assert data["text"] == "テストテキスト"
        assert data["waveform_data"] == [0.1, 0.2, 0.3]

        # 辞書から復元
        restored = TimelineSegment.from_dict(data)
        assert restored.id == original.id
        assert restored.start == original.start
        assert restored.end == original.end
        assert restored.text == original.text
        assert restored.waveform_data == original.waveform_data


class TestTimelineProcessor:
    """TimelineProcessorクラスのテスト"""

    def test_create_segments_from_ranges(self):
        """時間範囲からセグメント作成テスト"""
        processor = TimelineProcessor()

        time_ranges = [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)]
        transcription_result = {
            "segments": [
                {
                    "words": [
                        {"word": "こんにちは", "start": 0.0, "end": 2.0},
                        {"word": "世界", "start": 2.0, "end": 3.0},
                        {"word": "テスト", "start": 10.0, "end": 12.0},
                        {"word": "です", "start": 20.0, "end": 22.0},
                    ]
                }
            ]
        }

        segments = processor.create_segments_from_ranges(time_ranges, transcription_result, video_duration=30.0)

        assert len(segments) == 3
        assert segments[0].id == "segment_1"
        assert segments[0].start == 0.0
        assert segments[0].end == 5.0
        assert segments[0].text == "こんにちは世界"

        assert segments[1].id == "segment_2"
        assert segments[1].text == "テスト"

        assert segments[2].id == "segment_3"
        assert segments[2].text == "です"

    def test_adjust_segment_time(self):
        """セグメント時間調整テスト"""
        processor = TimelineProcessor()
        processor.video_duration = 30.0
        processor.fps = 30.0

        # セグメントを追加
        segment = TimelineSegment(id="test_1", start=10.0, end=20.0, text="テスト")
        processor.segments.append(segment)

        # 秒単位の調整
        assert processor.adjust_segment_time("test_1", start_delta=1.0)
        assert segment.start == 11.0

        assert processor.adjust_segment_time("test_1", end_delta=-2.0)
        assert segment.end == 18.0

        # フレーム単位の調整
        assert processor.adjust_segment_time("test_1", start_delta=5, fps=30.0)
        assert segment.start == pytest.approx(11.0 + 5 / 30.0)

        # 存在しないセグメント
        assert not processor.adjust_segment_time("invalid_id", start_delta=1.0)

    def test_validate_segments(self):
        """セグメント検証テスト"""
        processor = TimelineProcessor()
        processor.video_duration = 30.0

        # 正常なセグメント
        processor.segments = [
            TimelineSegment("seg1", 0.0, 5.0, ""),
            TimelineSegment("seg2", 10.0, 15.0, ""),
            TimelineSegment("seg3", 20.0, 25.0, ""),
        ]

        is_valid, errors = processor.validate_segments()
        assert is_valid
        assert len(errors) == 0

        # エラーケース1: 開始時間が負
        processor.segments[0].start = -1.0
        is_valid, errors = processor.validate_segments()
        assert not is_valid
        assert "開始時間が負の値です" in errors[0]

        # エラーケース2: 終了時間が動画長を超える
        processor.segments[0].start = 0.0
        processor.segments[2].end = 35.0
        is_valid, errors = processor.validate_segments()
        assert not is_valid
        assert "終了時間が動画長を超えています" in errors[0]

        # エラーケース3: セグメントの重複
        processor.segments[2].end = 25.0
        processor.segments[1].end = 21.0  # seg3と重複
        is_valid, errors = processor.validate_segments()
        assert not is_valid
        assert "重複しています" in errors[0]

    def test_merge_overlapping_segments(self):
        """重複セグメントのマージテスト"""
        processor = TimelineProcessor()

        # 重複するセグメントを作成
        processor.segments = [
            TimelineSegment("seg1", 0.0, 5.0, "テキスト1"),
            TimelineSegment("seg2", 3.0, 8.0, "テキスト2"),  # seg1と重複
            TimelineSegment("seg3", 10.0, 15.0, "テキスト3"),
            TimelineSegment("seg4", 14.0, 20.0, "テキスト4"),  # seg3と重複
        ]

        merge_count = processor.merge_overlapping_segments()

        assert merge_count == 2
        assert len(processor.segments) == 2
        assert processor.segments[0].start == 0.0
        assert processor.segments[0].end == 8.0
        assert processor.segments[0].text == "テキスト1テキスト2"
        assert processor.segments[1].start == 10.0
        assert processor.segments[1].end == 20.0

    def test_processor_serialization(self):
        """プロセッサーのシリアライズテスト"""
        processor = TimelineProcessor()
        processor.video_duration = 30.0
        processor.fps = 60.0
        processor.segments = [
            TimelineSegment("seg1", 0.0, 5.0, "テキスト1"),
            TimelineSegment("seg2", 10.0, 15.0, "テキスト2"),
        ]

        # 辞書に変換
        data = processor.to_dict()
        assert data["video_duration"] == 30.0
        assert data["fps"] == 60.0
        assert len(data["segments"]) == 2

        # 新しいプロセッサーに復元
        new_processor = TimelineProcessor()
        new_processor.from_dict(data)

        assert new_processor.video_duration == 30.0
        assert new_processor.fps == 60.0
        assert len(new_processor.segments) == 2
        assert new_processor.segments[0].id == "seg1"
        assert new_processor.segments[1].text == "テキスト2"


class TestTimelineEditingService:
    """TimelineEditingServiceクラスのテスト"""

    def test_service_initialization(self):
        """サービス初期化テスト"""
        service = TimelineEditingService()

        assert service.timeline_processor is not None
        assert service.video_processor is not None
        assert service.config is not None

    def test_get_timeline_statistics(self):
        """統計情報取得テスト"""
        service = TimelineEditingService()

        # セッション状態なしの場合
        stats = service.get_timeline_statistics()
        assert stats == {}

        # TODO: Streamlitセッション状態のモックが必要なため、
        # 実際のUIテストは統合テストで実施


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
