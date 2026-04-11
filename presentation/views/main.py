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
from ui.dark_mode_styles import apply_dark_mode_styles


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

        # ダークモード対応スタイルを適用
        apply_dark_mode_styles()

    def _apply_custom_css(self) -> None:
        """カスタムCSSを適用"""
        # テーマ検出器をインポート
        from utils.theme_detector import ThemeDetector

        # テーマ検出
        is_dark = ThemeDetector.is_dark_mode()

        # 共通CSS
        css = """
        <style>
        /* Streamlitのデフォルト余白を調整 */
        .block-container {
            padding-top: 1rem !important;
            padding-bottom: 2rem !important;
            max-width: 1200px !important;
        }
        
        /* メインエリアの上部余白を削除 */
        .main .block-container {
            padding-top: 0.5rem !important;
        }
        
        /* タイトル部分の余白調整 */
        .stMarkdown h1:first-of-type {
            margin-top: 0 !important;
        }
        
        /* Streamlitヘッダーの余白調整 */
        [data-testid="stHeader"] {
            height: 3rem !important;
        }
        
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
            border-radius: 0.5rem;
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
            font-weight: bold;
        }
        
        /* シンプルステップインジケーター */
        .simple-step-indicator {
            margin: 1.5rem 0;
        }
        
        /* ステップコンテナ */
        .steps-container {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0;
        }
        
        /* ステップアイテムラッパー */
        .step-item-wrapper {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.5rem;
            position: relative;
            z-index: 2;
        }
        
        /* ステップサークル */
        .step-circle {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 600;
            font-size: 0.9rem;
            transition: all 0.3s ease;
            cursor: pointer;
        }
        
        .step-circle.disabled {
            cursor: not-allowed;
            opacity: 0.5;
        }
        
        .step-circle:not(.disabled):not(.current):hover {
            transform: scale(1.05);
        }
        
        /* ステップラベル */
        .step-label {
            font-size: 0.8rem;
            text-align: center;
            white-space: nowrap;
        }
        
        /* ステップコネクター */
        .step-connector {
            width: 60px;
            height: 2px;
            margin: 0 -8px;
            margin-bottom: 1.5rem;
            z-index: 1;
            transition: background 0.3s ease;
        }
        
        /* エラーメッセージ */
        .error-container {
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
        }
        
        /* 成功メッセージ */
        .success-container {
            border-radius: 0.5rem;
            padding: 1rem;
            margin: 1rem 0;
        }
        
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)

        # テーマ別CSS
        if is_dark:
            # ダークテーマ用CSS
            dark_theme_css = """
            <style>
            /* ダークテーマカラー */
            .step-indicator {
                background: #262730;
            }
            
            .step.active {
                background: #1f77b4;
                color: white;
            }
            
            .step.completed {
                background: #2ca02c;
                color: white;
            }
            
            .step.disabled {
                background: #333;
                color: #666;
            }
            
            /* ステップサークル - ダークテーマ */
            .step-circle {
                background: #2a2a3e;
                border: 2px solid #333;
                color: #666;
            }
            
            .step-circle.completed {
                background: #00b894;
                border-color: #00b894;
                color: #fff;
            }
            
            .step-circle.current {
                background: #fff;
                border-color: #00b894;
                color: #00b894;
                box-shadow: 0 0 0 3px rgba(0, 184, 148, 0.2);
            }
            
            .step-circle:not(.disabled):not(.current):hover {
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
            }
            
            /* ステップラベル - ダークテーマ */
            .step-label {
                color: rgba(255, 255, 255, 0.6);
            }
            
            .step-label.completed {
                color: #00b894;
            }
            
            .step-label.current {
                color: #fff;
                font-weight: 500;
            }
            
            /* ステップコネクター - ダークテーマ */
            .step-connector {
                background: #333;
            }
            
            .step-connector.completed {
                background: #00b894;
            }
            
            /* ナビゲーションボタン - ダークテーマ */
            [data-testid*="nav_"] > button {
                background: transparent !important;
                border: 1px solid rgba(255, 255, 255, 0.2) !important;
                color: rgba(255, 255, 255, 0.8) !important;
                font-size: 0.8rem !important;
                padding: 0.25rem 0.5rem !important;
                height: auto !important;
                transition: all 0.2s ease !important;
            }
            
            [data-testid*="nav_"] > button:hover {
                background: rgba(0, 184, 148, 0.1) !important;
                border-color: #00b894 !important;
                color: #00b894 !important;
            }
            
            /* エラーコンテナ - ダークテーマ */
            .error-container {
                background: #3d1f1f;
                border: 1px solid #ef5350;
            }
            
            /* 成功コンテナ - ダークテーマ */
            .success-container {
                background: #1f3d1f;
                border: 1px solid #4caf50;
            }
            
            /* ボタンのエフェクト */
            .step-grid .stButton > button::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(45deg, transparent 30%, rgba(255, 255, 255, 0.1) 50%, transparent 70%);
                transform: translateX(-100%);
                transition: transform 0.6s;
            }
            
            .step-grid .stButton > button:hover::before {
                transform: translateX(100%);
            }
            
            /* 区切り線 - ダークテーマ */
            hr {
                border: none;
                height: 1px;
                background: rgba(255, 255, 255, 0.1);
                margin: 2rem 0;
            }
            </style>
            """
            st.markdown(dark_theme_css, unsafe_allow_html=True)
        else:
            # ライトテーマ用CSS
            light_theme_css = """
            <style>
            /* ライトテーマカラー */
            .step-indicator {
                background: #f0f2f6;
            }
            
            .step.active {
                background: #1f77b4;
                color: white;
            }
            
            .step.completed {
                background: #2ca02c;
                color: white;
            }
            
            .step.disabled {
                background: #e0e0e0;
                color: #999;
            }
            
            /* ステップサークル - ライトテーマ */
            .step-circle {
                background: #f0f2f6;
                border: 2px solid #ddd;
                color: #999;
            }
            
            .step-circle.completed {
                background: #2ca02c;
                border-color: #2ca02c;
                color: #fff;
            }
            
            .step-circle.current {
                background: #1f77b4;
                border-color: #1f77b4;
                color: #fff;
                box-shadow: 0 0 0 3px rgba(31, 119, 180, 0.2);
            }
            
            .step-circle:not(.disabled):not(.current):hover {
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
            }
            
            /* ステップラベル - ライトテーマ */
            .step-label {
                color: #666;
            }
            
            .step-label.completed {
                color: #2ca02c;
            }
            
            .step-label.current {
                color: #1f77b4;
                font-weight: 500;
            }
            
            /* ステップコネクター - ライトテーマ */
            .step-connector {
                background: #ddd;
            }
            
            .step-connector.completed {
                background: #2ca02c;
            }
            
            /* ナビゲーションボタン - ライトテーマ */
            [data-testid*="nav_"] > button {
                background: transparent !important;
                border: 1px solid #ddd !important;
                color: #666 !important;
                font-size: 0.8rem !important;
                padding: 0.25rem 0.5rem !important;
                height: auto !important;
                transition: all 0.2s ease !important;
            }
            
            [data-testid*="nav_"] > button:hover {
                background: rgba(31, 119, 180, 0.1) !important;
                border-color: #1f77b4 !important;
                color: #1f77b4 !important;
            }
            
            /* エラーコンテナ - ライトテーマ */
            .error-container {
                background: #ffebee;
                border: 1px solid #ef5350;
            }
            
            /* 成功コンテナ - ライトテーマ */
            .success-container {
                background: #e8f5e9;
                border: 1px solid #4caf50;
            }
            
            /* 区切り線 - ライトテーマ */
            hr {
                border: none;
                height: 1px;
                background: #e0e0e0;
                margin: 2rem 0;
            }
            </style>
            """
            st.markdown(light_theme_css, unsafe_allow_html=True)

    def render(self) -> None:
        """UIをレンダリング"""
        # サイドバーをレンダリング
        self.sidebar_view.render()

        # リセット要求の処理
        if st.session_state.get("reset_requested", False):
            self.presenter.reset_workflow()
            st.session_state["reset_requested"] = False
            st.rerun()

        # ナビゲーション遷移チェック（最初に処理）
        if st.session_state.get("navigate_to_export", False):
            st.session_state.navigate_to_export = False
            self.presenter.view_model.complete_text_edit()
            st.rerun()

        # 戻るボタンのナビゲーション要求を処理
        if st.session_state.get("request_navigation_to_transcription", False):
            import logging

            logger = logging.getLogger(__name__)
            logger.info("request_navigation_to_transcription detected")
            st.session_state.request_navigation_to_transcription = False
            self.presenter.view_model.set_current_step("transcription")
            st.rerun()

        if st.session_state.get("request_navigation_to_video_input", False):
            import logging

            logger = logging.getLogger(__name__)
            logger.info("request_navigation_to_video_input detected")
            st.session_state.request_navigation_to_video_input = False
            self.presenter.view_model.set_current_step("video_input")
            st.rerun()

        # メインコンテンツ
        with st.container():
            # タイトル（SVGロゴとスタイル付き）
            from ui.components_modules.header import show_app_title
            from utils.version_helpers import get_app_version

            # SVGが表示されない場合は、以下のコメントを外してPNG版を使用
            # from ui.components_modules.header_alternative import show_app_title_with_image
            # show_app_title_with_image(version=get_app_version())

            show_app_title(version=get_app_version())

            # エラー表示
            if self.view_model.has_error:
                self._show_error()

            # 現在のステップを初期化とコンテンツ表示
            self.presenter.initialize_step(self.view_model.current_step)
            self._render_step_content(self.view_model.current_step)

    def _show_error(self) -> None:
        """エラーメッセージを表示"""
        st.error(f"⚠️ {self.view_model.error_message}")
        if self.view_model.error_context:
            with st.expander("詳細情報"):
                st.text(self.view_model.error_context)

        if st.button("エラーをクリア", key="clear_error"):
            self.view_model.clear_error()
            st.rerun()

    def _render_step_content(self, step: str) -> None:
        """指定されたステップのコンテンツを表示"""

        # ステップに応じたビューを表示
        if step == "video_input":
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
                        # 自動的に文字起こしタブに移動
                        self.presenter.navigate_to_step("transcription")
                        # ページを再実行して状態を反映
                        st.rerun()

        elif step == "transcription":
            container = st.container()
            with container:
                # 現在のPresenterから対応するPresenterを取得
                transcription_presenter = self.presenter.transcription_presenter
                view = TranscriptionView(transcription_presenter)
                view.render()

        elif step == "text_edit":
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

        elif step == "export":
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
