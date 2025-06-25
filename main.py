"""
TextffCut - メインアプリケーション
リファクタリング版：モジュール化された構造を使用
"""

import os
from pathlib import Path
from typing import Any

import streamlit as st

from config import config
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
from ui.recovery_components import (
    show_recovery_check,
    show_recovery_history,
    show_recovery_settings,
    show_recovery_status,
    show_startup_recovery,
)
from utils import ProcessingContext, cleanup_intermediate_files
from utils.environment import IS_DOCKER, VIDEOS_DIR
from utils.file_utils import ensure_directory, get_safe_filename
from utils.logging import get_logger
from utils.time_utils import format_time

# Streamlitの設定
# アイコンファイルのパスを設定

icon_path = Path(__file__).parent / "assets" / "icon.png"
if icon_path.exists():
    page_icon = str(icon_path)
else:
    # フォールバック
    page_icon = "🎬"

st.set_page_config(
    page_title=config.ui.page_title, page_icon=page_icon, layout=config.ui.layout, initial_sidebar_state="expanded"
)

# フォントサイズを調整するCSS
st.markdown(
    """
<style>
    /* 全体的なフォントサイズを小さく */
    .stApp {
        font-size: 14px;
    }
    
    /* 見出しのサイズ調整 */
    h1 {
        font-size: 2rem !important;
    }
    h2 {
        font-size: 1.5rem !important;
    }
    h3 {
        font-size: 1.25rem !important;
    }
    h4 {
        font-size: 1.1rem !important;
    }
    
    /* テキスト入力やセレクトボックスのフォントサイズ */
    .stSelectbox > div > div {
        font-size: 14px !important;
    }
    
    /* ボタンのフォントサイズ */
    .stButton > button {
        font-size: 14px !important;
    }
    
    /* キャプションのフォントサイズ */
    .caption {
        font-size: 12px !important;
    }
    
    /* サイドバーのフォントサイズ調整 */
    .sidebar .sidebar-content {
        font-size: 14px !important;
    }
    
    /* サイドバーの見出し */
    .sidebar h1, .sidebar h2, .sidebar h3, .sidebar h4 {
        font-size: 1rem !important;
    }
    
    /* サイドバーのボタン */
    .sidebar .stButton > button {
        font-size: 13px !important;
    }
    
    /* サイドバーのタブ */
    .sidebar .stTabs [data-baseweb="tab-list"] button {
        font-size: 13px !important;
    }
    
    /* サイドバーのセレクトボックス */
    .sidebar .stSelectbox {
        font-size: 13px !important;
    }
    
    /* 画像の表示品質を向上 */
    img {
        image-rendering: auto;
        image-rendering: -webkit-optimize-contrast;
        max-width: 100%;
        height: auto;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ダークモード対応のスタイルを適用
apply_dark_mode_styles()


def debug_words_status(result: Any) -> None:
    """wordsフィールドの状態を詳細に出力（デバッグ用）"""
    logger = get_logger(__name__)

    if hasattr(result, "segments"):
        total_segments = len(result.segments)
        segments_with_words = sum(1 for seg in result.segments if hasattr(seg, "words") and seg.words)
        logger.info(f"Words状態: {segments_with_words}/{total_segments} セグメント")

        # 最初の数セグメントの詳細
        for i, seg in enumerate(result.segments[:3]):
            if hasattr(seg, "words") and seg.words:
                logger.info(f"  セグメント{i}: {len(seg.words)}words - {seg.text[:30]}...")
            else:
                logger.warning(f"  セグメント{i}: wordsなし! - {seg.text[:30]}...")


def get_display_path(file_path: str) -> str:
    """
    ファイルパスを表示用に変換

    Args:
        file_path: 実際のファイルパス

    Returns:
        表示用のパス
    """
    if IS_DOCKER:
        # Docker環境：ホストパスに変換
        host_base = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "/app") + "/videos")
        # /app/videos/xxx を host_path/xxx に変換
        relative_path = str(file_path).replace(VIDEOS_DIR + "/", "")
        if relative_path == str(file_path):
            # VIDEOS_DIR以外のパスの場合はそのまま返す
            return file_path
        return os.path.join(host_base, relative_path)
    else:
        # ローカル環境：そのまま返す
        return file_path


def main() -> None:
    """メインアプリケーション"""

    # ロガーを初期化
    from utils.logging import get_logger as _get_logger

    logger = _get_logger(__name__)

    # ロゴを表示（ダークモード対応）
    icon_svg = """
    <svg width="45" height="50" viewBox="0 0 139.61 154.82" xmlns="http://www.w3.org/2000/svg" style="vertical-align: middle; margin-right: 10px;" class="textffcut-logo">
      <style>
        @media (prefers-color-scheme: dark) {
          .textffcut-logo .icon-dark { fill: #ffffff; }
          .textffcut-logo .icon-red { fill: #fd444d; }
        }
        @media (prefers-color-scheme: light) {
          .textffcut-logo .icon-dark { fill: #2a363b; }
          .textffcut-logo .icon-red { fill: #fd444d; }
        }
      </style>
      <path class="icon-dark" d="M30.29,33.32C31.39,15.5,44.76,1.16,62.8.19c11.65-.62,23.84.49,35.54,0,3.39.21,5.97.97,8.62,3.14l29.53,29.75c4.33,5.24,2.49,14.91,2.51,21.49,0,3.18-.02,6.41,0,9.59.06,14.84,1.16,31.13.27,45.85-1.02,16.99-15.67,31.08-32.53,32.03-6.37.36-16.28.53-22.55,0-4.89-.42-8.08-4.88-5.6-9.43,1.3-2.39,3.75-3.1,6.31-3.29,13.41-.98,28.28,4.04,37.67-8.41,1.48-1.96,4.22-7.35,4.22-9.7v-61.68s-.33-.36-.36-.36h-18.48c-6.87,0-14.52-8.54-14.52-15.24V12.92h-32.76c-4.15,0-10.3,4.41-12.83,7.57-6.53,8.16-5.23,14-5.28,23.74s.62,20.49,0,30.02c-.55,8.4-9.92,9.57-12.25,1.79.73.13.46-.37.48-.83.52-13.04.44-28,0-41.06-.02-.46.24-.96-.48-.83ZM123.18,37.64c.44-.44-1.49-2.58-1.91-3.01-4.53-4.7-9.37-9.2-13.94-13.9-.37-.38-.69-1.09-1.06-1.34-1.35-.92-.63.56-.6,1.32.13,3.91-.39,8.46,0,12.25s3.98,4.66,7.32,4.92c1.17.09,9.84.12,10.2-.24Z"/>
      <path class="icon-red" d="M69.41,89.96c5.54-.69,11.11-1.24,16.65-1.95,6.41-.83,13.88-2.55,20.2-2.84,4.56-.21,7.15,3.02,4.4,7.04-4.89,7.14-13.45,9.51-21.5,10.9-8.65,1.49-17.5,1.97-26.12,3.64-.17,1.11-3.04,6.07-2.99,6.61.05.56,2.34,2.49,2.89,3.14,9.22,10.9,9.98,26.45-2.7,34.97-12.08,8.12-30.07.79-31.61-13.86-.05-.47.09-2.43,0-2.52-.25-.25-6.01.09-7.08,0-18.82-1.55-28.92-25.82-15.16-39.51,8.13-8.09,20.56-8.98,30.72-4.37,2.11.96,3.13,2.24,5.55,2.12,2.76-.14,6.43-.64,9.24-.96,5.8-.66,11.66-1.67,17.52-2.4ZM47.57,106.28c-.05-.05-1.12.03-1.5-.06-9.08-1.97-19.86-9.92-28.96-4.36-11.06,6.75-4.66,21.86,7.79,22.18,7.33.19,19.23-8.91,21.99-15.44.16-.38.92-2.08.68-2.32ZM49.91,123.62c-1.6.31-6,3.57-7.14,4.86-3.55,4.01-3.95,10.19.89,13.28,8.8,5.63,18.62-4.16,13.8-13.32-1.4-2.67-4.27-5.44-7.55-4.82Z"/>
      <path class="icon-dark" d="M69.41,89.96c-5.86.73-11.72,1.74-17.52,2.4,4.22-9.39,6.59-19.65,11.44-28.76,3.08-5.79,7.68-11,13.6-14,3.3-1.67,6.38-2.77,9.92-.96,2.77,1.41,3.26,4.72,1.62,7.23-1.86,2.85-3.67,5.17-5.43,8.25-4.81,8.45-8.84,17.37-13.64,25.84Z"/>
      <path class="icon-dark" d="M95.03,65.78h19.8c4.77,1.39,4.4,7.98-.69,8.55-6.03.67-13.2-.39-19.35-.02-4.41-1.47-4.15-7.26.24-8.53Z"/>
    </svg>
    """

    # Docker環境判定（環境変数から取得）
    is_docker = IS_DOCKER

    # バージョン情報を取得（VERSION.txtから読み込む）
    try:
        version_file = Path(__file__).parent / "VERSION.txt"
        if version_file.exists():
            version = version_file.read_text().strip()
        else:
            version = "v1.0.0"  # デフォルト値
    except:
        version = "v1.0.0"  # エラー時のフォールバック

    # 起動時のリカバリーチェック（自動リカバリーが有効な場合）
    if st.session_state.get("auto_recovery", True) and "startup_recovery_checked" not in st.session_state:
        st.session_state["startup_recovery_checked"] = True
        recoverable = show_startup_recovery()
        if recoverable:
            # リカバリー可能な処理があれば停止
            st.stop()

    # タイトル表示
    title_text = f'Text<span style="color: red; font-style: italic;">ff</span>Cut <span style="color: #666; font-size: 1rem;">{version}</span>'
    subtitle_text = "切り抜き動画編集支援ツール"

    st.markdown(
        f'{icon_svg}<span style="font-size: 3rem; font-weight: bold; vertical-align: middle;">{title_text}</span>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p style="margin-top: -10px; margin-bottom: 20px; color: #666; font-size: 1.1rem;">{subtitle_text}</p>',
        unsafe_allow_html=True,
    )

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

    # 分離モードに応じて適切なTranscriberを選択
    if config.transcription.isolation_mode == "subprocess":
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
                st.markdown(f"{duration_minutes:.1f}分 ({format_time(video_info.duration)})")

            with price_col:
                if use_api:
                    # ConfigurationServiceを使用して料金計算
                    config_service = ConfigurationService(config)
                    cost_result = config_service.calculate_api_cost(duration_minutes)

                    if cost_result.success:
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

            if st.button(button_text, type=button_type, use_container_width=True):
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

            error_handler = ErrorHandler(logger)
            error_info = error_handler.handle_error(file_error)
            st.error(f"📁 {error_info['user_message']}")
            return

        except OSError as e:
            # 新しいエラーハンドリングシステムを使用
            from core.error_handling import ResourceError

            resource_error = ResourceError(f"ファイルアクセスエラー: {str(e)}", cause=e)

            try:
                error_handler = ErrorHandler(logger)
                error_info = error_handler.handle_error(resource_error, context="動画情報取得", raise_after=False)
                st.error(f"💾 {error_info['user_message']}")
            except:
                st.error(f"💾 ファイルアクセスエラー: {str(e)}")
            return

        except Exception as e:
            # 新しいエラーハンドリングシステムを使用
            from core.error_handling import ProcessingError

            wrapped_error = ProcessingError(f"動画情報の取得に失敗: {str(e)}", cause=e)

            try:
                error_handler = ErrorHandler(logger)
                error_info = error_handler.handle_error(wrapped_error, context="動画情報取得", raise_after=False)
                st.error(error_info["user_message"])
            except:
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
                    config.transcription.use_api = True
                    config.transcription.api_key = st.session_state.get("api_key", "")
                else:
                    config.transcription.use_api = False

                # 設定を反映したTranscriberを再初期化
                # 分離モードに応じて適切なTranscriberを選択
                if config.transcription.isolation_mode == "subprocess":
                    transcriber = SubprocessTranscriber(config)
                else:
                    transcriber = SmartSplitTranscriber(config)

                # シンプルなプログレスコールバック
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def cancellable_progress_callback(progress: float, status: str):
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
                    if config.transcription.use_api:
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
                                segments = []
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
                        debug_words_status(result)

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
                    error_handler = ErrorHandler(logger)
                    error_info = error_handler.handle_error(memory_error, context="文字起こし", raise_after=False)
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
                    error_handler = ErrorHandler(logger)

                    # 既存のエラー型との互換性を維持
                    if isinstance(e, LegacyTranscriptionError):
                        st.error(e.get_user_message())
                    elif isinstance(e, (ProcessingError, NewTranscriptionError)):
                        error_info = error_handler.handle_error(e, context="文字起こし", raise_after=False)
                        st.error(error_info["user_message"])
                    else:
                        # 未知のエラーをProcessingErrorでラップ
                        wrapped_error = ProcessingError(f"文字起こし処理でエラーが発生しました: {str(e)}", cause=e)
                        error_info = error_handler.handle_error(wrapped_error, context="文字起こし", raise_after=False)
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

                if found_separator:
                    # 区切り文字がある場合：区切り文字を除去して差分計算
                    text_without_separator = saved_edited_text.replace(found_separator, " ")  # スペースで置換
                    # 互換性のためTextProcessorも使用（サービス層への移行を段階的に行う）
                    text_processor = TextProcessor()
                    diff = text_processor.find_differences(full_text, text_without_separator)
                    show_diff_viewer(full_text, diff)
                else:
                    # 区切り文字がない場合：サービスを使用
                    diff_result = text_service.find_differences(transcription.segments, saved_edited_text)
                    if diff_result.success:
                        # 既存の差分表示と互換性を保つため、TextProcessorも使用
                        text_processor = TextProcessor()
                        diff = text_processor.find_differences(full_text, saved_edited_text)
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

                # 区切り文字パターンをチェック
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None

                for pattern in separator_patterns:
                    if pattern in display_text:
                        found_separator = pattern
                        break

                if found_separator:
                    time_ranges = text_processor.find_differences_with_separator(
                        full_text, display_text, transcription, found_separator
                    )
                    sections = text_processor.split_text_by_separator(display_text, found_separator)
                    separator_info = f" / セクション数: {len(sections)}"
                else:
                    diff = text_processor.find_differences(full_text, display_text)
                    time_ranges = diff.get_time_ranges(transcription)
                    separator_info = ""

                total_duration = sum(end - start for start, end in time_ranges)
                st.caption(
                    f"文字数: {len(display_text)}文字 / 時間: {total_duration:.1f}秒（無音削除前）{separator_info}"
                )

            # ボタンを横並びに配置
            button_col1, button_col2 = st.columns([1, 2])

            with button_col1:
                # 更新ボタン
                if st.button("🔄 更新", type="primary", use_container_width=True):
                    st.session_state.edited_text = edited_text
                    
                    # 時間範囲を計算して保存
                    if edited_text:
                        text_processor = TextProcessor()
                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in edited_text:
                                found_separator = pattern
                                break
                        
                        if found_separator:
                            time_ranges = text_processor.find_differences_with_separator(
                                full_text, edited_text, transcription, found_separator
                            )
                        else:
                            diff = text_processor.find_differences(full_text, edited_text)
                            time_ranges = diff.get_time_ranges(transcription)
                        
                        st.session_state.time_ranges = time_ranges
                        st.session_state.show_timeline_section = True  # タイムライン編集セクションを表示
                        # タイムライン編集が完了していない状態にリセット
                        if "timeline_completed" in st.session_state:
                            del st.session_state.timeline_completed

                    # 赤ハイライトがあるかチェック
                    if edited_text:
                        text_processor = TextProcessor()

                        # 区切り文字対応
                        separator_patterns = ["---", "——", "－－－"]
                        found_separator = None
                        for pattern in separator_patterns:
                            if pattern in edited_text:
                                found_separator = pattern
                                break

                        has_additions = False
                        if found_separator:
                            # 区切り文字がある場合：各セクションで追加文字をチェック
                            sections = text_processor.split_text_by_separator(edited_text, found_separator)
                            for section in sections:
                                diff = text_processor.find_differences(full_text, section)
                                if diff.has_additions():
                                    has_additions = True
                                    break

                            # 区切り文字がある場合は、区切り文字を除去した全体テキストを渡す
                            if has_additions:
                                text_without_separator = edited_text.replace(found_separator, " ")
                                diff = text_processor.find_differences(full_text, text_without_separator)
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = text_without_separator
                                st.session_state.original_edited_text = (
                                    edited_text  # 元のテキスト（区切り文字付き）も保存
                                )
                        else:
                            # 区切り文字がない場合：通常のチェック
                            diff = text_processor.find_differences(full_text, edited_text)
                            if diff.has_additions():
                                has_additions = True
                                st.session_state.current_diff = diff
                                st.session_state.current_edited_text = edited_text
                                st.session_state.original_edited_text = edited_text

                        if has_additions:
                            # エラー表示と削除ボタンを表示状態にする
                            st.session_state.show_error_and_delete = True
                            st.rerun()
                        else:
                            # エラー状態をクリア
                            st.session_state.show_error_and_delete = False
                            st.rerun()

            with button_col2:
                # 削除ボタン（エラーがある場合のみ表示）
                if st.session_state.get("show_error_and_delete", False):
                    if st.button("エラー箇所を確認して削除", key="delete_highlights_main", use_container_width=True):
                        st.session_state.show_modal = True
                        st.rerun()

        # タイムライン編集セクション（show_timeline_sectionがTrueの場合）
        if st.session_state.get("show_timeline_section", False):
            st.markdown("---")
            st.subheader("📊 タイムライン編集")
            
            from ui.timeline_editor import render_timeline_editor
            
            # タイムライン編集UIをインラインで表示
            time_ranges = st.session_state.get("time_ranges", [])
            if time_ranges:
                adjusted_ranges = render_timeline_editor(
                    time_ranges,
                    transcription,
                    video_path
                )
                
                if adjusted_ranges is not None:
                    if adjusted_ranges:
                        # 調整後の時間範囲を保存
                        st.session_state.adjusted_time_ranges = adjusted_ranges
                        st.session_state.timeline_completed = True
                        st.session_state.show_timeline_section = False  # タイムライン編集セクションを非表示
                        st.success("タイムライン編集が完了しました。")
                        st.rerun()
                    else:
                        # キャンセルされた場合
                        st.info("タイムライン編集がキャンセルされました。")
                        st.session_state.show_timeline_section = False
                        # adjusted_time_rangesがあれば削除
                        if "adjusted_time_ranges" in st.session_state:
                            del st.session_state.adjusted_time_ranges
                        if "timeline_completed" in st.session_state:
                            del st.session_state.timeline_completed
                        st.rerun()
            else:
                st.error("時間範囲が計算されていません。更新ボタンをクリックしてください。")
        
        # 切り抜き処理セクション（編集テキストがあり、タイムライン編集が完了しているか、タイムライン編集を使用しない場合）
        if st.session_state.get("edited_text") and (st.session_state.get("timeline_completed", False) or not st.session_state.get("show_timeline_section", False)):
            st.markdown("---")
            st.subheader("🎬 切り抜き箇所の抽出")

            # 処理オプション
            st.markdown("#### ⚙️ 処理オプション")
            process_type, primary_format, export_srt, timeline_fps = show_export_settings()

            if process_type == "無音削除付き":
                st.markdown("##### 🔇 無音削除の設定")
                st.info(
                    f"現在の設定: 閾値{noise_threshold}dB | 無音{min_silence_duration}秒 | セグメント{min_segment_duration}秒 | パディング{padding_start}-{padding_end}秒 | 設定変更は左サイドパネルの「無音検出」タブから"
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
                    config.transcription.use_api = True
                    config.transcription.api_key = st.session_state.get("api_key", "")
                else:
                    config.transcription.use_api = False

                # 区切り文字対応の差分検索を使用
                text_processor = TextProcessor()

                # 区切り文字の様々なパターンをチェック（処理実行時）
                separator_patterns = ["---", "——", "－－－"]
                found_separator = None

                for pattern in separator_patterns:
                    if pattern in edited_text:
                        found_separator = pattern
                        break

                if found_separator:
                    # 区切り文字対応処理
                    time_ranges = text_processor.find_differences_with_separator(
                        full_text, edited_text, transcription, found_separator
                    )

                    # 各セクションで追加文字チェック
                    sections = text_processor.split_text_by_separator(edited_text, found_separator)
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
                    diff = text_processor.find_differences(full_text, edited_text)

                    if diff.has_additions():
                        st.error("元の動画に存在しない部分が含まれています。赤いハイライト部分を確認してください。")
                        return

                    time_ranges = diff.get_time_ranges(transcription)

                # タイムライン編集で調整された時間範囲があれば使用
                if "adjusted_time_ranges" in st.session_state:
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
                            # ExportServiceを使用してXMLを生成
                            export_service = ExportService(config)
                            from utils.file_utils import get_unique_path

                            # 形式を決定
                            if primary_format == "FCPXMLファイル":
                                export_format = "fcpxml"
                                xml_ext = ".fcpxml"
                            else:  # Premiere Pro XML
                                export_format = "xmeml"
                                xml_ext = ".xml"

                            xml_path = get_unique_path(project_path / f"{safe_name}_TextffCut_{type_suffix}{xml_ext}")

                            # keep_rangesからセグメントを作成
                            from core import TranscriptionSegment

                            # SRTも同時出力する場合
                            if export_srt:
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
                                    },
                                )

                                # 無音削除の有無で処理を分岐
                                srt_exporter = SRTDiffExporter(config)

                                if process_type == "切り抜きのみ":
                                    # 無音削除なし：従来の処理
                                    success = srt_exporter.export_from_diff(
                                        diff=diff,
                                        transcription_result=transcription,
                                        output_path=str(xml_path),
                                        encoding=srt_settings.get("encoding", "utf-8"),
                                        srt_settings=srt_settings,
                                    )
                                else:
                                    # 無音削除あり：タイムマッピングを使用
                                    from core.time_mapper import TimeMapper

                                    # TimeMapperを作成（time_rangesとkeep_rangesの対応）
                                    time_mapper = TimeMapper(time_ranges, keep_ranges)

                                    success = srt_exporter.export_from_diff_with_silence_removal(
                                        diff=diff,
                                        transcription_result=transcription,
                                        output_path=str(xml_path),
                                        time_mapper=time_mapper,
                                        encoding=srt_settings.get("encoding", "utf-8"),
                                        srt_settings=srt_settings,
                                    )

                                if success:
                                    # メタデータを作成
                                    export_result = type(
                                        "Result",
                                        (),
                                        {
                                            "success": True,
                                            "metadata": {
                                                "used_duration": sum(end - start for start, end in time_ranges)
                                            },
                                        },
                                    )()
                                else:
                                    export_result = type("Result", (), {"success": False})()

                            # XMLの場合は空のセグメントでOK
                            export_segments = []
                            for i, (start, end) in enumerate(keep_ranges):
                                export_segments.append(TranscriptionSegment(start=start, end=end, text="", words=[]))

                            # XMLエクスポート実行
                            export_result = export_service.execute(
                                format=export_format,
                                video_path=video_path,
                                segments=export_segments,
                                output_path=str(xml_path),
                                project_name=f"{safe_name} Project",
                                event_name="TextffCut",
                                remove_silence=(process_type != "切り抜きのみ"),
                            )

                            success = export_result.success
                            if success:
                                # メタデータから統計情報を取得
                                timeline_pos = export_result.metadata.get("used_duration", 0)

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

                                    # 差分検出ベースのSRTエクスポーターを使用
                                    from core.srt_diff_exporter import SRTDiffExporter

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
                                        srt_display_path = get_display_path(srt_path)

                                        show_progress(
                                            1.0,
                                            f"処理が完了しました！ 出力先: {display_path} | SRT字幕: {srt_display_path} | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
                                            progress_bar,
                                            status_text,
                                        )
                                    else:
                                        # SRT出力は失敗したが、XMLは成功
                                        show_progress(
                                            1.0,
                                            f"処理が完了しました！ 出力先: {display_path} | ⚠️ SRT字幕の生成に失敗 | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
                                            progress_bar,
                                            status_text,
                                        )
                                else:
                                    # SRT出力なし
                                    show_progress(
                                        1.0,
                                        f"処理が完了しました！ 出力先: {display_path} | 📊 {len(keep_ranges)}個のクリップ、総時間: {timeline_pos:.1f}秒",
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

                            for i, (start, end) in enumerate(keep_ranges):
                                progress = (i + 1) / total_ranges * 0.8  # 最大80%まで
                                show_progress(
                                    progress, f"セグメント {i+1}/{total_ranges} を抽出中...", progress_bar, status_text
                                )

                                segment_file = project_path / f"segment_{i+1}.mp4"
                                # VideoProcessingServiceを使用
                                if "video_service" not in locals():
                                    video_service = VideoProcessingService(config)

                                # 一つのセグメントを抽出するためのVideoSegmentを作成
                                from core import VideoSegment

                                segments_to_extract = [VideoSegment(start=start, end=end)]

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
                                                srt_display_path = srt_path

                                            show_progress(
                                                1.0,
                                                f"処理が完了しました！ 出力先: {display_path} | SRT字幕: {srt_display_path} | 📊 {len(keep_ranges)}個のセグメントを結合",
                                                progress_bar,
                                                status_text,
                                            )
                                        else:
                                            # SRT出力は失敗したが、動画は成功
                                            show_progress(
                                                1.0,
                                                f"処理が完了しました！ 出力先: {display_path} | ⚠️ SRT字幕の生成に失敗 | 📊 {len(keep_ranges)}個のセグメントを結合",
                                                progress_bar,
                                                status_text,
                                            )
                                    else:
                                        # SRT出力なし
                                        show_progress(
                                            1.0,
                                            f"処理が完了しました！ 出力先: {display_path} | 📊 {len(keep_ranges)}個のセグメントを結合",
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
                            error_handler = ErrorHandler(logger)

                            # 既存のエラー型の互換性を維持
                            from utils.exceptions import VideoProcessingError

                            if isinstance(e, VideoProcessingError):
                                st.error(e.get_user_message())
                            elif isinstance(e, (ProcessingError, ValidationError)):
                                error_info = error_handler.handle_error(e, context="動画処理", raise_after=False)
                                st.error(error_info["user_message"])
                            else:
                                # 未知のエラーをProcessingErrorでラップ
                                wrapped_error = ProcessingError(f"動画処理中にエラーが発生しました: {str(e)}", cause=e)
                                error_info = error_handler.handle_error(
                                    wrapped_error, context="動画処理", raise_after=False
                                )
                                st.error(error_info["user_message"])
                        except Exception:
                            st.error(f"動画処理中にエラーが発生しました: {str(e)}")

    # モーダル表示
    if st.session_state.get("show_modal", False):
        show_red_highlight_modal(
            st.session_state.get("current_edited_text", ""), st.session_state.get("current_diff", None)
        )

    # モーダル表示は削除（メイン画面で確認表示に変更）


# モーダル関数は削除（メイン画面表示に変更）


if __name__ == "__main__":
    # セッション終了時のクリーンアップを登録
    import atexit

    atexit.register(cleanup_temp_files)

    main()
