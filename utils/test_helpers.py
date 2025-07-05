"""
テスト用ヘルパー関数

UI要素のIDやセレクタを一元管理し、E2Eテストを容易にします。
"""


class UITestIds:
    """UI要素のテストID定義"""

    # テキスト編集セクション
    TRANSCRIPTION_RESULT_CONTAINER = "transcription-result-container"
    TEXT_EDITOR_WIDGET = "text_editor_widget"
    UPDATE_BUTTON = "update_button"
    BOUNDARY_ADJUSTMENT_CHECKBOX = "boundary_adjustment_checkbox"

    # タイムライン編集
    TIMELINE_EDIT_BUTTON = "timeline_edit_button"
    TIMELINE_APPLY_BUTTON = "timeline_apply_simple"
    TIMELINE_CANCEL_BUTTON = "timeline_cancel_simple"

    # 音声プレビュー
    AUDIO_PREVIEW_CONTAINER = "audio-preview-container"

    # エラー表示
    ERROR_MODAL_DELETE_BUTTON = "delete_highlights_modal"
    MARKER_ERROR_DELETE_BUTTON = "delete_marker_errors"

    # 処理実行
    PROCESS_EXECUTE_BUTTON = "process_execute_button"

    @classmethod
    def get_selector(cls, test_id: str) -> str:
        """SeleniumやPlaywright用のセレクタを返す"""
        return f'[data-testid="{test_id}"]'

    @classmethod
    def get_key_selector(cls, key: str) -> str:
        """Streamlit keyベースのセレクタを返す"""
        return f'[key="{key}"]'


def mark_test_element(element_type: str, test_id: str) -> dict:
    """
    Streamlit要素にテスト用の属性を追加

    Args:
        element_type: 要素のタイプ（button, input等）
        test_id: テストID

    Returns:
        Streamlitコンポーネントに渡す属性辞書
    """
    return {"key": test_id, "help": f"test-id:{test_id}"}  # helpフィールドを使ってtest-idを埋め込む


def add_test_container(test_id: str) -> str:
    """
    テスト用のコンテナHTMLを生成

    Args:
        test_id: コンテナのテストID

    Returns:
        HTML文字列
    """
    return f'<div data-testid="{test_id}" class="test-container">'


def close_test_container() -> str:
    """テスト用コンテナを閉じるHTML"""
    return "</div>"
