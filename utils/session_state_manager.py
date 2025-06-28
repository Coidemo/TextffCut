"""
セッション状態管理モジュール

Streamlitのセッション状態を一元管理します。
"""

from typing import Any, Optional

import streamlit as st


class SessionStateManager:
    """Streamlitセッション状態の一元管理"""

    @staticmethod
    def initialize() -> None:
        """セッション状態の初期化"""
        # 基本的な状態
        if "video_path" not in st.session_state:
            st.session_state.video_path = None
        if "transcription_result" not in st.session_state:
            st.session_state.transcription_result = None
        if "edited_text" not in st.session_state:
            st.session_state.edited_text = ""
        if "original_text" not in st.session_state:
            st.session_state.original_text = ""
        
        # ページ遷移制御
        if "show_transcription" not in st.session_state:
            st.session_state.show_transcription = True
        if "show_text_editing" not in st.session_state:
            st.session_state.show_text_editing = False
        if "show_processing" not in st.session_state:
            st.session_state.show_processing = False
        
        # 処理フラグ
        if "transcription_in_progress" not in st.session_state:
            st.session_state.transcription_in_progress = False
        if "processing_in_progress" not in st.session_state:
            st.session_state.processing_in_progress = False
        
        # API設定
        if "use_api" not in st.session_state:
            st.session_state.use_api = False
        if "api_key" not in st.session_state:
            st.session_state.api_key = None
        
        # モデル設定
        if "local_model_size" not in st.session_state:
            st.session_state.local_model_size = "medium"

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """値の取得"""
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any) -> None:
        """値の設定"""
        st.session_state[key] = value

    @staticmethod
    def delete(key: str) -> None:
        """値の削除"""
        if key in st.session_state:
            del st.session_state[key]

    @staticmethod
    def clear_processing_state() -> None:
        """処理関連の状態をクリア"""
        keys_to_clear = [
            "transcription_result",
            "edited_text",
            "original_text",
            "adjusted_time_ranges",
            "keep_ranges",
            "show_timeline_section",
            "timeline_edited",
            "transcription_in_progress",
            "processing_in_progress",
            "recovery_action",
            "modal_dismissed",
            "transcription_confirmed",
            "should_run_transcription",
            "modal_button_pressed",
        ]
        
        for key in keys_to_clear:
            SessionStateManager.delete(key)
        
        # ページ遷移をリセット
        SessionStateManager.set("show_transcription", True)
        SessionStateManager.set("show_text_editing", False)
        SessionStateManager.set("show_processing", False)

    @staticmethod
    def clear_all() -> None:
        """全ての状態をクリア（デバッグ用）"""
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        SessionStateManager.initialize()