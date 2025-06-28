"""
テキスト編集画面のページコントローラー（仮実装）

TODO: main.pyから実際のコードを移動
"""

import streamlit as st

from utils.session_state_manager import SessionStateManager


class TextEditingPageController:
    """テキスト編集画面の制御"""

    def __init__(self):
        pass

    def render(self) -> None:
        """テキスト編集画面をレンダリング"""
        st.markdown("---")
        st.subheader("✂️ 切り抜き箇所指定")
        
        # TODO: main.pyから実際のテキスト編集処理を移動
        st.info("テキスト編集画面（実装予定）")
        
        # デバッグ用：処理画面への遷移ボタン
        if st.button("処理画面へ（デバッグ用）"):
            SessionStateManager.set("show_processing", True)
            SessionStateManager.set("show_text_editing", False)
            st.rerun()