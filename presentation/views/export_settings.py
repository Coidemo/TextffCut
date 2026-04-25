"""
エクスポート設定View

StreamlitのUIコンポーネントを使用してエクスポート設定画面を表示します。
"""

from typing import Any

import streamlit as st
from utils.logging import get_logger

from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel
from utils.test_ids import TestIds

logger = get_logger(__name__)


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
            # エクスポート形式選択
            self._render_export_format_selection()

            # 実行ボタンと進捗表示
            self._render_execution_section()

            # 結果表示
            self._render_results()

    def _render_export_format_selection(self) -> None:
        """エクスポート形式選択のレンダリング"""
        st.markdown("#### 📤 エクスポート形式")

        # 形式選択
        format_options = {
            "video": "動画（MP4）",
            "fcpxml": "Final Cut Pro XML",
            "xmeml": "Premiere Pro XML",
            "srt": "SRT字幕のみ",
        }

        selected_format = st.radio(
            "出力形式を選択",
            options=list(format_options.keys()),
            format_func=lambda x: format_options[x],
            index=list(format_options.keys()).index(self.view_model.export_format),
            horizontal=True,
            label_visibility="collapsed",
            key=TestIds.EXPORT_FORMAT_RADIO,
        )
        self.presenter.set_export_format(selected_format)

        # FCPXMLの追加設定
        if selected_format == "fcpxml":
            # 設定マネージャーをインポート
            from utils import settings_manager

            with st.expander("🎥 FCPXML詳細設定", expanded=True):
                # タイムライン解像度選択
                saved_timeline_resolution = settings_manager.get("fcpxml_timeline_resolution", "horizontal")
                timeline_resolution = st.radio(
                    "タイムライン解像度",
                    options=["horizontal", "vertical"],
                    format_func=lambda x: "横型 (1920x1080)" if x == "horizontal" else "縦型 (1080x1920)",
                    horizontal=True,
                    index=["horizontal", "vertical"].index(saved_timeline_resolution),
                    key="fcpxml_timeline_resolution",
                )
                if timeline_resolution != saved_timeline_resolution:
                    settings_manager.set("fcpxml_timeline_resolution", timeline_resolution)

                # ズーム設定（速度設定は削除）
                saved_zoom = settings_manager.get("fcpxml_zoom", 100)
                zoom_percent = st.number_input(
                    "ズーム (%)",
                    min_value=50,
                    max_value=300,
                    value=saved_zoom,
                    step=10,
                    help="100% = 元のサイズ、200% = 2倍拡大",
                    key="fcpxml_zoom",
                )
                scale = zoom_percent / 100.0
                # 値が変更されたら保存
                if zoom_percent != saved_zoom:
                    settings_manager.set("fcpxml_zoom", zoom_percent)

                # アンカー位置設定
                saved_anchor_x = settings_manager.get("fcpxml_anchor_x", 0.0)
                saved_anchor_y = settings_manager.get("fcpxml_anchor_y", 0.0)

                col3, col4 = st.columns(2)
                with col3:
                    anchor_x = st.number_input(
                        "アンカー位置 X",
                        min_value=-100.0,
                        max_value=100.0,
                        value=saved_anchor_x,
                        step=0.1,
                        help="横方向の位置調整（0 = 中央）",
                        key="fcpxml_anchor_x",
                    )
                    if anchor_x != saved_anchor_x:
                        settings_manager.set("fcpxml_anchor_x", anchor_x)

                with col4:
                    anchor_y = st.number_input(
                        "アンカー位置 Y",
                        min_value=-100.0,
                        max_value=100.0,
                        value=saved_anchor_y,
                        step=0.1,
                        help="縦方向の位置調整（0 = 中央）",
                        key="fcpxml_anchor_y",
                    )
                    if anchor_y != saved_anchor_y:
                        settings_manager.set("fcpxml_anchor_y", anchor_y)

                # アンカー自動検出（vertical時のみ表示）
                auto_anchor = False
                if timeline_resolution == "vertical":
                    saved_auto_anchor = settings_manager.get("fcpxml_auto_anchor", False)
                    auto_anchor = st.checkbox(
                        "被写体位置からアンカーを自動検出",
                        value=saved_auto_anchor,
                        help="GPT-4o Visionで動画を分析し、被写体に合わせてアンカーを自動設定（追加コスト: 約0.4円）",
                        key="fcpxml_auto_anchor",
                    )
                    if auto_anchor != saved_auto_anchor:
                        settings_manager.set("fcpxml_auto_anchor", auto_anchor)

                # セッション状態に保存
                st.session_state.fcpxml_settings = {
                    "scale": (scale, scale),
                    "anchor": (anchor_x, anchor_y),
                    "timeline_resolution": timeline_resolution,
                    "auto_anchor": auto_anchor,
                }

            # メディア素材の自動検出
            from pathlib import Path as _Path

            from utils.media_asset_detector import detect_media_assets

            detected_config = detect_media_assets(self.view_model.video_path) if self.view_model.video_path else None

            # 画像オーバーレイ設定
            with st.expander("🖼️ 画像オーバーレイ（オプション）", expanded=False):
                st.info(
                    "💡 videosと並列の preset/ フォルダに" " frame.png（透過背景）を配置すると自動的に読み込まれます。"
                )

                overlay_settings = {}
                if detected_config and detected_config.overlay_settings:
                    frame_name = _Path(detected_config.overlay_settings["frame_path"]).name
                    st.success(f"✅ 背景フレーム検出: {frame_name}")
                    overlay_settings = dict(detected_config.overlay_settings)
                    logger.info(f"オーバーレイ設定 - frame_path: {overlay_settings['frame_path']}")
                    st.info("💡 ロゴなどの要素は背景フレーム画像に含めてください。")
                elif self.view_model.video_path:
                    from utils.media_asset_detector import _resolve_preset_dir

                    preset_dir = _resolve_preset_dir(self.view_model.video_path)
                    if preset_dir.exists():
                        st.info("frame.png が見つかりません。" " preset/frame.png を配置してください。")
                    else:
                        st.info(
                            "preset/ フォルダが見つかりません。"
                            " videos/ と並列に preset/ フォルダを作成してください。"
                        )

                st.session_state.fcpxml_overlay_settings = overlay_settings

            # BGM設定
            with st.expander("🎵 BGM（オプション）", expanded=False):
                st.info("💡 preset/ フォルダに bgm.mp3 を配置すると自動的に読み込まれます。")

                bgm_settings = {}
                if detected_config and detected_config.bgm_settings:
                    bgm_name = _Path(detected_config.bgm_settings["bgm_path"]).name
                    st.success(f"✅ BGM検出: {bgm_name}")
                    bgm_settings["bgm_path"] = detected_config.bgm_settings["bgm_path"]
                    logger.info(f"BGM設定 - bgm_path: {bgm_settings['bgm_path']}")

                    # 音量調整
                    saved_bgm_volume = settings_manager.get("bgm_volume", -25)
                    bgm_volume = st.slider(
                        "BGM音量",
                        min_value=-50,
                        max_value=0,
                        value=saved_bgm_volume,
                        step=5,
                        help="0 = 元の音量、-50 = 最小音量",
                        key="bgm_volume",
                    )
                    bgm_settings["bgm_volume"] = bgm_volume
                    if bgm_volume != saved_bgm_volume:
                        settings_manager.set("bgm_volume", bgm_volume)

                    # ループ設定
                    saved_bgm_loop = settings_manager.get("bgm_loop", True)
                    bgm_loop = st.checkbox(
                        "BGMをループ再生",
                        value=saved_bgm_loop,
                        help="動画の長さに合わせてBGMを繰り返し再生します",
                        key="bgm_loop",
                    )
                    bgm_settings["bgm_loop"] = bgm_loop
                    if bgm_loop != saved_bgm_loop:
                        settings_manager.set("bgm_loop", bgm_loop)
                else:
                    st.info("bgm.mp3 が見つかりません。BGMを使用する場合は preset/bgm.mp3 を配置してください。")

                st.session_state.fcpxml_bgm_settings = bgm_settings

            # 追加オーディオ設定
            with st.expander("🎶 追加オーディオ（オプション）", expanded=False):
                st.info(
                    "💡 preset/ フォルダ内の bgm.mp3 以外のMP3ファイルを"
                    " 自動的に検出し、BGMの下のレーンに並べて配置します。"
                )

                additional_audio_settings = {}
                if detected_config and detected_config.additional_audio_settings:
                    audio_files = detected_config.additional_audio_settings["audio_files"]
                    st.success(f"✅ {len(audio_files)}個の追加オーディオファイルを検出しました")

                    st.caption("検出されたファイル:")
                    files_text = "\n".join([f"{idx}. {_Path(f).name}" for idx, f in enumerate(audio_files, 1)])
                    st.code(files_text, language=None)

                    # 音量調整
                    saved_additional_audio_volume = settings_manager.get("additional_audio_volume", -20)
                    additional_audio_volume = st.slider(
                        "追加オーディオ音量",
                        min_value=-50,
                        max_value=0,
                        value=saved_additional_audio_volume,
                        step=5,
                        help="0 = 元の音量、-50 = 最小音量",
                        key="additional_audio_volume",
                    )
                    if additional_audio_volume != saved_additional_audio_volume:
                        settings_manager.set("additional_audio_volume", additional_audio_volume)

                    additional_audio_settings["audio_files"] = audio_files
                    logger.info(f"追加オーディオ設定 - audio_files: {audio_files}")
                    additional_audio_settings["volume"] = additional_audio_volume
                    additional_audio_settings["muted"] = False
                elif self.view_model.video_path:
                    from utils.media_asset_detector import _resolve_preset_dir as _rpd

                    preset_dir_2 = _rpd(self.view_model.video_path)
                    if preset_dir_2.exists():
                        st.info(
                            "追加のMP3ファイルが見つかりません。" " preset/ フォルダ内にMP3ファイルを配置してください。"
                        )
                    else:
                        st.info("preset/ フォルダが見つかりません。")

                st.session_state.fcpxml_additional_audio_settings = additional_audio_settings

        # オプション設定（SRT字幕のみ以外）
        if selected_format != "srt":
            # 無音削除とSRT字幕を横並び
            col1, col2 = st.columns(2)

            with col1:
                # 無音削除チェックボックス
                remove_silence = st.checkbox(
                    "無音部分を削除",
                    value=self.view_model.remove_silence,
                    help="無音部分を自動的に削除します。詳細設定はサイドバーで変更できます。",
                    key=TestIds.EXPORT_REMOVE_SILENCE_CHECKBOX,
                )
                self.presenter.set_remove_silence(remove_silence)

            with col2:
                # SRT字幕出力チェックボックス
                include_srt = st.checkbox(
                    "SRT字幕も同時に出力",
                    value=self.view_model.include_srt,
                    help="各クリップに対応するSRT字幕ファイルを生成します",
                    key=TestIds.EXPORT_INCLUDE_SRT_CHECKBOX,
                )
                self.presenter.set_include_srt(include_srt)

            # auto_blur 利用設定: cache 存在時のみ有効化
            try:
                from use_cases.auto_blur import AutoBlurUseCase as _AutoBlurUseCase

                _blur_uc = _AutoBlurUseCase()
                _blur_cached = (
                    self.view_model.video_path is not None
                    and _blur_uc.is_cached(self.view_model.video_path)
                )
            except Exception:  # noqa: BLE001
                _blur_cached = False

            if _blur_cached:
                use_blurred_default = st.session_state.get("export_use_blurred_source", True)
                use_blurred_source = st.checkbox(
                    "🔒 塗りつぶし版動画をソースとして利用",
                    value=use_blurred_default,
                    help=(
                        "文字起こし時に生成された塗りつぶし版動画を使ってクリップを生成します. "
                        "OFF にすると元動画 (塗りつぶしなし) が使われます."
                    ),
                    key="export_use_blurred_source",
                )
                st.session_state["export_use_blurred_source"] = use_blurred_source
            else:
                # cache がなければ説明だけ表示
                st.session_state.pop("export_use_blurred_source", None)
                st.caption(
                    "ℹ️ 動画内テキスト自動塗りつぶしを使うには、文字起こし画面で「🔒 動画内テキスト自動塗りつぶし」"
                    "を有効にして再実行してください."
                )
        else:
            # SRT字幕のみの場合：無音削除のみ
            remove_silence = st.checkbox(
                "無音部分を削除",
                value=self.view_model.remove_silence,
                help="無音部分を自動的に削除します。詳細設定はサイドバーで変更できます。",
                key=TestIds.EXPORT_REMOVE_SILENCE_CHECKBOX_SRT,
            )
            self.presenter.set_remove_silence(remove_silence)

        # SRT字幕設定（SRT出力時のみ）
        if selected_format == "srt" or (selected_format != "srt" and self.view_model.include_srt):
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
                        key=TestIds.EXPORT_SRT_MAX_LINE_LENGTH,
                    )

                with col2:
                    max_lines = st.number_input(
                        "最大行数",
                        min_value=1,
                        max_value=4,
                        value=self.view_model.srt_max_lines,
                        step=1,
                        help="1つの字幕ブロックの最大行数",
                        key=TestIds.EXPORT_SRT_MAX_LINES,
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
            if st.button(
                "🚀 処理を実行",
                type="primary",
                use_container_width=True,
                disabled=not self.view_model.is_ready_to_export,
                key=TestIds.EXPORT_EXECUTE_BUTTON,
            ):
                # セッション状態にフラグを保存
                st.session_state.export_should_run = True
                st.rerun()

        # 処理状態の表示用コンテナ（処理中・完了後で同じ位置を使用）
        progress_container = st.container()

        with progress_container:
            # 処理中の表示
            if st.session_state.get("export_should_run", False) and not self.view_model.is_processing:
                self._execute_export()
            elif self.view_model.is_processing:
                self._show_progress()
            # 完了メッセージの表示
            elif st.session_state.get("export_completed", False):
                # プログレスバーとメッセージを表示
                st.progress(1.0)
                st.success("✅ エクスポート完了！")

    def _execute_export(self) -> None:
        """エクスポート実行"""
        # プログレスバーとステータステキスト（一つのコンテナで管理）
        progress_bar = st.progress(0.0)
        status_container = st.empty()

        def progress_callback(progress: float, message: str) -> None:
            progress_bar.progress(min(progress, 1.0))
            # 現在の操作と進捗メッセージを一つのコンテナに表示
            if self.view_model.current_operation:
                status_container.info(f"{message} - 🔄 {self.view_model.current_operation}")
            else:
                status_container.info(message)

        try:
            # エクスポート実行
            success = self.presenter.start_export(progress_callback)

            # 処理完了後の表示（同じコンテナを使用）
            if success:
                # プログレスバーを100%に設定
                progress_bar.progress(1.0)
                status_container.success("✅ エクスポート完了！")
                st.balloons()
                # フラグをリセット
                st.session_state.export_should_run = False
                # 完了フラグを設定
                st.session_state.export_completed = True
            else:
                status_container.error(f"❌ エクスポート失敗: {self.view_model.error_message}")
                # フラグをリセット
                st.session_state.export_should_run = False
        except Exception as e:
            status_container.error(f"❌ エクスポート中にエラーが発生しました: {str(e)}")
            # フラグをリセット
            st.session_state.export_should_run = False
            # スタックトレースも表示
            import traceback

            with st.expander("エラー詳細"):
                st.code(traceback.format_exc())

    def _show_progress(self) -> None:
        """進捗表示"""
        st.progress(self.view_model.progress)
        # 現在の操作と進捗メッセージを一つのメッセージに統合
        if self.view_model.current_operation:
            st.info(f"{self.view_model.status_message} - 🔄 {self.view_model.current_operation}")
        else:
            st.info(self.view_model.status_message)

    def _render_results(self) -> None:
        """結果表示"""
        if self.view_model.export_results:
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
