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

        # ヘッダー
        st.subheader("📹 動画ファイルの選択")

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")
            if self.view_model.error_details:
                with st.expander("詳細"):
                    st.json(self.view_model.error_details)

        # 更新ボタンとオプション
        col1, col2 = st.columns([1, 3])

        with col1:
            if st.button("🔄 更新", help="動画ファイル一覧を更新"):
                self.presenter.refresh_video_list()

        with col2:
            show_all = st.checkbox(
                "すべてのファイルを表示",
                value=self.view_model.show_all_files,
                help="対応していない拡張子のファイルも表示します",
            )
            if show_all != self.view_model.show_all_files:
                self.presenter.toggle_show_all_files()

        # ローディング表示
        if self.view_model.is_refreshing:
            st.info("🔍 動画ファイルを検索中...")
            st.spinner()

        # ファイル選択
        if self.view_model.video_files:
            # 現在の選択を含むオプションリスト
            options = ["-- 選択してください --"] + self.view_model.video_files

            # 現在の選択インデックス
            current_index = 0
            if self.view_model.selected_file in self.view_model.video_files:
                current_index = self.view_model.video_files.index(self.view_model.selected_file) + 1

            # セレクトボックス
            selected = st.selectbox("動画ファイル", options=options, index=current_index, key="video_file_select")

            # 選択が変更された場合
            if selected != "-- 選択してください --":
                if selected != self.view_model.selected_file:
                    self.presenter.select_video(selected)
            else:
                if self.view_model.selected_file is not None:
                    self.presenter.select_video(None)
        else:
            st.info("📁 動画ファイルが見つかりません。videosフォルダに動画ファイルを配置してください。")

        # 動画情報表示
        if self.view_model.is_loading:
            st.info("⏳ 動画情報を読み込み中...")
            with st.spinner("処理中..."):
                pass
        elif self.view_model.video_info:
            with st.expander("📊 動画情報", expanded=True):
                col1, col2 = st.columns(2)

                with col1:
                    st.metric("動画の長さ", self.view_model.duration_text)
                    st.metric("解像度", f"{self.view_model.video_info.width}x{self.view_model.video_info.height}")
                    st.metric("FPS", f"{self.view_model.video_info.fps:.1f}")

                with col2:
                    st.metric("ファイルサイズ", self.view_model.file_size_text)
                    st.metric("コーデック", self.view_model.video_info.codec)

                    # 処理可能かどうかの表示
                    if self.view_model.is_ready:
                        st.success("✅ 処理可能")
                    else:
                        st.warning("⚠️ 動画情報の読み込みが必要です")

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
