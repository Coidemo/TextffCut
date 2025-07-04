"""
TextffCut - メインアプリケーション (MVP版)

クリーンアーキテクチャに基づくMVP実装
"""

import logging

import streamlit as st

# DI統合
from di.bootstrap import bootstrap_di

# Presentation層のインポート
from presentation.views.main import show_main_view
from presentation.views.sidebar import SidebarView

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    """メインアプリケーション（MVP版）"""

    # ページ設定を最初に行う
    from pathlib import Path
    
    # アイコンファイルのパスを取得
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    page_icon = str(icon_path) if icon_path.exists() else "🎬"
    
    st.set_page_config(
        page_title="TextffCut - 動画の文字起こしと切り抜き",
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )

    try:
        # DIコンテナを初期化
        app_container = bootstrap_di()

        # Presentationコンテナを親コンテナから取得（既に依存関係が注入済み）
        presentation_container = app_container.presentation()

        # MainPresenterとSidebarPresenterを取得
        main_presenter = presentation_container.main_presenter()
        sidebar_presenter = presentation_container.sidebar_presenter()

        # 初期化
        sidebar_presenter.initialize()

        # SidebarViewを作成
        sidebar_view = SidebarView(sidebar_presenter)

        # メイン画面を表示
        show_main_view(main_presenter, sidebar_view)

    except Exception as e:
        logger.error(f"アプリケーションエラー: {e}", exc_info=True)
        st.error(f"エラーが発生しました: {str(e)}")

        # エラー詳細を表示
        with st.expander("エラー詳細"):
            st.exception(e)


if __name__ == "__main__":
    main()
