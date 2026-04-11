"""
動画入力View

StreamlitのUIコンポーネントを使用して動画入力画面を表示します。
"""

from pathlib import Path

import streamlit as st

from presentation.presenters.video_input import VideoInputPresenter
from presentation.view_models.video_input import VideoInputViewModel
from utils.test_ids import TestIds


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

        # ローカルファイル選択セクション
        col1, col2 = st.columns([4, 1])

        with col1:
            # オプションリストを作成
            if self.view_model.video_files:
                options = ["-- 選択してください --"] + self.view_model.video_files
                current_index = 0
                if self.view_model.selected_file in self.view_model.video_files:
                    current_index = self.view_model.video_files.index(self.view_model.selected_file) + 1
            else:
                options = ["動画ファイルがありません"]
                current_index = 0

            selected = st.selectbox(
                "",
                options=options,
                index=current_index,
                key=TestIds.VIDEO_SELECT_DROPDOWN,
                label_visibility="collapsed",
                disabled=(not self.view_model.video_files),
            )

        with col2:
            if st.button("🔄 更新", help="動画ファイル一覧を更新", use_container_width=True):
                self.presenter.refresh_video_list()

        # 選択が変更された場合
        if self.view_model.video_files:
            if selected != "-- 選択してください --":
                if selected != self.view_model.selected_file:
                    self.presenter.select_video(selected)
            else:
                if self.view_model.selected_file is not None:
                    self.presenter.select_video(None)

        # 動画フォルダのパス表示
        st.caption(f"📁 動画フォルダのパス: {self.view_model.video_directory}")

        # 動画ファイルがない場合のメッセージ
        if not self.view_model.video_files:
            st.info("動画ファイルが見つかりません。上記のフォルダに動画ファイルを配置してください。")
            st.caption("対応形式: MP4, MOV, AVI, MKV, WebM")

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
