"""
エクスポート設定View

StreamlitのUIコンポーネントを使用してエクスポート設定画面を表示します。
"""

from typing import Any

import streamlit as st

from presentation.presenters.export_settings import ExportSettingsPresenter
from presentation.view_models.export_settings import ExportSettingsViewModel
from utils.test_ids import TestIds


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
            with st.expander("🎥 FCPXML詳細設定", expanded=True):
                # タイムライン解像度選択
                timeline_resolution = st.radio(
                    "タイムライン解像度",
                    options=["horizontal", "vertical"],
                    format_func=lambda x: "横型 (1920x1080)" if x == "horizontal" else "縦型 (1080x1920)",
                    horizontal=True,
                    key="fcpxml_timeline_resolution",
                )
                
                # 速度設定
                col1, col2 = st.columns(2)
                with col1:
                    speed_percent = st.number_input(
                        "再生速度 (%)",
                        min_value=50,
                        max_value=200,
                        value=100,
                        step=10,
                        help="100% = 通常速度、120% = 1.2倍速",
                        key="fcpxml_speed",
                    )
                    speed = speed_percent / 100.0
                
                with col2:
                    # ズーム設定
                    zoom_percent = st.number_input(
                        "ズーム (%)",
                        min_value=50,
                        max_value=300,
                        value=100,
                        step=10,
                        help="100% = 元のサイズ、200% = 2倍拡大",
                        key="fcpxml_zoom",
                    )
                    scale = zoom_percent / 100.0
                
                # アンカー位置設定
                col3, col4 = st.columns(2)
                with col3:
                    anchor_x = st.number_input(
                        "アンカー位置 X",
                        min_value=-100.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        help="横方向の位置調整（0 = 中央）",
                        key="fcpxml_anchor_x",
                    )
                
                with col4:
                    anchor_y = st.number_input(
                        "アンカー位置 Y",
                        min_value=-100.0,
                        max_value=100.0,
                        value=0.0,
                        step=0.1,
                        help="縦方向の位置調整（0 = 中央）",
                        key="fcpxml_anchor_y",
                    )
                
                # セッション状態に保存
                st.session_state.fcpxml_settings = {
                    "speed": speed,
                    "scale": (scale, scale),
                    "anchor": (anchor_x, anchor_y),
                    "timeline_resolution": timeline_resolution,
                }
                
                # プレビュー機能
                st.markdown("#### 🖼️ プレビュー")
                
                # プレビュー設定
                if self.view_model.effective_time_ranges:
                    # 中間のクリップを選択
                    middle_idx = len(self.view_model.effective_time_ranges) // 2
                    middle_range = self.view_model.effective_time_ranges[middle_idx]
                    preview_time = (middle_range.start + middle_range.end) / 2
                    
                    preview_col1, preview_col2 = st.columns([3, 1])
                    with preview_col1:
                        preview_orientation = st.radio(
                            "プレビュー向き",
                            options=["vertical", "horizontal"],
                            format_func=lambda x: "縦型 (1080x1920)" if x == "vertical" else "横型 (1920x1080)",
                            horizontal=True,
                            key="fcpxml_preview_orientation",
                        )
                    
                    with preview_col2:
                        if st.button("🔄 プレビュー更新", key="fcpxml_preview_update"):
                            st.session_state.fcpxml_preview_update_trigger = not st.session_state.get("fcpxml_preview_update_trigger", False)
                    
                    # プレビュー表示
                    self._render_fcpxml_preview(preview_time, scale, anchor_x, anchor_y, preview_orientation)

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

    def _render_fcpxml_preview(self, time: float, scale: float, anchor_x: float, anchor_y: float, orientation: str = "vertical") -> None:
        """FCPXMLプレビューの表示"""
        import tempfile
        import os
        from pathlib import Path
        from PIL import Image
        import numpy as np
        
        try:
            # 一時ファイル用のディレクトリ
            temp_dir = Path(tempfile.gettempdir()) / "textffcut_preview"
            temp_dir.mkdir(exist_ok=True)
            
            # プレビュー画像のキャッシュキー
            cache_key = f"preview_{self.view_model.video_path}_{time:.1f}"
            preview_path = temp_dir / f"{cache_key}.jpg"
            
            # キャッシュがない場合は生成
            if not preview_path.exists() or st.session_state.get("fcpxml_preview_update_trigger", False):
                with st.spinner("プレビュー画像を生成中..."):
                    # サムネイルを生成
                    from domain.value_objects.file_path import FilePath
                    self.presenter.video_processor_gateway.create_thumbnail(
                        video_path=FilePath(str(self.view_model.video_path)),
                        time=time,
                        output_path=FilePath(str(preview_path)),
                        width=640,  # プレビュー用サイズ
                    )
            
            # 画像を読み込み
            if preview_path.exists():
                img = Image.open(preview_path)
                img_array = np.array(img)
                
                # 画像の寸法を取得
                height, width = img_array.shape[:2]
                center_x, center_y = width / 2, height / 2
                
                # 出力サイズを決定（縦型または横型）
                if orientation == "horizontal":
                    output_width, output_height = 1920, 1080
                else:  # vertical
                    output_width, output_height = 1080, 1920
                
                # アスペクト比を計算
                output_aspect = output_width / output_height
                
                # スケール適用後のサイズを計算
                scaled_width = int(width * scale)
                scaled_height = int(height * scale)
                
                # アンカー位置を考慮したクロップ範囲を計算
                # anchor_xは-100〜100の範囲で、画像の幅に対する割合として扱う
                anchor_offset_x = anchor_x * width / 100
                anchor_offset_y = anchor_y * height / 100
                
                # クロップの中心点
                crop_center_x = center_x + anchor_offset_x
                crop_center_y = center_y + anchor_offset_y
                
                # 出力アスペクト比に合わせてクロップサイズを計算
                if scaled_width / scaled_height > output_aspect:
                    # 横が長すぎる場合
                    crop_width = int(scaled_height * output_aspect)
                    crop_height = scaled_height
                else:
                    # 縦が長すぎる場合
                    crop_width = scaled_width
                    crop_height = int(scaled_width / output_aspect)
                
                # クロップ範囲を計算（ズームを考慮）
                crop_left = max(0, int(crop_center_x - crop_width / 2 / scale))
                crop_top = max(0, int(crop_center_y - crop_height / 2 / scale))
                crop_right = min(width, int(crop_center_x + crop_width / 2 / scale))
                crop_bottom = min(height, int(crop_center_y + crop_height / 2 / scale))
                
                # クロップとリサイズ
                cropped = img.crop((crop_left, crop_top, crop_right, crop_bottom))
                preview = cropped.resize((output_width, output_height), Image.Resampling.LANCZOS)
                
                # 元画像も縦型/横型に合わせて表示
                if orientation == "vertical":
                    # 縦型の場合：横長動画を縦型フレームに収める（上下に黒帯）
                    # 黒背景の縦型キャンバスを作成
                    original_preview = Image.new('RGB', (output_width, output_height), (0, 0, 0))
                    
                    # 元画像を縦型フレームに収まるようにリサイズ
                    # 横幅を1080に合わせる
                    resize_width = output_width
                    resize_height = int(height * (output_width / width))
                    
                    # リサイズ
                    img_resized = img.resize((resize_width, resize_height), Image.Resampling.LANCZOS)
                    
                    # 縦中央に配置（上下に黒帯）
                    paste_y = (output_height - resize_height) // 2
                    original_preview.paste(img_resized, (0, paste_y))
                else:
                    # 横型の場合は元画像そのまま（必要に応じてリサイズ）
                    if width > output_width or height > output_height:
                        # アスペクト比を保持してリサイズ
                        img.thumbnail((output_width, output_height), Image.Resampling.LANCZOS)
                    original_preview = img
                
                # 画像表示
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**元の画像**")
                    st.image(original_preview, use_container_width=True)
                
                with col2:
                    st.markdown("**調整後プレビュー**")
                    st.image(preview, use_container_width=True)
                    
                # 情報表示
                orientation_text = "縦型 (1080x1920)" if orientation == "vertical" else "横型 (1920x1080)"
                st.caption(f"{orientation_text} | ズーム: {scale * 100:.0f}% | アンカー: ({anchor_x:.1f}, {anchor_y:.1f})")
                
        except Exception as e:
            st.error(f"プレビュー生成エラー: {str(e)}")
            import traceback
            with st.expander("エラー詳細"):
                st.code(traceback.format_exc())
    
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
