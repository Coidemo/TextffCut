"""
テキスト編集View

StreamlitのUIコンポーネントを使用してテキスト編集画面を表示します。
"""

from pathlib import Path
from typing import Any

import streamlit as st

from domain.entities import TranscriptionResult
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.view_models.text_editor import TextEditorViewModel
from ui.components import show_diff_viewer, show_edited_text_with_highlights, show_red_highlight_modal, show_text_editor
from utils.logging import get_logger

logger = get_logger(__name__)


class TextEditorView:
    """
    テキスト編集のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: TextEditorPresenter):
        """
        初期化

        Args:
            presenter: テキスト編集Presenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: TextEditorViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(self, transcription_result: TranscriptionResult, video_path: Path) -> dict[str, Any]:
        """
        UIをレンダリング

        Args:
            transcription_result: 文字起こし結果
            video_path: 動画ファイルパス

        Returns:
            処理結果の辞書
        """
        # バズクリップ候補を使用する場合は、先にセッション状態をクリアしてフラグを立てる
        skip_initial_processing = False
        if st.session_state.get("use_buzz_clips", False) and "buzz_clip_candidates" in st.session_state:
            # 古いテキストや差分情報をクリア
            if "edited_text" in st.session_state:
                del st.session_state["edited_text"]
            if "text_differences" in st.session_state:
                del st.session_state["text_differences"]
            # 初期処理をスキップするフラグ
            skip_initial_processing = True

        # 初期化（バズクリップ使用時は初期処理をスキップ）
        if skip_initial_processing:
            # 一時的に初期処理をスキップするフラグを設定
            st.session_state["_skip_initial_text_processing"] = True

        self.presenter.initialize(transcription_result)

        # フラグをクリア
        if "_skip_initial_text_processing" in st.session_state:
            del st.session_state["_skip_initial_text_processing"]

        # バズクリップ候補を使用する場合
        if st.session_state.get("use_buzz_clips", False) and "buzz_clip_candidates" in st.session_state:
            candidates = st.session_state["buzz_clip_candidates"]
            # 候補からテキストを生成
            text_parts = []
            for candidate in candidates:
                text_parts.append(candidate.text)

            # セパレータで結合
            edited_text = "\n\n---\n\n".join(text_parts)

            # テキストエディタに設定
            st.session_state["text_editor_value"] = edited_text

            # フラグをリセット
            st.session_state["use_buzz_clips"] = False

            # 使用した候補の情報を表示
            st.info(f"🎬 {len(candidates)}個のバズクリップ候補をテキストエディタに設定しました")

        # モーダル表示（最優先）
        if st.session_state.get("show_modal", False):
            with st.container():
                st.markdown("### ⚠️ 元動画に存在しない文字が検出されました")
                edited_text = st.session_state.get("current_edited_text", "")
                diff = st.session_state.get("current_diff")
                show_red_highlight_modal(edited_text, diff)
                # モーダルが表示されているときは他の処理をスキップ
                return {}

        # エラー表示（2カラムの上に表示）
        if st.session_state.get("show_error_and_delete", False):
            st.error("⚠️ 元動画に存在しない文字が切り抜き箇所に入力されています。削除してください。")

        # 2カラムレイアウト
        col1, col2 = st.columns([1, 1])

        # 左カラム: 文字起こし結果
        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した箇所が緑色でハイライトされます")
            # 文字起こし結果を表示
            self._render_transcription_result()
            
            # バズクリップ機能を表示
            self._render_buzz_clip_section()

        # 右カラム: テキスト編集
        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く箇所を入力してください")

            # テキストエディタ
            edited_text = self._render_text_editor()

            # 文字数と時間の表示
            if edited_text:
                self._render_text_stats()

            # アクションボタン
            self._render_action_buttons()

        # 境界調整マーカー検出時の表示
        if self.view_model.has_boundary_markers:
            self._render_boundary_markers_info()

        # セクション分割時の表示
        if self.view_model.has_separator:
            self._render_sections_info()

        # 時間範囲の計算結果表示
        if self.view_model.has_time_ranges:
            self._render_time_ranges_info()

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")

        # マーカー位置エラーの表示
        if st.session_state.get("show_marker_error", False):
            st.error("⚠️ 境界調整マーカーの位置が不適切です。マーカーは各行の先頭と末尾にのみ配置してください。")
            marker_errors = st.session_state.get("marker_position_errors", [])
            for error in marker_errors:
                st.error(f"❌ {error}")

        # 処理データを返す
        return self.presenter.get_processed_data()

    def _render_transcription_result(self) -> None:
        """文字起こし結果を表示"""
        if self.view_model.full_text:
            # 編集テキストがある場合は差分を表示
            if self.view_model.edited_text and self.view_model.differences:
                show_diff_viewer(self.view_model.full_text, self.view_model.differences)
            else:
                # 差分がない場合は元のテキストのみ表示
                show_diff_viewer(self.view_model.full_text)
        else:
            st.info("文字起こし結果がありません")

    def _render_text_editor(self) -> str:
        """テキストエディタを表示"""
        # セッション状態から初期値を取得
        initial_text = st.session_state.get("text_editor_value", self.view_model.edited_text)

        # テキストエディタ表示
        edited_text = st.text_area(
            "編集エリア", value=initial_text, height=400, key="text_editor", label_visibility="collapsed"
        )

        # テキストが変更されたら更新
        if edited_text != self.view_model.edited_text:
            self.presenter.update_edited_text(edited_text)

        return edited_text

    def _render_buzz_clip_navigation(self) -> None:
        """バズクリップ候補のナビゲーションUIを表示"""
        candidates = st.session_state.buzz_clip_all_candidates
        current_index = st.session_state.get("buzz_clip_current_index", 0)
        
        # ナビゲーションコントロール
        nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 6, 1, 1])

        with nav_col1:
            # 前の候補ボタン
            if st.button("◀", key="buzz_prev", disabled=current_index == 0, use_container_width=True):
                new_index = current_index - 1
                st.session_state.buzz_clip_current_index = new_index
                # 候補を切り替え
                self._switch_to_candidate(candidates[new_index])
                st.rerun()

        with nav_col2:
            # 現在の候補情報
            candidate = candidates[current_index]
            st.info(f"候補 {current_index + 1}/{len(candidates)}: {candidate.title}")

        with nav_col3:
            # 次の候補ボタン
            if st.button("▶", key="buzz_next", disabled=current_index >= len(candidates) - 1, use_container_width=True):
                new_index = current_index + 1
                st.session_state.buzz_clip_current_index = new_index
                # 候補を切り替え
                self._switch_to_candidate(candidates[new_index])
                st.rerun()

        with nav_col4:
            # クリアボタン
            if st.button("❌", key="buzz_clear", use_container_width=True, help="バズクリップ候補をクリア"):
                del st.session_state.buzz_clip_all_candidates
                if "buzz_clip_current_index" in st.session_state:
                    del st.session_state.buzz_clip_current_index
                st.session_state.text_editor_value = ""
                st.rerun()

    def _switch_to_candidate(self, candidate) -> None:
        """指定された候補に切り替え"""
        # テキストエディタに候補のテキストを設定
        st.session_state.text_editor_value = candidate.text
        # ビューモデルも更新
        self.presenter.update_edited_text(candidate.text)
    
    def _render_buzz_clip_section(self) -> None:
        """バズクリップセクションを表示"""
        # バズクリップ候補がある場合はナビゲーションを表示
        if "buzz_clip_all_candidates" in st.session_state and st.session_state.buzz_clip_all_candidates:
            st.markdown("")
            self._render_buzz_clip_navigation()
        else:
            # バズクリップ生成ボタンを表示
            st.markdown("")
            if st.button("🤖 AIでバズクリップ候補を生成", key="generate_buzz_clips", use_container_width=True):
                # バズクリップ生成フラグを設定
                st.session_state["request_buzz_clip_generation"] = True
                st.rerun()

    def _render_text_stats(self) -> None:
        """文字数と時間の統計を表示"""
        stats_parts = [f"文字数: {self.view_model.char_count}文字"]

        if self.view_model.total_duration > 0:
            stats_parts.append(f"時間: {self.view_model.duration_text}（無音削除前）")

        if self.view_model.section_count > 1:
            stats_parts.append(f"セクション数: {self.view_model.section_count}")

        st.caption(" / ".join(stats_parts))

    def _render_action_buttons(self) -> None:
        """アクションボタンを表示"""
        button_col1, button_col2 = st.columns([1, 3])

        with button_col1:
            # 更新ボタン
            if st.button("更新", type="primary", use_container_width=True, key="update_button"):
                # 境界調整モードかどうかをPresenterに伝える
                boundary_mode = st.session_state.get("boundary_adjustment_mode", False)

                # 編集されたテキストを取得（text_editorの最新値）
                current_text = st.session_state.get("text_editor_value", self.view_model.edited_text)

                if boundary_mode and current_text:
                    # 境界調整モードの場合、マーカーを挿入
                    self.presenter.apply_boundary_adjustment_markers(current_text)
                    # 処理後のテキストをtext_editorに反映
                    st.session_state.text_editor_value = self.view_model.edited_text
                else:
                    # 通常モードの場合、マーカーを削除してテキストを再処理
                    if current_text:
                        # マーカーが含まれている場合は削除
                        if any(marker in current_text for marker in ["[<", "[>", "<]", ">]"]):
                            cleaned_text = self.presenter.remove_boundary_markers(current_text)
                            st.session_state.text_editor_value = cleaned_text
                            self.presenter.update_edited_text(cleaned_text)
                        else:
                            self.presenter.update_edited_text(current_text)

                # セッション状態に保存（既存コードとの互換性）
                st.session_state.edited_text = self.view_model.edited_text
                st.session_state.preview_update_requested = True

                # 時間範囲をセッション状態に保存
                if self.view_model.time_ranges:
                    time_ranges_tuples = [(tr.start, tr.end) for tr in self.view_model.time_ranges]
                    st.session_state.time_ranges = time_ranges_tuples
                    st.session_state.has_boundary_adjustments = self.view_model.has_boundary_markers

                    # 時間範囲が計算されたらナビゲーションを有効にするためのフラグ
                    st.session_state.text_edit_has_time_ranges = True
                    # text_edit_completedは「エクスポートへ進む」ボタンを押した時のみ設定

                # 差分に追加された文字がある場合はモーダル表示フラグを設定
                if self.view_model.has_added_chars:
                    st.session_state.show_modal = True
                    st.session_state.current_edited_text = self.view_model.edited_text
                    st.session_state.current_diff = self.view_model.differences
                    st.session_state.original_edited_text = current_text

                st.rerun()

        with button_col2:
            # 音声プレビュー（更新ボタンクリック時に生成・表示）
            if st.session_state.get("preview_update_requested", False) and self.view_model.time_ranges:
                # 音声を生成
                try:
                    # セッション状態から動画パスを取得（SessionManagerが設定する複数のキーを確認）
                    video_path = (
                        st.session_state.get("video_path")
                        or st.session_state.get("current_video_path")
                        or st.session_state.get("selected_video")
                    )
                    if not video_path:
                        # デバッグ情報を表示
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.error(
                            f"動画パスが見つかりません。セッション状態: video_path={st.session_state.get('video_path')}, current_video_path={st.session_state.get('current_video_path')}, selected_video={st.session_state.get('selected_video')}"
                        )
                        st.error("動画が選択されていません。動画を選択してから文字起こしを実行してください。")
                    else:
                        # Presenter経由で音声プレビューを生成
                        # プレビュー用の時間範囲を準備
                        time_ranges = [(tr.start, tr.end) for tr in self.view_model.time_ranges]

                        # Presenter経由で音声プレビューを生成
                        audio_path = self.presenter.generate_audio_preview(
                            str(video_path), time_ranges, max_duration=60.0
                        )

                        if audio_path:
                            # 音声プレイヤーを表示
                            with open(audio_path, "rb") as audio_file:
                                audio_bytes = audio_file.read()
                                st.audio(audio_bytes, format="audio/wav")

                            # 一時ファイルを削除
                            import os

                            os.unlink(audio_path)

                            # プレビュー情報を表示
                            st.caption("音声プレビューを生成しました（最大60秒）")
                        else:
                            st.warning("音声プレビューの生成に失敗しました")

                except Exception as e:
                    st.error(f"音声プレビューの生成に失敗しました: {e}")

                # フラグをリセット
                st.session_state.preview_update_requested = False

        # 境界調整モード切り替え（2カラムの外に配置）
        boundary_mode = st.checkbox(
            "🎯 境界調整モード",
            value=st.session_state.get("boundary_adjustment_mode", False),
            help="マーカーを使用してクリップの境界を細かく調整できます",
            key="boundary_adjustment_checkbox",
        )
        st.session_state.boundary_adjustment_mode = boundary_mode

    def _render_boundary_markers_info(self) -> None:
        """境界調整マーカー情報を表示"""
        with st.expander("🎯 境界調整マーカーが検出されました", expanded=True):
            st.info(
                "境界調整マーカーを使用してクリップの開始・終了位置を調整できます。\n\n"
                "**使用方法:**\n"
                "- `[数値<]` = 前のクリップを縮める\n"
                "- `[数値>]` = 前のクリップを延ばす\n"
                "- `[<数値]` = 後のクリップを早める\n"
                "- `[>数値]` = 後のクリップを遅らせる"
            )

            # ハイライト表示
            if self.view_model.differences:
                st.markdown("**マーカー適用後のプレビュー:**")
                show_edited_text_with_highlights(self.view_model.edited_text, self.view_model.differences, height=200)

    def _render_sections_info(self) -> None:
        """セクション分割情報を表示"""
        with st.expander(f"📑 {self.view_model.section_count}個のセクションに分割されています", expanded=True):
            st.info(f"区切り文字 `{self.view_model.separator}` で分割されました")

            # 各セクションの情報
            for i, section in enumerate(self.view_model.sections):
                st.markdown(f"**セクション {i + 1}:**")
                st.text(section[:100] + "..." if len(section) > 100 else section)

    def _render_time_ranges_info(self) -> None:
        """時間範囲の計算結果を表示"""
        # 時間範囲が計算されたことを示すだけ（特に表示なし）
        pass


def show_text_editor_section(
    transcription_result: TranscriptionResult, video_path: Path, container: Any | None = None
) -> dict[str, Any]:
    """
    テキスト編集セクション（既存のUI関数との互換性のため）

    Args:
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
        container: DIコンテナ

    Returns:
        処理結果の辞書
    """
    if not container:
        # 互換性のため、コンテナなしでは空の結果を返す
        return {}

    if not transcription_result:
        st.error("文字起こし結果がありません")
        return {}

    # PresenterとViewを作成
    presenter = container.presentation.text_editor_presenter()
    view = TextEditorView(presenter)

    # UIをレンダリングして結果を返す
    return view.render(transcription_result, video_path)


def show_text_editor(container: Any) -> None:
    """
    テキスト編集セクションを表示

    Args:
        container: Streamlitコンテナ
    """
    container.subheader("✏️ テキスト編集")
    container.info("ここにテキスト編集UIが表示されます")
    # TODO: 実際のテキスト編集UIを実装
