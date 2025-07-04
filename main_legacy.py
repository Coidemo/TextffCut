"""
TextffCut - メインアプリケーション
リファクタリング版：モジュール化された構造を使用
"""

import os
from pathlib import Path

import streamlit as st

from core import TextProcessor
from core.error_handling import ErrorHandler

# DI統合
from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.containers import ApplicationContainer
from services import ConfigurationService, VideoProcessingService
from ui import (
    apply_dark_mode_styles,
    cleanup_temp_files,
    show_api_key_manager,
    show_help,
    show_progress,
    show_red_highlight_modal,
    show_silence_settings,
    show_video_input,
)
from ui.components_modules.header import show_app_title
from ui.constants import get_app_icon
from ui.recovery_components import (
    show_recovery_check,
    show_recovery_history,
    show_recovery_settings,
)
from ui.styles import get_custom_css
from utils import ProcessingContext, cleanup_intermediate_files
from utils.config_helpers import get_ui_layout, get_ui_page_title, set_api_mode
from utils.export_helpers import (
    determine_export_format,
    export_srt_with_diff,
    export_xml,
    format_export_success_message,
    generate_export_paths,
    get_srt_settings_from_session,
)
from utils.file_utils import ensure_directory, get_safe_filename
from utils.logging import get_logger
from utils.path_helpers import get_display_path
from utils.startup import run_initial_checks

logger = get_logger(__name__)

# DIコンテナのグローバルインスタンス
_app_container: ApplicationContainer | None = None


def get_container() -> ApplicationContainer:
    """アプリケーションコンテナを取得"""
    global _app_container
    if _app_container is None:
        _app_container = bootstrap_di()
    return _app_container


# Streamlitの設定
st.set_page_config(
    page_title=get_ui_page_title(), page_icon=get_app_icon(), layout=get_ui_layout(), initial_sidebar_state="expanded"
)

# フォントサイズを調整するCSS
st.markdown(get_custom_css(), unsafe_allow_html=True)

# ダークモード対応のスタイルを適用
apply_dark_mode_styles()


