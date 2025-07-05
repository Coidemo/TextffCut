"""
エクスポートゲートウェイのテスト
"""

from unittest.mock import Mock, patch

import pytest

from adapters.gateways.export.fcpxml_export_gateway import FCPXMLExportGatewayAdapter, FCPXMLTimeMapper
from adapters.gateways.export.srt_export_gateway import SRTExportGatewayAdapter
from domain.entities import TranscriptionResult, TranscriptionSegment, Word
from domain.value_objects import FilePath, TimeRange
from use_cases.exceptions import ExportError
from use_cases.interfaces import ExportSegment


class TestFCPXMLExportGatewayAdapter:
    """FCPXMLExportGatewayAdapterのテスト"""

    @pytest.fixture
    def gateway(self):
        """テスト用ゲートウェイ"""
        return FCPXMLExportGatewayAdapter()

    @pytest.fixture
    def mock_legacy_exporter(self):
        """モックレガシーエクスポーター"""
        with patch("adapters.gateways.export.fcpxml_export_gateway.LegacyFCPXMLExporter") as mock:
            yield mock

    @pytest.fixture
    def export_segments(self):
        """テスト用エクスポートセグメント"""
        return [
            ExportSegment(video_path=FilePath("/test/video1.mp4"), time_range=TimeRange(0.0, 10.0)),
            ExportSegment(video_path=FilePath("/test/video2.mp4"), time_range=TimeRange(15.0, 25.0)),
        ]

    def test_export_success(self, mock_legacy_exporter, export_segments):
        """FCPXMLエクスポートの成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.export.return_value = True
        mock_legacy_exporter.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = FCPXMLExportGatewayAdapter()
        output_path = FilePath("/output/project.fcpxml")

        gateway.export(segments=export_segments, output_path=output_path, project_name="Test Project", fps=30.0)

        # レガシーメソッドが正しく呼ばれたことを確認
        mock_instance.export.assert_called_once()
        call_args = mock_instance.export.call_args[1]

        # セグメントが正しく変換されたことを確認
        assert len(call_args["segments"]) == 2
        assert call_args["segments"][0].source_path == "/test/video1.mp4"
        assert call_args["segments"][0].start_time == 0.0
        assert call_args["segments"][0].end_time == 10.0
        assert call_args["segments"][0].timeline_start == 0.0

        assert call_args["segments"][1].source_path == "/test/video2.mp4"
        assert call_args["segments"][1].start_time == 15.0
        assert call_args["segments"][1].end_time == 25.0
        assert call_args["segments"][1].timeline_start == 10.0  # 前のセグメントの長さ分オフセット

        assert call_args["output_path"] == "/output/project.fcpxml"
        assert call_args["project_name"] == "Test Project"
        assert call_args["timeline_fps"] == 30

    def test_export_error_handling(self, mock_legacy_exporter, export_segments):
        """FCPXMLエクスポートのエラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.export.return_value = False
        mock_legacy_exporter.return_value = mock_instance

        # ゲートウェイの作成
        gateway = FCPXMLExportGatewayAdapter()
        output_path = FilePath("/output/project.fcpxml")

        # エラーが適切に変換されることを確認
        with pytest.raises(ExportError, match="Failed to export FCPXML"):
            gateway.export(segments=export_segments, output_path=output_path)

    def test_get_video_info(self):
        """動画情報取得のテスト"""
        with patch("adapters.gateways.export.fcpxml_export_gateway.VideoInfo") as mock_info:
            # モックの設定
            mock_video_info = Mock()
            mock_video_info.path = "/test/video.mp4"
            mock_video_info.duration = 60.0
            mock_video_info.fps = 30.0
            mock_video_info.width = 1920
            mock_video_info.height = 1080
            mock_video_info.codec = "h264"

            mock_info.from_file.return_value = mock_video_info

            # ゲートウェイの作成と実行
            gateway = FCPXMLExportGatewayAdapter()
            video_path = FilePath("/test/video.mp4")

            result = gateway.get_video_info(video_path)

            # 検証
            assert result["path"] == "/test/video.mp4"
            assert result["duration"] == 60.0
            assert result["fps"] == 30.0
            assert result["width"] == 1920
            assert result["height"] == 1080
            assert result["codec"] == "h264"

    def test_create_time_mapper(self):
        """時間マッパー作成のテスト"""
        gateway = FCPXMLExportGatewayAdapter()
        silence_ranges = [TimeRange(5.0, 8.0), TimeRange(15.0, 18.0)]

        mapper = gateway.create_time_mapper(silence_ranges)

        assert isinstance(mapper, FCPXMLTimeMapper)
        assert mapper.silence_ranges == silence_ranges


class TestFCPXMLTimeMapper:
    """FCPXMLTimeMapperのテスト"""

    def test_map_time_range_no_silence(self):
        """サイレンスなしの時間マッピング"""
        mapper = FCPXMLTimeMapper([])
        time_range = TimeRange(10.0, 20.0)

        mapped = mapper.map_time_range(time_range)

        assert mapped == time_range

    def test_map_time_range_with_silence(self):
        """サイレンスありの時間マッピング"""
        silence_ranges = [TimeRange(5.0, 8.0), TimeRange(15.0, 18.0)]  # 3秒のサイレンス  # 3秒のサイレンス
        mapper = FCPXMLTimeMapper(silence_ranges)

        # サイレンス前の範囲（そのまま）
        range1 = TimeRange(0.0, 4.0)
        mapped1 = mapper.map_time_range(range1)
        assert mapped1.start == 0.0
        assert mapped1.end == 4.0

        # 最初のサイレンス後の範囲（3秒シフト）
        range2 = TimeRange(10.0, 14.0)
        mapped2 = mapper.map_time_range(range2)
        assert mapped2.start == 7.0  # 10 - 3
        assert mapped2.end == 11.0  # 14 - 3

        # 2番目のサイレンス後の範囲（6秒シフト）
        range3 = TimeRange(20.0, 25.0)
        mapped3 = mapper.map_time_range(range3)
        assert mapped3.start == 14.0  # 20 - 6
        assert mapped3.end == 19.0  # 25 - 6


