"""
エクスポートヘルパー関数のユニットテスト
"""

from pathlib import Path
from unittest.mock import patch, Mock, MagicMock, call

import pytest

from utils.export_helpers import (
    get_default_srt_settings,
    get_srt_settings_from_session,
    determine_export_format,
    create_export_segments,
    export_xml,
    export_srt_with_diff,
    generate_export_paths,
    format_export_success_message
)


class TestSrtSettings:
    """SRT設定関連のテスト"""
    
    def test_get_default_srt_settings(self):
        """デフォルトSRT設定の取得"""
        settings = get_default_srt_settings()
        
        assert isinstance(settings, dict)
        assert settings["min_duration"] == 0.5
        assert settings["max_duration"] == 7.0
        assert settings["gap_threshold"] == 0.1
        assert settings["chars_per_second"] == 15.0
        assert settings["max_line_length"] == 42
        assert settings["max_lines"] == 2
        assert settings["encoding"] == "utf-8"
    
    @patch('streamlit.session_state', {"srt_settings": {"max_lines": 3, "encoding": "shift-jis"}})
    def test_get_srt_settings_from_session_custom(self):
        """カスタム設定がセッションにある場合"""
        settings = get_srt_settings_from_session()
        
        assert settings["max_lines"] == 3
        assert settings["encoding"] == "shift-jis"
    
    @patch('streamlit.session_state', {})
    def test_get_srt_settings_from_session_default(self):
        """セッションに設定がない場合"""
        settings = get_srt_settings_from_session()
        
        # デフォルト設定が返される
        assert settings == get_default_srt_settings()


class TestExportFormat:
    """エクスポート形式関連のテスト"""
    
    def test_determine_export_format_fcpxml(self):
        """FCPXML形式の判定"""
        format_type, ext = determine_export_format("FCPXMLファイル")
        
        assert format_type == "fcpxml"
        assert ext == ".fcpxml"
    
    def test_determine_export_format_premiere(self):
        """Premiere Pro XML形式の判定"""
        format_type, ext = determine_export_format("Premiere Pro XML")
        
        assert format_type == "xmeml"
        assert ext == ".xml"
    
    def test_determine_export_format_unknown(self):
        """不明な形式の場合のデフォルト"""
        format_type, ext = determine_export_format("Unknown Format")
        
        assert format_type == "fcpxml"
        assert ext == ".fcpxml"


class TestCreateExportSegments:
    """エクスポートセグメント作成のテスト"""
    
    def test_create_segments_single_range(self):
        """単一の時間範囲"""
        keep_ranges = [(0.0, 10.0)]
        
        segments = create_export_segments(keep_ranges)
        
        assert len(segments) == 1
        assert segments[0].start == 0.0
        assert segments[0].end == 10.0
        assert segments[0].text == ""
        assert segments[0].words == []
    
    def test_create_segments_multiple_ranges(self):
        """複数の時間範囲"""
        keep_ranges = [(0.0, 5.0), (10.0, 15.0), (20.0, 25.0)]
        
        segments = create_export_segments(keep_ranges)
        
        assert len(segments) == 3
        assert segments[1].start == 10.0
        assert segments[1].end == 15.0
    
    def test_create_segments_empty_ranges(self):
        """空の時間範囲"""
        keep_ranges = []
        
        segments = create_export_segments(keep_ranges)
        
        assert len(segments) == 0


class TestExportXml:
    """XMLエクスポートのテスト"""
    
    @patch('utils.export_helpers.ExportService')
    def test_export_xml_success(self, mock_export_service_class):
        """XML出力成功"""
        # モックの設定
        mock_service = Mock()
        mock_result = Mock()
        mock_result.success = True
        mock_result.metadata = {"used_duration": 30.5}
        mock_service.execute.return_value = mock_result
        mock_export_service_class.return_value = mock_service
        
        # 実行
        success, error, duration = export_xml(
            config=Mock(),
            video_path=Path("/test/video.mp4"),
            keep_ranges=[(0, 10), (20, 30)],
            output_path=Path("/test/output.fcpxml"),
            export_format="fcpxml",
            timeline_fps="30fps"
        )
        
        assert success is True
        assert error is None
        assert duration == 30.5
        
        # サービスの呼び出しを確認
        mock_service.execute.assert_called_once()
        call_args = mock_service.execute.call_args[1]
        assert call_args["format"] == "fcpxml"
        assert call_args["video_path"] == "/test/video.mp4"
        assert len(call_args["segments"]) == 2
        assert call_args["remove_silence"] is False  # デフォルト値を確認
    
    @patch('utils.export_helpers.ExportService')
    def test_export_xml_failure(self, mock_export_service_class):
        """XML出力失敗"""
        mock_service = Mock()
        mock_result = Mock()
        mock_result.success = False
        mock_service.execute.return_value = mock_result
        mock_export_service_class.return_value = mock_service
        
        success, error, duration = export_xml(
            config=Mock(),
            video_path=Path("/test/video.mp4"),
            keep_ranges=[(0, 10)],
            output_path=Path("/test/output.fcpxml"),
            export_format="fcpxml"
        )
        
        assert success is False
        assert error == "XMLエクスポートに失敗しました"
        assert duration is None
    
    @patch('utils.export_helpers.ExportService')
    def test_export_xml_exception(self, mock_export_service_class):
        """例外発生時"""
        mock_export_service_class.side_effect = Exception("Test error")
        
        success, error, duration = export_xml(
            config=Mock(),
            video_path=Path("/test/video.mp4"),
            keep_ranges=[(0, 10)],
            output_path=Path("/test/output.fcpxml"),
            export_format="fcpxml"
        )
        
        assert success is False
        assert "Test error" in error
        assert duration is None


