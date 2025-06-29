"""
UIルーター - ページ間のナビゲーションを管理

移行期間中は段階的に機能を追加していく。
"""

import streamlit as st
from typing import Optional, Dict, Callable

from utils.config_helpers import get_ui_page_title, get_ui_layout
from ui.constants import get_app_icon
from ui.styles import get_custom_css
from ui import apply_dark_mode_styles
from ui.components_modules.header import show_app_title
from utils.startup import run_initial_checks


class Router:
    """ページ間のルーティングを管理"""
    
    def __init__(self):
        self.pages: Dict[str, Callable] = {}
        self._setup_pages()
    
    def _setup_pages(self):
        """利用可能なページを設定"""
        # Phase 1では基本的なページ構造のみ
        # 後のフェーズで実際のページを追加
        self.pages = {
            "🏠 ホーム": self._show_home_page,
            "🎬 文字起こし": self._show_transcription_placeholder,
            "✂️ 編集": self._show_editing_placeholder,
            "📤 エクスポート": self._show_export_placeholder,
        }
    
    def route(self):
        """現在のページをルーティング"""
        # Streamlitの基本設定（main.pyと同じ）
        if "page_configured" not in st.session_state:
            st.set_page_config(
                page_title=get_ui_page_title(),
                page_icon=get_app_icon(),
                layout=get_ui_layout(),
                initial_sidebar_state="expanded"
            )
            st.session_state["page_configured"] = True
        
        # スタイル適用
        st.markdown(get_custom_css(), unsafe_allow_html=True)
        apply_dark_mode_styles()
        
        # 初期チェック
        is_docker, version = run_initial_checks()
        
        # タイトル表示
        show_app_title(version)
        
        # サイドバーでページ選択
        with st.sidebar:
            st.subheader("📍 ナビゲーション")
            selected_page = st.radio(
                "ページを選択",
                options=list(self.pages.keys()),
                label_visibility="collapsed"
            )
            
            st.markdown("---")
            
            # クリーンアーキテクチャモードの切り替え（開発用）
            if st.checkbox("🧪 レガシーモードに戻る"):
                st.session_state["use_clean_architecture"] = False
                st.rerun()
        
        # 選択されたページを表示
        page_function = self.pages[selected_page]
        page_function()
    
    def _show_home_page(self):
        """ホームページを表示"""
        st.header("🏠 ホーム")
        st.info(
            "TextffCutのクリーンアーキテクチャ版へようこそ！\n\n"
            "現在、段階的な移行を進めています。"
        )
        
        st.subheader("📊 移行状況")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Phase", "1/7", "基盤整備")
        
        with col2:
            st.metric("進捗", "10%", "ディレクトリ構造作成済み")
        
        with col3:
            st.metric("残タスク", "2", "Router実装中")
        
        st.subheader("🎯 次のステップ")
        st.write(
            "1. ✅ ディレクトリ構造の作成\n"
            "2. 🔄 app.pyとRouterの実装\n"
            "3. ⏳ ページの分割"
        )
        
        with st.expander("🔍 技術詳細"):
            st.code("""
# 現在の構造
TextffCut/
├── app.py          # 新しいエントリーポイント
├── main.py         # レガシーコード（保持）
├── domain/         # ビジネスロジック
├── use_cases/      # アプリケーションロジック
├── adapters/       # インターフェース実装
└── infrastructure/ # 具体的な実装
            """)
    
    def _show_transcription_placeholder(self):
        """文字起こしページのプレースホルダー"""
        st.header("🎬 文字起こし")
        st.warning(
            "⚠️ このページは移行作業中です。\n\n"
            "レガシーモードに戻って、従来の機能をご利用ください。"
        )
        
        if st.button("🔙 レガシーモードに戻る"):
            st.session_state["use_clean_architecture"] = False
            st.rerun()
    
    def _show_editing_placeholder(self):
        """編集ページのプレースホルダー"""
        st.header("✂️ 編集")
        st.warning(
            "⚠️ このページは移行作業中です。\n\n"
            "レガシーモードに戻って、従来の機能をご利用ください。"
        )
        
        if st.button("🔙 レガシーモードに戻る"):
            st.session_state["use_clean_architecture"] = False
            st.rerun()
    
    def _show_export_placeholder(self):
        """エクスポートページのプレースホルダー"""
        st.header("📤 エクスポート")
        st.warning(
            "⚠️ このページは移行作業中です。\n\n"
            "レガシーモードに戻って、従来の機能をご利用ください。"
        )
        
        if st.button("🔙 レガシーモードに戻る"):
            st.session_state["use_clean_architecture"] = False
            st.rerun()