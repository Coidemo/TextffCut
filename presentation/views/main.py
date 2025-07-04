"""
メイン画面のView

アプリケーション全体のUI統合を担当します。
"""

from pathlib import Path

import streamlit as st

from presentation.presenters.main import MainPresenter
from presentation.view_models.base import BaseViewModel
from presentation.view_models.main import MainViewModel
from presentation.views.base import BaseView
from presentation.views.export_settings import ExportSettingsView
from presentation.views.sidebar import SidebarView
from presentation.views.text_editor import TextEditorView
from presentation.views.transcription import TranscriptionView
from presentation.views.video_input import VideoInputView


class MainView(BaseView[MainViewModel]):
    """
    メイン画面のView

    各MVPコンポーネントのViewを統合し、全体のUIフローを管理します。
    """

    def __init__(self, presenter: MainPresenter, sidebar_view: SidebarView):
        """
        初期化

        Args:
            presenter: メインPresenter
            sidebar_view: サイドバーView
        """
        super().__init__(presenter.view_model)
        self.presenter = presenter
        self.sidebar_view = sidebar_view

        # カスタムCSS
        self._apply_custom_css()

    def _apply_custom_css(self) -> None:
        """カスタムCSSを適用"""
        css = """
        <style>
        /* メインコンテナのスタイル */
        .main-container {
            padding: 1rem;
        }
        
        /* ステップインジケーター */
        .step-indicator {
            display: flex;
            justify-content: space-between;
            margin-bottom: 2rem;
            padding: 1rem;
            background: #f0f2f6;
            border-radius: 0.5rem;
        }
        
        .step-indicator.dark {
            background: #262730;
        }
        
        .step {
            flex: 1;
            text-align: center;
            padding: 0.5rem;
            border-radius: 0.25rem;
            margin: 0 0.25rem;
            transition: all 0.3s ease;
        }
        
        .step.active {
            background: #1f77b4;
            color: white;
            font-weight: bold;
        }
        
        .step.completed {
            background: #2ca02c;
            color: white;
        }
        
        .step.disabled {
            background: #e0e0e0;
            color: #999;
        }
        
        /* プログレスバー */
        .progress-container {
            width: 100%;
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            margin: 1rem 0;
            overflow: hidden;
        }
        
        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #1f77b4 0%, #2ca02c 100%);
            transition: width 0.3s ease;
        }
        
        /* エラーメッセージ */
        .error-container {
            background: #ffebee;
            border: 1px solid #ef5350;
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
        }
        
        /* 成功メッセージ */
        .success-container {
            background: #e8f5e9;
            border: 1px solid #4caf50;
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
        }
        </style>
        """

        st.markdown(css, unsafe_allow_html=True)

    def render(self) -> None:
        """UIをレンダリング"""
        # サイドバーをレンダリング
        self.sidebar_view.render()

        # リセット要求の処理
        if st.session_state.get("reset_requested", False):
            self.presenter.reset_workflow()
            st.session_state["reset_requested"] = False
            st.rerun()

        # メインコンテンツ
        with st.container():
            # タイトル
            st.markdown("# 🎬 TextffCut")
            st.markdown("動画の文字起こしと切り抜きを効率化するツール")

            # エラー表示
            if self.view_model.has_error:
                self._show_error()

            # プログレス表示
            self._render_progress()

            # ステップインジケーター
            self._render_step_indicator()

            # 現在のステップに応じたコンテンツを表示
            self._render_current_step()

    def _show_error(self) -> None:
        """エラーメッセージを表示"""
        st.error(f"⚠️ {self.view_model.error_message}")
        if self.view_model.error_context:
            with st.expander("詳細情報"):
                st.text(self.view_model.error_context)

        if st.button("エラーをクリア", key="clear_error"):
            self.view_model.clear_error()
            st.rerun()

    def _render_progress(self) -> None:
        """全体の進捗を表示"""
        progress = self.view_model.workflow_progress

        # プログレスバーHTML
        progress_html = f"""
        <div class="progress-container">
            <div class="progress-bar" style="width: {progress * 100}%"></div>
        </div>
        <p style="text-align: center; color: #666;">
            全体の進捗: {int(progress * 100)}%
        </p>
        """

        st.markdown(progress_html, unsafe_allow_html=True)

    def _render_step_indicator(self) -> None:
        """ステップインジケーターを表示"""
        steps = [
            ("video_input", "1. 動画選択", self.view_model.video_input_completed),
            ("transcription", "2. 文字起こし", self.view_model.transcription_completed),
            ("text_edit", "3. テキスト編集", self.view_model.text_edit_completed),
            ("export", "4. エクスポート", self.view_model.export_completed),
        ]

        # ダークモードクラス
        dark_class = "dark" if self.view_model.dark_mode else ""

        indicator_html = f'<div class="step-indicator {dark_class}">'

        for step_id, label, completed in steps:
            # ステップの状態を判定
            if completed:
                step_class = "completed"
            elif step_id == self.view_model.current_step:
                step_class = "active"
            else:
                # 到達可能かチェック
                can_reach = False
                if step_id == "video_input":
                    can_reach = True
                elif step_id == "transcription":
                    can_reach = self.view_model.can_proceed_to_transcription
                elif step_id == "text_edit":
                    can_reach = self.view_model.can_proceed_to_text_edit
                elif step_id == "export":
                    can_reach = self.view_model.can_proceed_to_export

                step_class = "disabled" if not can_reach else ""

            indicator_html += f'<div class="step {step_class}">{label}</div>'

        indicator_html += "</div>"

        st.markdown(indicator_html, unsafe_allow_html=True)

        # ステップ切り替えボタン
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            if st.button("動画選択", key="goto_video", disabled=self.view_model.current_step == "video_input"):
                self.presenter.navigate_to_step("video_input")
                st.rerun()

        with col2:
            if st.button(
                "文字起こし",
                key="goto_transcription",
                disabled=not self.view_model.can_proceed_to_transcription
                or self.view_model.current_step == "transcription",
            ):
                self.presenter.navigate_to_step("transcription")
                st.rerun()

        with col3:
            if st.button(
                "テキスト編集",
                key="goto_text_edit",
                disabled=not self.view_model.can_proceed_to_text_edit or self.view_model.current_step == "text_edit",
            ):
                self.presenter.navigate_to_step("text_edit")
                st.rerun()

        with col4:
            if st.button(
                "エクスポート",
                key="goto_export",
                disabled=not self.view_model.can_proceed_to_export or self.view_model.current_step == "export",
            ):
                self.presenter.navigate_to_step("export")
                st.rerun()

    def _render_current_step(self) -> None:
        """現在のステップのコンテンツを表示"""
        st.markdown("---")

        # 現在のステップを初期化
        self.presenter.initialize_step(self.view_model.current_step)

        # ステップに応じたビューを表示
        if self.view_model.current_step == "video_input":
            container = st.container()
            with container:
                # 現在のPresenterから対応するPresenterを取得
                video_input_presenter = self.presenter.video_input_presenter
                view = VideoInputView(video_input_presenter)
                view.render()

                # 動画選択時の状態を確認して、MainPresenterに通知
                if video_input_presenter.view_model.is_valid and video_input_presenter.view_model.file_path:
                    # 現在の状態と比較して、新しく動画が選択された場合
                    if not self.view_model.video_input_completed:
                        self.presenter._on_video_input_changed()
                        # ページを再実行して状態を反映
                        st.rerun()

        elif self.view_model.current_step == "transcription":
            container = st.container()
            with container:
                # 現在のPresenterから対応するPresenterを取得
                transcription_presenter = self.presenter.transcription_presenter
                view = TranscriptionView(transcription_presenter)
                view.render()

        elif self.view_model.current_step == "text_edit":
            container = st.container()
            with container:
                # 現在のPresenterから対応するPresenterを取得
                text_editor_presenter = self.presenter.text_editor_presenter

                # SessionManagerから必要なデータを取得
                transcription_result = self.presenter.session_manager.get_transcription_result()
                video_path = self.presenter.session_manager.get_video_path()

                if transcription_result and video_path:
                    # TranscriptionResultAdapterの場合、ドメインエンティティを取得
                    from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter
                    if isinstance(transcription_result, TranscriptionResultAdapter):
                        actual_result = transcription_result.domain_result
                        if not actual_result:
                            st.error("文字起こし結果のドメインエンティティが見つかりません")
                            return
                    else:
                        actual_result = transcription_result
                    
                    view = TextEditorView(text_editor_presenter)
                    view.render(actual_result, Path(video_path))
                else:
                    st.error("文字起こし結果または動画パスが見つかりません")

        elif self.view_model.current_step == "export":
            container = st.container()
            with container:
                # 現在のPresenterから対応するPresenterを取得
                export_settings_presenter = self.presenter.export_settings_presenter
                view = ExportSettingsView(export_settings_presenter)
                view.render()

    def update(self, view_model: BaseViewModel) -> None:
        """ViewModelの変更を反映"""
        # Streamlitは自動的に再レンダリングするため、
        # 特別な処理は不要
        pass


def show_main_view(main_presenter: MainPresenter, sidebar_view: SidebarView) -> None:
    """
    メイン画面を表示

    Args:
        main_presenter: メインPresenter
        sidebar_view: サイドバーView
    """
    view = MainView(main_presenter, sidebar_view)
    view.render()
