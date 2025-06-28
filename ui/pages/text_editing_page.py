"""
テキスト編集画面のページコントローラー

main.pyから分離されたテキスト編集処理を管理します。
"""

import streamlit as st

from config import Config
from core import TextProcessor
from services import TextEditingService
from ui import (
    show_audio_preview_for_clips,
    show_boundary_adjusted_preview,
    show_diff_viewer,
    show_edited_text_with_highlights,
    show_red_highlight_modal,
    show_text_editor,
)
from utils.logging import get_logger
from utils.session_state_manager import SessionStateManager

logger = get_logger(__name__)


class TextEditingPageController:
    """テキスト編集画面の制御"""

    def __init__(self):
        self.config = Config()
        self.text_service = TextEditingService(self.config)
        self.text_processor = TextProcessor()

    def render(self) -> None:
        """テキスト編集画面をレンダリング"""
        # 文字起こし結果の確認
        transcription = SessionStateManager.get("transcription_result")
        if not transcription:
            st.warning("文字起こし結果がありません。文字起こしを実行してください。")
            if st.button("文字起こし画面に戻る"):
                SessionStateManager.set("show_text_editing", False)
                SessionStateManager.set("show_transcription", True)
                st.rerun()
            return
        
        # 文字起こし結果の検証
        if not self._validate_transcription(transcription):
            return
        
        st.markdown("---")
        st.subheader("✂️ 切り抜き箇所の指定")
        
        # 現在の文字起こし情報を表示
        self._show_transcription_info(transcription)
        
        # エラー表示
        self._show_errors()
        
        # 全テキストを取得
        try:
            full_text = transcription.get_full_text()
        except Exception:
            st.error("❌ 文字位置情報（words）が見つかりません。文字起こしを再度実行して下さい。")
            return
        
        # 保存用に全テキストをセッション状態に保存
        SessionStateManager.set("original_text", full_text)
        
        # 2カラムレイアウト
        col1, col2 = st.columns(2)
        
        with col1:
            self._render_transcription_viewer(full_text, transcription)
        
        with col2:
            self._render_text_editor(full_text, transcription)
        
        # 音声プレビューセクション
        self._render_audio_preview()
        
        # 赤ハイライトのモーダル処理
        if SessionStateManager.get("show_red_highlight_modal", False):
            show_red_highlight_modal(SessionStateManager.get("edited_text", ""))
        
        # 処理実行ボタン
        self._render_process_button()
        
        # 再実行フラグの処理
        if SessionStateManager.get("need_rerun", False):
            SessionStateManager.delete("need_rerun")
            st.rerun()

    def _validate_transcription(self, transcription) -> bool:
        """文字起こし結果の検証"""
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
            error = WordsFieldMissingError(
                segment_count=len(segments_without_words),
                sample_segments=sample_texts
            )
            st.error(error.get_user_message())
            return False
        
        return True

    def _show_transcription_info(self, transcription):
        """文字起こし情報の表示"""
        model_info = transcription.model_size
        
        # APIモードかどうかの判定
        if "_api" in model_info or model_info == "whisper-1":
            mode_text = "API"
            model_text = model_info.replace("_api", "")
        else:
            mode_text = "ローカル"
            model_text = model_info
        
        st.caption(f"📝 現在の文字起こし結果: {mode_text}モード・{model_text}")

    def _show_errors(self):
        """エラー表示"""
        if SessionStateManager.get("show_error_and_delete", False):
            st.error("⚠️ 元動画に存在しない文字が切り抜き箇所に入力されています。削除してください。")
        
        if SessionStateManager.get("show_marker_error", False):
            st.error("⚠️ 境界調整マーカーの位置が不適切です。マーカーは各行の先頭と末尾にのみ配置してください。")
            marker_errors = SessionStateManager.get("marker_position_errors", [])
            for error in marker_errors:
                st.error(f"❌ {error}")

    def _render_transcription_viewer(self, full_text: str, transcription):
        """文字起こし結果ビューア"""
        st.markdown("#### 文字起こし結果")
        st.caption("切り抜き箇所に指定した箇所が緑色でハイライトされます")
        
        saved_edited_text = SessionStateManager.get("edited_text", "")
        if saved_edited_text:
            # 区切り文字の検出
            separator_patterns = ["---", "——", "－－－"]
            found_separator = None
            for pattern in separator_patterns:
                if pattern in saved_edited_text:
                    found_separator = pattern
                    break
            
            # 境界調整マーカーの検出
            has_boundary_markers = any(
                marker in saved_edited_text for marker in ["[<", "[>", "<]", ">]"]
            )
            
            # 差分を計算
            if found_separator:
                # 区切り文字対応
                diff = self.text_processor.find_differences_with_separator(
                    full_text,
                    self.text_processor.remove_boundary_markers(saved_edited_text),
                    transcription,
                    found_separator,
                    skip_normalization=has_boundary_markers
                )
            else:
                # 通常の差分
                diff = self.text_processor.find_differences(
                    full_text,
                    self.text_processor.remove_boundary_markers(saved_edited_text),
                    skip_normalization=has_boundary_markers
                )
            
            # 差分を表示
            show_diff_viewer(full_text, diff)
        else:
            # 初期表示（差分なし）
            show_diff_viewer(full_text)

    def _render_text_editor(self, full_text: str, transcription):
        """テキストエディタ"""
        st.markdown("#### 切り抜き箇所")
        st.caption("文字起こし結果から切り抜く箇所を入力してください")
        
        # テキストエディタを表示
        edited_text = show_text_editor(SessionStateManager.get("edited_text", ""), height=400)
        
        # 更新ボタンが押された場合の処理
        boundary_mode = SessionStateManager.get("boundary_adjustment_mode", False)
        if st.button("🔍 更新", use_container_width=True, type="primary"):
            self._handle_update_button(edited_text, full_text, transcription, boundary_mode)
        
        # 境界調整モード（更新ボタンの下に配置）
        boundary_mode = st.checkbox(
            "境界調整モード",
            value=SessionStateManager.get("boundary_adjustment_mode", False),
            key="boundary_adjustment_mode",
            help="文字単位での精密な境界調整を行います"
        )
        
        if boundary_mode:
            st.caption("💡 [< >] で前後に0.1秒、[<< >>] で前後に0.5秒、[<<< >>>] で前後に1秒調整")

    def _handle_update_button(self, edited_text: str, full_text: str, transcription, boundary_mode: bool):
        """更新ボタンの処理"""
        # 境界調整モードに応じたマーカー処理
        if not boundary_mode and any(marker in edited_text for marker in ["[<", "[>", "<]", ">]"]):
            # 通常モードでマーカーがある場合は削除
            cleaned_text = self.text_processor.remove_boundary_markers(edited_text)
            if cleaned_text != edited_text:
                SessionStateManager.set("text_editor_value", cleaned_text)
                edited_text = cleaned_text
                logger.info("通常モード：境界調整マーカーを削除しました")
        
        SessionStateManager.set("edited_text", edited_text)
        SessionStateManager.set("preview_update_requested", True)
        
        # 時間範囲を計算
        if edited_text:
            self._calculate_time_ranges(edited_text, full_text, transcription)
        
        # エラーチェック
        self._check_for_errors(edited_text, full_text, boundary_mode)

    def _calculate_time_ranges(self, edited_text: str, full_text: str, transcription):
        """時間範囲の計算"""
        # 境界マーカーを解析
        boundary_adjustments = self.text_processor.parse_boundary_markers(edited_text)
        
        # マーカーを除去したテキストで差分検出
        cleaned_text = self.text_processor.remove_boundary_markers(edited_text)
        
        # 区切り文字の検出
        separator_patterns = ["---", "——", "－－－"]
        found_separator = None
        for pattern in separator_patterns:
            if pattern in cleaned_text:
                found_separator = pattern
                break
        
        has_boundary_markers = any(
            marker in edited_text for marker in ["[<", "[>", "<]", ">]"]
        )
        
        if found_separator:
            time_ranges = self.text_processor.find_differences_with_separator(
                full_text,
                cleaned_text,
                transcription,
                found_separator,
                skip_normalization=has_boundary_markers
            )
        else:
            diff = self.text_processor.find_differences(
                full_text,
                cleaned_text,
                skip_normalization=has_boundary_markers
            )
            time_ranges = diff.get_time_ranges(transcription)
        
        # 境界調整を適用
        if boundary_adjustments:
            adjusted_time_ranges = self.text_processor.apply_boundary_adjustments(
                time_ranges,
                boundary_adjustments,
                edited_text
            )
            SessionStateManager.set("time_ranges", adjusted_time_ranges)
            SessionStateManager.set("has_boundary_adjustments", True)
        else:
            SessionStateManager.set("time_ranges", time_ranges)
            SessionStateManager.set("has_boundary_adjustments", False)
        
        # タイムライン編集セクションは表示しない（境界調整で代替）
        SessionStateManager.set("show_timeline_section", False)
        SessionStateManager.set("timeline_completed", True)

    def _check_for_errors(self, edited_text: str, full_text: str, boundary_mode: bool):
        """エラーチェック"""
        if not edited_text:
            return
        
        cleaned_text = self.text_processor.remove_boundary_markers(edited_text)
        
        # 区切り文字対応
        separator_patterns = ["---", "——", "－－－"]
        found_separator = None
        for pattern in separator_patterns:
            if pattern in cleaned_text:
                found_separator = pattern
                break
        
        has_boundary_markers = any(
            marker in edited_text for marker in ["[<", "[>", "<]", ">]"]
        )
        
        # 境界調整モードに応じたエラーチェック
        if boundary_mode:
            # マーカー位置エラーをチェック
            if has_boundary_markers:
                # 自動修正を試みる
                fixed_text = self.text_processor.auto_fix_marker_newlines(edited_text)
                if fixed_text != edited_text:
                    SessionStateManager.set("text_editor_value", fixed_text)
                    logger.info("マーカー配置を自動修正しました")
                    SessionStateManager.set("need_rerun", True)
                else:
                    # 修正不要の場合は検証
                    marker_errors = self.text_processor.validate_marker_positions(edited_text)
                    if marker_errors:
                        SessionStateManager.set("show_marker_error", True)
                        SessionStateManager.set("marker_position_errors", marker_errors)
                    else:
                        SessionStateManager.set("show_marker_error", False)
                        SessionStateManager.delete("marker_position_errors")
        
        # 赤ハイライトチェック（追加文字チェック）
        has_red_highlights = False
        if found_separator:
            # 区切り文字がある場合：各セクションで追加文字をチェック
            sections = self.text_processor.split_text_by_separator(cleaned_text, found_separator)
            for i, section in enumerate(sections):
                diff = self.text_processor.find_differences(
                    full_text, section, skip_normalization=has_boundary_markers
                )
                if diff.has_additions():
                    has_red_highlights = True
                    break
        else:
            # 通常の差分チェック
            diff = self.text_processor.find_differences(
                full_text, cleaned_text, skip_normalization=has_boundary_markers
            )
            has_red_highlights = diff.has_additions()
        
        if has_red_highlights:
            # 通常モードでマーカーがある場合は警告
            if not boundary_mode and has_boundary_markers:
                SessionStateManager.set("show_red_highlight_modal", True)
                SessionStateManager.set("modal_from_normal_mode", True)
            # 境界調整モードまたはマーカーなしの場合
            elif not has_boundary_markers or boundary_mode:
                SessionStateManager.set("show_error_and_delete", True)
        else:
            SessionStateManager.set("show_error_and_delete", False)
            SessionStateManager.set("show_red_highlight_modal", False)

    def _render_audio_preview(self):
        """音声プレビューセクション"""
        time_ranges = SessionStateManager.get("time_ranges")
        if not time_ranges:
            return
        
        # 音声プレビューの更新判定
        should_update_preview = (
            SessionStateManager.get("preview_update_requested", False) or
            not SessionStateManager.get("audio_preview_generated", False)
        )
        
        if should_update_preview:
            SessionStateManager.set("preview_update_requested", False)
            SessionStateManager.set("audio_preview_generated", True)
        
        # 音声プレビューセクション
        st.markdown("---")
        st.subheader("🎧 音声プレビュー")
        
        video_path = SessionStateManager.get("video_path")
        if not video_path:
            st.warning("動画ファイルが選択されていません")
            return
        
        # 境界調整モードかどうかで表示を切り替え
        if SessionStateManager.get("has_boundary_adjustments", False):
            # 境界調整後のプレビュー
            # 注: 元の範囲と調整後の範囲が必要
            # 現在は調整後の範囲のみ利用可能なので、同じものを渡す
            show_boundary_adjusted_preview(
                video_path,
                time_ranges,  # original_ranges
                time_ranges   # adjusted_ranges (同じものを使用)
            )
        else:
            # 通常のプレビュー
            show_audio_preview_for_clips(video_path, time_ranges)

    def _render_process_button(self):
        """処理実行ボタン"""
        time_ranges = SessionStateManager.get("time_ranges")
        if time_ranges and not SessionStateManager.get("show_error_and_delete", False):
            st.markdown("---")
            if st.button("🎬 次へ進む", type="primary", use_container_width=True):
                # 処理実行画面へ遷移
                SessionStateManager.set("show_processing", True)
                SessionStateManager.set("show_text_editing", False)
                st.rerun()