class TestExportSrt:
    """SRTエクスポートのテスト"""
    
    @patch('utils.export_helpers.SRTDiffExporter')
    @patch('utils.export_helpers.get_srt_settings_from_session')
    def test_export_srt_without_silence_removal(self, mock_get_settings, mock_exporter_class):
        """無音削除なしのSRT出力"""
        mock_get_settings.return_value = {"max_line_length": 42, "max_lines": 2}
        
        mock_exporter = Mock()
        mock_exporter.export_from_diff.return_value = True
        mock_exporter_class.return_value = mock_exporter
        
        success, error = export_srt_with_diff(
            config=Mock(),
            video_path=Path("/test/video.mp4"),
            output_path=Path("/test/output.srt"),
            diff_data=Mock(),
            transcription_result=Mock(),
            remove_silence=False
        )
        
        assert success is True
        assert error is None
        
        # 正しいメソッドが呼ばれたか確認
        mock_exporter.export_from_diff.assert_called_once()
        mock_exporter.export_from_diff_with_silence_removal.assert_not_called()
    
    @patch('utils.export_helpers.SRTDiffExporter')
    @patch('utils.export_helpers.get_srt_settings_from_session')
    def test_export_srt_with_silence_removal(self, mock_get_settings, mock_exporter_class):
        """無音削除ありのSRT出力"""
        mock_get_settings.return_value = {"max_line_length": 42, "max_lines": 2}
        
        mock_exporter = Mock()
        mock_exporter.export_from_diff_with_silence_removal.return_value = True
        mock_exporter_class.return_value = mock_exporter
        
        mock_time_mapper = Mock()
        
        success, error = export_srt_with_diff(
            config=Mock(),
            video_path=Path("/test/video.mp4"),
            output_path=Path("/test/output.srt"),
            diff_data=Mock(),
            transcription_result=Mock(),
            time_mapper=mock_time_mapper,
            remove_silence=True
        )
        
        assert success is True
        assert error is None
        
        # 正しいメソッドが呼ばれたか確認
        mock_exporter.export_from_diff_with_silence_removal.assert_called_once()
        call_args = mock_exporter.export_from_diff_with_silence_removal.call_args[1]
        assert call_args["time_mapper"] == mock_time_mapper


class TestGenerateExportPaths:
    """エクスポートパス生成のテスト"""
    
    @patch('utils.export_helpers.get_unique_path')
    def test_generate_paths_xml_only(self, mock_get_unique):
        """XMLのみのパス生成"""
        mock_get_unique.return_value = Path("/project/test_TextffCut_silence.fcpxml")
        
        paths = generate_export_paths(
            project_path=Path("/project"),
            base_name="test",
            type_suffix="silence",
            export_srt=False
        )
        
        assert "xml" in paths
        assert "srt" not in paths
        assert paths["xml"] == Path("/project/test_TextffCut_silence.fcpxml")
    
    @patch('utils.export_helpers.get_unique_path')
    def test_generate_paths_with_srt(self, mock_get_unique):
        """XMLとSRT両方のパス生成"""
        mock_get_unique.return_value = Path("/project/test_TextffCut_silence(2).fcpxml")
        
        paths = generate_export_paths(
            project_path=Path("/project"),
            base_name="test",
            type_suffix="silence",
            export_srt=True
        )
        
        assert "xml" in paths
        assert "srt" in paths
        # SRTは同じ連番を使用
        assert paths["srt"] == Path("/project/test_TextffCut_silence(2).srt")


class TestFormatExportMessage:
    """エクスポートメッセージのフォーマットテスト"""
    
    @patch('utils.path_helpers.get_display_path')
    @patch('utils.time_utils.format_time')
    def test_format_message_basic(self, mock_format_time, mock_get_display):
        """基本的なメッセージフォーマット"""
        mock_get_display.return_value = "/display/path.fcpxml"
        mock_format_time.return_value = "00:30"
        
        message = format_export_success_message(
            format_name="FCPXML",
            output_path=Path("/test/output.fcpxml"),
            timeline_duration=30.0
        )
        
        assert "✅ FCPXMLを生成しました" in message
        assert "FCPXML: /display/path.fcpxml" in message
        assert "タイムライン長: 00:30" in message
    
    @patch('utils.path_helpers.get_display_path')
    def test_format_message_with_srt_success(self, mock_get_display):
        """SRT成功時のメッセージ"""
        mock_get_display.side_effect = ["/display/xml.fcpxml", "/display/srt.srt"]
        
        message = format_export_success_message(
            format_name="FCPXML",
            output_path=Path("/test/output.fcpxml"),
            srt_path=Path("/test/output.srt"),
            srt_success=True
        )
        
        assert "SRT字幕: /display/srt.srt" in message
        assert "⚠️" not in message
    
    @patch('utils.path_helpers.get_display_path')
    def test_format_message_with_srt_failure(self, mock_get_display):
        """SRT失敗時のメッセージ"""
        mock_get_display.return_value = "/display/xml.fcpxml"
        
        message = format_export_success_message(
            format_name="FCPXML",
            output_path=Path("/test/output.fcpxml"),
            srt_path=Path("/test/output.srt"),
            srt_success=False
        )
        
        assert "⚠️ SRT字幕の生成に失敗" in message