"""
TextffCut - メインアプリケーション（リファクタリング版）
"""

import os
from pathlib import Path

import streamlit as st

from config import config
from ui import (
    apply_dark_mode_styles,
    show_help,
    show_video_input,
)
from ui.pages import (
    ProcessingPageController,
    TextEditingPageController,
    TranscriptionPageController,
)
from ui.recovery_components import (
    show_recovery_history,
    show_recovery_settings,
    show_startup_recovery,
)
from utils.environment import IS_DOCKER
from utils.logging import get_logger
from utils.session_state_manager import SessionStateManager

logger = get_logger(__name__)


def setup_streamlit() -> None:
    """Streamlitの初期設定"""
    # アイコンファイルのパスを設定
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    if icon_path.exists():
        page_icon = str(icon_path)
    else:
        page_icon = "🎬"

    st.set_page_config(
        page_title=config.ui.page_title,
        page_icon=page_icon,
        layout=config.ui.layout,
        initial_sidebar_state="expanded",
    )

    # フォントサイズを調整するCSS
    st.markdown(
        """
    <style>
        /* 全体的なフォントサイズを小さく */
        .stApp {
            font-size: 14px;
        }
        
        /* 見出しのサイズ調整 */
        h1 {
            font-size: 2rem !important;
        }
        h2 {
            font-size: 1.5rem !important;
        }
        h3 {
            font-size: 1.25rem !important;
        }
        h4 {
            font-size: 1.1rem !important;
        }
        
        /* テキスト入力やセレクトボックスのフォントサイズ */
        .stSelectbox > div > div {
            font-size: 14px !important;
        }
        
        /* ボタンのフォントサイズ */
        .stButton > button {
            font-size: 14px !important;
        }
        
        /* キャプションのフォントサイズ */
        .caption {
            font-size: 12px !important;
            color: #888888 !important;
        }
        
        /* ボディテキスト */
        .main p {
            font-size: 14px !important;
        }
        
        /* Codeブロック */
        .stCodeBlock {
            font-size: 12px !important;
        }
        
        /* サイドバーのテキスト */
        .sidebar .sidebar-content {
            font-size: 14px !important;
        }
        
        /* タブのフォントサイズ */
        button[data-baseweb="tab"] {
            font-size: 14px !important;
        }
        
        /* メトリクスの値 */
        [data-testid="metric-value"] {
            font-size: 20px !important;
        }
        
        /* メトリクスのラベル */
        [data-testid="metric-label"] {
            font-size: 12px !important;
        }
        
        /* タイムライン関連 */
        #timeline-editor {
            font-size: 12px !important;
        }
        
        /* ファイルアップローダー */
        .uploadedFile {
            font-size: 12px !important;
        }
        
        /* 情報・警告・エラーメッセージ */
        .stAlert {
            font-size: 13px !important;
        }
    </style>
    """,
        unsafe_allow_html=True,
    )


