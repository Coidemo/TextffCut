"""
TextffCut - メインアプリケーション
リファクタリング版：モジュール化された構造を使用
"""

import os
from pathlib import Path
from typing import Any, Optional

import streamlit as st

# DI統合
from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.containers import ApplicationContainer

from config import config  # 段階的にConfigurationService経由に移行中
from core import TextProcessor
from core.alignment_processor import AlignmentProcessor
from core.constants import (
    ApiSettings,
    ModelSettings,
)
from core.error_handling import ErrorHandler
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription_subprocess import SubprocessTranscriber
from services import ConfigurationService, ExportService, TextEditingService, VideoProcessingService
from ui import (
    apply_dark_mode_styles,
    cleanup_temp_files,
    show_api_key_manager,
    show_diff_viewer,
    show_export_settings,
    show_help,
    show_progress,
    show_red_highlight_modal,
    show_silence_settings,
    show_text_editor,
    show_transcription_controls,
    show_video_input,
)
from ui.styles import get_custom_css
from ui.recovery_components import (
    show_recovery_check,
    show_recovery_history,
    show_recovery_settings,
    show_recovery_status,
)
from utils import ProcessingContext, cleanup_intermediate_files
from utils.config_helpers import get_ui_page_title, get_ui_layout, get_isolation_mode, set_api_mode, is_api_mode
from utils.debug_helpers import debug_words_status
from utils.environment import VIDEOS_DIR
from utils.file_utils import ensure_directory, get_safe_filename
from utils.logging import get_logger
from utils.path_helpers import get_display_path
from utils.time_utils import format_time
from utils.startup import run_initial_checks
from utils.export_helpers import (
    determine_export_format,
    create_export_segments,
    export_xml,
    export_srt_with_diff,
    generate_export_paths,
    format_export_success_message,
    get_srt_settings_from_session
)
from ui.constants import get_app_icon
from ui.components_modules.header import show_app_title

logger = get_logger(__name__)

