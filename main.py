"""
TextffCut - メインアプリケーション (ワンページ版)

シンプルなワンページアプリケーションとして実装
"""

import logging
from pathlib import Path

import streamlit as st

# DI統合
from di.bootstrap import bootstrap_di

# ロギング設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def render_video_input_section(container):
    """動画入力セクション"""
    st.subheader("🎥 動画ファイル選択")
    
    # YouTubeダウンロードビューのインスタンスを保持
    if st.session_state.get("show_youtube_download", False):
        if "youtube_download_view" not in st.session_state:
            youtube_presenter = container.presentation.youtube_download_presenter()
            youtube_presenter.initialize()
            from presentation.views.youtube_download import YouTubeDownloadView
            st.session_state.youtube_download_view = YouTubeDownloadView(youtube_presenter)
    
    # VideoInputPresenterを使用
    video_input_presenter = container.presentation.video_input_presenter()
    video_input_presenter.initialize()
    
    # ダウンロード完了した動画がある場合は自動的に更新
    if "downloaded_video" in st.session_state and st.session_state.downloaded_video:
        video_input_presenter.refresh_video_list()
        # ダウンロードした動画を自動選択
        filename = Path(st.session_state.downloaded_video).name
        if filename in video_input_presenter.view_model.video_files:
            video_input_presenter.select_video(filename)
        del st.session_state.downloaded_video
    
    from presentation.views.video_input import VideoInputView
    view = VideoInputView(video_input_presenter)
    view.render()
    
    # 動画が選択されたかチェック（mainブランチのようにシンプルに）
    if video_input_presenter.view_model.selected_file:
        st.session_state.video_selected = True
        if video_input_presenter.view_model.file_path:
            video_path_str = str(video_input_presenter.view_model.file_path)
            st.session_state.video_path = video_path_str
            
            # SessionManagerにも動画パスを設定
            presentation_container = container.presentation()
            session_manager = presentation_container.session_manager()
            session_manager.set_video_path(video_path_str)
            
        if video_input_presenter.view_model.duration > 0:
            st.session_state.video_duration = video_input_presenter.view_model.duration
        return True
    return False


def render_transcription_section(container):
    """文字起こしセクション"""
    if not st.session_state.get("video_selected", False):
        return False
        
    st.subheader("📝 文字起こし")
    
    # TranscriptionPresenterを使用
    transcription_presenter = container.presentation.transcription_presenter()
    
    # 初期化処理（should_runフラグなどを復元）
    transcription_presenter.initialize()
    
    # 動画パスを設定
    video_path = st.session_state.get("video_path")
    if video_path:
        transcription_presenter.initialize_with_video(Path(video_path))
    
    from presentation.views.transcription import TranscriptionView
    view = TranscriptionView(transcription_presenter)
    view.render()
    
    # 文字起こし結果があるかチェック
    if transcription_presenter.view_model.has_result:
        st.session_state.transcription_completed = True
        # 文字起こし結果もセッションに保存
        if transcription_presenter.view_model.transcription_result:
            st.session_state.transcription_result = transcription_presenter.view_model.transcription_result
        return True
    
    # セッション状態から既存の結果を確認
    if st.session_state.get("transcription_result"):
        st.session_state.transcription_completed = True
        return True
    
    # SessionManagerから結果を確認
    presentation_container = container.presentation()
    session_manager = presentation_container.session_manager()
    if session_manager.get_transcription_result():
        st.session_state.transcription_completed = True
        return True
        
    return False


def render_text_edit_section(container):
    """テキスト編集セクション"""
    if not st.session_state.get("transcription_completed", False):
        st.warning("文字起こしが完了していません")
        return False
        
    st.subheader("✂️ 切り抜き箇所の指定")
    
    # TextEditorPresenterを使用
    presentation_container = container.presentation()
    text_editor_presenter = presentation_container.text_editor_presenter()
    
    # 文字起こし結果を取得
    session_manager = presentation_container.session_manager()
    transcription_result = session_manager.get_transcription_result()
    video_path = session_manager.get_video_path()
    
    # video_pathがNoneの場合、セッション状態から直接取得
    if not video_path:
        video_path = st.session_state.get("video_path")
    
    
    if transcription_result and video_path:
        from presentation.views.text_editor import TextEditorView
        view = TextEditorView(text_editor_presenter)
        
        # TranscriptionResultAdapterの処理
        from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter
        if isinstance(transcription_result, TranscriptionResultAdapter):
            actual_result = transcription_result.domain_result
        else:
            actual_result = transcription_result
            
        view.render(actual_result, Path(video_path))
        
        # 時間範囲が計算されたかチェック
        if text_editor_presenter.view_model.has_time_ranges:
            st.session_state.text_edit_completed = True
            return True
    else:
        if not transcription_result:
            st.info("📝 文字起こし結果が見つかりません。先に文字起こしを実行してください。")
        elif not video_path:
            st.error("❌ 動画パスが見つかりません。")
    return False