def show_header() -> None:
    """ヘッダー部分を表示"""
    # ロゴを表示（ダークモード対応）
    icon_svg = """
    <svg width="45" height="50" viewBox="0 0 139.61 154.82" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 10px;" class="textffcut-logo">
      <style>
        @media (prefers-color-scheme: dark) {
          .textffcut-logo .icon-dark { fill: #ffffff; }
          .textffcut-logo .icon-red { fill: #fd444d; }
        }
        @media (prefers-color-scheme: light) {
          .textffcut-logo .icon-dark { fill: #2a363b; }
          .textffcut-logo .icon-red { fill: #fd444d; }
        }
      </style>
      <path class="icon-dark" d="M30.29,33.32C31.39,15.5,44.76,1.16,62.8.19c11.65-.62,23.84.49,35.54,0,3.39.21,5.97.97,8.62,3.14l29.53,29.75c4.33,5.24,2.49,14.91,2.51,21.49,0,3.18-.02,6.41,0,9.59.06,14.84,1.16,31.13.27,45.85-1.02,16.99-15.67,31.08-32.53,32.03-6.37.36-16.28.53-22.55,0-4.89-.42-8.08-4.88-5.6-9.43,1.3-2.39,3.75-3.1,6.31-3.29,13.41-.98,28.28,4.04,37.67-8.41,1.48-1.96,4.22-7.35,4.22-9.7v-61.68s-.33-.36-.36-.36h-18.48c-6.87,0-14.52-8.54-14.52-15.24V12.92h-32.76c-4.15,0-10.3,4.41-12.83,7.57-6.53,8.16-5.23,14-5.28,23.74s.62,20.49,0,30.02c-.55,8.4-9.92,9.57-12.25,1.79.73.13.46-.37.48-.83.52-13.04.44-28,0-41.06-.02-.46.24-.96-.48-.83ZM123.18,37.64c.44-.44-1.49-2.58-1.91-3.01-4.53-4.7-9.37-9.2-13.94-13.9-.37-.38-.69-1.09-1.06-1.34-1.35-.92-.63.56-.6,1.32.13,3.91-.39,8.46,0,12.25s3.98,4.66,7.32,4.92c1.17.09,9.84.12,10.2-.24Z"/>
      <path class="icon-red" d="M69.41,89.96c5.54-.69,11.11-1.24,16.65-1.95,6.41-.83,13.88-2.55,20.2-2.84,4.56-.21,7.15,3.02,4.4,7.04-4.89,7.14-13.45,9.51-21.5,10.9-8.65,1.49-17.5,1.97-26.12,3.64-.17,1.11-3.04,6.07-2.99,6.61.05.56,2.34,2.49,2.89,3.14,9.22,10.9,9.98,26.45-2.7,34.97-12.08,8.12-30.07.79-31.61-13.86-.05-.47.09-2.43,0-2.52-.25-.25-6.01.09-7.08,0-18.82-1.55-28.92-25.82-15.16-39.51,8.13-8.09,20.56-8.98,30.72-4.37,2.11.96,3.13,2.24,5.55,2.12,2.76-.14,6.43-.64,9.24-.96,5.8-.66,11.66-1.67,17.52-2.4ZM47.57,106.28c-.05-.05-1.12.03-1.5-.06-9.08-1.97-19.86-9.92-28.96-4.36-11.06,6.75-4.66,21.86,7.79,22.18,7.33.19,19.23-8.91,21.99-15.44.16-.38.92-2.08.68-2.32ZM49.91,123.62c-1.6.31-6,3.57-7.14,4.86-3.55,4.01-3.95,10.19.89,13.28,8.8,5.63,18.62-4.16,13.8-13.32-1.4-2.67-4.27-5.44-7.55-4.82Z"/>
      <path class="icon-dark" d="M69.41,89.96c-5.86.73-11.72,1.74-17.52,2.4,4.22-9.39,6.59-19.65,11.44-28.76,3.08-5.79,7.68-11,13.6-14,3.3-1.67,6.38-2.77,9.92-.96,2.77,1.41,3.26,4.72,1.62,7.23-1.86,2.85-3.67,5.17-5.43,8.25-4.81,8.45-8.84,17.37-13.64,25.84Z"/>
      <path class="icon-dark" d="M95.03,65.78h19.8c4.77,1.39,4.4,7.98-.69,8.55-6.03.67-13.2-.39-19.35-.02-4.41-1.47-4.15-7.26.24-8.53Z"/>
    </svg>
    """

    # バージョン情報を取得
    try:
        version_file = Path(__file__).parent / "VERSION.txt"
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            version = "v1.0.0"
    except:
        version = "v1.0.0"

    # 起動時のリカバリーチェック
    if SessionStateManager.get("auto_recovery", True) and "startup_recovery_checked" not in st.session_state:
        st.session_state["startup_recovery_checked"] = True
        show_startup_recovery()

    # ヘッダーを表示
    header_col1, header_col2 = st.columns([6, 1])
    with header_col1:
        st.markdown(
            f'{icon_svg}<span style="font-size: 2rem; font-weight: bold; vertical-align: middle;">TextffCut</span>',
            unsafe_allow_html=True,
        )
    with header_col2:
        st.caption(f"バージョン: {version}")

    # Docker環境の場合は注意事項を表示
    if IS_DOCKER:
        st.info("🐳 Docker環境で実行中です。動画ファイルはvideosフォルダに配置してください。")
    
    apply_dark_mode_styles()


def render_sidebar() -> None:
    """サイドバーをレンダリング"""
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # APIキー管理（必要に応じて表示）
        if config.transcription.use_api:
            from ui import show_api_key_manager
            show_api_key_manager()
        
        # 無音検出設定
        from ui import show_silence_settings
        show_silence_settings()
        
        # SRT字幕設定
        from ui import show_export_settings
        show_export_settings()
        
        # リカバリー設定
        show_recovery_settings()
        
        # 処理履歴
        show_recovery_history()
        
        # ヘルプ
        show_help()


def main() -> None:
    """メインエントリーポイント"""
    # 初期設定
    setup_streamlit()
    SessionStateManager.initialize()
    
    # ヘッダー表示
    show_header()
    
    # サイドバー
    render_sidebar()
    
    # 動画入力
    video_input = show_video_input()
    if not video_input:
        return
    
    # 現在の動画パスと前回の動画パスを比較
    current_video_path = str(video_input) if video_input else None
    previous_video_path = SessionStateManager.get("video_path")
    
    if current_video_path != previous_video_path:
        # 動画が変更された場合は状態をクリア
        SessionStateManager.clear_processing_state()
        SessionStateManager.set("video_path", current_video_path)
    
    # ページコントローラーの初期化
    transcription_controller = TranscriptionPageController()
    text_editing_controller = TextEditingPageController()
    processing_controller = ProcessingPageController()
    
    # ページ遷移制御
    if SessionStateManager.get("show_text_editing"):
        text_editing_controller.render()
    elif SessionStateManager.get("show_processing"):
        processing_controller.render()
    else:
        # デフォルトは文字起こし画面
        transcription_controller.render(video_input)


if __name__ == "__main__":
    main()