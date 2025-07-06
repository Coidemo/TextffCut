"""
UIルーター - 画面セクションの表示を管理

移行期間中は既存の1ページUIを維持しながら、
内部的にモジュール化を進める。
"""

import streamlit as st

from ui import apply_dark_mode_styles
from ui.components_modules.header import show_app_title
from ui.constants import get_app_icon
from ui.styles import get_custom_css
from utils.config_helpers import get_ui_layout, get_ui_page_title
from utils.startup import run_initial_checks


class Router:
    """画面表示のルーティングを管理"""

    def __init__(self):
        self.use_new_architecture = False  # 段階的移行フラグ

    def route(self):
        """画面をルーティング（段階的移行対応）"""
        if self.use_new_architecture:
            # 新アーキテクチャ版（開発中）
            from .main_view import MainView

            view = MainView()
            view.render()
        else:
            # デモ画面を表示
            self._show_demo_page()

    def _show_demo_page(self):
        """デモページを表示"""
        # Streamlitの基本設定
        if "page_configured" not in st.session_state:
            st.set_page_config(
                page_title=get_ui_page_title(),
                page_icon=get_app_icon(),
                layout=get_ui_layout(),
                initial_sidebar_state="expanded",
            )
            st.session_state["page_configured"] = True

        # スタイル適用
        st.markdown(get_custom_css(), unsafe_allow_html=True)
        apply_dark_mode_styles()

        # 初期チェック
        is_docker, version = run_initial_checks()

        # タイトル表示
        show_app_title(version)

        # サイドバー
        with st.sidebar:
            st.subheader("⚙️ 開発モード")

            # レガシーモードに戻る
            if st.button("🔙 レガシーモードに戻る", use_container_width=True):
                st.session_state["use_clean_architecture"] = False
                st.rerun()

        self._show_home_content()

    def _show_home_content(self):
        """ホームページを表示"""
        st.header("🏠 ホーム")
        st.info("TextffCutのクリーンアーキテクチャ版へようこそ！\n\n" "現在、段階的な移行を進めています。")

        st.subheader("📊 移行状況")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Phase", "1/7", "基盤整備")

        with col2:
            st.metric("進捗", "10%", "ディレクトリ構造作成済み")

        with col3:
            st.metric("残タスク", "2", "Router実装中")

        st.subheader("🎯 次のステップ")
        st.write("1. ✅ ディレクトリ構造の作成\n" "2. 🔄 app.pyとRouterの実装\n" "3. ⏳ ページの分割")

        with st.expander("🔍 技術詳細"):
            st.code(
                """
# 現在の構造
TextffCut/
├── app.py          # 新しいエントリーポイント
├── main.py         # レガシーコード（保持）
├── domain/         # ビジネスロジック
├── use_cases/      # アプリケーションロジック
├── adapters/       # インターフェース実装
└── infrastructure/ # 具体的な実装
            """
            )
