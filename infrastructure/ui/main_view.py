"""
メインビュー - 既存のUIレイアウトを維持

main.pyと同じ1ページレイアウトを提供しながら、
内部的には各セクションをモジュール化する。
"""

import streamlit as st

from ui import apply_dark_mode_styles
from ui.components_modules.header import show_app_title
from ui.constants import get_app_icon
from ui.styles import get_custom_css
from utils.config_helpers import get_ui_layout, get_ui_page_title
from utils.startup import run_initial_checks

from .sections.editing_section import show_editing_section
from .sections.export_section import show_export_section
from .sections.transcription_section import show_transcription_section

# セクションモジュール（段階的に追加）
from .sections.video_input_section import show_video_input_section


class MainView:
    """メインビューコントローラー"""

    def __init__(self):
        """初期化"""
        self._setup_page_config()
        self._apply_styles()

    def _setup_page_config(self):
        """ページ設定（初回のみ）"""
        if "page_configured" not in st.session_state:
            st.set_page_config(
                page_title=get_ui_page_title(),
                page_icon=get_app_icon(),
                layout=get_ui_layout(),
                initial_sidebar_state="expanded",
            )
            st.session_state["page_configured"] = True

    def _apply_styles(self):
        """スタイル適用"""
        st.markdown(get_custom_css(), unsafe_allow_html=True)
        apply_dark_mode_styles()

    def render(self):
        """画面を描画（main.pyと同じレイアウト）"""
        # 初期チェック
        is_docker, version = run_initial_checks()

        # タイトル表示
        show_app_title(version)

        # サイドバー設定（現在はmain.pyからそのまま移植予定）
        self._render_sidebar()

        # メインコンテンツ（現在のmain.pyと同じ流れ）
        # Phase 1では一部だけモジュール化、残りは既存コードを呼び出す

        # 1. 動画入力セクション
        video_path = show_video_input_section()

        if video_path:
            # 2. 文字起こしセクション
            transcription_result = show_transcription_section(video_path)

            if transcription_result:
                # 3. 編集セクション
                edited_text, time_ranges = show_editing_section(transcription_result)

                if edited_text and time_ranges:
                    # 4. エクスポートセクション
                    show_export_section(video_path, edited_text, time_ranges, transcription_result)

    def _render_sidebar(self):
        """サイドバーを描画（Phase 1では既存のコードを使用）"""
        # TODO: 段階的に移植
        pass
