"""
エクスポートユースケースのテスト
"""

from unittest.mock import Mock, patch

import pytest

from domain.entities import Char, TranscriptionResult, TranscriptionSegment, VideoSegment, Word
from domain.value_objects import FilePath, TimeRange
from use_cases.exceptions import ExportError
from use_cases.export import (
    ExportFCPXMLRequest,
    ExportFCPXMLUseCase,
    ExportSRTRequest,
    ExportSRTUseCase,
)


class TestExportFCPXMLUseCase:
    """ExportFCPXMLUseCaseのテスト"""

    @pytest.fixture
    def mock_export_gateway(self):
        """モックエクスポートゲートウェイ"""
        gateway = Mock()
        gateway.get_video_info.return_value = {
            "duration": 60.0,
            "fps": 30.0,
            "width": 1920,
            "height": 1080,
            "audio_channels": 2,
            "audio_rate": 48000,
        }
        gateway.generate_fcpxml.return_value = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.10">
    <resources>
        <asset id="r1" name="test.mp4" uid="r1" start="0s" duration="60s" hasVideo="1" hasAudio="1"/>
    </resources>
    <library>
        <event name="TextffCut Project">
            <project name="TextffCut Project">
                <sequence format="r1" tcStart="0s" duration="10s">
                    <spine>
                        <clip name="Clip 1" ref="r1" duration="5s"/>
                        <clip name="Clip 2" ref="r1" duration="5s"/>
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""
        return gateway

    @pytest.fixture
    def mock_file_gateway(self):
        """モックファイルゲートウェイ"""
        gateway = Mock()
        gateway.exists.return_value = True
        gateway.write_text.return_value = None
        return gateway

    @pytest.fixture
    def video_segments(self):
        """テスト用ビデオセグメント"""
        return [
            VideoSegment(
                id="seg1",
                start=0.0,
                end=5.0,
                is_silence=False,
                metadata={"label": "Segment 1", "video_path": "/test/video.mp4"},
            ),
            VideoSegment(
                id="seg2",
                start=10.0,
                end=15.0,
                is_silence=False,
                metadata={"label": "Segment 2", "video_path": "/test/video.mp4"},
            ),
        ]

    def test_successful_fcpxml_export(self, mock_export_gateway, mock_file_gateway, video_segments):
        """正常なFCPXMLエクスポート"""
        # Arrange
        use_case = ExportFCPXMLUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportFCPXMLRequest(
            video_path=FilePath("/test/video.mp4"),
            output_path=FilePath("/output/project.fcpxml"),
            segments=video_segments,
            timeline_name="Test Project",
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".fcpxml")):
                    with patch.object(FilePath, "name", property(lambda self: "video.mp4")):
                        # Act
                        response = use_case(request)

        # Assert
        assert response.output_path == FilePath("/output/project.fcpxml")
        assert response.asset.id == "r1"
        assert response.asset.name == "video.mp4"
        assert response.asset.duration.seconds == 60.0
        assert len(response.clips) == 2
        assert response.clip_count == 2
        assert response.total_duration.seconds == 10.0  # 5 + 5

        # ゲートウェイメソッドの呼び出し確認
        mock_export_gateway.get_video_info.assert_called_once_with(FilePath("/test/video.mp4"))
        mock_export_gateway.generate_fcpxml.assert_called_once()
        mock_file_gateway.write_text.assert_called_once()

    def test_remove_silence_mode(self, mock_export_gateway, mock_file_gateway, video_segments):
        """無音削除モード"""
        # Arrange
        use_case = ExportFCPXMLUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportFCPXMLRequest(
            video_path=FilePath("/test/video.mp4"),
            output_path=FilePath("/output/project.fcpxml"),
            segments=video_segments,
            timeline_name="Test Project",
            remove_silence=True,
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".fcpxml")):
                    with patch.object(FilePath, "name", property(lambda self: "video.mp4")):
                        # Act
                        response = use_case(request)

        # Assert
        # 無音削除モードでは、クリップが隙間なく配置される
        assert response.clips[0].start_time == 0.0
        assert response.clips[1].start_time == 5.0  # 最初のクリップの直後
        assert response.timeline_duration == 10.0  # 5 + 5

    def test_file_not_found(self, mock_export_gateway, mock_file_gateway, video_segments):
        """ファイルが存在しない場合"""
        use_case = ExportFCPXMLUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportFCPXMLRequest(
            video_path=FilePath("/test/nonexistent.mp4"),
            output_path=FilePath("/output/project.fcpxml"),
            segments=video_segments,
            timeline_name="Test Project",
        )

        with patch.object(FilePath, "exists", property(lambda self: False)):
            with pytest.raises(ExportError, match="Video file not found"):
                use_case(request)

    def test_invalid_extension(self, mock_export_gateway, mock_file_gateway, video_segments):
        """無効な拡張子"""
        use_case = ExportFCPXMLUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportFCPXMLRequest(
            video_path=FilePath("/test/video.mp4"),
            output_path=FilePath("/output/project.txt"),  # 無効な拡張子
            segments=video_segments,
            timeline_name="Test Project",
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "extension", property(lambda self: ".txt")):
                with pytest.raises(ExportError, match="Invalid output format"):
                    use_case(request)

    def test_no_segments(self, mock_export_gateway, mock_file_gateway):
        """セグメントがない場合"""
        use_case = ExportFCPXMLUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportFCPXMLRequest(
            video_path=FilePath("/test/video.mp4"),
            output_path=FilePath("/output/project.fcpxml"),
            segments=[],  # 空のセグメント
            timeline_name="Test Project",
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with pytest.raises(ExportError, match="No segments provided"):
                use_case(request)


class TestExportSRTUseCase:
    """ExportSRTUseCaseのテスト"""

    @pytest.fixture
    def mock_export_gateway(self):
        """モックエクスポートゲートウェイ"""
        gateway = Mock()

        # TimeMapperのモック
        time_mapper = Mock()
        time_mapper.map_time_range.side_effect = lambda tr: TimeRange(
            start=tr.start * 0.8, end=tr.end * 0.8  # 簡単な時間調整シミュレーション
        )
        gateway.create_time_mapper.return_value = time_mapper

        return gateway

    @pytest.fixture
    def mock_file_gateway(self):
        """モックファイルゲートウェイ"""
        gateway = Mock()
        gateway.exists.return_value = True
        gateway.write_text.return_value = None
        return gateway

    @pytest.fixture
    def transcription_result(self):
        """テスト用文字起こし結果"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=2.0,
                text="これはテストです",
                words=[
                    Word(word="これは", start=0.0, end=1.0, confidence=0.95),
                    Word(word="テストです", start=1.0, end=2.0, confidence=0.95),
                ],
                chars=[
                    Char(char="こ", start=0.0, end=0.25, confidence=0.95),
                    Char(char="れ", start=0.25, end=0.5, confidence=0.95),
                    Char(char="は", start=0.5, end=1.0, confidence=0.95),
                    Char(char="テ", start=1.0, end=1.33, confidence=0.95),
                    Char(char="ス", start=1.33, end=1.66, confidence=0.95),
                    Char(char="ト", start=1.66, end=2.0, confidence=0.95),
                ],
            ),
            TranscriptionSegment(id="seg2", start=3.0, end=5.0, text="字幕のテスト", words=[], chars=[]),
            TranscriptionSegment(id="seg3", start=10.0, end=12.0, text="範囲外のテキスト", words=[], chars=[]),
        ]

        return TranscriptionResult(
            id="test-transcription",
            language="ja",
            segments=segments,
            original_audio_path="/test/audio.wav",
            model_size="large-v3",
            processing_time=10.0,
        )

    def test_successful_srt_export(self, mock_export_gateway, mock_file_gateway, transcription_result):
        """正常なSRTエクスポート"""
        # Arrange
        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportSRTRequest(
            transcription=transcription_result,
            output_path=FilePath("/output/subtitles.srt"),
            max_chars_per_line=21,  # 日本語字幕の標準設定
            max_lines=2,
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".srt")):
                    # Act
                    response = use_case(request)

        # Assert
        assert response.output_path == FilePath("/output/subtitles.srt")
        assert response.total_entries == 1  # 42文字制限内なので1つのエントリに統合される
        assert response.filtered_segments == 0
        assert response.total_duration == 12.0

        # 字幕エントリの確認
        assert len(response.entries) == 1
        assert response.entries[0].text == "これはテストです 字幕のテスト 範囲外のテキスト"
        assert len(response.entries[0].lines) == 2  # 2行に分割

        # ファイル書き込みの確認
        mock_file_gateway.write_text.assert_called_once()
        args = mock_file_gateway.write_text.call_args
        assert args[1]["encoding"] == "utf-8-sig"  # BOM付きUTF-8

    def test_with_time_range_filter(self, mock_export_gateway, mock_file_gateway, transcription_result):
        """時間範囲フィルタ付き"""
        # Arrange
        time_ranges = [TimeRange(0.0, 6.0)]  # 10-12秒のセグメントを除外

        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportSRTRequest(
            transcription=transcription_result,
            output_path=FilePath("/output/subtitles.srt"),
            time_ranges=time_ranges,
            max_chars_per_line=21,
            max_lines=2,
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".srt")):
                    # Act
                    response = use_case(request)

        # Assert
        assert response.total_entries == 1  # フィルタ後の2セグメントが1エントリに統合
        assert response.filtered_segments == 1
        assert response.entries[0].text == "これはテストです 字幕のテスト"

    def test_with_silence_removal(self, mock_export_gateway, mock_file_gateway, transcription_result):
        """無音削除モード"""
        # Arrange
        silence_ranges = [TimeRange(2.0, 3.0), TimeRange(5.0, 10.0)]

        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportSRTRequest(
            transcription=transcription_result,
            output_path=FilePath("/output/subtitles.srt"),
            remove_silence=True,
            silence_ranges=silence_ranges,
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".srt")):
                    # Act
                    response = use_case(request)

        # Assert
        # 時間調整が適用されたことを確認
        assert response.entries[0].start_time == 0.0  # 開始時間
        assert response.entries[0].end_time == pytest.approx(9.6)  # 12.0 * 0.8 (3つのセグメントが統合)
        assert response.total_entries == 1  # すべてのセグメントが1つに統合
        mock_export_gateway.create_time_mapper.assert_called_once_with(silence_ranges=silence_ranges)

    def test_progress_callback(self, mock_export_gateway, mock_file_gateway, transcription_result):
        """進捗コールバック"""
        # Arrange
        progress_values = []

        def progress_callback(value):
            progress_values.append(value)

        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportSRTRequest(
            transcription=transcription_result,
            output_path=FilePath("/output/subtitles.srt"),
            progress_callback=progress_callback,
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with patch.object(FilePath, "parent", property(lambda self: Mock(exists=True))):
                with patch.object(FilePath, "extension", property(lambda self: ".srt")):
                    # Act
                    use_case(request)

        # Assert
        assert len(progress_values) > 0
        assert progress_values[0] == 0.1  # 開始時
        assert progress_values[-1] == 1.0  # 終了時

    def test_no_segments(self, mock_export_gateway, mock_file_gateway):
        """セグメントがない場合"""
        # Arrange
        # TranscriptionResultは空のセグメントを許可しないため、
        # ダミーセグメントを作成してからクリアする
        dummy_segment = TranscriptionSegment(id="dummy", start=0.0, end=0.1, text="dummy", words=[])
        empty_transcription = TranscriptionResult(
            id="empty",
            language="ja",
            segments=[dummy_segment],  # ダミーセグメントで初期化
            original_audio_path="/test/audio.wav",
            model_size="large-v3",
            processing_time=0.0,
        )
        # セグメントをクリア
        empty_transcription.segments = []

        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)
        request = ExportSRTRequest(transcription=empty_transcription, output_path=FilePath("/output/subtitles.srt"))

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with pytest.raises(ExportError, match="No transcription segments"):
                use_case(request)

    def test_invalid_parameters(self, mock_export_gateway, mock_file_gateway, transcription_result):
        """無効なパラメータ"""
        use_case = ExportSRTUseCase(mock_export_gateway, mock_file_gateway)

        # 無効な最大文字数
        request = ExportSRTRequest(
            transcription=transcription_result, output_path=FilePath("/output/subtitles.srt"), max_chars_per_line=0
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with pytest.raises(ExportError, match="max_chars_per_line must be positive"):
                use_case(request)

        # 無効な最大行数
        request = ExportSRTRequest(
            transcription=transcription_result, output_path=FilePath("/output/subtitles.srt"), max_lines=0
        )

        with patch.object(FilePath, "exists", property(lambda self: True)):
            with pytest.raises(ExportError, match="max_lines must be positive"):
                use_case(request)
