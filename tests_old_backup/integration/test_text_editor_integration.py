"""
TextEditor機能の統合テスト

実際のコンポーネントを使用した統合的な動作確認
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import streamlit as st

from di.bootstrap import bootstrap_di
from domain.entities import TranscriptionResult, TranscriptionSegment, Word
from presentation.views.text_editor import TextEditorView


class TestTextEditorIntegration:
    """TextEditor機能の統合テスト"""

    @pytest.fixture
    def container(self):
        """DIコンテナ"""
        return bootstrap_di()

    @pytest.fixture
    def sample_transcription(self):
        """サンプルの文字起こし結果"""
        words1 = [
            Word(word="本日は", start=0.0, end=0.5),
            Word(word="晴天", start=0.5, end=1.0),
            Word(word="なり", start=1.0, end=1.3),
        ]
        words2 = [
            Word(word="明日も", start=2.0, end=2.5),
            Word(word="良い", start=2.5, end=2.8),
            Word(word="天気", start=2.8, end=3.2),
        ]

        segments = [
            TranscriptionSegment(id=str(uuid4()), start=0.0, end=1.3, text="本日は晴天なり", words=words1),
            TranscriptionSegment(id=str(uuid4()), start=2.0, end=3.2, text="明日も良い天気", words=words2),
        ]

        return TranscriptionResult(
            id=str(uuid4()),
            segments=segments,
            language="ja",
            model_size="base",
            original_audio_path="/test/audio.wav",
            processing_time=2.0,
        )

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    @patch("streamlit.container")
    @patch("streamlit.info")
    @patch("streamlit.error")
    @patch("streamlit.success")
    @patch("streamlit.button")
    @patch("streamlit.checkbox")
    @patch("streamlit.expander")
    @patch("streamlit.text")
    @patch("streamlit.audio")
    @patch("streamlit.session_state", new_callable=dict)
    def test_complete_workflow(
        self,
        mock_session_state,
        mock_audio,
        mock_text,
        mock_expander,
        mock_checkbox,
        mock_button,
        mock_success,
        mock_error,
        mock_info,
        mock_container_func,
        mock_caption,
        mock_markdown,
        mock_columns,
        container,
        sample_transcription,
    ):
        """完全なワークフローのテスト"""
        # Streamlitのモックを設定
        mock_columns.return_value = [MagicMock(), MagicMock()]
        mock_container_func.return_value.__enter__ = MagicMock()
        mock_container_func.return_value.__exit__ = MagicMock()
        mock_expander.return_value.__enter__ = MagicMock()
        mock_expander.return_value.__exit__ = MagicMock()

        # セッション状態を設定
        st.session_state = mock_session_state

        # Presenterを取得
        presenter = container.presentation.text_editor_presenter()

        # Viewを作成
        view = TextEditorView(presenter)

        # show_diff_viewerとshow_text_editorをモック
        with patch("presentation.views.text_editor.show_diff_viewer") as mock_diff_viewer:
            with patch(
                "presentation.views.text_editor.show_text_editor", return_value="本日は晴天なり"
            ) as mock_text_editor:
                # 初回レンダリング
                result = view.render(sample_transcription, Path("/test/video.mp4"))

                # 基本的な確認
                assert mock_diff_viewer.called
                assert mock_text_editor.called
                assert result is not None

        # 更新ボタンのクリックをシミュレート
        mock_button.return_value = True
        mock_session_state["text_editor_value"] = "本日は晴天"

        with patch("presentation.views.text_editor.show_diff_viewer"):
            with patch("presentation.views.text_editor.show_text_editor", return_value="本日は晴天"):
                with patch("streamlit.rerun"):
                    result = view.render(sample_transcription, Path("/test/video.mp4"))

        # セッション状態に保存されたことを確認
        assert "edited_text" in mock_session_state
        assert mock_session_state["edited_text"] == "本日は晴天"

    def test_error_scenarios(self, container, sample_transcription):
        """エラーシナリオのテスト"""
        presenter = container.presentation.text_editor_presenter()
        view = TextEditorView(presenter)

        # 無効な文字起こし結果でのテスト
        invalid_transcription = TranscriptionResult(
            id=str(uuid4()),
            segments=[TranscriptionSegment(id=str(uuid4()), text="", start=0.0, end=0.0, words=[])],
            language="ja",
            model_size="base",
            original_audio_path="/test/audio.wav",
            processing_time=0.0,
        )

        with patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
            with patch("streamlit.info") as mock_info:
                with patch("presentation.views.text_editor.show_text_editor", return_value=""):
                    result = view.render(invalid_transcription, Path("/test/video.mp4"))

                # エラー表示を確認
                mock_info.assert_called_with("文字起こし結果がありません")

    def test_boundary_adjustment_mode(self, container, sample_transcription):
        """境界調整モードのテスト"""
        presenter = container.presentation.text_editor_presenter()

        # 境界調整モードでテキストを処理
        st.session_state = {"boundary_adjustment_mode": True}

        with patch("streamlit.session_state", st.session_state):
            presenter.initialize(sample_transcription)
            presenter.apply_boundary_adjustment_markers("本日は晴天なり")

            # マーカーが挿入されていることを確認
            assert "[<" in presenter.view_model.edited_text
            assert ">]" in presenter.view_model.edited_text

    def test_separator_processing(self, container, sample_transcription):
        """区切り文字処理のテスト"""
        presenter = container.presentation.text_editor_presenter()
        presenter.initialize(sample_transcription)

        # 区切り文字付きテキストを処理
        separated_text = "本日は晴天\n---\n明日も良い"
        presenter.update_edited_text(separated_text)

        # セクションが正しく分割されていることを確認
        assert presenter.view_model.separator == "---"
        assert len(presenter.view_model.sections) == 2
        assert presenter.view_model.sections[0] == "本日は晴天"
        assert presenter.view_model.sections[1] == "明日も良い"