class TestSRTExportGatewayAdapter:
    """SRTExportGatewayAdapterのテスト"""

    @pytest.fixture
    def gateway(self):
        """テスト用ゲートウェイ"""
        return SRTExportGatewayAdapter()

    @pytest.fixture
    def mock_legacy_exporter(self):
        """モックレガシーエクスポーター"""
        with patch("adapters.gateways.export.srt_export_gateway.LegacySRTExporter") as mock:
            yield mock

    @pytest.fixture
    def transcription_result(self):
        """テスト用文字起こし結果"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                text="これはテストです",
                start=0.0,
                end=2.0,
                words=[
                    Word(word="これは", start=0.0, end=1.0, confidence=0.95),
                    Word(word="テストです", start=1.0, end=2.0, confidence=0.93),
                ],
                chars=[],
            ),
            TranscriptionSegment(id="seg2", text="SRTエクスポートのテスト", start=5.0, end=8.0, words=[], chars=[]),
        ]

        return TranscriptionResult(
            id="test-id",
            language="ja",
            segments=segments,
            original_audio_path="/test/audio.mp4",
            model_size="large-v3",
            processing_time=5.0,
        )

    def test_export_from_transcription_success(self, mock_legacy_exporter, transcription_result):
        """文字起こしからのSRTエクスポート成功テスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.export.return_value = True
        mock_legacy_exporter.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = SRTExportGatewayAdapter()
        output_path = FilePath("/output/subtitles.srt")

        gateway.export_from_transcription(
            transcription_result=transcription_result, output_path=output_path, max_chars_per_line=30, max_lines=2
        )

        # レガシーメソッドが正しく呼ばれたことを確認
        mock_instance.export.assert_called_once()
        call_args = mock_instance.export.call_args[1]

        # レガシー形式に変換されたことを確認
        assert call_args["output_path"] == "/output/subtitles.srt"
        assert call_args["max_chars_per_line"] == 30
        assert call_args["max_lines"] == 2

        # 文字起こし結果が正しく変換されたことを確認
        legacy_transcription = call_args["transcription"]
        assert legacy_transcription.language == "ja"
        assert len(legacy_transcription.segments) == 2

    def test_export_from_diff(self, gateway, transcription_result):
        """差分からのSRTエクスポートテスト"""
        time_ranges = [TimeRange(0.0, 3.0), TimeRange(10.0, 15.0)]  # 最初のセグメントを含む  # どのセグメントも含まない

        output_path = FilePath("/output/diff_subtitles.srt")

        # export_from_transcriptionをモック
        with patch.object(gateway, "export_from_transcription") as mock_export:
            gateway.export_from_diff(
                transcription_result=transcription_result, time_ranges=time_ranges, output_path=output_path
            )

            # フィルタリングされた結果でエクスポートが呼ばれたことを確認
            mock_export.assert_called_once()
            call_args = mock_export.call_args[1]

            filtered_result = call_args["transcription_result"]
            assert len(filtered_result.segments) == 1  # 最初のセグメントのみ
            assert filtered_result.segments[0].text == "これはテストです"

    def test_export_with_time_mapping(self, gateway, transcription_result):
        """時間マッピング付きSRTエクスポートテスト"""
        # 時間を半分に圧縮するマッピング
        time_mapping = [(TimeRange(0.0, 10.0), TimeRange(0.0, 5.0))]

        output_path = FilePath("/output/mapped_subtitles.srt")

        # export_from_transcriptionをモック
        with patch.object(gateway, "export_from_transcription") as mock_export:
            gateway.export_with_time_mapping(
                transcription_result=transcription_result, time_mapping=time_mapping, output_path=output_path
            )

            # マッピングされた結果でエクスポートが呼ばれたことを確認
            mock_export.assert_called_once()
            call_args = mock_export.call_args[1]

            adjusted_result = call_args["transcription_result"]
            assert len(adjusted_result.segments) == 2

            # 時間が半分に圧縮されていることを確認
            assert adjusted_result.segments[0].start == 0.0
            assert adjusted_result.segments[0].end == 1.0  # 2.0 の半分
            assert adjusted_result.segments[1].start == 2.5  # 5.0 の半分
            assert adjusted_result.segments[1].end == 4.0  # 8.0 の半分

    def test_ranges_overlap(self, gateway):
        """時間範囲の重なりチェックテスト"""
        range1 = TimeRange(0.0, 10.0)
        range2 = TimeRange(5.0, 15.0)
        range3 = TimeRange(15.0, 20.0)

        # 重なっている
        assert gateway._ranges_overlap(range1, range2) is True

        # 重なっていない
        assert gateway._ranges_overlap(range1, range3) is False

        # 境界で接している（重なっていない）
        assert gateway._ranges_overlap(TimeRange(0.0, 5.0), TimeRange(5.0, 10.0)) is False
