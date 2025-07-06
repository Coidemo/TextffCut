"""
YouTube ダウンロードのView

YouTube動画ダウンロードのUIを提供します。
"""

import streamlit as st

from presentation.presenters.youtube_download import YouTubeDownloadPresenter
from presentation.view_models.youtube_download import YouTubeDownloadViewModel
from presentation.views.base import BaseView


class YouTubeDownloadView(BaseView[YouTubeDownloadViewModel]):
    """
    YouTube ダウンロードのView

    URLの入力、動画情報表示、ダウンロード進捗表示などのUIを実装します。
    """

    def __init__(self, presenter: YouTubeDownloadPresenter):
        """
        初期化

        Args:
            presenter: YouTubeダウンロードPresenter
        """
        super().__init__(presenter.view_model)
        self.presenter = presenter

    def render(self) -> None:
        """UIをレンダリング"""
        # YouTube URLダウンロードセクション
        with st.container(border=True):
            st.markdown("#### 🎥 YouTubeからダウンロード")
            st.caption("作者の許可を得た動画のみダウンロードしてください")

            # URL入力
            col1, col2 = st.columns([3, 1])

            with col1:
                url = st.text_input(
                    "YouTube URL",
                    value=self.view_model.url,
                    placeholder="https://youtube.com/watch?v=...",
                    label_visibility="collapsed",
                    disabled=self.view_model.is_downloading or self.view_model.download_complete,
                    help="作者の許可を得た動画のURLを入力してください",
                )

                if url != self.view_model.url:
                    self.view_model.url = url
                    if url:
                        # URL入力時に自動的に動画情報を取得
                        self.presenter.get_video_info(url)

            with col2:
                # 情報取得ボタン
                if st.button(
                    "🔍 情報取得",
                    use_container_width=True,
                    disabled=not url or self.view_model.is_downloading or self.view_model.download_complete,
                ):
                    self.presenter.get_video_info(url)

            # エラー表示
            if self.view_model.has_error:
                st.error(self.view_model.error_message)

            # ローディング表示
            if self.view_model.is_loading:
                st.info(self.view_model.loading_message)

            # 動画情報表示
            if self.view_model.has_video_info and not self.view_model.is_downloading:
                self._render_video_info()

            # ダウンロード進捗表示
            if self.view_model.is_downloading:
                self._render_download_progress()

            # ダウンロード完了表示
            if self.view_model.download_complete:
                self._render_download_complete()

    def _render_video_info(self) -> None:
        """動画情報を表示"""
        with st.expander("📊 動画情報", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**タイトル:**")
                st.text(self.view_model.video_title)

                st.markdown("**アップロード者:**")
                st.text(self.view_model.video_uploader)

            with col2:
                st.markdown("**動画時間:**")
                st.text(self.view_model.duration_text)

                st.markdown("**推定サイズ:**")
                st.text(f"{self.view_model.estimated_size_mb:.1f} MB")

        # ダウンロードボタン
        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "📥 ダウンロード開始",
                type="primary",
                use_container_width=True,
                disabled=not self.view_model.can_download,
            ):
                with st.spinner(f"ダウンロード中... 動画サイズ: 約{self.view_model.estimated_size_mb:.1f}MB"):
                    self.presenter.start_download(self.view_model.url)

        with col2:
            if st.button(
                "❌ キャンセル",
                use_container_width=True,
                disabled=self.view_model.download_complete,
            ):
                self.presenter.reset()
                st.rerun()

    def _render_download_progress(self) -> None:
        """ダウンロード進捗を表示"""
        # 進捗バー
        progress_text = f"ダウンロード中... {self.view_model.progress_percent:.1f}%"
        st.progress(self.view_model.progress_percent / 100, text=progress_text)

        # 詳細情報
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "ダウンロード済み", f"{self.view_model.downloaded_mb:.1f} MB", f"/ {self.view_model.total_mb:.1f} MB"
            )

        with col2:
            st.metric("速度", f"{self.view_model.download_speed_mbps:.1f} MB/s")

        # ダウンロード実行中のメッセージ
        st.info("💡 ダウンロードが完了するまでお待ちください...")

        with col3:
            st.metric("残り時間", self.view_model.eta_text)

        # キャンセルボタン
        if st.button("⏸️ ダウンロードをキャンセル", use_container_width=True):
            self.presenter.cancel_download()

    def _render_download_complete(self) -> None:
        """ダウンロード完了を表示"""
        st.success("✅ ダウンロード完了！")

        if self.view_model.downloaded_file_path:
            st.info(f"保存先: {self.view_model.downloaded_file_path}")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("📂 動画ファイル選択へ", type="primary", use_container_width=True):
                # セッション状態を更新して動画選択画面へ
                st.session_state.downloaded_video = self.view_model.downloaded_file_path
                st.session_state.show_youtube_download = False
                st.rerun()

        with col2:
            if st.button("🔄 別の動画をダウンロード", use_container_width=True):
                self.presenter.reset()
                st.rerun()
