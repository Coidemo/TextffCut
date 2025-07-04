"""
TextEditor MVPの網羅的なテスト

ViewModel、Presenter、Viewの統合的な動作を確認
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from domain.entities import TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType, TextDifference
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.view_models.text_editor import TextEditorViewModel, TimeRange
from presentation.views.text_editor import TextEditorView


class TestTextEditorComprehensive:
    """TextEditor機能の網羅的テスト"""

    @pytest.fixture
    def mock_transcription_result(self):
        """テスト用の文字起こし結果"""
        words = [
            Word(word="これは", start=0.0, end=0.5),
            Word(word="テスト", start=0.5, end=1.0),
            Word(word="です", start=1.0, end=1.5),
        ]
        segments = [TranscriptionSegment(id=str(uuid4()), start=0.0, end=1.5, text="これはテストです", words=words)]
        return TranscriptionResult(
            id=str(uuid4()),
            segments=segments,
            language="ja",
            model_size="base",
            original_audio_path="/test/audio.wav",
            processing_time=1.0,
        )

    @pytest.fixture
    def mock_text_processor_gateway(self):
        """モックのテキスト処理ゲートウェイ"""
        gateway = Mock()

        # find_differencesのモック
        gateway.find_differences.return_value = TextDifference(
            id=str(uuid4()),
            original_text="これはテストです",
            edited_text="これはテスト",
            differences=[(DifferenceType.UNCHANGED, "これは", None), (DifferenceType.UNCHANGED, "テスト", None)],
        )

        # get_time_rangesのモック - TimeRangeオブジェクトを返す

        gateway.get_time_ranges.return_value = [TimeRange(start=0.0, end=1.0, duration=1.0, text="")]

        # remove_boundary_markersのモック
        import re

        def remove_markers(text):
            # 正規表現でマーカーを削除
            # [<数値] と [数値>] のパターンを削除
            text = re.sub(r"\[<[\d.]+\]", "", text)
            text = re.sub(r"\[[\d.]+>\]", "", text)
            return text

        gateway.remove_boundary_markers.side_effect = remove_markers

        # extract_existing_markersのモック
        gateway.extract_existing_markers.return_value = {}

        # split_text_by_separatorのモック
        gateway.split_text_by_separator.side_effect = lambda text, sep: text.split(sep)

        return gateway

    @pytest.fixture
    def mock_error_handler(self):
        """モックのエラーハンドラー"""
        handler = Mock()
        handler.handle_error.return_value = {"user_message": "エラーが発生しました"}
        return handler

    @pytest.fixture
    def view_model(self):
        """ViewModelのインスタンス"""
        return TextEditorViewModel()

    @pytest.fixture
    def presenter(self, view_model, mock_text_processor_gateway, mock_error_handler):
        """Presenterのインスタンス"""
        return TextEditorPresenter(
            view_model=view_model, text_processor_gateway=mock_text_processor_gateway, error_handler=mock_error_handler
        )

    def test_presenter_initialization(self, presenter, mock_transcription_result):
        """Presenterの初期化テスト"""
        # 初期化を実行
        presenter.initialize(mock_transcription_result)

        # ViewModelが正しく設定されていることを確認
        assert presenter.view_model.transcription_result == mock_transcription_result
        assert presenter.view_model.full_text == "これはテストです"

    def test_text_update_flow(self, presenter, mock_transcription_result):
        """テキスト更新のフローテスト"""
        # 初期化
        presenter.initialize(mock_transcription_result)

        # テキストを更新
        edited_text = "これはテスト"
        presenter.update_edited_text(edited_text)

        # ViewModelが更新されていることを確認
        assert presenter.view_model.edited_text == edited_text
        assert presenter.view_model.char_count == len(edited_text)
        assert len(presenter.view_model.time_ranges) > 0

    def test_boundary_marker_detection(self, presenter, mock_transcription_result):
        """境界調整マーカーの検出テスト"""
        presenter.initialize(mock_transcription_result)

        # マーカー付きテキストを設定
        marked_text = "[<0.5]これは[0.3>]\n[<0.2]テスト[0.4>]"
        presenter.update_edited_text(marked_text)

        # マーカーが検出されていることを確認
        assert presenter.view_model.has_boundary_markers is True
        assert presenter.view_model.cleaned_text == "これは\nテスト"

    def test_separator_detection(self, presenter, mock_transcription_result):
        """区切り文字の検出テスト"""
        presenter.initialize(mock_transcription_result)

        # 区切り文字付きテキストを設定
        separated_text = "これは\n---\nテスト"
        presenter.update_edited_text(separated_text)

        # セクションが分割されていることを確認
        assert presenter.view_model.separator == "---"
        assert presenter.view_model.section_count == 2
        assert len(presenter.view_model.sections) == 2

    def test_timeline_adjustment(self, presenter):
        """タイムライン調整のテスト"""
        # 調整済み時間範囲を適用
        adjusted_ranges = [{"start": 0.0, "end": 0.8, "text": ""}, {"start": 1.0, "end": 1.3, "text": ""}]
        presenter.apply_timeline_adjustments(adjusted_ranges)

        # ViewModelが更新されていることを確認
        assert presenter.view_model.timeline_edited is True
        assert len(presenter.view_model.time_ranges) == 2
        assert presenter.view_model.time_ranges[0].start == 0.0
        assert presenter.view_model.time_ranges[0].end == 0.8

    def test_boundary_adjustment_marker_application(self, presenter, mock_transcription_result):
        """境界調整マーカーの適用テスト"""
        presenter.initialize(mock_transcription_result)

        # マーカーを適用
        text = "これはテスト"
        presenter.apply_boundary_adjustment_markers(text)

        # マーカーが挿入されていることを確認
        assert "[<" in presenter.view_model.edited_text
        assert ">]" in presenter.view_model.edited_text
        assert presenter.view_model.has_boundary_markers is True

    def test_error_handling(self, presenter, mock_error_handler, mock_transcription_result):
        """エラーハンドリングのテスト"""
        # まず初期化
        presenter.initialize(mock_transcription_result)

        # エラーは内部でキャッチされるため、エラーメッセージが設定されているかを確認
        # テキスト処理ゲートウェイでエラーを発生させる
        presenter.text_processor_gateway.find_differences.side_effect = Exception("Test error")

        # エラーが発生する処理を実行
        presenter.update_edited_text("テスト")

        # エラーメッセージが設定されていることを確認
        assert presenter.view_model.error_message == "テキスト処理でエラーが発生しました"

    def test_processed_data_export(self, presenter, mock_transcription_result):
        """処理済みデータのエクスポートテスト"""
        presenter.initialize(mock_transcription_result)
        presenter.update_edited_text("これはテスト")

        # 処理済みデータを取得
        processed_data = presenter.get_processed_data()

        # 必要なデータが含まれていることを確認
        assert "edited_text" in processed_data
        assert "cleaned_text" in processed_data
        assert "time_ranges" in processed_data
        assert "total_duration" in processed_data
        assert "has_boundary_markers" in processed_data
        assert "separator" in processed_data
        assert "sections" in processed_data
        assert "differences" in processed_data

        # time_rangesがタプル形式であることを確認
        assert isinstance(processed_data["time_ranges"], list)
        if processed_data["time_ranges"]:
            assert isinstance(processed_data["time_ranges"][0], tuple)
            assert len(processed_data["time_ranges"][0]) == 2

    @patch("streamlit.columns")
    @patch("streamlit.markdown")
    @patch("streamlit.caption")
    @patch("streamlit.button")
    @patch("streamlit.checkbox")
    @patch("streamlit.container")
    @patch("streamlit.info")
    @patch("streamlit.text")
    def test_view_rendering(
        self,
        mock_text,
        mock_info,
        mock_container_func,
        mock_checkbox,
        mock_button,
        mock_caption,
        mock_markdown,
        mock_columns,
        presenter,
        mock_transcription_result,
    ):
        """Viewのレンダリングテスト"""

        # Streamlitのモックを設定
        # デフォルトでcolumnsが2つのカラムを返すように設定
        def mock_columns_side_effect(spec):
            if isinstance(spec, list) and len(spec) == 3:
                return [MagicMock(), MagicMock(), MagicMock()]
            else:
                return [MagicMock(), MagicMock()]

        mock_columns.side_effect = mock_columns_side_effect
        mock_button.return_value = False
        mock_checkbox.return_value = False
        mock_container_func.return_value.__enter__ = MagicMock()
        mock_container_func.return_value.__exit__ = MagicMock()

        # Viewを作成してレンダリング
        view = TextEditorView(presenter)
        with patch("presentation.views.text_editor.show_diff_viewer"):
            with patch("presentation.views.text_editor.show_text_editor", return_value="テスト"):
                result = view.render(mock_transcription_result, Path("/test/video.mp4"))

        # UI要素が呼ばれたことを確認
        assert mock_columns.called
        assert mock_markdown.called
        assert mock_caption.called

        # 結果が返されることを確認
        assert isinstance(result, dict)