def main() -> None:
    """メインアプリケーション"""

    # MVP版を使用するかどうかのフラグ（環境変数で制御）
    use_mvp = os.environ.get("TEXTFFCUT_USE_MVP", "false").lower() == "true"

    if use_mvp:
        # MVP版のメイン処理を実行
        from main_mvp import main as main_mvp

        return main_mvp()

    # 以下は従来のコード
    # DIコンテナを初期化
    container = get_container()
    inject_streamlit_session(container)

    # DIコンテナの状態をログ出力（デバッグ用）
    logger.info("DI container initialized")
    logger.debug(f"Container config: {container.config().environment}")

    # 初期チェックを実行
    is_docker, version = run_initial_checks()

    # タイトル表示
    show_app_title(version)

    # サイドバー
    with st.sidebar:
        st.subheader("⚙️ 設定")

        # タブで設定を整理
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(
            ["🔑 APIキー", "🔇 無音検出", "🎬 SRT字幕", "🔄 リカバリー", "📋 履歴", "❓ ヘルプ"]
        )

        with tab1:
            # APIキー管理のみ
            show_api_key_manager()

        with tab2:
            # 無音検出のパラメータ
            noise_threshold, min_silence_duration, min_segment_duration, padding_start, padding_end = (
                show_silence_settings()
            )

        with tab3:
            # SRT字幕設定
            from ui.srt_export_components import show_srt_export_info, show_srt_export_settings

            srt_settings = show_srt_export_settings()
            # 設定をセッションに保存
            st.session_state.srt_settings = srt_settings
            # SRT字幕についての説明
            show_srt_export_info()

        with tab4:
            # リカバリー設定
            show_recovery_settings()

        with tab5:
            # 処理履歴
            show_recovery_history()

        with tab6:
            show_help()

    # 動画ファイル選択（新しい入力方式）
    video_input = show_video_input()
    if not video_input:
        return

    video_path, output_dir = video_input

    # 動画パス変更の検知とクリア処理
    previous_video_path = st.session_state.get("current_video_path", "")
    if previous_video_path != video_path:
        # 動画が変更された場合、前の文字起こし結果と関連状態をクリア
        session_keys_to_clear = [
            "transcription_result",  # 文字起こし結果
            "edited_text",  # 編集されたテキスト
            "original_edited_text",  # 元の編集テキスト
            "show_modal",  # モーダル表示状態
            "show_error_and_delete",  # エラー表示状態
            "transcription_confirmed",  # 文字起こし設定確認状態
            "should_run_transcription",  # 文字起こし実行フラグ
            "show_confirmation_modal",  # 確認モーダル状態
            "confirmation_info",  # 確認情報
            "last_modal_settings",  # 最後のモーダル設定
            "modal_dismissed",  # モーダル閉じられたフラグ
            "modal_button_pressed",  # モーダルボタン押下フラグ
            "transcription_in_progress",  # 文字起こし処理中フラグ
            "cancel_transcription",  # 文字起こし中止フラグ
            "previous_transcription_mode",  # 前回の文字起こしモード
            "previous_transcription_model",  # 前回の文字起こしモデル
        ]

        for key in session_keys_to_clear:
            if key in st.session_state:
                del st.session_state[key]

        # 現在の動画パスを保存
        st.session_state.current_video_path = video_path

    # video_pathをセッション状態に保存（音声プレビュー用）
    st.session_state.video_path = video_path

    # 不要なタイムライン編集モードのチェックを削除

    # 文字起こし処理
    st.markdown("---")
    st.subheader("📝 文字起こし")

    # リカバリーチェック
    recovery_info = show_recovery_check(video_path)
    if recovery_info and st.session_state.get("recovery_action") == "resume":
        # リカバリー処理を実行
        st.info("🔄 前回の処理を再開しています...")
        # TODO: リカバリー処理の実装
        pass

    # モード・モデル変更の検知と処理中止（確認画面で選択される前なので一時的にコメントアウト）
    # current_mode = st.session_state.get('use_api', False)
    # current_model = model_size
    # previous_mode = st.session_state.get('previous_transcription_mode', None)
    # previous_model = st.session_state.get('previous_transcription_model', None)

    # モードまたはモデルが変更された場合の処理中止（確認画面で選択されるまでコメントアウト）
    # mode_changed = previous_mode is not None and previous_mode != current_mode
    # model_changed = previous_model is not None and previous_model != current_model

    # if mode_changed or model_changed:
    # # モーダル関連のフラグをリセット
    # if 'last_modal_settings' in st.session_state:
    #     del st.session_state.last_modal_settings
    # if 'modal_dismissed' in st.session_state:
    #     del st.session_state.modal_dismissed
    # if 'show_confirmation_modal' in st.session_state:
    #     del st.session_state.show_confirmation_modal
    # if 'transcription_confirmed' in st.session_state:
    #     del st.session_state.transcription_confirmed
    # if 'should_run_transcription' in st.session_state:
    #     del st.session_state.should_run_transcription
    # if 'modal_button_pressed' in st.session_state:
    #     del st.session_state.modal_button_pressed
    #
    # # 処理中の場合は中止
    # if st.session_state.get('transcription_in_progress', False):
    #     st.session_state.cancel_transcription = True
    #     st.session_state.transcription_in_progress = False
    #
    #     if mode_changed:
    #         st.warning("⚠️ モードが変更されました。文字起こし処理を中止しました。")
    #     elif model_changed:
    #         st.warning("⚠️ モデルが変更されました。文字起こし処理を中止しました。")

    # 現在のモードとモデルを保存（確認画面で決定されるまでコメントアウト）
    # st.session_state.previous_transcription_mode = current_mode
    # st.session_state.previous_transcription_model = current_model

    # 設定の初期化
    from config import Config

    config = Config()

    # MVPパターンを使用した文字起こしUI
    import presentation.views.text_editor
    from presentation.views.transcription import show_transcription_controls

    # APIキーをセッションから取得
    api_key = st.session_state.get("api_key")

    # 文字起こしコントロールUIを表示
    use_cache, run_new, result_data = show_transcription_controls(
        video_path=Path(video_path), api_key=api_key, container=container
    )

    # 結果からキャッシュ情報を取得
    selected_cache = None
    if use_cache and result_data:
        # SessionManagerがすでに状態を管理しているため、ここでの設定は不要
        pass

    # MVPパターンでは、キャッシュの読み込みはすでにView内で完了している
    if use_cache and result_data:
        st.rerun()

    # MVPパターンでは、文字起こしUIはすべてTranscriptionView内で処理される
    # 新規実行の場合の処理もView内で完結しているため、ここでは何もしない

    # 以前のコードではavailable_cachesを使用していたが、
    # MVPパターンでは必要ないため削除

    # 文字起こし処理の実行（run_newがtrueの場合）
    if run_new:
        # この処理もすでにTranscriptionView内で完了している
        pass

    # SessionManagerから文字起こし結果を取得
    session_manager = container.presentation.session_manager()
    transcription_result_from_session = session_manager.get_transcription_result()

    # 直接session_stateからも確認（デバッグ用）
    transcription_in_state = st.session_state.get("transcription_result")
    logger.info(f"SessionManagerから: {type(transcription_result_from_session)}")
    logger.info(f"session_stateから: {type(transcription_in_state)}")

    # 文字起こし結果の処理
    if transcription_result_from_session:
        transcription = transcription_result_from_session

        # 文字起こし結果の厳密な検証（表示前に必ず実行）
        # wordsフィールドが必須
        logger.info(f"文字起こし結果の型: {type(transcription)}")
        logger.info(f"セグメント数: {len(transcription.segments) if hasattr(transcription, 'segments') else 0}")

        has_valid_words = True
        segments_without_words = []

        # ドメインエンティティとレガシー形式の両方に対応
        for seg in transcription.segments:
            # ドメインエンティティの場合
            if hasattr(seg, "has_word_level_timestamps"):
                logger.info(
                    f"ドメインエンティティセグメント: has_word_level_timestamps={seg.has_word_level_timestamps}"
                )
                if not seg.has_word_level_timestamps:
                    has_valid_words = False
                    segments_without_words.append(seg)
            # レガシー形式の場合
            else:
                logger.info(
                    f"レガシーセグメント: words属性={hasattr(seg, 'words')}, words値={seg.words if hasattr(seg, 'words') else 'なし'}"
                )
                if not hasattr(seg, "words") or not seg.words or len(seg.words) == 0:
                    has_valid_words = False
                    segments_without_words.append(seg)

        if not has_valid_words:
            from core.exceptions import WordsFieldMissingError

            sample_texts = [
                seg.text[:50] + "..." if seg.text and len(seg.text) > 50 else seg.text
                for seg in segments_without_words[:3]
            ]
            error = WordsFieldMissingError(segment_count=len(segments_without_words), sample_segments=sample_texts)
            st.error(error.get_user_message())
            return

        st.markdown("---")
        st.subheader("✂️ 切り抜き箇所の指定")

        # 現在表示中の文字起こし情報を表示
        model_info = transcription.model_size

        # APIモードかどうかの判定を改善
        # whisper-1_apiまたはwhisper-1のようなAPIモデル名を判定
        if "_api" in model_info or model_info == "whisper-1":
            mode_text = "API"
            model_text = model_info.replace("_api", "")
        else:
            mode_text = "ローカル"
            model_text = model_info

        st.caption(f"📝 現在の文字起こし結果: {mode_text}モード・{model_text}")

        # エラー表示（2カラムの上に表示）
        if st.session_state.get("show_error_and_delete", False):
            st.error("⚠️ 元動画に存在しない文字が切り抜き箇所に入力されています。削除してください。")

        # マーカー位置エラーの表示
        if st.session_state.get("show_marker_error", False):
            st.error("⚠️ 境界調整マーカーの位置が不適切です。マーカーは各行の先頭と末尾にのみ配置してください。")
            marker_errors = st.session_state.get("marker_position_errors", [])
            for error in marker_errors:
                st.error(f"❌ {error}")

        # 全テキストを取得（wordsベース必須）
        try:
            full_text = transcription.get_full_text()
        except Exception:
            st.error("❌ 文字位置情報（words）が見つかりません。文字起こしを再度実行して下さい。")
            return

        # MVPパターンでテキスト編集UIを表示
        container = get_container()
        presenter = container.presentation.text_editor_presenter()
        view = presentation.views.text_editor.TextEditorView(presenter)
        processed_data = view.render(transcription, Path(video_path))

        # 処理データがある場合は保存
        if processed_data:
            if processed_data.get("edited_text"):
                st.session_state.edited_text = processed_data["edited_text"]
            if processed_data.get("time_ranges"):
                st.session_state.time_ranges = processed_data["time_ranges"]
            if processed_data.get("has_boundary_markers") is not None:
                st.session_state.has_boundary_adjustments = processed_data["has_boundary_markers"]
        # タイムライン編集セクション（show_timeline_sectionがTrueの場合）
        if st.session_state.get("show_timeline_section", False):
            st.markdown("---")
            st.subheader("📊 タイムライン編集")

            # タイムライン編集完了フラグをチェック
            if st.session_state.get("timeline_editing_completed", False):
                adjusted_ranges = st.session_state.get("adjusted_time_ranges", [])
                if adjusted_ranges:
                    # フラグをクリア
                    del st.session_state.timeline_editing_completed
                    st.session_state.timeline_completed = True
                    st.session_state.show_timeline_section = False
                    st.success("タイムライン編集が完了しました。")
                    st.rerun()
            elif st.session_state.get("timeline_editing_cancelled", False):
                # キャンセルフラグをクリア
                del st.session_state.timeline_editing_cancelled
                st.session_state.show_timeline_section = False
                st.info("タイムライン編集がキャンセルされました。")
                st.rerun()
            else:
                # タイムライン編集UIをインラインで表示
                time_ranges = st.session_state.get("time_ranges", [])
                if time_ranges:
                    # シンプルなバージョンを使用（確実に動作）
                    from ui.timeline_editor_simple import render_timeline_editor_simple

                    render_timeline_editor_simple(time_ranges, transcription, video_path)
                else:
                    st.error("時間範囲が計算されていません。更新ボタンをクリックしてください。")

        # 切り抜き処理セクション（編集テキストがある場合は常に表示）
        if st.session_state.get("edited_text") and not st.session_state.get("show_timeline_section", False):
            st.markdown("---")
            st.subheader("🎬 切り抜き箇所の抽出")

            # タイムライン編集ボタン（時間範囲が計算されている場合のみ表示）
            if st.session_state.get("time_ranges"):
                col1, col2 = st.columns([1, 3])
                with col1:
                    if st.button(
                        "📊 タイムライン編集", use_container_width=True, help="クリップの境界を細かく調整します"
                    ):
                        st.session_state.show_timeline_section = True
                        st.rerun()

                # 調整された時間範囲がある場合は表示
                if "adjusted_time_ranges" in st.session_state:
                    with col2:
                        st.success("✅ タイムライン編集済み（調整が適用されます）")

            # 処理オプション - MVP版を使用
            from presentation.views.export_settings import show_export_settings

            show_export_settings(container)

            # 古いエクスポートコードはMVP版で置き換えられたため削除
            return  # ここでmain関数を終了（古いコードはスキップ）

            # 以下の古いコードは削除予定
            if False:  # process_type == "無音削除付き":
                st.markdown("##### 🔇 無音削除の設定")
                st.info(
                    f"現在の設定: 閾値{noise_threshold}dB | 無音{min_silence_duration}秒 | "
                    f"セグメント{min_segment_duration}秒 | パディング{padding_start}-{padding_end}秒 | "
                    f"設定変更は左サイドパネルの「無音検出」タブから"
                )

            # 出力先の表示
            st.markdown("#### 📁 出力先")
            video_name = Path(video_path).stem
            safe_name = get_safe_filename(video_name)

            # 出力パスを表示（Docker環境ではホストパスに変換）
            video_parent = Path(video_path).parent
            project_path = video_parent / f"{safe_name}_TextffCut"

            if os.path.exists("/.dockerenv"):
                # Docker環境：ホストパスに変換して表示
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", str(video_parent))
                display_path = os.path.join(host_videos_path, f"{safe_name}_TextffCut")
            else:
                # ローカル環境：そのまま表示
                display_path = str(project_path)

            st.code(display_path, language=None)

            # 処理実行ボタン
            if st.button("🚀 処理を実行", type="primary", use_container_width=True):
                # edited_textをセッション状態から取得
                edited_text = st.session_state.get("edited_text", "")
                if not edited_text:
                    st.error("切り抜き箇所が指定されていません。")
                    return

                # 実行前にAPI設定を反映
                if st.session_state.get("use_api", False):
                    set_api_mode(True, st.session_state.get("api_key", ""))
                else:
                    set_api_mode(False)

                # 区切り文字対応の差分検索を使用
                text_processor = TextProcessor()

                # 境界マーカーを解析
                boundary_adjustments = text_processor.parse_boundary_markers(edited_text)

                # マーカーを除去したテキストで処理
                cleaned_text = text_processor.remove_boundary_markers(edited_text)

                # 区切り文字の様々なパターンをチェック（処理実行時）
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None

                for pattern in separator_patterns:
                    if pattern in cleaned_text:
                        found_separator = pattern
                        break

                if found_separator:
                    # 区切り文字対応処理
                    time_ranges = text_processor.find_differences_with_separator(
                        full_text, cleaned_text, transcription, found_separator
                    )

                    # 各セクションで追加文字チェック
                    sections = text_processor.split_text_by_separator(cleaned_text, found_separator)
                    has_additions = False
                    for section in sections:
                        diff = text_processor.find_differences(full_text, section)
                        if diff.has_additions():
                            has_additions = True
                            break

                    if has_additions:
                        st.error("元の動画に存在しない部分が含まれています。各セクションを確認してください。")
                        return

                else:
                    # 従来の処理
                    diff = text_processor.find_differences(full_text, cleaned_text)

                    if diff.has_additions():
                        st.error("元の動画に存在しない部分が含まれています。赤いハイライト部分を確認してください。")
                        return

                    time_ranges = diff.get_time_ranges(transcription)

                # 境界調整を適用
                if boundary_adjustments:
                    time_ranges = text_processor.apply_boundary_adjustments(
                        time_ranges, boundary_adjustments, cleaned_text
                    )

                # タイムライン編集で調整された時間範囲があれば使用
                if "adjusted_time_ranges" in st.session_state:
                    st.info(
                        f"📊 タイムライン編集済みの時間範囲を使用します"
                        f"（{len(st.session_state.adjusted_time_ranges)}クリップ）"
                    )
                    time_ranges = st.session_state.adjusted_time_ranges
                    # adjusted_time_rangesは保持（出力設定変更時にクリア）

                if not time_ranges:
                    st.error("切り抜き箇所が見つかりませんでした。")
                    return

                # 出力ディレクトリの設定（動画と同じ場所にTextffCutフォルダ作成）
                video_name = Path(video_path).stem
                safe_name = get_safe_filename(video_name)
                video_parent = Path(video_path).parent

                # 動画と同じ場所にTextffCutフォルダを作成
                project_dir = video_parent / f"{safe_name}_TextffCut"

                # ディレクトリを作成（XMLファイル保護のためクリーンしない）
                project_path = ensure_directory(Path(project_dir), clean=False)

                # ConfigurationServiceを使用して出力パス情報を取得
                config_service = ConfigurationService(config)

                # 処理タイプのマッピング
                process_type_map = {"切り抜きのみ": "clip", "切り抜き + 無音削除": "both"}
                mapped_process_type = process_type_map.get(process_type, "full")

                # 処理タイプに応じたサフィックス（アルファベット表現）
                if process_type == "切り抜きのみ":
                    type_suffix = "Clip"
                else:
                    type_suffix = "NoSilence"

                # デバッグ：使用する時間範囲を表示（spinner外で表示）
                with st.expander("🔍 デバッグ情報", expanded=True):
                    st.write(f"処理に使用する時間範囲: {len(time_ranges)}クリップ")
                    for i, (start, end) in enumerate(time_ranges[:3]):  # 最初の3つだけ表示
                        st.write(f"  - クリップ{i + 1}: {start:.1f}秒 〜 {end:.1f}秒 (長さ: {end - start:.1f}秒)")
                    if len(time_ranges) > 3:
                        st.write(f"  ... 他 {len(time_ranges) - 3} クリップ")

                # ProcessingContextで処理を実行（エラー時は自動クリーンアップ）
                with st.spinner("処理中..."), ProcessingContext(project_path) as temp_manager:
                    try:
                        # サービス層を使用するため、直接インスタンス化は不要

                        # プログレスバーを初期化
                        progress_bar, status_text = show_progress(0, "処理を開始しています...")

                        # 残す時間範囲を決定
                        if process_type == "切り抜きのみ":
                            # 切り抜きのみの場合はtime_rangesをそのまま使用
                            keep_ranges = time_ranges
                            show_progress(0.5, "切り抜き箇所を処理中...", progress_bar, status_text)

                        else:
                            # 無音削除付きで処理（新フロー）
                            def progress_callback(progress, status):
                                show_progress(progress, status, progress_bar, status_text)

                            # VideoProcessingServiceを使用して無音削除
                            video_service = VideoProcessingService(config)
                            from core import TranscriptionSegment

                            # time_rangesからセグメントを作成
                            segments_for_removal = []
                            for start, end in time_ranges:
                                segments_for_removal.append(
                                    TranscriptionSegment(start=start, end=end, text="", words=[])
                                )

                            silence_result = video_service.remove_silence(
                                video_path=video_path,
                                segments=segments_for_removal,
                                threshold=noise_threshold,
                                min_silence_duration=min_silence_duration,
                                pad_start=padding_start,
                                pad_end=padding_end,
                                min_segment_duration=min_segment_duration,
                                progress_callback=progress_callback,
                            )

                            if silence_result.success:
                                # 調整されたセグメントから時間範囲を抽出
                                adjusted_segments = silence_result.data
                                keep_ranges = [(seg.start, seg.end) for seg in adjusted_segments]
                            else:
                                st.error(f"無音削除エラー: {silence_result.error}")
                                return

                        # 出力形式に応じて処理
                        if primary_format in ["FCPXMLファイル", "Premiere Pro XML"]:
                            # XMLファイル生成の準備
                            timeline_pos = 0  # timeline_posを初期化

                            # 形式を決定
                            export_format, xml_ext = determine_export_format(primary_format)

                            # 出力パスを生成
                            export_paths = generate_export_paths(
                                project_path=project_path,
                                base_name=safe_name,
                                type_suffix=type_suffix,
                                export_srt=export_srt,
                                xml_ext=xml_ext,
                            )
                            xml_path = export_paths["xml"]

                            # SRTも同時出力する場合
                            if export_srt:
                                # 差分検出ベースのSRTエクスポート

                                # 差分情報を取得（すでに計算済み）
                                if found_separator:
                                    # 区切り文字を除去して差分計算
                                    text_without_separator = cleaned_text.replace(found_separator, " ")
                                    diff = text_processor.find_differences(full_text, text_without_separator)
                                else:
                                    diff = text_processor.find_differences(full_text, cleaned_text)

                                # SRT設定を取得
                                srt_settings = get_srt_settings_from_session()

                                # TimeMapperを作成（無音削除時に必要）
                                time_mapper = None
                                if process_type != "切り抜きのみ":
                                    from core.time_mapper import TimeMapper

                                    time_mapper = TimeMapper(time_ranges, keep_ranges)

                                # SRTエクスポート
                                srt_success, srt_error = export_srt_with_diff(
                                    config=config,
                                    video_path=Path(video_path),
                                    output_path=xml_path,  # この時点ではXMLと同じパス
                                    diff_data=diff,
                                    transcription_result=transcription,
                                    time_mapper=time_mapper,
                                    remove_silence=(process_type != "切り抜きのみ"),
                                )

                                if not timeline_pos and srt_success:
                                    # SRTが成功した場合のタイムライン長を計算
                                    timeline_pos = sum(end - start for start, end in time_ranges)

                            # XMLの場合は空のセグメントでOK
                            # XMLエクスポート実行
                            success, error_msg, timeline_pos = export_xml(
                                config=config,
                                video_path=Path(video_path),
                                keep_ranges=keep_ranges,
                                output_path=xml_path,
                                export_format=export_format,
                                remove_silence=(process_type != "切り抜きのみ"),
                            )

                            if success:
                                # 100%完了を表示
                                # パス表示（Docker環境ではホストパスに変換）
                                display_path = get_display_path(xml_path)
                                # SRT字幕も出力する場合
                                if export_srt:
                                    # SRT出力処理（XMLと同じ連番を使用）
                                    srt_output_success = False
                                    # XMLファイル名から連番を抽出
                                    xml_stem = xml_path.stem  # 例: safe_name_TextffCut_NoSilence_01
                                    srt_path = project_path / f"{xml_stem}.srt"

                                    # edited_textをセッション状態から取得
                                    saved_edited_text = st.session_state.get("edited_text", "")

                                    # 差分情報を取得（すでに計算済み）
                                    if found_separator:
                                        # 区切り文字を除去して差分計算
                                        text_without_separator = saved_edited_text.replace(found_separator, " ")
                                        diff = text_processor.find_differences(full_text, text_without_separator)
                                    else:
                                        diff = text_processor.find_differences(full_text, saved_edited_text)

                                    # SRT設定を取得
                                    srt_settings = get_srt_settings_from_session()

                                    # TimeMapperを作成（無音削除時に必要）
                                    time_mapper = None
                                    if process_type != "切り抜きのみ":
                                        from core.time_mapper import TimeMapper

                                        time_mapper = TimeMapper(time_ranges, keep_ranges)

                                    # SRTエクスポート
                                    srt_output_success, srt_error = export_srt_with_diff(
                                        config=config,
                                        video_path=Path(video_path),
                                        output_path=srt_path,
                                        diff_data=diff,
                                        transcription_result=transcription,
                                        time_mapper=time_mapper,
                                        remove_silence=(process_type != "切り抜きのみ"),
                                    )

                                    # 成功メッセージを作成
                                    success_message = format_export_success_message(
                                        format_name=primary_format,
                                        output_path=xml_path,
                                        timeline_duration=timeline_pos,
                                        srt_path=srt_path if export_srt else None,
                                        srt_success=srt_output_success if export_srt else True,
                                    )

                                    # クリップ数と総時間を追加
                                    additional_info = (
                                        f" | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒"
                                    )

                                    show_progress(
                                        1.0,
                                        success_message + additional_info,
                                        progress_bar,
                                        status_text,
                                    )

                                # XMLやSRTの場合は中間ファイルを削除（TextffCutファイルと文字起こしを保護）
                                cleanup_intermediate_files(
                                    project_path,
                                    keep_patterns=[
                                        f"{safe_name}_TextffCut_*.fcpxml",
                                        f"{safe_name}_TextffCut_*.xml",
                                        f"{safe_name}_TextffCut_*.srt",
                                        f"{safe_name}_TextffCut_*.mp4",
                                        "transcriptions/",
                                    ],
                                )

                            else:
                                st.error(f"{primary_format}ファイルの生成に失敗しました。")
                        else:
                            # 動画ファイル出力（時間範囲から抽出）
                            show_progress(0.0, "動画セグメントを抽出中...", progress_bar, status_text)

                            output_files = []
                            total_ranges = len(keep_ranges)

                            for _i, (start, end) in enumerate(keep_ranges):
                                progress = (i + 1) / total_ranges * 0.8  # 最大80%まで
                                show_progress(
                                    progress,
                                    f"セグメント {i + 1}/{total_ranges} を抽出中...",
                                    progress_bar,
                                    status_text,
                                )

                                segment_file = project_path / f"segment_{i + 1}.mp4"
                                # VideoProcessingServiceを使用
                                if "video_service" not in locals():
                                    video_service = VideoProcessingService(config)

                                # 一つのセグメントを抽出

                                from core import TranscriptionSegment

                                segments_to_extract = [TranscriptionSegment(start=start, end=end, text="")]

                                extract_result = video_service.extract_segments(
                                    video_path=video_path,
                                    segments=segments_to_extract,
                                    output_dir=str(project_path),
                                    format="mp4",
                                )

                                if extract_result.success:
                                    extracted_files = extract_result.data
                                    if extracted_files:
                                        # ファイル名をリネーム
                                        import shutil

                                        shutil.move(extracted_files[0], str(segment_file))
                                        success = True
                                    else:
                                        success = False
                                else:
                                    success = False

                                if success:
                                    output_files.append(str(segment_file))

                            # 結合処理
                            if len(output_files) > 1:
                                # 統一された命名規則で出力
                                from utils.file_utils import get_unique_path

                                combined_path = get_unique_path(
                                    project_path / f"{safe_name}_TextffCut_{type_suffix}.mp4"
                                )
                                show_progress(0.8, "動画を統合しています...", progress_bar, status_text)

                                # VideoProcessingServiceを使用して動画を結合
                                if "video_service" not in locals():
                                    video_service = VideoProcessingService(config)

                                merge_result = video_service.merge_videos(
                                    video_files=output_files,
                                    output_path=str(combined_path),
                                    progress_callback=lambda p, s: show_progress(
                                        0.8 + p * 0.2, s, progress_bar, status_text
                                    ),
                                )

                                success = merge_result.success

                                if success:
                                    # 100%完了を表示
                                    # パス表示（Docker環境ではホストパスに変換）
                                    display_path = get_display_path(project_path)
                                    # SRT字幕も出力する場合
                                    if export_srt:
                                        # SRT出力処理（動画と同じ連番を使用）
                                        srt_output_success = False
                                        # 動画ファイル名から連番を抽出
                                        video_stem = combined_path.stem  # 例: safe_name_TextffCut_NoSilence_01
                                        srt_path = project_path / f"{video_stem}.srt"

                                        # 差分検出ベースのSRTエクスポーターを使用
                                        from core.srt_diff_exporter import SRTDiffExporter

                                        # 差分情報を取得（すでに計算済み）
                                        if found_separator:
                                            # 区切り文字を除去して差分計算
                                            text_without_separator = edited_text.replace(found_separator, " ")
                                            diff = text_processor.find_differences(full_text, text_without_separator)
                                        else:
                                            diff = text_processor.find_differences(full_text, edited_text)

                                        # SRT設定を取得
                                        srt_settings = st.session_state.get(
                                            "srt_settings",
                                            {
                                                "min_duration": 0.5,
                                                "max_duration": 7.0,
                                                "gap_threshold": 0.1,
                                                "chars_per_second": 15.0,
                                                "max_line_length": 42,
                                                "max_lines": 2,
                                                "encoding": "utf-8",
                                                "fps": float(timeline_fps),
                                            },
                                        )

                                        # FPSを追加
                                        srt_settings["fps"] = float(timeline_fps)

                                        # 無音削除の有無で処理を分岐
                                        srt_exporter = SRTDiffExporter(config)

                                        if process_type == "切り抜きのみ":
                                            # 無音削除なし：従来の処理
                                            srt_output_success = srt_exporter.export_from_diff(
                                                diff=diff,
                                                transcription_result=transcription,
                                                output_path=str(srt_path),
                                                encoding=srt_settings.get("encoding", "utf-8"),
                                                srt_settings=srt_settings,
                                            )
                                        else:
                                            # 無音削除あり：タイムマッピングを使用
                                            from core.time_mapper import TimeMapper

                                            # TimeMapperを作成（time_rangesとkeep_rangesの対応）
                                            time_mapper = TimeMapper(time_ranges, keep_ranges)

                                            srt_output_success = srt_exporter.export_from_diff_with_silence_removal(
                                                diff=diff,
                                                transcription_result=transcription,
                                                output_path=str(srt_path),
                                                time_mapper=time_mapper,
                                                encoding=srt_settings.get("encoding", "utf-8"),
                                                srt_settings=srt_settings,
                                            )

                                        if srt_output_success:
                                            # SRT出力成功メッセージを追加
                                            if os.path.exists("/.dockerenv"):
                                                srt_display_path = get_display_path(srt_path)
                                            else:
                                                srt_display_path = str(srt_path)

                                            show_progress(
                                                1.0,
                                                f"処理が完了しました！ 出力先: {display_path} | "
                                                f"SRT字幕: {srt_display_path} | "
                                                f"📊 {len(keep_ranges)}個のセグメントを結合",
                                                progress_bar,
                                                status_text,
                                            )
                                        else:
                                            # SRT出力は失敗したが、動画は成功
                                            show_progress(
                                                1.0,
                                                f"処理が完了しました！ 出力塩: {display_path} | "
                                                f"⚠️ SRT字幕の生成に失敗 | "
                                                f"📊 {len(keep_ranges)}個のセグメントを結合",
                                                progress_bar,
                                                status_text,
                                            )
                                    else:
                                        # SRT出力なし
                                        show_progress(
                                            1.0,
                                            f"処理が完了しました！ 出力先: {display_path} | "
                                            f"📊 {len(keep_ranges)}個のセグメントを結合",
                                            progress_bar,
                                            status_text,
                                        )

                                    # 動画プレビュー
                                    st.video(str(combined_path))

                                    # 中間ファイルをクリーンアップ（TextffCutファイルと文字起こしは保持）
                                    cleanup_intermediate_files(
                                        project_path,
                                        keep_patterns=[
                                            f"{safe_name}_TextffCut_*.mp4",
                                            f"{safe_name}_TextffCut_*.fcpxml",
                                            f"{safe_name}_TextffCut_*.srt",
                                            "transcriptions/",
                                        ],
                                    )

                                    # 結果フォルダセクションを表示（Docker版のみ）
                                    # show_result_folder_section(project_path, safe_name)
                                else:
                                    st.error("動画の結合に失敗しました")

                            elif output_files:
                                # 100%完了を表示
                                # パス表示（Docker環境ではホストパスに変換）
                                display_path = get_display_path(project_path)
                                show_progress(
                                    1.0, f"処理が完了しました！ 出力先: {display_path}", progress_bar, status_text
                                )

                                # 動画プレビュー
                                st.video(output_files[0])

                                # 中間ファイルをクリーンアップ（TextffCutファイルと文字起こしは保持）
                                cleanup_intermediate_files(
                                    project_path,
                                    keep_patterns=[
                                        f"{safe_name}_TextffCut_*.mp4",
                                        f"{safe_name}_TextffCut_*.fcpxml",
                                        "transcriptions/",
                                    ],
                                )

                            else:
                                st.error("動画の抽出に失敗しました")

                    except Exception as e:
                        # 新しい統一エラーハンドリングシステムを使用
                        from core.error_handling import ProcessingError, ValidationError

                        try:
                            error_handler = ErrorHandler(logger)  # type: ignore

                            # 既存のエラー型の互換性を維持
                            from utils.exceptions import VideoProcessingError

                            if isinstance(e, VideoProcessingError):
                                st.error(e.get_user_message())
                            elif isinstance(e, ProcessingError | ValidationError):
                                error_info = error_handler.handle_error(e, context="動画処理", raise_after=False)
                                if error_info:
                                    st.error(error_info["user_message"])
                            else:
                                # 未知のエラーをProcessingErrorでラップ
                                wrapped_error = ProcessingError(f"動画処理中にエラーが発生しました: {str(e)}", cause=e)
                                error_info = error_handler.handle_error(
                                    wrapped_error, context="動画処理", raise_after=False
                                )
                                if error_info:
                                    st.error(error_info["user_message"])
                        except Exception:
                            st.error(f"動画処理中にエラーが発生しました: {str(e)}")

    # モーダル表示
    if st.session_state.get("show_modal", False):
        show_red_highlight_modal(
            st.session_state.get("current_edited_text", ""), st.session_state.get("current_diff", None)
        )

    # モーダル表示は削除（メイン画面で確認表示に変更）

    # UIの最後でrerunを実行（チェックボックス状態保持のため）
    if st.session_state.get("need_rerun", False):
        st.session_state.need_rerun = False
        st.rerun()

    # DIコンテナのデバッグ情報（開発環境のみ）
    if os.getenv("TEXTFFCUT_ENV", "production") == "development":
        with st.sidebar:
            with st.expander("🔧 DI Container Debug", expanded=False):
                st.caption("DI Container Status")
                st.text(f"Environment: {container.config().environment}")
                st.text(f"Testing Mode: {container.config().is_testing}")
                st.text(f"Container ID: {id(container)}")


# モーダル関数は削除（メイン画面表示に変更）


if __name__ == "__main__":
    # セッション終了時のクリーンアップを登録
    import atexit

    atexit.register(cleanup_temp_files)

    main()