# DIコンテナのグローバルインスタンス
_app_container: Optional[ApplicationContainer] = None

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

    # 分離モードに応じて適切なTranscriberを選択
    transcriber: Any
    if get_isolation_mode() == "subprocess":
        transcriber = SubprocessTranscriber(config)
    else:
        transcriber = SmartSplitTranscriber(config)

    # 利用可能なキャッシュを取得
    available_caches = transcriber.get_available_caches(video_path)

    # キャッシュ選択UIを表示（設定が決まる前なので、全キャッシュを表示）
    use_cache, run_new, selected_cache = show_transcription_controls(False, available_caches)

    if use_cache and selected_cache:
        # 選択されたキャッシュを読み込み
        result = transcriber.load_from_cache(selected_cache["file_path"])
        if result:
            st.session_state.transcription_result = result

            # 選択されたキャッシュの設定をセッションに反映
            if selected_cache["is_api"]:
                st.success(f"✅ APIモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")
            else:
                st.success(f"✅ ローカルモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")

            st.rerun()

    # 文字起こし実行の確認画面を常に表示（キャッシュがない場合、または新規実行したい場合）
    if True:  # 常に表示
        # 動画情報を取得
        try:
            from core.video import VideoInfo

            video_info = VideoInfo.from_file(video_path)
            duration_minutes = video_info.duration / 60

            # 確認画面を表示
            # （警告メッセージは実行ボタンの直前に移動）

            # 処理モード・モデル選択・動画時間・料金を4カラムで横並び表示
            mode_col, model_col, time_col, price_col = st.columns(4)

            with mode_col:
                st.markdown("**⚙️ 処理モード**")
                mode_options = ["🖥️ ローカル", "🌐 API"]
                previous_mode = st.session_state.get("use_api", False)
                default_index = 1 if previous_mode else 0

                selected_mode = st.radio(
                    "処理モード",
                    mode_options,
                    index=default_index,
                    key="mode_radio_main",
                    label_visibility="collapsed",
                    horizontal=True,
                )
                use_api = selected_mode == "🌐 API"
                st.session_state.use_api = use_api

            with model_col:
                if use_api:
                    st.markdown("**🤖 モデル**")
                    st.markdown("whisper-1")
                    model_size = "whisper-1"

                    # APIキーをセッションに保存
                    from utils.api_key_manager import api_key_manager

                    saved_key = api_key_manager.load_api_key()
                    if saved_key:
                        st.session_state.api_key = saved_key
                else:
                    st.markdown("**🤖 モデル**")
                    st.markdown("medium（固定）")
                    model_size = "medium"
                    st.session_state.local_model_size = model_size

            with time_col:
                st.markdown("**📊 動画時間**")
                from utils.time_utils import format_time as fmt_time

                st.markdown(f"{duration_minutes:.1f}分 ({fmt_time(video_info.duration)})")

            with price_col:
                if use_api:
                    # ConfigurationServiceを使用して料金計算
                    config_service = ConfigurationService(config)
                    cost_result = config_service.calculate_api_cost(duration_minutes)

                    if cost_result.success and cost_result.data:
                        cost_data = cost_result.data
                        estimated_cost_usd = cost_data["cost_usd"]
                        estimated_cost_jpy = cost_data["cost_jpy"]
                        st.markdown("**💰 推定料金**")
                        st.markdown(f"${estimated_cost_usd:.3f} (約{estimated_cost_jpy:.0f}円)")
                    else:
                        # フォールバック（サービスエラー時）
                        estimated_cost_usd = duration_minutes * ApiSettings.OPENAI_COST_PER_MINUTE
                        estimated_cost_jpy = estimated_cost_usd * 150
                        st.markdown("**💰 推定料金**")
                        st.markdown(f"${estimated_cost_usd:.3f} (約{estimated_cost_jpy:.0f}円)")
                else:
                    st.markdown("**💰 料金**")
                    st.markdown("無料（ローカル処理）")

            # API利用時の注意事項をコンパクトに表示
            if use_api:
                st.caption(
                    f"⚠️ API料金: ${ApiSettings.OPENAI_COST_PER_MINUTE}/分 | 為替変動あり | [最新料金](https://openai.com/pricing)を確認"
                )

                # 自動最適化モード（固定・内部処理）
                pass
            else:
                # ローカルモード（自動処理）
                pass

            # GPU/CPU情報はタブ内で表示されるため、ここでは削除

            # 実行ボタン（保存済みの文字起こしがあるかどうかで表示を変更）
            if available_caches:
                # 保存済みの文字起こしがある場合
                if use_api:
                    button_text = "💳 新たにAPIで文字起こしを実行する"
                else:
                    button_text = "🖥️ 新たにローカルで文字起こしを実行する"
                button_type = "secondary"  # 白塗り
            else:
                # 保存済みの文字起こしがない場合
                if use_api:
                    button_text = "💳 APIで文字起こしを実行する"
                else:
                    button_text = "🖥️ ローカルで文字起こしを実行する"
                button_type = "primary"  # 赤塗り

            # 過去の結果がある場合は上書き警告を表示
            if available_caches:
                st.warning("⚠️ 同じ設定の過去の文字起こし結果は上書きされます")

            if st.button(button_text, type=button_type, use_container_width=True):  # type: ignore
                # APIモードでAPIキーチェック
                if use_api and not st.session_state.get("api_key"):
                    st.error("⚠️ APIキーが設定されていません。サイドバーのAPIキー設定で設定してください。")
                    return

                # 確認情報を保存
                st.session_state.confirmation_info = {
                    "mode": "api" if use_api else "local",
                    "model_size": model_size,
                    "duration_minutes": duration_minutes,
                    "formatted_time": format_time(video_info.duration),
                }
                if use_api:
                    st.session_state.confirmation_info.update(
                        {"estimated_cost_usd": estimated_cost_usd, "estimated_cost_jpy": estimated_cost_jpy}
                    )

                # 実行フラグを設定
                st.session_state.should_run_transcription = True

                # 現在のモードとモデルを保存（変更検知用）
                st.session_state.previous_transcription_mode = use_api
                st.session_state.previous_transcription_model = model_size

                st.rerun()

        except FileNotFoundError:
            # 新しいエラーハンドリングシステムを使用
            from core.error_handling import FileValidationError

            file_error = FileValidationError(
                "指定された動画ファイルが見つかりません", details={"path": str(video_path)}
            )

            error_handler = ErrorHandler(logger)  # type: ignore
            error_info = error_handler.handle_error(file_error, context="ファイルアクセス")
            if error_info:
                st.error(f"📁 {error_info['user_message']}")
            return

        except OSError as e:
            # 新しいエラーハンドリングシステムを使用
            from core.error_handling import ResourceError

            resource_error = ResourceError(f"ファイルアクセスエラー: {str(e)}", cause=e)

            try:
                error_handler = ErrorHandler(logger)  # type: ignore
                error_info = error_handler.handle_error(resource_error, context="動画情報取得", raise_after=False)
                if error_info:
                    st.error(f"💾 {error_info['user_message']}")
            except AttributeError:
                st.error(f"💾 ファイルアクセスエラー: {str(e)}")
            return

        except Exception as e:
            # 新しいエラーハンドリングシステムを使用
            from core.error_handling import ProcessingError

            wrapped_error = ProcessingError(f"動画情報の取得に失敗: {str(e)}", cause=e)

            try:
                error_handler = ErrorHandler(logger)  # type: ignore
                error_info = error_handler.handle_error(wrapped_error, context="動画情報取得", raise_after=False)
                if error_info:
                    st.error(error_info["user_message"])
            except Exception:
                st.error(f"動画情報の取得に失敗: {str(e)}")
            return

    # 文字起こし実行の判定
    should_run_transcription = st.session_state.get("should_run_transcription", False)

    if should_run_transcription:
        # 実行フラグをリセット（次回実行時のため）
        if "should_run_transcription" in st.session_state:
            del st.session_state.should_run_transcription

        # 処理中止フラグをリセット
        st.session_state.cancel_transcription = False
        st.session_state.transcription_in_progress = True

        # キャンセルボタンを表示
        cancel_placeholder = st.empty()
        with cancel_placeholder.container():
            if st.button("❌ 処理を中止", type="secondary", use_container_width=True):
                st.session_state.cancel_transcription = True
                st.session_state.transcription_in_progress = False
                st.warning("文字起こし処理を中止しました。")
                return

        with st.spinner("文字起こし中..."):
            try:
                # キャンセルチェック
                if st.session_state.get("cancel_transcription", False):
                    st.session_state.transcription_in_progress = False
                    st.warning("文字起こし処理が中止されました。")
                    return

                # 実行前にAPI設定を反映（確認モーダルの情報を使用）
                confirmation_info = st.session_state.get("confirmation_info", {})
                if confirmation_info.get("mode") == "api":
                    set_api_mode(True, st.session_state.get("api_key", ""))
                else:
                    set_api_mode(False)

                # 設定を反映したTranscriberを再初期化
                # 分離モードに応じて適切なTranscriberを選択
                if get_isolation_mode() == "subprocess":
                    transcriber = SubprocessTranscriber(config)
                else:
                    transcriber = SmartSplitTranscriber(config)

                # シンプルなプログレスコールバック
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def cancellable_progress_callback(progress: float, status: str) -> None:
                    """キャンセル可能なプログレスコールバック"""
                    if st.session_state.get("cancel_transcription", False):
                        raise InterruptedError("処理が中止されました")
                    progress_bar.progress(min(progress, 1.0))
                    progress_text.info(status)

                    # 状態を表示
                    show_recovery_status(video_path, "transcribing", progress)

                progress_callback = cancellable_progress_callback

                # 文字起こし実行（新規実行：キャッシュ読み込みせず、結果は保存）
                model_to_use = confirmation_info.get("model_size", "base")
                result = transcriber.transcribe(
                    video_path, model_to_use, progress_callback=progress_callback, use_cache=False, save_cache=True
                )

                if result:
                    # APIモードでwordsが欠落している場合、アライメント処理を実行
                    if is_api_mode():
                        try:
                            # wordsフィールドのチェック
                            has_words = True
                            if hasattr(result, "segments"):
                                segments_without_words = [
                                    seg
                                    for seg in result.segments
                                    if not hasattr(seg, "words") or not seg.words or len(seg.words) == 0
                                ]
                                if segments_without_words:
                                    has_words = False

                            # wordsがない場合、アライメント処理を実行
                            if not has_words:
                                progress_text.info("🔄 文字位置情報を生成中...")
                                progress_bar.progress(0.7)

                                # アライメント処理
                                alignment_processor = AlignmentProcessor(config)

                                # アライメント用のプログレスコールバック
                                def alignment_progress(progress: float, status: str):
                                    # アライメントは全体の70-100%
                                    overall_progress = 0.7 + (progress * 0.3)
                                    progress_bar.progress(min(overall_progress, 1.0))
                                    progress_text.info(f"🔄 {status}")

                                # アライメント実行
                                # resultオブジェクトからセグメントを取得
                                segments: list[Any] = []
                                if hasattr(result, "segments"):
                                    # V2形式に変換（必要な場合）
                                    if hasattr(result, "to_v2_format"):
                                        v2_result = result.to_v2_format()
                                        segments = v2_result.segments if hasattr(v2_result, "segments") else []
                                    else:
                                        segments = result.segments

                                # 言語情報を取得
                                language = result.language if hasattr(result, "language") else "ja"

                                # アライメント実行
                                aligned_segments = alignment_processor.align(
                                    segments, video_path, language, progress_callback=alignment_progress
                                )

                                if aligned_segments:
                                    # アライメント結果で元のセグメントを更新
                                    if hasattr(result, "segments"):
                                        result.segments = aligned_segments
                                    # V2形式の場合は新しいオブジェクトを作成
                                    elif hasattr(result, "to_v2_format"):

                                        # 既存のresultからV2形式を作成し、セグメントを更新
                                        v2_result = result.to_v2_format()
                                        v2_result.segments = aligned_segments
                                        result = v2_result

                                    progress_text.success("✅ 文字位置情報の生成完了！")
                                else:
                                    # アライメントが失敗した場合もエラーとして扱う
                                    st.error("❌ 文字位置情報の生成に失敗しました。")
                                    st.error("文字位置情報（words）は必須です。文字起こしを再実行してください。")
                                    st.session_state.transcription_in_progress = False
                                    cancel_placeholder.empty()
                                    progress_bar.empty()
                                    progress_text.empty()
                                    return

                        except Exception as e:
                            # アライメントエラーは致命的なエラーとして扱う
                            st.error(f"❌ 文字位置情報の生成に失敗しました: {str(e)}")
                            st.error("文字位置情報（words）は必須です。文字起こしを再実行してください。")
                            logger.error(f"アライメントエラー（致命的）: {str(e)}")
                            # 処理を中止
                            st.session_state.transcription_in_progress = False
                            cancel_placeholder.empty()
                            progress_bar.empty()
                            progress_text.empty()
                            return

                    # デバッグ: wordsフィールドの状態を出力
                    if os.environ.get("TEXTFFCUT_DEBUG"):
                        debug_words_status(result, logger_name=__name__)

                    st.session_state.transcription_result = result
                    st.session_state.transcription_in_progress = False

                    # UI要素をクリーンアップ
                    cancel_placeholder.empty()
                    progress_bar.empty()
                    progress_text.empty()
                    st.success("✅ 文字起こし完了！")
                    st.rerun()

            except InterruptedError as e:
                # キャンセルされた場合
                st.session_state.transcription_in_progress = False
                cancel_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()
                st.warning(f"⚠️ {str(e)}")
            except MemoryError as e:
                # メモリエラーの特別処理
                st.session_state.transcription_in_progress = False
                cancel_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()

                # 新しいエラーハンドリングシステムを使用
                from core.error_handling import ResourceError

                memory_error = ResourceError(
                    f"メモリ不足エラー: {str(e)}",
                    cause=e,
                    details={
                        "recovery_suggestions": [
                            f"より小さなモデル（{ModelSettings.DEFAULT_SIZE}等）を使用してください",
                            "他のアプリケーションを終了してメモリを解放してください",
                            "システムのメモリを増設してください",
                        ]
                    },
                )

                try:
                    error_handler = ErrorHandler(logger)  # type: ignore
                    error_info = error_handler.handle_error(memory_error, context="文字起こし", raise_after=False)
                    if error_info:
                        st.error(f"❌ {error_info['user_message']}")
                        if "details" in error_info and "recovery_suggestions" in error_info["details"]:
                            for suggestion in error_info["details"]["recovery_suggestions"]:
                                st.error(f"💡 {suggestion}")
                except Exception:
                    st.error(f"❌ メモリ不足エラー: {str(e)}")

            except Exception as e:
                # その他のエラー
                st.session_state.transcription_in_progress = False
                cancel_placeholder.empty()
                progress_bar.empty()
                progress_text.empty()

                # 新しい統一エラーハンドリングシステムを使用
                from core.error_handling import ProcessingError
                from core.error_handling import TranscriptionError as NewTranscriptionError
                from utils.exceptions import TranscriptionError as LegacyTranscriptionError

                try:
                    error_handler = ErrorHandler(logger)  # type: ignore

                    # 既存のエラー型との互換性を維持
                    if isinstance(e, LegacyTranscriptionError):
                        st.error(e.get_user_message())
                    elif isinstance(e, (ProcessingError, NewTranscriptionError)):
                        error_info = error_handler.handle_error(e, context="文字起こし", raise_after=False)
                        if error_info:
                            st.error(error_info["user_message"])
                    else:
                        # 未知のエラーをProcessingErrorでラップ
                        wrapped_error = ProcessingError(f"文字起こし処理でエラーが発生しました: {str(e)}", cause=e)
                        error_info = error_handler.handle_error(wrapped_error, context="文字起こし", raise_after=False)
                        if error_info:
                            st.error(error_info["user_message"])
                except Exception:
                    st.error(f"文字起こし処理でエラーが発生しました: {str(e)}")

    # 文字起こし結果の処理
    if "transcription_result" in st.session_state and st.session_state.transcription_result:
        transcription = st.session_state.transcription_result

        # 文字起こし結果の厳密な検証（表示前に必ず実行）
        # wordsフィールドが必須
        has_valid_words = True
        segments_without_words = []

        for seg in transcription.segments:
            if not seg.words or len(seg.words) == 0:
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

        # 2カラムレイアウト
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した箇所が緑色でハイライトされます")

            # 編集されたテキストがある場合は差分を表示
            saved_edited_text = st.session_state.get("edited_text", "")
            if saved_edited_text:
                text_processor = TextProcessor()

                # TextEditingServiceを使用して差分計算
                text_service = TextEditingService(config)

                # 区切り文字がある場合は区切り文字対応の差分表示
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None
                for pattern in separator_patterns:
                    if pattern in saved_edited_text:
                        found_separator = pattern
                        break

                # 境界調整マーカーが含まれているかチェック
                has_boundary_markers = any(marker in saved_edited_text for marker in ["[<", "[>", "<]", ">]"])

                if found_separator:
                    # 区切り文字がある場合：区切り文字を除去して差分計算
                    text_without_separator = saved_edited_text.replace(found_separator, " ")  # スペースで置換
                    # 互換性のためTextProcessorも使用（サービス層への移行を段階的に行う）
                    text_processor = TextProcessor()
                    # 境界マーカーを除去してから差分計算
                    cleaned_text = (
                        text_processor.remove_boundary_markers(text_without_separator)
                        if has_boundary_markers
                        else text_without_separator
                    )
                    diff = text_processor.find_differences(
                        full_text, cleaned_text, skip_normalization=has_boundary_markers
                    )
                    show_diff_viewer(full_text, diff)
                else:
                    # 区切り文字がない場合：サービスを使用
                    diff_result = text_service.find_differences(transcription.segments, saved_edited_text)
                    if diff_result.success:
                        # 既存の差分表示と互換性を保つため、TextProcessorも使用
                        text_processor = TextProcessor()
                        # 境界マーカーを除去してから差分計算
                        cleaned_text = (
                            text_processor.remove_boundary_markers(saved_edited_text)
                            if has_boundary_markers
                            else saved_edited_text
                        )
                        diff = text_processor.find_differences(
                            full_text, cleaned_text, skip_normalization=has_boundary_markers
                        )
                        show_diff_viewer(full_text, diff)
                    else:
                        st.error(f"差分検出エラー: {diff_result.error}")
            else:
                show_diff_viewer(full_text)

        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く箇所を入力してください")

            # テキストエディタ
            edited_text = show_text_editor(st.session_state.get("edited_text", ""), height=400)

            # モーダル表示の処理を削除（更新ボタンでのみ表示するため）

            # 文字数と時間の表示
            display_text = edited_text

            # 保存されたテキストがあれば、それを優先
            saved_edited_text = st.session_state.get("edited_text", "")
            if saved_edited_text:
                display_text = saved_edited_text

            if display_text:
                # 時間計算
                text_processor = TextProcessor()

                # 境界調整マーカーが含まれているかチェック
                has_boundary_markers = any(marker in display_text for marker in ["[<", "[>", "<]", ">]"])

                # マーカーを除去したテキストで時間計算
                cleaned_display_text = (
                    text_processor.remove_boundary_markers(display_text) if has_boundary_markers else display_text
                )

                # 区切り文字パターンをチェック
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None

                for pattern in separator_patterns:
                    if pattern in cleaned_display_text:
                        found_separator = pattern
                        break

                if found_separator:
                    time_ranges = text_processor.find_differences_with_separator(
                        full_text,
                        cleaned_display_text,
                        transcription,
                        found_separator,
                        skip_normalization=has_boundary_markers,
                    )
                    sections = text_processor.split_text_by_separator(cleaned_display_text, found_separator)
                    separator_info = f" / セクション数: {len(sections)}"
                else:
                    diff = text_processor.find_differences(
                        full_text, cleaned_display_text, skip_normalization=has_boundary_markers
                    )
                    time_ranges = diff.get_time_ranges(transcription)
                    separator_info = ""

                total_duration = sum(end - start for start, end in time_ranges)
                st.caption(
                    f"文字数: {len(display_text)}文字 / 時間: {total_duration:.1f}秒（無音削除前）{separator_info}"
                )

            # ボタンを横並びに配置
            button_col1, button_col2 = st.columns([1, 3])

            with button_col1:
                # 更新ボタン
                update_clicked = st.button("更新", type="primary", use_container_width=True)
                if update_clicked:
                    text_processor = TextProcessor()

                    # 境界調整モードに応じた処理
                    if st.session_state.get("boundary_adjustment_mode", False):
                        # 境界調整モードON
                        # 1. 既存のマーカー情報を抽出
                        existing_markers = text_processor.extract_existing_markers(edited_text)

                        # 2. マーカーを除去したテキストで処理
                        cleaned_text = text_processor.remove_boundary_markers(edited_text)

                        # 3. 区切り文字の確認
                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in cleaned_text:
                                found_separator = pattern
                                break

                        if found_separator:
                            # 区切り文字がある場合：各セクションを処理
                            sections = text_processor.split_text_by_separator(cleaned_text, found_separator)
                            processed_sections = []

                            for section in sections:
                                # 各セクションの差分を検出してセグメント化
                                diff = text_processor.find_differences(full_text, section)
                                if len(diff.common_positions) > 0:
                                    # セグメントごとに改行とマーカーを挿入
                                    section_with_markers = ""
                                    for i, pos in enumerate(diff.common_positions):
                                        if i > 0:
                                            section_with_markers += "\n"
                                        # 既存マーカーがあればその値を使用、なければ初期値
                                        if pos.text in existing_markers:
                                            start_val = existing_markers[pos.text]["start"]
                                            end_val = existing_markers[pos.text]["end"]
                                        else:
                                            start_val = 0.0
                                            end_val = 0.0
                                        section_with_markers += f"[<{start_val}]{pos.text}[{end_val}>]"
                                    processed_sections.append(section_with_markers)
                                else:
                                    processed_sections.append(section)

                            # セクションを区切り文字で結合
                            processed_text = f"\n{found_separator}\n".join(processed_sections)
                        else:
                            # 区切り文字がない場合：全体を処理
                            diff = text_processor.find_differences(full_text, cleaned_text)
                            if len(diff.common_positions) > 0:
                                # セグメントごとに改行とマーカーを挿入
                                processed_text = ""
                                for i, pos in enumerate(diff.common_positions):
                                    if i > 0:
                                        processed_text += "\n"
                                    # 既存マーカーがあればその値を使用、なければ初期値
                                    if pos.text in existing_markers:
                                        start_val = existing_markers[pos.text]["start"]
                                        end_val = existing_markers[pos.text]["end"]
                                    else:
                                        start_val = 0.0
                                        end_val = 0.0
                                    processed_text += f"[<{start_val}]{pos.text}[{end_val}>]"
                            else:
                                processed_text = cleaned_text

                        # 処理後のテキストを設定
                        st.session_state.text_editor_value = processed_text
                        edited_text = processed_text

                        st.session_state.time_ranges = time_ranges
                        # タイムライン編集セクションは自動で表示しない（ユーザーが選択）
                        # adjusted_time_rangesがある場合はクリア（新しいテキストに更新されたため）
                        if "adjusted_time_ranges" in st.session_state:
                            del st.session_state.adjusted_time_ranges

                        # マーカー位置の検証（境界調整モードON時のみ）
                        marker_errors = text_processor.validate_marker_positions(processed_text)
                        if marker_errors:
                            # セグメント内配置エラー
                            st.session_state.marker_position_errors = marker_errors
                            st.session_state.show_marker_error = True
                            st.session_state.original_edited_text = processed_text
                            st.error("境界調整マーカーの位置を修正してから更新してください。")
                            return
                    else:
                        # 通常モード：マーカーを削除
                        cleaned_text = text_processor.remove_boundary_markers(edited_text)
                        if cleaned_text != edited_text:
                            st.session_state.text_editor_value = cleaned_text
                            edited_text = cleaned_text
                            logger.info("通常モード：境界調整マーカーを削除しました")

                    st.session_state.edited_text = edited_text
                    st.session_state.preview_update_requested = True  # 音声プレビュー更新フラグ

                    # 時間範囲を計算して保存
                    if edited_text:
                        text_processor = TextProcessor()

                        # 境界マーカーを解析
                        boundary_adjustments = text_processor.parse_boundary_markers(edited_text)

                        # マーカーを除去したテキストで差分検出
                        cleaned_text = text_processor.remove_boundary_markers(edited_text)

                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in cleaned_text:
                                found_separator = pattern
                                break

                        # 境界調整マーカーが含まれているかチェック
                        has_boundary_markers_in_edited = any(
                            marker in edited_text for marker in ["[<", "[>", "<]", ">]"]
                        )

                        if found_separator:
                            time_ranges = text_processor.find_differences_with_separator(
                                full_text,
                                cleaned_text,
                                transcription,
                                found_separator,
                                skip_normalization=has_boundary_markers_in_edited,
                            )
                        else:
                            diff = text_processor.find_differences(
                                full_text, cleaned_text, skip_normalization=has_boundary_markers_in_edited
                            )
                            time_ranges = diff.get_time_ranges(transcription)

                        # 境界調整を適用
                        if boundary_adjustments:
                            adjusted_time_ranges = text_processor.apply_boundary_adjustments(
                                time_ranges, boundary_adjustments, edited_text
                            )
                            st.session_state.time_ranges = adjusted_time_ranges
                            st.session_state.has_boundary_adjustments = True
                        else:
                            st.session_state.time_ranges = time_ranges
                            st.session_state.has_boundary_adjustments = False

                        # タイムライン編集セクションは表示しない（境界調整で代替）
                        st.session_state.show_timeline_section = False
                        st.session_state.timeline_completed = True  # 境界調整完了として扱う

                    # 赤ハイライトがあるかチェック（モード別処理）
                    if edited_text:
                        text_processor = TextProcessor()

                        # マーカーを除去したテキストでチェック
                        cleaned_text = text_processor.remove_boundary_markers(edited_text)

                        # デバッグ：マーカー除去前後の比較
                        if edited_text != cleaned_text:
                            logger.debug(f"マーカー除去前: {edited_text[:100]}...")
                            logger.debug(f"マーカー除去後: {cleaned_text[:100]}...")

                        # 区切り文字対応
                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in cleaned_text:
                                found_separator = pattern
                                break

                        # 境界調整マーカーが含まれているかチェック
                        has_boundary_markers = any(marker in edited_text for marker in ["[<", "[>", "<]", ">]"])

                        # 境界調整モードに応じたエラーチェック
                        if st.session_state.get("boundary_adjustment_mode", False):
                            # 境界調整モードON時：マーカー位置エラーをチェック
                            marker_errors = []
                            if has_boundary_markers:
                                # まず自動修正を試みる
                                fixed_text = text_processor.auto_fix_marker_newlines(edited_text)
                                if fixed_text != edited_text:
                                    # 自動修正が行われた場合はテキストを更新
                                    st.session_state.text_editor_value = fixed_text
                                    logger.info("マーカー配置を自動修正しました")
                                    # 自動修正を反映させるために再読み込み
                                    st.session_state.need_rerun = True
                                else:
                                    # 修正不要の場合はそのまま検証
                                    marker_errors = text_processor.validate_marker_positions(edited_text)

                                if marker_errors:
                                    # セグメント内配置エラーがある場合（自動修正できない）
                                    st.session_state.marker_position_errors = marker_errors
                                    st.session_state.show_marker_error = True
                                    st.session_state.original_edited_text = edited_text
                                    st.session_state.need_rerun = True
                            else:
                                # マーカーがない場合はエラーをクリア
                                st.session_state.marker_position_errors = []
                                st.session_state.show_marker_error = False
                        else:
                            # 通常モード：マーカー位置エラーはチェックしない
                            st.session_state.marker_position_errors = []
                            st.session_state.show_marker_error = False

                        # 追加文字エラーのチェック（両モードで実施）
                        has_additions = False
                        if found_separator:
                            # 区切り文字がある場合：各セクションで追加文字をチェック
                            sections = text_processor.split_text_by_separator(cleaned_text, found_separator)
                            for i, section in enumerate(sections):
                                # 境界調整マーカーがある場合は正規化をスキップ
                                diff = text_processor.find_differences(
                                    full_text, section, skip_normalization=has_boundary_markers
                                )
                                if diff.has_additions():
                                    has_additions = True
                                    # デバッグ情報
                                    logger.debug(f"セクション{i}で追加文字を検出: {section[:50]}...")
                                    logger.debug(f"追加文字: {diff.added_chars}")
                                    break

                            # 区切り文字がある場合は、区切り文字を除去した全体テキストを渡す
                            if has_additions:
                                text_without_separator = cleaned_text.replace(found_separator, " ")
                                diff = text_processor.find_differences(
                                    full_text, text_without_separator, skip_normalization=has_boundary_markers
                                )
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = text_without_separator
                                st.session_state.original_edited_text = (
                                    edited_text  # 元のテキスト（マーカー付き）も保存
                                )
                        else:
                            # 区切り文字がない場合：通常のチェック
                            diff = text_processor.find_differences(
                                full_text, cleaned_text, skip_normalization=has_boundary_markers
                            )
                            if diff.has_additions():
                                has_additions = True
                                # デバッグ情報
                                logger.debug(f"追加文字を検出: {cleaned_text[:50]}...")
                                logger.debug(f"追加文字: {diff.added_chars}")
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = cleaned_text
                                st.session_state.original_edited_text = edited_text

                        if has_additions:
                            # エラー表示と削除ボタンを表示状態にする
                            st.session_state.show_error_and_delete = True
                            st.session_state.need_rerun = True
                        else:
                            # エラー状態をクリア
                            st.session_state.show_error_and_delete = False
                            st.session_state.need_rerun = True

                with button_col2:
                    # 音声プレビュー（更新ボタンクリック時に生成・表示）
                    if st.session_state.get("preview_update_requested", False) and st.session_state.get("time_ranges"):
                        # 音声を生成
                        try:
                            import tempfile

                            from core.video import VideoProcessor
                            from ui.audio_preview import _generate_combined_audio

                            # VideoProcessorのインスタンス
                            video_processor = VideoProcessor(config)

                            # 一時ファイルに結合音声を生成
                            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                                output_path = tmp_file.name

                            # プレビュー用の時間範囲を調整（最大30秒）
                            time_ranges = st.session_state.time_ranges
                            preview_ranges = []
                            accumulated_duration = 0.0
                            max_duration = 30.0

                            for start, end in time_ranges:
                                segment_duration = end - start
                                if accumulated_duration + segment_duration <= max_duration:
                                    preview_ranges.append((start, end))
                                    accumulated_duration += segment_duration
                                else:
                                    # 残り時間分だけ追加
                                    remaining = max_duration - accumulated_duration
                                    if remaining > 0:
                                        preview_ranges.append((start, start + remaining))
                                    break

                            # 結合音声を生成
                            # video_pathはセッション状態から取得
                            current_video_path = st.session_state.get("video_path", video_path)
                            _generate_combined_audio(video_processor, current_video_path, preview_ranges, output_path)

                            # セッション状態に保存
                            st.session_state.preview_audio_path = output_path
                            st.session_state.preview_audio_duration = accumulated_duration
                            st.session_state.preview_update_requested = False  # フラグをクリア

                        except Exception as e:
                            import traceback

                            st.error(f"音声プレビュー生成エラー: {str(e)}")
                            st.code(traceback.format_exc())
                            st.session_state.preview_update_requested = False

                    # 音声プレーヤーを表示（生成済みの場合）
                    if st.session_state.get("preview_audio_path"):
                        st.audio(st.session_state.preview_audio_path, format="audio/wav")

                    # 削除ボタン（エラーがある場合のみ、音声プレビューの下に表示）
                    if st.session_state.get("show_error_and_delete", False) and st.button(
                        "エラー箇所を確認して削除", key="delete_highlights_main", use_container_width=True
                    ):
                        st.session_state.show_modal = True
                        st.session_state.need_rerun = True

                    # マーカー位置エラーの削除ボタン
                    if st.session_state.get("show_marker_error", False) and st.button(
                        "不適切なマーカーを削除", key="delete_marker_errors", use_container_width=True
                    ):
                        # マーカーを削除
                        text_processor = TextProcessor()
                        current_text = st.session_state.get("original_edited_text", "")
                        cleaned_text = text_processor.remove_boundary_markers(current_text)
                        st.session_state.text_editor_value = cleaned_text
                        st.session_state.show_marker_error = False
                        st.session_state.marker_position_errors = []
                        st.session_state.need_rerun = True

            # 境界調整モードのチェックボックス（更新ボタンの下に配置）
            st.checkbox(
                "境界調整モード",
                value=st.session_state.get("boundary_adjustment_mode", False),
                help="セグメントごとに時間調整マーカーを挿入します",
                key="boundary_adjustment_mode",
            )

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

            # 処理オプション
            st.markdown("#### ⚙️ 処理オプション")
            process_type, primary_format, export_srt, timeline_fps = show_export_settings()

            if process_type == "無音削除付き":
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
                                xml_ext=xml_ext
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
                                    remove_silence=(process_type != "切り抜きのみ")
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
                                remove_silence=(process_type != "切り抜きのみ")
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
                                        remove_silence=(process_type != "切り抜きのみ")
                                    )

                                    # 成功メッセージを作成
                                    success_message = format_export_success_message(
                                        format_name=primary_format,
                                        output_path=xml_path,
                                        timeline_duration=timeline_pos,
                                        srt_path=srt_path if export_srt else None,
                                        srt_success=srt_output_success if export_srt else True
                                    )
                                    
                                    # クリップ数と総時間を追加
                                    additional_info = f" | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒"
                                    
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
