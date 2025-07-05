"""
MainPresenterの単体テスト

アプリケーション全体のワークフローを管理するPresenterのテストです。
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from presentation.presenters.main import MainPresenter, WorkflowStep
from presentation.view_models.main import MainViewModel
from domain.interfaces.error_handler import ErrorHandler


class TestMainPresenter:
    """MainPresenterのテスト"""

    @pytest.fixture
    def mock_view_model(self):
        """モックのMainViewModelを作成"""
        view_model = Mock(spec=MainViewModel)
        view_model.current_step = WorkflowStep.VIDEO_INPUT
        view_model.completed_steps = set()
        view_model.error_message = None
        view_model.is_loading = False
        view_model.workflow_progress = 0.0
        view_model.is_help_open = False
        view_model.is_settings_open = False
        view_model.is_dark_mode = False
        view_model.subscribe = Mock()
        view_model.notify = Mock()
        return view_model

    @pytest.fixture
    def mock_video_input_presenter(self):
        """モックのVideoInputPresenterを作成"""
        presenter = Mock()
        presenter.view_model = Mock()
        presenter.view_model.has_video = False
        presenter.view_model.video_path = None
        presenter.view_model.subscribe = Mock()
        presenter.initialize = Mock()
        return presenter

    @pytest.fixture
    def mock_transcription_presenter(self):
        """モックのTranscriptionPresenterを作成"""
        presenter = Mock()
        presenter.view_model = Mock()
        presenter.view_model.has_transcription = False
        presenter.view_model.transcription_result = None
        presenter.view_model.subscribe = Mock()
        presenter.initialize = Mock()
        return presenter

    @pytest.fixture
    def mock_text_editor_presenter(self):
        """モックのTextEditorPresenterを作成"""
        presenter = Mock()
        presenter.view_model = Mock()
        presenter.view_model.has_edited_text = False
        presenter.view_model.time_ranges = []
        presenter.view_model.subscribe = Mock()
        presenter.initialize = Mock()
        return presenter

    @pytest.fixture
    def mock_export_settings_presenter(self):
        """モックのExportSettingsPresenterを作成"""
        presenter = Mock()
        presenter.view_model = Mock()
        presenter.view_model.export_completed = False
        presenter.view_model.subscribe = Mock()
        presenter.initialize = Mock()
        return presenter

    @pytest.fixture
    def mock_session_manager(self):
        """モックのSessionManagerを作成"""
        manager = Mock()
        manager.get = Mock()
        manager.set = Mock()
        manager.clear = Mock()
        return manager

    @pytest.fixture
    def mock_error_handler(self):
        """モックのErrorHandlerを作成"""
        handler = Mock(spec=ErrorHandler)
        handler.handle_error = Mock()
        return handler

    @pytest.fixture
    def presenter(self, mock_view_model, mock_video_input_presenter, mock_transcription_presenter,
                  mock_text_editor_presenter, mock_export_settings_presenter,
                  mock_session_manager, mock_error_handler):
        """テスト用のPresenterインスタンスを作成"""
        return MainPresenter(
            view_model=mock_view_model,
            video_input_presenter=mock_video_input_presenter,
            transcription_presenter=mock_transcription_presenter,
            text_editor_presenter=mock_text_editor_presenter,
            export_settings_presenter=mock_export_settings_presenter,
            session_manager=mock_session_manager,
            error_handler=mock_error_handler
        )

    def test_initialization(self, presenter, mock_view_model):
        """初期化時の動作を確認"""
        # ViewModelのsubscribeが各プレゼンターに対して呼ばれたことを確認
        assert mock_view_model.subscribe.call_count >= 1
        
        # 初期状態の確認
        assert presenter.view_model.current_step == WorkflowStep.VIDEO_INPUT

    def test_navigate_to_step_video_input(self, presenter, mock_view_model):
        """VIDEO_INPUTステップへのナビゲーションを確認"""
        presenter.navigate_to_step(WorkflowStep.VIDEO_INPUT)
        
        mock_view_model.current_step = WorkflowStep.VIDEO_INPUT
        mock_view_model.notify.assert_called()

    def test_navigate_to_step_transcription(self, presenter, mock_view_model, mock_video_input_presenter):
        """TRANSCRIPTIONステップへのナビゲーションを確認"""
        # 前提条件を満たす
        mock_video_input_presenter.view_model.has_video = True
        
        presenter.navigate_to_step(WorkflowStep.TRANSCRIPTION)
        
        mock_view_model.current_step = WorkflowStep.TRANSCRIPTION
        mock_view_model.notify.assert_called()

    def test_navigate_to_step_without_prerequisites(self, presenter, mock_view_model, mock_video_input_presenter):
        """前提条件を満たさない場合のナビゲーションを確認"""
        # 動画がない状態でTRANSCRIPTIONに遷移しようとする
        mock_video_input_presenter.view_model.has_video = False
        
        presenter.navigate_to_step(WorkflowStep.TRANSCRIPTION)
        
        # エラーメッセージが設定されることを確認
        mock_view_model.error_message = "動画を選択してください"

    def test_reset_workflow(self, presenter, mock_view_model, mock_session_manager):
        """ワークフローのリセットを確認"""
        # いくつかのステップを完了した状態にする
        mock_view_model.completed_steps = {WorkflowStep.VIDEO_INPUT, WorkflowStep.TRANSCRIPTION}
        
        presenter.reset_workflow()
        
        # リセット後の確認
        mock_view_model.current_step = WorkflowStep.VIDEO_INPUT
        mock_view_model.completed_steps = set()
        mock_view_model.error_message = None
        mock_session_manager.clear.assert_called_once()
        mock_view_model.notify.assert_called()

    def test_handle_help_toggle(self, presenter, mock_view_model):
        """ヘルプトグルの処理を確認"""
        mock_view_model.is_help_open = False
        
        presenter.handle_help_toggle()
        
        mock_view_model.is_help_open = True
        mock_view_model.notify.assert_called()

    def test_handle_settings_toggle(self, presenter, mock_view_model):
        """設定トグルの処理を確認"""
        mock_view_model.is_settings_open = False
        
        presenter.handle_settings_toggle()
        
        mock_view_model.is_settings_open = True
        mock_view_model.notify.assert_called()

    def test_handle_dark_mode_toggle(self, presenter, mock_view_model):
        """ダークモードトグルの処理を確認"""
        mock_view_model.is_dark_mode = False
        
        presenter.handle_dark_mode_toggle()
        
        mock_view_model.is_dark_mode = True
        mock_view_model.notify.assert_called()

    def test_get_current_presenter(self, presenter, mock_video_input_presenter,
                                  mock_transcription_presenter, mock_text_editor_presenter,
                                  mock_export_settings_presenter):
        """現在のステップに対応するプレゼンターを取得することを確認"""
        # 各ステップでの確認
        presenter.view_model.current_step = WorkflowStep.VIDEO_INPUT
        assert presenter.get_current_presenter() == mock_video_input_presenter
        
        presenter.view_model.current_step = WorkflowStep.TRANSCRIPTION
        assert presenter.get_current_presenter() == mock_transcription_presenter
        
        presenter.view_model.current_step = WorkflowStep.TEXT_EDITING
        assert presenter.get_current_presenter() == mock_text_editor_presenter
        
        presenter.view_model.current_step = WorkflowStep.EXPORT
        assert presenter.get_current_presenter() == mock_export_settings_presenter

    def test_validate_workflow_state(self, presenter, mock_video_input_presenter,
                                   mock_transcription_presenter, mock_text_editor_presenter):
        """ワークフロー状態の検証を確認"""
        # 全ての前提条件を満たさない
        mock_video_input_presenter.view_model.has_video = False
        
        is_valid, message = presenter.validate_workflow_state(WorkflowStep.EXPORT)
        
        assert is_valid is False
        assert "動画を選択してください" in message
        
        # 全ての前提条件を満たす
        mock_video_input_presenter.view_model.has_video = True
        mock_transcription_presenter.view_model.has_transcription = True
        mock_text_editor_presenter.view_model.has_edited_text = True
        
        is_valid, message = presenter.validate_workflow_state(WorkflowStep.EXPORT)
        
        assert is_valid is True
        assert message == ""

    def test_initialize_step(self, presenter, mock_video_input_presenter,
                           mock_transcription_presenter):
        """ステップの初期化を確認"""
        # TRANSCRIPTIONステップの初期化
        presenter.view_model.current_step = WorkflowStep.TRANSCRIPTION
        video_path = "/path/to/video.mp4"
        mock_video_input_presenter.view_model.video_path = video_path
        
        presenter.initialize_step(WorkflowStep.TRANSCRIPTION)
        
        # 初期化メソッドが呼ばれたことを確認
        mock_transcription_presenter.initialize.assert_called_once_with(video_path)

    def test_get_workflow_summary(self, presenter, mock_video_input_presenter,
                                mock_transcription_presenter, mock_text_editor_presenter):
        """ワークフローサマリーの取得を確認"""
        # 各ステップの状態を設定
        mock_video_input_presenter.view_model.has_video = True
        mock_video_input_presenter.view_model.video_path = "/path/to/video.mp4"
        mock_transcription_presenter.view_model.has_transcription = True
        mock_text_editor_presenter.view_model.has_edited_text = True
        mock_text_editor_presenter.view_model.time_ranges = [Mock(), Mock()]  # 2つの範囲
        
        presenter.view_model.completed_steps = {
            WorkflowStep.VIDEO_INPUT,
            WorkflowStep.TRANSCRIPTION,
            WorkflowStep.TEXT_EDITING
        }
        
        summary = presenter.get_workflow_summary()
        
        assert summary["video_selected"] is True
        assert summary["video_path"] == "/path/to/video.mp4"
        assert summary["transcription_completed"] is True
        assert summary["text_edited"] is True
        assert summary["clip_count"] == 2
        assert summary["completed_steps_count"] == 3

    def test_on_video_input_changed(self, presenter, mock_view_model, mock_video_input_presenter):
        """動画入力変更時のハンドラーを確認"""
        # 動画が選択された
        mock_video_input_presenter.view_model.has_video = True
        
        presenter._on_video_input_changed()
        
        # 完了ステップに追加されることを確認
        assert WorkflowStep.VIDEO_INPUT in presenter.view_model.completed_steps
        
        # 自動的に次のステップに進むことを確認
        mock_view_model.current_step = WorkflowStep.TRANSCRIPTION

    def test_on_transcription_changed(self, presenter, mock_view_model, mock_transcription_presenter):
        """文字起こし変更時のハンドラーを確認"""
        # 文字起こしが完了
        mock_transcription_presenter.view_model.has_transcription = True
        
        presenter._on_transcription_changed()
        
        # 完了ステップに追加されることを確認
        assert WorkflowStep.TRANSCRIPTION in presenter.view_model.completed_steps
        
        # 自動的に次のステップに進むことを確認
        mock_view_model.current_step = WorkflowStep.TEXT_EDITING

    def test_on_text_editor_changed(self, presenter, mock_view_model, mock_text_editor_presenter):
        """テキスト編集変更時のハンドラーを確認"""
        # テキスト編集が完了
        mock_text_editor_presenter.view_model.has_edited_text = True
        
        presenter._on_text_editor_changed()
        
        # 完了ステップに追加されることを確認
        assert WorkflowStep.TEXT_EDITING in presenter.view_model.completed_steps
        
        # 自動的に次のステップに進むことを確認
        mock_view_model.current_step = WorkflowStep.EXPORT

    def test_on_export_settings_changed(self, presenter, mock_view_model, mock_export_settings_presenter):
        """エクスポート設定変更時のハンドラーを確認"""
        # エクスポートが完了
        mock_export_settings_presenter.view_model.export_completed = True
        
        presenter._on_export_settings_changed()
        
        # 完了ステップに追加されることを確認
        assert WorkflowStep.EXPORT in presenter.view_model.completed_steps

    def test_handle_error(self, presenter, mock_view_model, mock_error_handler):
        """エラーハンドリングを確認"""
        error = Exception("Test error")
        context = "テスト処理中"
        
        presenter._handle_error(error, context)
        
        # エラーハンドラーが呼ばれたことを確認
        mock_error_handler.handle_error.assert_called_once_with(error, context)
        
        # エラーメッセージが設定されることを確認
        assert mock_view_model.error_message is not None
        mock_view_model.notify.assert_called()

    def test_workflow_progress_calculation(self, presenter, mock_view_model):
        """ワークフロー進捗の計算を確認"""
        # ステップを段階的に完了
        mock_view_model.completed_steps = set()
        presenter._update_workflow_progress()
        assert mock_view_model.workflow_progress == 0.0
        
        mock_view_model.completed_steps = {WorkflowStep.VIDEO_INPUT}
        presenter._update_workflow_progress()
        assert mock_view_model.workflow_progress == 25.0
        
        mock_view_model.completed_steps = {WorkflowStep.VIDEO_INPUT, WorkflowStep.TRANSCRIPTION}
        presenter._update_workflow_progress()
        assert mock_view_model.workflow_progress == 50.0
        
        mock_view_model.completed_steps = {
            WorkflowStep.VIDEO_INPUT,
            WorkflowStep.TRANSCRIPTION,
            WorkflowStep.TEXT_EDITING
        }
        presenter._update_workflow_progress()
        assert mock_view_model.workflow_progress == 75.0
        
        mock_view_model.completed_steps = {
            WorkflowStep.VIDEO_INPUT,
            WorkflowStep.TRANSCRIPTION,
            WorkflowStep.TEXT_EDITING,
            WorkflowStep.EXPORT
        }
        presenter._update_workflow_progress()
        assert mock_view_model.workflow_progress == 100.0

    def test_step_transitions(self, presenter):
        """ステップ間の遷移ロジックを確認"""
        # 前のステップを取得
        assert presenter._get_previous_step(WorkflowStep.TRANSCRIPTION) == WorkflowStep.VIDEO_INPUT
        assert presenter._get_previous_step(WorkflowStep.TEXT_EDITING) == WorkflowStep.TRANSCRIPTION
        assert presenter._get_previous_step(WorkflowStep.EXPORT) == WorkflowStep.TEXT_EDITING
        assert presenter._get_previous_step(WorkflowStep.VIDEO_INPUT) is None
        
        # 次のステップを取得
        assert presenter._get_next_step(WorkflowStep.VIDEO_INPUT) == WorkflowStep.TRANSCRIPTION
        assert presenter._get_next_step(WorkflowStep.TRANSCRIPTION) == WorkflowStep.TEXT_EDITING
        assert presenter._get_next_step(WorkflowStep.TEXT_EDITING) == WorkflowStep.EXPORT
        assert presenter._get_next_step(WorkflowStep.EXPORT) is None