"""
エクスポート設定View

StreamlitのUIコンポーネントを使用してエクスポート設定画面を表示します。
"""

from typing import Any

import streamlit as st

from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel


class ExportSettingsView:
    """
    エクスポート設定のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: ExportSettingsPresenter):
        """
        初期化

        Args:
            presenter: エクスポート設定Presenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: ExportSettingsViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(self) -> None:
        """UIをレンダリング"""
        # 初期化
        self.presenter.initialize()

        # エクスポート可能かチェック
        if not self.view_model.is_ready_to_export and not self.view_model.is_processing:
            st.warning("⚠️ エクスポートに必要な処理が完了していません。文字起こしとテキスト編集を先に行ってください。")
            return

        # メインコンテナ
        with st.container(border=True):
            st.markdown("### 🎬 切り抜き処理")

            # 無音削除設定
            self._render_silence_removal_settings()

            # エクスポート形式選択
            self._render_export_format_selection()

            # 実行ボタンと進捗表示
            self._render_execution_section()

            # 結果表示
            self._render_results()

    def _render_silence_removal_settings(self) -> None:
        """無音削除設定のレンダリング"""
        with st.expander("🔇 無音削除設定", expanded=False):
            # 無音削除の有効/無効
            remove_silence = st.checkbox(
                "無音部分を削除", value=self.view_model.remove_silence, help="動画から無音部分を自動的に削除します"
            )
            self.presenter.set_remove_silence(remove_silence)

            if remove_silence:
                col1, col2 = st.columns(2)

                with col1:
                    # 無音検出閾値
                    threshold = st.slider(
                        "無音検出閾値 (dB)",
                        min_value=-60,
                        max_value=-20,
                        value=int(self.view_model.silence_threshold),
                        step=1,
                        help="この値より小さい音量を無音として検出します",
                    )
                    self.presenter.set_silence_threshold(float(threshold))

                    # 最小無音時間
                    min_duration = st.slider(
                        "最小無音時間 (秒)",
                        min_value=0.1,
                        max_value=2.0,
                        value=self.view_model.min_silence_duration,
                        step=0.1,
                        help="この時間以上続く無音のみを削除対象とします",
                    )
                    self.presenter.set_min_silence_duration(min_duration)

                with col2:
                    # パディング設定
                    pad_start = st.slider(
                        "開始パディング (秒)",
                        min_value=0.0,
                        max_value=1.0,
                        value=self.view_model.silence_pad_start,
                        step=0.1,
                        help="有音部分の開始前に残す時間",
                    )

                    pad_end = st.slider(
                        "終了パディング (秒)",
                        min_value=0.0,
                        max_value=1.0,
                        value=self.view_model.silence_pad_end,
                        step=0.1,
                        help="有音部分の終了後に残す時間",
                    )

                    self.presenter.set_silence_padding(pad_start, pad_end)

    def _render_export_format_selection(self) -> None:
        """エクスポート形式選択のレンダリング"""
        st.markdown("#### 📤 エクスポート形式")

        # 形式選択
        format_options = {
            "video": "🎥 動画（MP4）",
            "fcpxml": "🎬 Final Cut Pro XML",
            "edl": "🎞️ EDL (DaVinci Resolve)",
            "srt": "💬 SRT字幕のみ",
        }

        selected_format = st.radio(
            "出力形式を選択",
            options=list(format_options.keys()),
            format_func=lambda x: format_options[x],
            index=list(format_options.keys()).index(self.view_model.export_format),
            horizontal=True,
            label_visibility="collapsed",
        )
        self.presenter.set_export_format(selected_format)

        # 動画出力時のSRT字幕オプション
        if selected_format == "video":
            include_srt = st.checkbox(
                "SRT字幕も同時に出力",
                value=self.view_model.include_srt,
                help="各動画クリップに対応するSRT字幕ファイルを生成します",
            )
            self.presenter.set_include_srt(include_srt)

        # SRT字幕設定（SRT出力時のみ）
        if selected_format == "srt" or (selected_format == "video" and self.view_model.include_srt):
            with st.expander("💬 SRT字幕設定", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    max_line_length = st.number_input(
                        "1行の最大文字数",
                        min_value=10,
                        max_value=100,
                        value=self.view_model.srt_max_line_length,
                        step=5,
                        help="字幕の1行あたりの最大文字数",
                    )

                with col2:
                    max_lines = st.number_input(
                        "最大行数",
                        min_value=1,
                        max_value=4,
                        value=self.view_model.srt_max_lines,
                        step=1,
                        help="1つの字幕ブロックの最大行数",
                    )

                self.presenter.set_srt_settings(max_line_length, max_lines)

    def _render_execution_section(self) -> None:
        """実行セクションのレンダリング"""
        st.markdown("---")

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")
            if self.view_model.error_details:
                with st.expander("詳細"):
                    st.json(self.view_model.error_details)

        # 実行ボタン
        if not self.view_model.is_processing:
            col1, col2, col3 = st.columns([2, 1, 2])
            with col2:
                if st.button(
                    "🚀 処理を実行",
                    type="primary",
                    use_container_width=True,
                    disabled=not self.view_model.is_ready_to_export,
                ):
                    self.view_model.should_run = True
                    st.rerun()

        # 処理中の表示
        if self.view_model.should_run and not self.view_model.is_processing:
            self._execute_export()
        elif self.view_model.is_processing:
            self._show_progress()

    def _execute_export(self) -> None:
        """エクスポート実行"""
        with st.spinner("処理中..."):
            # プログレスバーとステータステキスト
            progress_bar = st.progress(0.0)
            status_text = st.empty()
            operation_text = st.empty()

            def progress_callback(progress: float, message: str) -> None:
                progress_bar.progress(min(progress, 1.0))
                status_text.info(message)
                if self.view_model.current_operation:
                    operation_text.caption(f"🔄 {self.view_model.current_operation}")

            # エクスポート実行
            if self.presenter.start_export(progress_callback):
                st.success("✅ エクスポート完了！")
                st.balloons()
            else:
                st.error(f"❌ {self.view_model.error_message}")

    def _show_progress(self) -> None:
        """進捗表示"""
        progress_bar = st.progress(self.view_model.progress)
        st.info(self.view_model.status_message)
        if self.view_model.current_operation:
            st.caption(f"🔄 {self.view_model.current_operation}")

    def _render_results(self) -> None:
        """結果表示"""
        if self.view_model.export_results:
            st.markdown("---")
            st.success(f"✅ {len(self.view_model.export_results)}個のファイルを出力しました")

            # 出力ファイルリスト
            with st.expander("📁 出力ファイル", expanded=True):
                for result in self.view_model.export_results:
                    st.text(result)


def show_export_settings(container: Any) -> None:
    """
    エクスポート設定UIを表示（既存のUI関数との互換性のため）

    Args:
        container: DIコンテナ
    """
    # PresenterとViewを作成
    presenter = container.presentation.export_settings_presenter()
    view = ExportSettingsView(presenter)

    # UIをレンダリング
    view.render()
