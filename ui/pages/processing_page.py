"""
処理実行画面のページコントローラー（仮実装）

TODO: main.pyから実際のコードを移動
"""

import streamlit as st

from utils.session_state_manager import SessionStateManager


class ProcessingPageController:
    """処理実行画面の制御"""

    def __init__(self):
        pass

    def render(self) -> None:
        """処理実行画面をレンダリング"""
        st.markdown("---")
        st.subheader("🎬 切り抜き処理実行")
        
        # TODO: main.pyから実際の処理実行コードを移動
        st.info("処理実行画面（実装予定）")
        
        # デバッグ用：最初に戻るボタン
        if st.button("最初に戻る（デバッグ用）"):
            SessionStateManager.clear_processing_state()
            st.rerun()