def render_buzz_clip_section(container):
    """AIバズクリップ生成セクション"""
    if not st.session_state.get("transcription_completed", False):
        return False
    
    st.divider()
    st.subheader("🤖 AIバズクリップ生成（オプション）")
    
    # 展開可能なセクションとして実装
    with st.expander("AIが自動でバズる切り抜き候補を提案", expanded=False):
        # APIキーの確認
        presentation_container = container.presentation()
        session_manager = presentation_container.session_manager()
        api_key = session_manager.get("api_key")
        
        if not api_key:
            st.warning("⚠️ この機能を使用するには、サイドバーでOpenAI APIキーを設定してください")
            return False
        
        # AI Gatewayを作成
        try:
            ai_gateway = container.gateways.ai_gateway(api_key=api_key)
        except Exception as e:
            st.error(f"AI Gateway の初期化に失敗しました: {e}")
            return False
        
        # GenerateBuzzClipsUseCaseを作成
        generate_buzz_clips_use_case = container.use_cases.generate_buzz_clips(ai_gateway=ai_gateway)
        
        # BuzzClipPresenterを作成
        buzz_clip_presenter = container.presentation.buzz_clip_presenter(
            generate_buzz_clips_use_case=generate_buzz_clips_use_case
        )
        
        # 文字起こし結果を取得
        transcription_result = session_manager.get_transcription_result()
        if transcription_result:
            # TranscriptionResultAdapterの処理
            from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter
            if isinstance(transcription_result, TranscriptionResultAdapter):
                actual_result = transcription_result.domain_result
            else:
                actual_result = transcription_result
            
            # セグメントを辞書形式に変換
            segments = []
            for seg in actual_result.segments:
                segments.append({
                    "text": seg.text,
                    "start": seg.start,
                    "end": seg.end
                })
            
            # Viewを作成して表示
            from presentation.views.buzz_clip import BuzzClipView
            view = BuzzClipView(buzz_clip_presenter)
            view.render(transcription_segments=segments)
    
    return True


def render_export_section(container):
    """エクスポートセクション"""
    if not st.session_state.get("text_edit_completed", False):
        return False
        
    st.subheader("🎬 エクスポート")
    
    # ExportSettingsPresenterを使用
    export_settings_presenter = container.presentation.export_settings_presenter()
    
    from presentation.views.export_settings import ExportSettingsView
    view = ExportSettingsView(export_settings_presenter)
    view.render()


def main():
    """メインアプリケーション（ワンページ版）"""
    
    # ページ設定
    icon_path = Path(__file__).parent / "assets" / "icon.png"
    page_icon = str(icon_path) if icon_path.exists() else "🎬"
    
    st.set_page_config(
        page_title="TextffCut - 動画の文字起こしと切り抜き",
        page_icon=page_icon,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # カスタムCSS（mainブランチのスタイルを反映）
    st.markdown("""
    <style>
    /* タイトル上の余白を削減 */
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
    }
    
    /* メインエリアの上部余白を削除 */
    .main .block-container {
        padding-top: 0.5rem !important;
    }
    
    /* Streamlitヘッダーの高さを調整 */
    [data-testid="stHeader"] {
        height: 2.5rem !important;
    }
    
    /* 最初の要素の上マージンを削除 */
    .main .block-container > div:first-child {
        margin-top: 0 !important;
    }
    
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
    }
    </style>
    """, unsafe_allow_html=True)
    
    # ダークモードスタイルを適用
    from ui.dark_mode_styles import apply_dark_mode_styles
    apply_dark_mode_styles()
    
    # タイトル
    from ui.components_modules.header import show_app_title
    from utils.version_helpers import get_app_version
    show_app_title(version=get_app_version())
    
    try:
        # DIコンテナを初期化
        app_container = bootstrap_di()
        
        # Streamlitセッション状態から設定を更新
        from di.bootstrap import inject_streamlit_session
        inject_streamlit_session(app_container)
        
        # サイドバー
        presentation_container = app_container.presentation()
        sidebar_presenter = presentation_container.sidebar_presenter()
        sidebar_presenter.initialize()
        
        from presentation.views.sidebar import SidebarView
        sidebar_view = SidebarView(sidebar_presenter)
        sidebar_view.render()
        
        # 1. 動画選択
        video_selected = render_video_input_section(app_container)
        
        # 動画が選択された場合のみ以降のセクションを表示
        if video_selected or st.session_state.get("video_selected", False):
            # 区切り線
            st.markdown("---")
            
            # 2. 文字起こし
            transcription_completed = render_transcription_section(app_container)
            
            # 文字起こしが完了した場合のみ以降のセクションを表示
            if transcription_completed or st.session_state.get("transcription_completed", False):
                # 区切り線
                st.markdown("---")
                
                # 3. テキスト編集
                text_edit_completed = render_text_edit_section(app_container)
                
                # 3.5. AIバズクリップ生成（オプション）
                render_buzz_clip_section(app_container)
                
                # テキスト編集が完了した場合のみエクスポートセクションを表示
                if text_edit_completed:
                    # 区切り線
                    st.markdown("---")
                    
                    # 4. エクスポート
                    render_export_section(app_container)
        
    except Exception as e:
        logger.error(f"アプリケーションエラー: {e}", exc_info=True)
        st.error(f"エラーが発生しました: {str(e)}")
        
        with st.expander("エラー詳細"):
            st.exception(e)


if __name__ == "__main__":
    main()