"""
MainのMVP統合テスト

メイン画面のMVP実装が正しく動作することを確認する統合テストです。
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from core.error_handling import ErrorHandler
from infrastructure.ui.session_manager import SessionManager
from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.presenters.main import MainPresenter
from presentation.presenters.sidebar import SidebarPresenter
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.presenters.transcription import TranscriptionPresenter
from presentation.presenters.video_input import VideoInputPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel
from presentation.view_models.main import MainViewModel
from presentation.view_models.sidebar import SidebarViewModel
from presentation.view_models.text_editor import TextEditorViewModel
from presentation.view_models.transcription import TranscriptionViewModel
from presentation.view_models.video_input import VideoInputViewModel


class TestMainMVPIntegration:
    """Main MVP統合テストクラス"""

    @pytest.fixture
    def mock_dependencies(self):
        """依存関係のモック"""
        return {
            "file_gateway": Mock(),
            "video_processor_gateway": Mock(),
            "transcription_gateway": Mock(),
            "text_processor_gateway": Mock(),
            "video_export_gateway": Mock(),
            "fcpxml_export_gateway": Mock(),
            "edl_export_gateway": Mock(),
            "srt_export_gateway": Mock(),
            "transcribe_use_case": Mock(),
            "load_cache_use_case": Mock(),
            "error_handler": ErrorHandler(),
            "session_manager": SessionManager(),
        }

    @pytest.fixture
    def presenters(self, mock_dependencies):
        """各Presenterのセットアップ"""
        # ViewModels
        video_input_vm = VideoInputViewModel()
        transcription_vm = TranscriptionViewModel()
        text_editor_vm = TextEditorViewModel()
        export_settings_vm = ExportSettingsViewModel()
        sidebar_vm = SidebarViewModel()
        main_vm = MainViewModel()

        # Presenters
        video_input_presenter = VideoInputPresenter(
            view_model=video_input_vm,
            file_gateway=mock_dependencies["file_gateway"],
            video_gateway=mock_dependencies["video_processor_gateway"],
        )

        transcription_presenter = TranscriptionPresenter(
            view_model=transcription_vm,
            transcribe_use_case=mock_dependencies["transcribe_use_case"],
            load_cache_use_case=mock_dependencies["load_cache_use_case"],
            file_gateway=mock_dependencies["file_gateway"],
            transcription_gateway=mock_dependencies["transcription_gateway"],
            error_handler=mock_dependencies["error_handler"],
            session_manager=mock_dependencies["session_manager"],
        )

        text_editor_presenter = TextEditorPresenter(
            view_model=text_editor_vm,
            text_processor_gateway=mock_dependencies["text_processor_gateway"],
            error_handler=mock_dependencies["error_handler"],
        )

        export_settings_presenter = ExportSettingsPresenter(
            view_model=export_settings_vm,
            video_processor_gateway=mock_dependencies["video_processor_gateway"],
            video_export_gateway=mock_dependencies["video_export_gateway"],
            fcpxml_export_gateway=mock_dependencies["fcpxml_export_gateway"],
            edl_export_gateway=mock_dependencies["edl_export_gateway"],
            srt_export_gateway=mock_dependencies["srt_export_gateway"],
            session_manager=mock_dependencies["session_manager"],
            error_handler=mock_dependencies["error_handler"],
        )

        sidebar_presenter = SidebarPresenter(
            view_model=sidebar_vm,
            session_manager=mock_dependencies["session_manager"],
            file_gateway=mock_dependencies["file_gateway"],
            error_handler=mock_dependencies["error_handler"],
        )

        main_presenter = MainPresenter(
            view_model=main_vm,
            video_input_presenter=video_input_presenter,
            transcription_presenter=transcription_presenter,
            text_editor_presenter=text_editor_presenter,
            export_settings_presenter=export_settings_presenter,
            session_manager=mock_dependencies["session_manager"],
            error_handler=mock_dependencies["error_handler"],
        )

        return {
            "main": main_presenter,
            "sidebar": sidebar_presenter,
            "video_input": video_input_presenter,
            "transcription": transcription_presenter,
            "text_editor": text_editor_presenter,
            "export_settings": export_settings_presenter,
        }

    def test_initial_state(self, presenters):
        """初期状態の確認"""
        main_presenter = presenters["main"]

        # MainViewModelの初期状態
        assert main_presenter.view_model.is_initialized
        assert main_presenter.view_model.current_step == "video_input"
        assert not main_presenter.view_model.video_input_completed
        assert not main_presenter.view_model.transcription_completed
        assert not main_presenter.view_model.text_edit_completed
        assert not main_presenter.view_model.export_completed
        assert main_presenter.view_model.workflow_progress == 0.0

    def test_workflow_progression(self, presenters, mock_dependencies):
        """ワークフローの進行テスト"""
        main_presenter = presenters["main"]
        video_input_presenter = presenters["video_input"]

        # 動画選択
        test_video = Path("/test/video.mp4")
        mock_dependencies["file_gateway"].get_file_info.return_value = {"size": 1000000, "duration": 60.0}
        mock_dependencies["video_processor_gateway"].get_video_info.return_value = {
            "duration": 60.0,
            "fps": 30.0,
            "width": 1920,
            "height": 1080,
        }

        # VideoInputPresenterで動画を選択
        video_input_presenter.handle_file_selection(str(test_video))

        # MainViewModelが更新されることを確認
        assert main_presenter.view_model.video_input_completed
        assert main_presenter.view_model.video_path == test_video
        assert main_presenter.view_model.video_duration == 60.0
        assert main_presenter.view_model.current_step == "transcription"
        assert main_presenter.view_model.workflow_progress == 0.25

    def test_step_navigation(self, presenters):
        """ステップ間のナビゲーションテスト"""
        main_presenter = presenters["main"]

        # 前提条件を設定
        main_presenter.view_model.complete_video_input(Path("/test/video.mp4"), 60.0)
        main_presenter.view_model.complete_transcription()

        # テキスト編集ステップに移動
        main_presenter.navigate_to_step("text_edit")
        assert main_presenter.view_model.current_step == "text_edit"

        # 戻ることも可能
        main_presenter.navigate_to_step("transcription")
        assert main_presenter.view_model.current_step == "transcription"

        # 条件を満たさないステップには移動できない
        main_presenter.view_model.text_edit_completed = False
        main_presenter.navigate_to_step("export")
        assert main_presenter.view_model.current_step == "transcription"  # 移動していない
        assert main_presenter.view_model.has_error

    def test_sidebar_integration(self, presenters):
        """サイドバーとの統合テスト"""
        sidebar_presenter = presenters["sidebar"]

        # 設定の更新
        sidebar_presenter.toggle_silence_removal(True)
        sidebar_presenter.update_silence_threshold(-40.0)

        assert sidebar_presenter.view_model.remove_silence_enabled
        assert sidebar_presenter.view_model.silence_threshold == -40.0

        # API設定
        sidebar_presenter.toggle_api_mode(True)
        sidebar_presenter.set_api_key("sk-test-key")

        assert sidebar_presenter.view_model.use_api
        assert sidebar_presenter.view_model.api_key == "sk-test-key"
        assert sidebar_presenter.view_model.api_configured

    def test_error_propagation(self, presenters):
        """エラーの伝播テスト"""
        main_presenter = presenters["main"]

        # エラーを設定
        test_error = Exception("Test error")
        main_presenter._handle_error("テスト処理", test_error)

        # MainViewModelにエラーが設定される
        assert main_presenter.view_model.has_error
        assert "システムエラーが発生しました" in main_presenter.view_model.error_message
        assert main_presenter.view_model.error_context == "テスト処理"

    def test_workflow_reset(self, presenters, mock_dependencies):
        """ワークフローリセットのテスト"""
        main_presenter = presenters["main"]

        # ワークフローを進める
        main_presenter.view_model.complete_video_input(Path("/test/video.mp4"), 60.0)
        main_presenter.view_model.complete_transcription()
        main_presenter.view_model.complete_text_edit()

        # リセット
        main_presenter.reset_workflow()

        # すべてがリセットされる
        assert main_presenter.view_model.current_step == "video_input"
        assert not main_presenter.view_model.video_input_completed
        assert not main_presenter.view_model.transcription_completed
        assert not main_presenter.view_model.text_edit_completed
        assert main_presenter.view_model.video_path is None
        assert main_presenter.view_model.workflow_progress == 0.0

        # SessionManagerもクリアされる
        mock_dependencies["session_manager"].clear.assert_called_once()

    def test_presenter_initialization(self, presenters):
        """各ステップの初期化テスト"""
        main_presenter = presenters["main"]

        # 各ステップを初期化
        main_presenter.initialize_step("video_input")
        main_presenter.initialize_step("transcription")
        main_presenter.initialize_step("text_edit")
        main_presenter.initialize_step("export")

        # エラーが発生しないことを確認
        assert not main_presenter.view_model.has_error

    def test_workflow_validation(self, presenters):
        """ワークフロー状態の検証テスト"""
        main_presenter = presenters["main"]

        # 正常な状態
        main_presenter.view_model.complete_video_input(Path("/test/video.mp4"), 60.0)
        main_presenter.view_model.complete_transcription()
        main_presenter.view_model.complete_text_edit()

        assert main_presenter.validate_workflow_state()

        # 不整合な状態を作る
        main_presenter.view_model.transcription_completed = True
        main_presenter.view_model.video_input_completed = False

        assert not main_presenter.validate_workflow_state()

    def test_recovery_functionality(self, presenters, mock_dependencies):
        """リカバリー機能のテスト"""
        sidebar_presenter = presenters["sidebar"]

        # リカバリーファイルのモック
        with tempfile.TemporaryDirectory() as temp_dir:
            recovery_dir = Path(temp_dir) / "recovery"
            recovery_dir.mkdir()
            sidebar_presenter.recovery_dir = recovery_dir

            # リカバリー状態を保存
            mock_dependencies["session_manager"].get.side_effect = lambda key, default=None: {
                "current_step": "text_edit",
                "video_path": None,
                "adjusted_time_ranges": None,
            }.get(key, default)

            mock_dependencies["session_manager"].get_video_path.return_value = "/test/video.mp4"
            mock_dependencies["session_manager"].get_transcription_result.return_value = {"text": "test"}
            mock_dependencies["session_manager"].get_edited_text.return_value = "edited text"
            mock_dependencies["session_manager"].get_time_ranges.return_value = []

            success = sidebar_presenter.save_recovery_state()
            assert success

            # リカバリーファイルが作成される
            recovery_files = list(recovery_dir.glob("recovery_*.json"))
            assert len(recovery_files) == 1

    def test_complete_workflow(self, presenters, mock_dependencies):
        """完全なワークフローのテスト"""
        main_presenter = presenters["main"]

        # 1. 動画選択
        video_path = Path("/test/video.mp4")
        main_presenter.view_model.complete_video_input(video_path, 60.0)
        assert main_presenter.view_model.workflow_progress == 0.25

        # 2. 文字起こし
        main_presenter.view_model.complete_transcription()
        assert main_presenter.view_model.workflow_progress == 0.5

        # 3. テキスト編集
        main_presenter.view_model.complete_text_edit()
        assert main_presenter.view_model.workflow_progress == 0.75

        # 4. エクスポート
        main_presenter.view_model.complete_export()
        assert main_presenter.view_model.workflow_progress == 1.0

        # すべてのステップが完了
        assert main_presenter.view_model.video_input_completed
        assert main_presenter.view_model.transcription_completed
        assert main_presenter.view_model.text_edit_completed
        assert main_presenter.view_model.export_completed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
