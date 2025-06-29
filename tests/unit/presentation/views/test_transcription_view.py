"""
TranscriptionViewのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path
import streamlit as st

from presentation.views.transcription import TranscriptionView, show_transcription_controls
from presentation.view_models.transcription import TranscriptionViewModel, TranscriptionCache
from presentation.presenters.transcription import TranscriptionPresenter


class TestTranscriptionView:
    """TranscriptionViewのテスト"""
    
    @pytest.fixture
    def mock_presenter(self):
        """モックのPresenter"""
        presenter = Mock(spec=TranscriptionPresenter)
        
        # ViewModelのモック
        vm = TranscriptionViewModel()
        vm.video_duration_minutes = 10.0
        vm.video_duration_text = "10:00"
        vm.model_size = "medium"  # model_textではなくmodel_size
        presenter.view_model = vm
        
        # メソッドのモック
        presenter.initialize_with_video = Mock()
        presenter.set_processing_mode = Mock()
        presenter.select_cache = Mock()
        presenter.load_selected_cache = Mock(return_value=True)
        presenter.start_transcription = Mock(return_value=True)
        presenter.cancel_transcription = Mock()
        presenter.get_transcription_result = Mock(return_value={"segments": []})
        presenter.set_api_key = Mock()
        
        return presenter
    
    @pytest.fixture
    def view(self, mock_presenter):
        """テスト用View"""
        return TranscriptionView(mock_presenter)
    
    @patch('streamlit.container')
    @patch('streamlit.markdown')
    @patch('streamlit.selectbox')
    @patch('streamlit.button')
    @patch('streamlit.success')
    @patch('streamlit.rerun')
    def test_render_with_cache(self, mock_rerun, mock_success, mock_button,
                               mock_selectbox, mock_markdown, mock_container,
                               view, mock_presenter):
        """キャッシュ利用時のレンダリングテスト"""
        # キャッシュを設定
        cache = TranscriptionCache(
            file_path=Path("/test/cache.json"),
            mode="local",
            model_size="medium",
            modified_time=1234567890.0,
            is_api=False
        )
        view.view_model.available_caches = [cache]
        
        # 選択とボタンクリックをシミュレート
        mock_selectbox.return_value = "localモード - medium | 2009-02-14 08:31"
        mock_button.return_value = True
        
        video_path = Path("/test/video.mp4")
        use_cache, run_new, result = view.render(video_path)
        
        # 結果の確認
        assert use_cache is True
        assert run_new is False
        assert result is not None
        
        # メソッドが呼ばれたか確認
        mock_presenter.initialize_with_video.assert_called_once_with(video_path)
        mock_presenter.select_cache.assert_called_once()
        mock_presenter.load_selected_cache.assert_called_once()
        mock_success.assert_called_once()
        mock_rerun.assert_called_once()
    
    @patch('streamlit.columns')
    @patch('streamlit.markdown')
    @patch('streamlit.radio')
    @patch('streamlit.button')
    @patch('streamlit.caption')
    @patch('streamlit.rerun')
    def test_render_new_transcription(self, mock_rerun, mock_caption, mock_button,
                                     mock_radio, mock_markdown, mock_columns,
                                     view, mock_presenter):
        """新規文字起こしのレンダリングテスト"""
        # カラムのモック（コンテキストマネージャーをサポート）
        col_mocks = []
        for i in range(4):
            col_mock = MagicMock()
            col_mock.__enter__ = Mock(return_value=None)
            col_mock.__exit__ = Mock(return_value=None)
            col_mocks.append(col_mock)
        mock_columns.return_value = col_mocks
        
        # ラジオボタンでAPIモードを選択
        mock_radio.return_value = "🌐 API"
        
        # 実行ボタンクリック
        mock_button.return_value = True
        
        # APIキーを設定
        view.view_model.api_key = "sk-test"
        view.view_model.should_run = True
        
        video_path = Path("/test/video.mp4")
        use_cache, run_new, result = view.render(video_path)
        
        # 結果の確認
        assert run_new is True
        
        # メソッドが呼ばれたか確認
        mock_presenter.set_processing_mode.assert_called_with(True)
        mock_rerun.assert_called()
    
    @patch('streamlit.button')
    @patch('streamlit.spinner')
    @patch('streamlit.progress')
    @patch('streamlit.empty')
    @patch('streamlit.success')
    @patch('streamlit.rerun')
    def test_show_processing_ui(self, mock_rerun, mock_success, mock_empty,
                                mock_progress, mock_spinner, mock_button,
                                view, mock_presenter):
        """処理中UIのテスト"""
        # 処理中の状態を設定
        view.view_model.should_run = True
        view.view_model.transcription_result = None  # has_resultがFalseになる
        view.view_model.progress = 0.5
        view.view_model.status_message = "処理中..."
        
        # spinnerのコンテキストマネージャーをモック
        spinner_cm = MagicMock()
        spinner_cm.__enter__ = Mock(return_value=None)
        spinner_cm.__exit__ = Mock(return_value=None)
        mock_spinner.return_value = spinner_cm
        
        # プログレスバーとステータステキストのモック
        progress_bar = Mock()
        mock_progress.return_value = progress_bar
        status_text = Mock()
        mock_empty.return_value = status_text
        
        # キャンセルボタンは押されない
        mock_button.return_value = False
        
        view._show_processing_ui()
        
        # UIコンポーネントが作成されたか確認
        mock_button.assert_called_once()
        mock_spinner.assert_called_once_with("文字起こし中...")
        mock_progress.assert_called_once()
        mock_empty.assert_called_once()
    
    def test_get_button_text(self, view):
        """ボタンテキスト生成のテスト"""
        # キャッシュなし、ローカルモード
        view.view_model.available_caches = []
        view.view_model.use_api = False
        assert view._get_button_text() == "🖥️ ローカルで文字起こしを実行する"
        
        # キャッシュなし、APIモード
        view.view_model.use_api = True
        assert view._get_button_text() == "💳 APIで文字起こしを実行する"
        
        # キャッシュあり、ローカルモード
        view.view_model.available_caches = [Mock()]
        view.view_model.use_api = False
        assert view._get_button_text() == "🖥️ 新たにローカルで文字起こしを実行する"
        
        # キャッシュあり、APIモード
        view.view_model.use_api = True
        assert view._get_button_text() == "💳 新たにAPIで文字起こしを実行する"


class TestShowTranscriptionControls:
    """show_transcription_controls関数のテスト"""
    
    @patch('presentation.views.transcription.TranscriptionView')
    def test_show_transcription_controls_with_container(self, mock_view_class):
        """コンテナ使用時のテスト"""
        # モックの設定
        mock_container = Mock()
        mock_presenter = Mock()
        mock_container.presentation.transcription_presenter.return_value = mock_presenter
        
        mock_view = Mock()
        mock_view.render.return_value = (True, False, {"result": "test"})
        mock_view_class.return_value = mock_view
        
        # 実行
        video_path = Path("/test/video.mp4")
        api_key = "sk-test"
        use_cache, run_new, result = show_transcription_controls(
            video_path=video_path,
            api_key=api_key,
            container=mock_container
        )
        
        # 結果の確認
        assert use_cache is True
        assert run_new is False
        assert result == {"result": {"result": "test"}}
        
        # メソッドが呼ばれたか確認
        mock_presenter.set_api_key.assert_called_once_with(api_key)
        mock_view.render.assert_called_once_with(video_path)
    
    def test_show_transcription_controls_without_container(self):
        """コンテナなしの場合のテスト"""
        use_cache, run_new, result = show_transcription_controls()
        
        assert use_cache is False
        assert run_new is False
        assert result is None
    
    @patch('streamlit.error')
    def test_show_transcription_controls_no_video(self, mock_error):
        """動画パスなしの場合のテスト"""
        mock_container = Mock()
        
        use_cache, run_new, result = show_transcription_controls(
            container=mock_container
        )
        
        assert use_cache is False
        assert run_new is False
        assert result is None
        mock_error.assert_called_once_with("動画ファイルが指定されていません")