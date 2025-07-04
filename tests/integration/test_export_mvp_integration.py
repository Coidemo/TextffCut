"""
ExportSettings MVP統合テスト

エクスポート機能のMVP実装が正しく動作することを確認する統合テストです。
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from core.error_handling import ErrorHandler
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel


class TestExportSettingsMVPIntegration:
    """ExportSettings MVP統合テストクラス"""

    @pytest.fixture
    def mock_gateways(self):
        """モックゲートウェイのセットアップ"""
        return {
            "video_processor": Mock(),
            "video_export": Mock(),
            "fcpxml_export": Mock(),
            "edl_export": Mock(),
            "srt_export": Mock(),
        }

    @pytest.fixture
    def session_manager(self):
        """SessionManagerのモック"""
        manager = Mock(spec=SessionManager)
        manager.get_video_path.return_value = "/test/video.mp4"
        manager.get_transcription_result.return_value = {
            "text": "テストテキスト",
            "segments": [
                {"text": "セグメント1", "start": 0.0, "end": 5.0},
                {"text": "セグメント2", "start": 5.0, "end": 10.0},
            ],
        }
        manager.get_edited_text.return_value = "編集済みテキスト"
        manager.get_time_ranges.return_value = [Mock(start=0.0, end=5.0), Mock(start=5.0, end=10.0)]
        manager.get.return_value = None  # adjusted_time_rangesはデフォルトでNone
        return manager

    @pytest.fixture
    def presenter(self, mock_gateways, session_manager):
        """ExportSettingsPresenterのセットアップ"""
        view_model = ExportSettingsViewModel()
        error_handler = ErrorHandler()

        # ディレクトリ作成をモック
        with patch("pathlib.Path.mkdir"):
            presenter = ExportSettingsPresenter(
                view_model=view_model,
                video_processor_gateway=mock_gateways["video_processor"],
                video_export_gateway=mock_gateways["video_export"],
                fcpxml_export_gateway=mock_gateways["fcpxml_export"],
                edl_export_gateway=mock_gateways["edl_export"],
                srt_export_gateway=mock_gateways["srt_export"],
                session_manager=session_manager,
                error_handler=error_handler,
            )

        # _generate_output_pathメソッドをモック
        original_generate = presenter._generate_output_path

        def mock_generate(ext):
            with patch("pathlib.Path.mkdir"):
                return original_generate(ext)

        presenter._generate_output_path = mock_generate

        return presenter

    def test_initialize_loads_data_from_session(self, presenter, session_manager):
        """初期化時にSessionManagerからデータが読み込まれることを確認"""
        # Act
        presenter.initialize()

        # Assert
        assert presenter.view_model.video_path == Path("/test/video.mp4")
        assert presenter.view_model.transcription_result is not None
        assert presenter.view_model.edited_text == "編集済みテキスト"
        assert len(presenter.view_model.time_ranges) == 2

    def test_export_video_without_silence_removal(self, presenter, mock_gateways):
        """無音削除なしの動画エクスポート"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "video"
        presenter.view_model.remove_silence = False

        mock_gateways["video_export"].export_clips.return_value = ["/output/clip_0001.mp4", "/output/clip_0002.mp4"]

        # Act
        success = presenter.start_export()

        # Assert
        assert success
        mock_gateways["video_export"].export_clips.assert_called_once()
        assert len(presenter.view_model.export_results) == 2

    def test_export_video_with_silence_removal(self, presenter, mock_gateways):
        """無音削除ありの動画エクスポート"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "video"
        presenter.view_model.remove_silence = True
        presenter.view_model.silence_threshold = -40.0

        mock_gateways["video_processor"].remove_silence.return_value = [(0.5, 4.5), (5.5, 9.5)]
        mock_gateways["video_export"].export_clips.return_value = ["/output/clip_0001.mp4", "/output/clip_0002.mp4"]

        # Act
        success = presenter.start_export()

        # Assert
        assert success
        mock_gateways["video_processor"].remove_silence.assert_called_once()
        mock_gateways["video_export"].export_clips.assert_called_once()

    def test_export_fcpxml(self, presenter, mock_gateways):
        """FCPXMLエクスポート"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "fcpxml"

        # Act
        success = presenter.start_export()

        # Assert
        assert success
        mock_gateways["fcpxml_export"].export.assert_called_once()
        assert len(presenter.view_model.export_results) == 1

    def test_export_edl(self, presenter, mock_gateways):
        """EDLエクスポート"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "edl"

        # Act
        success = presenter.start_export()

        # Assert
        assert success
        mock_gateways["edl_export"].export.assert_called_once()
        assert len(presenter.view_model.export_results) == 1

    def test_export_srt(self, presenter, mock_gateways):
        """SRT字幕エクスポート"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "srt"
        presenter.view_model.srt_max_line_length = 30
        presenter.view_model.srt_max_lines = 2

        # Act
        success = presenter.start_export()

        # Assert
        assert success
        mock_gateways["srt_export"].export.assert_called_once()
        # SRT設定が渡されていることを確認
        call_args = mock_gateways["srt_export"].export.call_args
        # call_args[0]は位置引数、call_args[1]はキーワード引数
        settings = call_args[0][3] if len(call_args[0]) > 3 else call_args[1].get("settings")
        assert settings["max_line_length"] == 30
        assert settings["max_lines"] == 2

    def test_progress_callback_updates_view_model(self, presenter, mock_gateways):
        """進捗コールバックがViewModelを更新することを確認"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "video"
        progress_updates = []

        def capture_progress(progress, message):
            progress_updates.append((progress, message))

        # 進捗をキャプチャするようにモックを設定
        def export_clips_with_progress(*args, **kwargs):
            callback = kwargs.get("progress_callback")
            if callback:
                callback(0.5, "処理中...")
                callback(1.0, "完了")
            return ["/output/clip.mp4"]

        mock_gateways["video_export"].export_clips.side_effect = export_clips_with_progress

        # Act
        success = presenter.start_export(capture_progress)

        # Assert
        assert success
        # プログレスコールバックが呼ばれていることを確認
        # 注：wrapped_progressとcapture_progressの連携を考慮
        assert presenter.view_model.progress > 0  # 進捗が更新されている

    def test_error_handling(self, presenter, mock_gateways):
        """エラーハンドリングの確認"""
        # Arrange
        presenter.initialize()
        presenter.view_model.export_format = "video"
        mock_gateways["video_export"].export_clips.side_effect = Exception("Export failed")

        # Act
        success = presenter.start_export()

        # Assert
        assert not success
        assert presenter.view_model.error_message is not None
        # ErrorHandlerが「システムエラーが発生しました」という一般的なメッセージを返すことを考慮
        assert presenter.view_model.error_message in ["Export failed", "システムエラーが発生しました"]

    def test_adjusted_time_ranges_priority(self, presenter, session_manager):
        """調整済み時間範囲が優先されることを確認"""
        # Arrange
        adjusted_ranges = [Mock(start=1.0, end=4.0), Mock(start=6.0, end=9.0)]
        session_manager.get.return_value = adjusted_ranges

        presenter.initialize()

        # Assert
        assert presenter.view_model.adjusted_time_ranges == adjusted_ranges
        assert presenter.view_model.effective_time_ranges == adjusted_ranges

    def test_output_path_generation(self, presenter):
        """出力パス生成の確認"""
        # Arrange
        presenter.initialize()

        # Act
        with patch("pathlib.Path.mkdir"):  # ディレクトリ作成をモック
            output_path = presenter._generate_output_path("mp4")

        # Assert
        assert "video_TextffCut" in str(output_path)
        assert output_path.suffix == ".mp4"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
