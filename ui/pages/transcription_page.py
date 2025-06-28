"""
文字起こし画面のページコントローラー

main.pyから分離された文字起こし処理を管理します。
"""

import os
from pathlib import Path
from typing import Optional, Union

import streamlit as st

from config import Config
from core.alignment_processor import AlignmentProcessor
from core.constants import ApiSettings, ModelSettings
from core.error_handling import (
    ErrorHandler,
    FileValidationError,
    ProcessingError,
    ResourceError,
    TranscriptionError as NewTranscriptionError,
)
from core.transcription_smart_split import SmartSplitTranscriber
from core.transcription_subprocess import SubprocessTranscriber
from core.video import VideoInfo
from services import ConfigurationService, TranscriptionService
from ui import show_api_key_manager, show_transcription_controls
from ui.recovery_components import show_recovery_check, show_recovery_status
from utils.api_key_manager import api_key_manager
from utils.exceptions import TranscriptionError as LegacyTranscriptionError
from utils.logging import get_logger
from utils.session_state_manager import SessionStateManager
from utils.time_utils import format_time

logger = get_logger(__name__)


class TranscriptionPageController:
    """文字起こし画面の制御"""

    def __init__(self):
        self.config = Config()
        self.transcription_service = TranscriptionService(self.config)
        self.config_service = ConfigurationService(self.config)
        self.error_handler = ErrorHandler(logger)

    def render(self, video_path: Union[Path, str]) -> None:
        """文字起こし画面をレンダリング"""
        st.markdown("---")
        st.subheader("📝 文字起こし")

        # 動画パスを文字列に変換
        if isinstance(video_path, Path):
            video_path = str(video_path)

        # リカバリーチェック
        self._handle_recovery(video_path)

        # 適切なTranscriberを選択
        transcriber = self._get_transcriber()

        # 利用可能なキャッシュを取得
        available_caches = transcriber.get_available_caches(video_path)

        # キャッシュ選択UIを表示
        use_cache, run_new, selected_cache = show_transcription_controls(False, available_caches)

        if use_cache and selected_cache:
            # キャッシュから読み込み
            self._load_from_cache(transcriber, selected_cache)
            return

        # 文字起こし実行の確認画面
        self._show_transcription_confirmation(video_path, available_caches)

        # 文字起こし実行の判定
        if SessionStateManager.get("should_run_transcription", False):
            self._execute_transcription(video_path, transcriber)

        # 文字起こし結果の処理
        self._handle_transcription_result()

    def _handle_recovery(self, video_path: str) -> None:
        """リカバリー処理"""
        recovery_info = show_recovery_check(video_path)
        if recovery_info and SessionStateManager.get("recovery_action") == "resume":
            st.info("🔄 前回の処理を再開しています...")
            # TODO: リカバリー処理の実装

    def _get_transcriber(self) -> Union[SubprocessTranscriber, SmartSplitTranscriber]:
        """適切なTranscriberを取得"""
        if self.config.transcription.isolation_mode == "subprocess":
            return SubprocessTranscriber(self.config)
        else:
            return SmartSplitTranscriber(self.config)

    def _load_from_cache(self, transcriber, selected_cache) -> None:
        """キャッシュから結果を読み込み"""
        result = transcriber.load_from_cache(selected_cache["file_path"])
        if result:
            SessionStateManager.set("transcription_result", result)

            # 選択されたキャッシュの設定をセッションに反映
            if selected_cache["is_api"]:
                st.success(f"✅ APIモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")
            else:
                st.success(f"✅ ローカルモード（{selected_cache['model_size']}）の文字起こし結果を読み込みました！")

            st.rerun()

    def _show_transcription_confirmation(self, video_path: str, available_caches: list) -> None:
        """文字起こし実行の確認画面を表示"""
        try:
            # 動画情報を取得
            video_info = VideoInfo.from_file(video_path)
            duration_minutes = video_info.duration / 60

            # 処理モード・モデル選択・動画時間・料金を4カラムで横並び表示
            mode_col, model_col, time_col, price_col = st.columns(4)

            with mode_col:
                st.markdown("**⚙️ 処理モード**")
                mode_options = ["🖥️ ローカル", "🌐 API"]
                previous_mode = SessionStateManager.get("use_api", False)
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
                SessionStateManager.set("use_api", use_api)

            with model_col:
                if use_api:
                    st.markdown("**🤖 モデル**")
                    st.markdown("whisper-1")
                    model_size = "whisper-1"

                    # APIキーをセッションに保存
                    saved_key = api_key_manager.load_api_key()
                    if saved_key:
                        SessionStateManager.set("api_key", saved_key)
                else:
                    st.markdown("**🤖 モデル**")
                    st.markdown("medium（固定）")
                    model_size = "medium"
                    SessionStateManager.set("local_model_size", model_size)

            with time_col:
                st.markdown("**📊 動画時間**")
                st.markdown(f"{duration_minutes:.1f}分 ({format_time(video_info.duration)})")

            # 料金計算変数の初期化
            estimated_cost_usd = 0.0
            estimated_cost_jpy = 0.0
            
            with price_col:
                if use_api:
                    # 料金計算
                    cost_result = self.config_service.calculate_api_cost(duration_minutes)

                    if cost_result.success:
                        cost_data = cost_result.data
                        estimated_cost_usd = cost_data["cost_usd"]
                        estimated_cost_jpy = cost_data["cost_jpy"]
                        st.markdown("**💰 推定料金**")
                        st.markdown(f"${estimated_cost_usd:.3f} (約{estimated_cost_jpy:.0f}円)")
                    else:
                        # フォールバック
                        estimated_cost_usd = duration_minutes * ApiSettings.OPENAI_COST_PER_MINUTE
                        estimated_cost_jpy = estimated_cost_usd * 150
                        st.markdown("**💰 推定料金**")
                        st.markdown(f"${estimated_cost_usd:.3f} (約{estimated_cost_jpy:.0f}円)")
                else:
                    st.markdown("**💰 料金**")
                    st.markdown("無料（ローカル処理）")

            # API利用時の注意事項
            if use_api:
                st.caption(
                    f"⚠️ API料金: ${ApiSettings.OPENAI_COST_PER_MINUTE}/分 | 為替変動あり | [最新料金](https://openai.com/pricing)を確認"
                )

            # 実行ボタン
            button_text, button_type = self._get_button_config(use_api, available_caches)

            # 過去の結果がある場合は上書き警告
            if available_caches:
                st.warning("⚠️ 同じ設定の過去の文字起こし結果は上書きされます")

            if st.button(button_text, type=button_type, use_container_width=True):
                # APIモードでAPIキーチェック
                if use_api and not SessionStateManager.get("api_key"):
                    st.error("⚠️ APIキーが設定されていません。サイドバーのAPIキー設定で設定してください。")
                    return

                # 確認情報を保存
                confirmation_info = {
                    "mode": "api" if use_api else "local",
                    "model_size": model_size,
                    "duration_minutes": duration_minutes,
                    "formatted_time": format_time(video_info.duration),
                }
                
                if use_api:
                    confirmation_info.update({
                        "estimated_cost_usd": estimated_cost_usd,
                        "estimated_cost_jpy": estimated_cost_jpy,
                    })
                
                SessionStateManager.set("confirmation_info", confirmation_info)

                # 実行フラグを設定
                SessionStateManager.set("should_run_transcription", True)
                SessionStateManager.set("previous_transcription_mode", use_api)
                SessionStateManager.set("previous_transcription_model", model_size)

                st.rerun()

        except FileNotFoundError:
            error = FileValidationError("指定された動画ファイルが見つかりません", details={"path": str(video_path)})
            error_info = self.error_handler.handle_error(error)
            st.error(f"📁 {error_info['user_message']}")
        except Exception as e:
            error = ProcessingError(f"動画情報の取得に失敗: {str(e)}", cause=e)
            error_info = self.error_handler.handle_error(error, context="動画情報取得", raise_after=False)
            st.error(error_info["user_message"])

    def _get_button_config(self, use_api: bool, available_caches: list) -> tuple[str, str]:
        """実行ボタンの設定を取得"""
        if available_caches:
            if use_api:
                button_text = "💳 新たにAPIで文字起こしを実行する"
            else:
                button_text = "🖥️ 新たにローカルで文字起こしを実行する"
            button_type = "secondary"
        else:
            if use_api:
                button_text = "💳 APIで文字起こしを実行する"
            else:
                button_text = "🖥️ ローカルで文字起こしを実行する"
            button_type = "primary"
        
        return button_text, button_type

    def _execute_transcription(self, video_path: str, transcriber) -> None:
        """文字起こしを実行"""
        # 実行フラグをリセット
        SessionStateManager.delete("should_run_transcription")

        # 処理中止フラグをリセット
        SessionStateManager.set("cancel_transcription", False)
        SessionStateManager.set("transcription_in_progress", True)

        # キャンセルボタンを表示
        cancel_placeholder = st.empty()
        with cancel_placeholder.container():
            if st.button("❌ 処理を中止", type="secondary", use_container_width=True):
                SessionStateManager.set("cancel_transcription", True)
                SessionStateManager.set("transcription_in_progress", False)
                st.warning("文字起こし処理を中止しました。")
                return

        with st.spinner("文字起こし中..."):
            try:
                # キャンセルチェック
                if SessionStateManager.get("cancel_transcription", False):
                    SessionStateManager.set("transcription_in_progress", False)
                    st.warning("文字起こし処理が中止されました。")
                    return

                # 実行前にAPI設定を反映
                confirmation_info = SessionStateManager.get("confirmation_info", {})
                if confirmation_info.get("mode") == "api":
                    self.config.transcription.use_api = True
                    self.config.transcription.api_key = SessionStateManager.get("api_key", "")
                else:
                    self.config.transcription.use_api = False

                # 設定を反映したTranscriberを再初期化
                transcriber = self._get_transcriber()

                # プログレス表示
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def cancellable_progress_callback(progress: float, status: str):
                    """キャンセル可能なプログレスコールバック"""
                    if SessionStateManager.get("cancel_transcription", False):
                        raise InterruptedError("処理が中止されました")
                    progress_bar.progress(min(progress, 1.0))
                    progress_text.info(status)
                    show_recovery_status(video_path, "transcribing", progress)

                # 文字起こし実行
                model_to_use = confirmation_info.get("model_size", "base")
                result = transcriber.transcribe(
                    video_path,
                    model_to_use,
                    progress_callback=cancellable_progress_callback,
                    use_cache=False,
                    save_cache=True,
                )

                if result:
                    # APIモードでwordsが欠落している場合のアライメント処理
                    if self.config.transcription.use_api:
                        result = self._handle_alignment_if_needed(
                            result, video_path, progress_bar, progress_text
                        )
                        if not result:
                            return

                    SessionStateManager.set("transcription_result", result)
                    SessionStateManager.set("transcription_in_progress", False)

                    # UI要素をクリーンアップ
                    cancel_placeholder.empty()
                    progress_bar.empty()
                    progress_text.empty()
                    st.success("✅ 文字起こし完了！")
                    st.rerun()

            except InterruptedError as e:
                self._handle_transcription_error(e, cancel_placeholder, progress_bar, progress_text, "interrupted")
            except MemoryError as e:
                self._handle_transcription_error(e, cancel_placeholder, progress_bar, progress_text, "memory")
            except Exception as e:
                self._handle_transcription_error(e, cancel_placeholder, progress_bar, progress_text, "general")

    def _handle_alignment_if_needed(self, result, video_path: str, progress_bar, progress_text):
        """必要に応じてアライメント処理を実行"""
        try:
            # wordsフィールドのチェック
            has_words = self._check_has_words(result)

            if not has_words:
                progress_text.info("🔄 文字位置情報を生成中...")
                progress_bar.progress(0.7)

                # アライメント処理
                alignment_processor = AlignmentProcessor(self.config)

                def alignment_progress(progress: float, status: str):
                    overall_progress = 0.7 + (progress * 0.3)
                    progress_bar.progress(min(overall_progress, 1.0))
                    progress_text.info(f"🔄 {status}")

                # セグメントを取得
                segments = self._get_segments_from_result(result)
                language = result.language if hasattr(result, "language") else "ja"

                # アライメント実行
                aligned_segments = alignment_processor.align(
                    segments, video_path, language, progress_callback=alignment_progress
                )

                if aligned_segments:
                    result = self._update_result_with_aligned_segments(result, aligned_segments)
                    progress_text.success("✅ 文字位置情報の生成完了！")
                else:
                    raise Exception("文字位置情報の生成に失敗しました")

            return result

        except Exception as e:
            st.error(f"❌ 文字位置情報の生成に失敗しました: {str(e)}")
            st.error("文字位置情報（words）は必須です。文字起こしを再実行してください。")
            logger.error(f"アライメントエラー（致命的）: {str(e)}")
            SessionStateManager.set("transcription_in_progress", False)
            return None

    def _check_has_words(self, result) -> bool:
        """結果にwordsフィールドがあるかチェック"""
        has_words = True
        if hasattr(result, "segments"):
            segments_without_words = [
                seg
                for seg in result.segments
                if not hasattr(seg, "words") or not seg.words or len(seg.words) == 0
            ]
            if segments_without_words:
                has_words = False
        return has_words

    def _get_segments_from_result(self, result) -> list:
        """結果からセグメントを取得"""
        segments = []
        if hasattr(result, "segments"):
            if hasattr(result, "to_v2_format"):
                v2_result = result.to_v2_format()
                segments = v2_result.segments if hasattr(v2_result, "segments") else []
            else:
                segments = result.segments
        return segments

    def _update_result_with_aligned_segments(self, result, aligned_segments):
        """アライメント結果で元の結果を更新"""
        if hasattr(result, "segments"):
            result.segments = aligned_segments
        elif hasattr(result, "to_v2_format"):
            v2_result = result.to_v2_format()
            v2_result.segments = aligned_segments
            result = v2_result
        return result

    def _handle_transcription_error(self, error, cancel_placeholder, progress_bar, progress_text, error_type: str):
        """文字起こしエラーを処理"""
        SessionStateManager.set("transcription_in_progress", False)
        cancel_placeholder.empty()
        progress_bar.empty()
        progress_text.empty()

        if error_type == "interrupted":
            st.warning(f"⚠️ {str(error)}")
        elif error_type == "memory":
            memory_error = ResourceError(
                f"メモリ不足エラー: {str(error)}",
                cause=error,
                details={
                    "recovery_suggestions": [
                        f"より小さなモデル（{ModelSettings.DEFAULT_SIZE}等）を使用してください",
                        "他のアプリケーションを終了してメモリを解放してください",
                        "システムのメモリを増設してください",
                    ]
                },
            )
            error_info = self.error_handler.handle_error(memory_error, context="文字起こし", raise_after=False)
            st.error(f"❌ {error_info['user_message']}")
            if "details" in error_info and "recovery_suggestions" in error_info["details"]:
                for suggestion in error_info["details"]["recovery_suggestions"]:
                    st.error(f"💡 {suggestion}")
        else:
            # 一般的なエラー
            if isinstance(error, LegacyTranscriptionError):
                st.error(error.get_user_message())
            elif isinstance(error, (ProcessingError, NewTranscriptionError)):
                error_info = self.error_handler.handle_error(error, context="文字起こし", raise_after=False)
                st.error(error_info["user_message"])
            else:
                wrapped_error = ProcessingError(f"文字起こし処理でエラーが発生しました: {str(error)}", cause=error)
                error_info = self.error_handler.handle_error(wrapped_error, context="文字起こし", raise_after=False)
                st.error(error_info["user_message"])

    def _handle_transcription_result(self) -> None:
        """文字起こし結果の処理"""
        result = SessionStateManager.get("transcription_result")
        if result:
            # 次のページへの遷移
            SessionStateManager.set("show_text_editing", True)
            SessionStateManager.set("show_transcription", False)
            st.rerun()