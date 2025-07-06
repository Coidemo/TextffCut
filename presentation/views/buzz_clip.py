"""
バズクリップ生成View

StreamlitのUIコンポーネントを使用してバズクリップ生成画面を表示します。
"""

import logging
from typing import Any

import streamlit as st

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.presenters.buzz_clip import BuzzClipPresenter
from presentation.view_models.buzz_clip import BuzzClipViewModel

logger = logging.getLogger(__name__)


class BuzzClipView:
    """
    バズクリップ生成のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: BuzzClipPresenter):
        """
        初期化

        Args:
            presenter: バズクリップPresenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: BuzzClipViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(
        self,
        transcription_segments: list[dict[str, Any]] | None = None,
        video_path: str | None = None,
        transcription_model: str | None = None,
    ) -> None:
        """
        UIをレンダリング

        Args:
            transcription_segments: 文字起こしセグメント（結果がある場合）
            video_path: 動画ファイルパス（キャッシュ用）
            transcription_model: 文字起こしモデル名（キャッシュ紐付け用）
        """
        st.subheader("🎬 AIバズクリップ生成")

        # 文字起こし結果がない場合
        if not transcription_segments:
            st.info("💡 文字起こし結果からAIが自動でバズる切り抜き候補を提案します")
            st.warning("⚠️ まず文字起こしを実行してください")
            return

        # 生成パラメータ設定
        if not self.view_model.is_generating and not self.view_model.has_candidates:
            self._render_generation_settings()

        # 生成ボタン
        if not self.view_model.is_generating and not self.view_model.has_candidates:
            if st.button("🤖 AIで切り抜き候補を生成", type="primary", use_container_width=True):
                self._start_generation(transcription_segments, video_path, transcription_model)

        # 生成中の表示
        if self.view_model.is_generating:
            self._render_generating()

        # 結果表示
        if self.view_model.has_candidates:
            logger.info(f"Rendering results with {len(self.view_model.candidates)} candidates")
            self._render_results()
        else:
            logger.info(
                f"No candidates to display. has_candidates={self.view_model.has_candidates}, candidates={len(self.view_model.candidates)}"
            )

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")

    def _render_generation_settings(self) -> None:
        """生成設定UIを表示"""
        # Expanderを使わずに直接表示（既に親でExpanderが使われているため）
        st.markdown("### ⚙️ 生成設定")

        # 候補数
        col1, col2 = st.columns(2)

        with col1:
            num_candidates = st.number_input(
                "生成する候補数",
                min_value=1,
                max_value=10,
                value=self.view_model.num_candidates,
                help="AIが提案する切り抜き候補の数",
            )

        with col2:
            st.markdown("**時間範囲**")
            col2_1, col2_2 = st.columns(2)
            with col2_1:
                min_duration = st.number_input(
                    "最小（秒）", min_value=10, max_value=50, value=self.view_model.min_duration, step=5
                )
            with col2_2:
                max_duration = st.number_input(
                    "最大（秒）", min_value=20, max_value=60, value=self.view_model.max_duration, step=5
                )

        # カテゴリ選択
        st.markdown("**優先カテゴリ（複数選択可）**")
        selected_categories = []
        cols = st.columns(len(self.view_model.available_categories))
        for i, category in enumerate(self.view_model.available_categories):
            with cols[i]:
                if st.checkbox(category, value=category in self.view_model.selected_categories):
                    selected_categories.append(category)

            # パラメータを更新
            self.presenter.set_generation_params(
                num_candidates=num_candidates,
                min_duration=min_duration,
                max_duration=max_duration,
                categories=selected_categories,
            )

    def _start_generation(
        self,
        transcription_segments: list[dict[str, Any]],
        video_path: str | None = None,
        transcription_model: str | None = None,
    ) -> None:
        """生成を開始"""
        logger.info("Starting buzz clip generation from view")
        logger.info(f"Transcription model: {transcription_model}")

        def progress_callback(progress: float, status: str) -> None:
            self.view_model.update_generation_progress(progress, status)

        # 生成を実行
        success = self.presenter.generate_buzz_clips(
            transcription_segments=transcription_segments,
            video_path=video_path,
            transcription_model=transcription_model,
            progress_callback=progress_callback,
        )

        logger.info(f"Generation completed. Success={success}, has_candidates={self.view_model.has_candidates}")

        if success:
            logger.info(f"Rerunning app with {len(self.view_model.candidates)} candidates")
            st.rerun()

    def _render_generating(self) -> None:
        """生成中のUIを表示"""
        with st.spinner(self.view_model.generation_status):
            progress_bar = st.progress(self.view_model.generation_progress)
            st.info(self.view_model.generation_status)

    def _render_results(self) -> None:
        """結果を表示"""
        # 統計情報
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("生成された候補", f"{len(self.view_model.candidates)}個")
        with col2:
            st.metric("処理時間", f"{self.view_model.total_processing_time:.1f}秒")
        with col3:
            st.metric("使用モデル", self.view_model.model_used)

        # 選択ボタン
        col1, col2, col3 = st.columns([1, 1, 3])
        with col1:
            if st.button("✅ すべて選択"):
                self.presenter.select_all_candidates()
                st.rerun()
        with col2:
            if st.button("❌ すべて解除"):
                self.presenter.deselect_all_candidates()
                st.rerun()
        with col3:
            st.info(f"選択中: {self.view_model.selected_count}個")

        # 候補リスト
        st.divider()
        for candidate in self.view_model.candidates:
            self._render_candidate(candidate)

        # エクスポートボタン
        if self.view_model.can_export:
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📝 選択した候補を切り抜き箇所に設定", type="primary", use_container_width=True):
                    # 選択された候補を取得
                    selected_candidates = self.presenter.get_selected_candidates()
                    if selected_candidates:
                        # セッション状態に保存
                        st.session_state["buzz_clip_candidates"] = selected_candidates
                        st.session_state["use_buzz_clips"] = True
                        st.success(f"✅ {len(selected_candidates)}個の候補が切り抜き箇所として設定されました")
                        # テキスト編集セクションを表示するためのフラグ
                        st.session_state["show_text_edit_after_buzz"] = True
                        st.rerun()
                    else:
                        st.error("❌ 候補を選択してください")
            with col2:
                if st.button("🔄 新しく生成し直す", type="secondary", use_container_width=True):
                    self.presenter.reset()
                    st.rerun()

    def _render_candidate(self, candidate: BuzzClipCandidate) -> None:
        """候補を表示"""
        is_selected = candidate.id in self.view_model.selected_candidates

        with st.container():
            # チェックボックスとタイトル
            col1, col2 = st.columns([1, 11])
            with col1:
                # チェックボックスの現在の状態を取得
                new_state = st.checkbox("", value=is_selected, key=f"select_{candidate.id}")
                # 状態が変わった場合のみ更新
                if new_state != is_selected:
                    self.presenter.toggle_candidate_selection(candidate.id)
                    st.rerun()

            with col2:
                # タイトルとスコア
                col2_1, col2_2 = st.columns([10, 2])
                with col2_1:
                    st.markdown(f"### {candidate.title}")
                with col2_2:
                    # スコアをバッジ風に表示
                    score_color = self._get_score_color(candidate.score)
                    st.markdown(
                        f'<span style="background-color: {score_color}; color: white; '
                        f'padding: 4px 8px; border-radius: 4px; font-weight: bold;">'
                        f"スコア: {candidate.score}/20</span>",
                        unsafe_allow_html=True,
                    )

                # メタ情報
                col_meta1, col_meta2, col_meta3 = st.columns(3)
                with col_meta1:
                    st.caption(f"⏱️ {candidate.start_time:.1f}秒 〜 {candidate.end_time:.1f}秒")
                with col_meta2:
                    st.caption(f"⏳ 長さ: {candidate.duration:.1f}秒")
                with col_meta3:
                    st.caption(f"📁 {candidate.category}")

                # テキスト内容（Expanderの代わりにトグルボタンを使用）
                toggle_key = f"show_content_{candidate.id}"

                # ボタンをクリックしたときの処理
                if st.button(
                    f"{'📝 内容を隠す' if st.session_state.get(toggle_key, False) else '📝 内容を見る'}",
                    key=f"toggle_btn_{candidate.id}",
                ):
                    # セッション状態でトグル管理
                    st.session_state[toggle_key] = not st.session_state.get(toggle_key, False)
                    st.rerun()

                # 内容表示
                if st.session_state.get(toggle_key, False):
                    with st.container():
                        st.text(candidate.text)
                        st.divider()
                        st.markdown("**選定理由:**")
                        st.info(candidate.reasoning)
                        if candidate.keywords:
                            st.markdown("**キーワード:** " + ", ".join(candidate.keywords))

            st.divider()

    def _get_score_color(self, score: int) -> str:
        """スコアに応じた色を取得"""
        if score >= 16:
            return "#28a745"  # 緑
        elif score >= 12:
            return "#ffc107"  # 黄
        elif score >= 8:
            return "#fd7e14"  # オレンジ
        else:
            return "#dc3545"  # 赤


def show_buzz_clip_generation(container: Any, transcription_segments: list[dict[str, Any]] | None = None) -> None:
    """
    バズクリップ生成セクションを表示

    Args:
        container: DIコンテナ
        transcription_segments: 文字起こしセグメント
    """
    # PresenterとViewを作成
    presenter = container.presentation.buzz_clip_presenter()
    view = BuzzClipView(presenter)

    # 初期化
    presenter.initialize()

    # UIをレンダリング
    view.render(transcription_segments)
