"""
動画入力View

StreamlitのUIコンポーネントを使用して動画入力画面を表示します。
"""

from pathlib import Path

import streamlit as st

from presentation.presenters.video_input import VideoInputPresenter
from presentation.view_models.video_input import VideoInputViewModel


class VideoInputView:
    """
    動画入力のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: VideoInputPresenter):
        """
        初期化

        Args:
            presenter: 動画入力Presenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)
        
        # メモリリーク対策: 古いYouTubeビューのクリーンアップ
        self._cleanup_old_youtube_view()
    
    def _cleanup_old_youtube_view(self) -> None:
        """古いYouTubeビューインスタンスをクリーンアップ"""
        # セッションの有効期限を確認（1時間以上経過していたら削除）
        if "youtube_view_created_at" in st.session_state:
            import time
            current_time = time.time()
            created_time = st.session_state.get("youtube_view_created_at", 0)
            
            # 1時間以上経過していたらクリーンアップ
            if current_time - created_time > 3600:
                if "youtube_download_view" in st.session_state:
                    del st.session_state.youtube_download_view
                if "youtube_view_created_at" in st.session_state:
                    del st.session_state.youtube_view_created_at

    def update(self, view_model: VideoInputViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(self) -> Path | None:
        """
        UIをレンダリング

        Returns:
            選択された動画のパス（未選択の場合はNone）
        """
        # 初期化を保証
        self.presenter.ensure_initialized()

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")
            if self.view_model.error_details:
                with st.expander("詳細"):
                    st.json(self.view_model.error_details)

        # ローディング表示
        if self.view_model.is_refreshing:
            st.info("🔍 動画ファイルを検索中...")
            st.spinner()

        # ソースタイプの選択（タブ形式）
        source_tab1, source_tab2 = st.tabs(["📁 ローカルファイル", "🎥 YouTubeからダウンロード"])
        
        with source_tab1:
            # ローカルファイル選択セクション
            # ファイル選択と更新ボタン（mainブランチのレイアウト）
            if self.view_model.video_files:
                col1, col2 = st.columns([4, 1])

                with col1:
                    # 現在の選択を含むオプションリスト
                    options = ["-- 選択してください --"] + self.view_model.video_files

                    # 現在の選択インデックス
                    current_index = 0
                    if self.view_model.selected_file in self.view_model.video_files:
                        current_index = self.view_model.video_files.index(self.view_model.selected_file) + 1

                    # セレクトボックス（ラベルなし）
                    selected = st.selectbox(
                        "", options=options, index=current_index, key="video_file_select", label_visibility="collapsed"
                    )

                with col2:
                    # 更新ボタン
                    if st.button("🔄 更新", help="動画ファイル一覧を更新", use_container_width=True):
                        self.presenter.refresh_video_list()

                # 選択が変更された場合
                if selected != "-- 選択してください --":
                    if selected != self.view_model.selected_file:
                        self.presenter.select_video(selected)
                else:
                    if self.view_model.selected_file is not None:
                        self.presenter.select_video(None)
            else:
                st.info("📁 動画ファイルが見つかりません。videosフォルダに動画ファイルを配置してください。")

                # 動画フォルダのパス表示
                st.caption(f"📁 動画フォルダのパス: {self.view_model.video_directory}")
                st.caption("対応形式: MP4, MOV, AVI, MKV, WebM")
        
        with source_tab2:
            # YouTubeダウンロードセクション
            # YouTubeダウンロードビューを初期化
            if "youtube_download_view" not in st.session_state:
                try:
                    # DIコンテナを取得
                    from di.containers import ApplicationContainer
                    container = ApplicationContainer()
                    container.wire(modules=[__name__])
                    
                    # プレゼンターを作成
                    youtube_presenter = container.presentation.youtube_download_presenter()
                    youtube_presenter.initialize()
                    from presentation.views.youtube_download import YouTubeDownloadView
                    
                    st.session_state.youtube_download_view = YouTubeDownloadView(youtube_presenter)
                    
                    # 作成時刻を記録（メモリリーク対策）
                    import time
                    st.session_state.youtube_view_created_at = time.time()
                except Exception as e:
                    st.error(f"YouTube機能の初期化エラー: {e}")
                    st.info("ページをリロードしてもう一度お試しください。")
                    return self.presenter.get_selected_video_path()
            
            # ビューをレンダリング
            if "youtube_download_view" in st.session_state:
                st.session_state.youtube_download_view.render()
            else:
                st.warning("YouTube機能が利用できません。")

        # 動画情報表示（mainブランチのようにシンプルに）
        if self.view_model.is_loading:
            with st.spinner("動画情報を読み込み中..."):
                pass

        # 選択された動画のパスを返す
        return self.presenter.get_selected_video_path()


def show_video_input(container) -> Path | None:
    """
    動画入力UIを表示（既存のUI関数との互換性のため）

    Args:
        container: DIコンテナ

    Returns:
        選択された動画のパス
    """
    # PresenterとViewを作成
    presenter = container.presentation.video_input_presenter()
    view = VideoInputView(presenter)

    # UIをレンダリング
    return view.render()
