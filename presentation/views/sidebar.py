"""
サイドバーのView

サイドバーのUI表示を担当します。
"""


import streamlit as st

from presentation.presenters.sidebar import SidebarPresenter
from presentation.view_models.sidebar import SidebarViewModel
from presentation.views.base import BaseView


class SidebarView(BaseView[SidebarViewModel]):
    """
    サイドバーのView

    StreamlitでサイドバーのUIを実装します。
    """

    def __init__(self, presenter: SidebarPresenter):
        """
        初期化

        Args:
            presenter: サイドバーPresenter
        """
        super().__init__(presenter.view_model)
        self.presenter = presenter

    def render(self) -> None:
        """UIをレンダリング"""
        with st.sidebar:
            # タイトル
            st.markdown("## 🎬 TextffCut")
            st.markdown("---")

            # リカバリーセクション
            if self.view_model.can_recover:
                self._render_recovery_section()

            # プロセス状態
            self._render_process_status()

            # 設定セクション
            st.markdown("### ⚙️ 設定")

            # 無音削除設定
            self._render_silence_settings()

            # API設定
            self._render_api_settings()

            # 高度な設定
            self._render_advanced_settings()

            # アクションボタン
            st.markdown("---")
            self._render_action_buttons()

            # ヘルプとバージョン情報
            self._render_footer()

    def _render_recovery_section(self) -> None:
        """リカバリーセクション"""
        with st.expander("🔄 リカバリー", expanded=False):
            st.info(f"前回の作業を復元できます（{self.view_model.recovery_timestamp}）")

            if st.button("前回の作業を復元", key="recover_button"):
                # 最新のリカバリーアイテムを使用
                if self.view_model.recovery_items:
                    success = self.presenter.load_recovery_state(self.view_model.recovery_items[0])
                    if success:
                        st.success("リカバリー完了！")
                        st.rerun()
                    else:
                        st.error("リカバリーに失敗しました")

    def _render_process_status(self) -> None:
        """プロセス状態表示"""
        status_emoji = {"ready": "✅", "running": "🔄", "stopped": "⏸️"}

        emoji = status_emoji.get(self.view_model.process_status, "❓")
        st.markdown(f"### {emoji} 状態: {self.view_model.process_message}")

        if self.view_model.process_details:
            with st.expander("詳細", expanded=False):
                for detail in self.view_model.process_details:
                    st.text(detail)

    def _render_silence_settings(self) -> None:
        """無音削除設定"""
        with st.expander("🔇 無音削除", expanded=False):
            # 有効/無効
            enabled = st.checkbox(
                "無音部分を削除する",
                value=self.view_model.remove_silence_enabled,
                key="silence_enabled",
                help="動画の無音部分を自動的に削除します",
            )

            if enabled != self.view_model.remove_silence_enabled:
                self.presenter.toggle_silence_removal(enabled)

            if enabled:
                # 閾値
                threshold = st.slider(
                    "無音判定の閾値 (dB)",
                    min_value=-60.0,
                    max_value=0.0,
                    value=self.view_model.silence_threshold,
                    step=1.0,
                    key="silence_threshold",
                    help="この値より小さい音量を無音と判定します",
                )

                if threshold != self.view_model.silence_threshold:
                    self.presenter.update_silence_threshold(threshold)

                # 詳細設定
                col1, col2 = st.columns(2)

                with col1:
                    min_duration = st.number_input(
                        "最小無音時間 (秒)",
                        min_value=0.1,
                        max_value=5.0,
                        value=self.view_model.min_silence_duration,
                        step=0.1,
                        key="min_silence_duration",
                    )

                with col2:
                    pad_start = st.number_input(
                        "開始パディング (秒)",
                        min_value=0.0,
                        max_value=2.0,
                        value=self.view_model.silence_pad_start,
                        step=0.1,
                        key="pad_start",
                    )

                # 設定が変更されたら更新
                if (
                    min_duration != self.view_model.min_silence_duration
                    or pad_start != self.view_model.silence_pad_start
                ):
                    self.view_model.update_silence_settings(
                        enabled=True,
                        threshold=threshold,
                        min_duration=min_duration,
                        pad_start=pad_start,
                        pad_end=self.view_model.silence_pad_end,
                    )
                    self.presenter.save_settings()

    def _render_api_settings(self) -> None:
        """API設定"""
        with st.expander("🌐 API設定", expanded=False):
            # APIモード
            use_api = st.checkbox(
                "OpenAI Whisper APIを使用",
                value=self.view_model.use_api,
                key="use_api",
                help="ローカルのWhisperXの代わりにOpenAI APIを使用します",
            )

            if use_api != self.view_model.use_api:
                self.presenter.toggle_api_mode(use_api)

            if use_api:
                # APIキー入力
                api_key = st.text_input(
                    "OpenAI APIキー",
                    value=self.view_model.api_key or "",
                    type="password",
                    key="api_key",
                    help="sk-で始まるAPIキーを入力してください",
                )

                if api_key and api_key != self.view_model.api_key:
                    self.presenter.set_api_key(api_key)

                # 料金情報
                st.info("💰 料金: $0.006/分（約0.9円/分）")

    def _render_advanced_settings(self) -> None:
        """高度な設定"""
        if st.checkbox("🔧 高度な設定を表示", value=self.view_model.show_advanced_settings):
            self.view_model.toggle_advanced_settings()

        if self.view_model.show_advanced_settings:
            with st.expander("高度な設定", expanded=True):
                # モデルサイズ（API使用時は無効）
                if not self.view_model.use_api:
                    model_size = st.selectbox(
                        "Whisperモデルサイズ",
                        options=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
                        index=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"].index(
                            self.view_model.model_size
                        ),
                        key="model_size",
                        help="大きいモデルほど精度が高くなりますが、処理時間も長くなります",
                    )

                    if model_size != self.view_model.model_size:
                        self.presenter.set_model_size(model_size)

                # 言語設定
                language = st.selectbox(
                    "音声の言語",
                    options=["ja", "en", "auto"],
                    index=["ja", "en", "auto"].index(self.view_model.audio_language),
                    key="audio_language",
                    help="音声の言語を指定します（autoで自動検出）",
                )

                if language != self.view_model.audio_language:
                    self.view_model.audio_language = language
                    self.presenter.save_settings()

                # GPU設定（API使用時は無効）
                if not self.view_model.use_api:
                    col1, col2 = st.columns(2)

                    with col1:
                        compute_type = st.selectbox(
                            "計算タイプ",
                            options=["float16", "float32", "int8"],
                            index=["float16", "float32", "int8"].index(self.view_model.whisper_compute_type),
                            key="compute_type",
                        )

                    with col2:
                        device = st.selectbox(
                            "デバイス",
                            options=["cuda", "cpu"],
                            index=["cuda", "cpu"].index(self.view_model.whisper_device),
                            key="device",
                        )

                    if compute_type != self.view_model.whisper_compute_type or device != self.view_model.whisper_device:
                        self.view_model.update_advanced_settings(
                            model_size=self.view_model.model_size,
                            language=self.view_model.audio_language,
                            compute_type=compute_type,
                            device=device,
                        )
                        self.presenter.save_settings()

    def _render_action_buttons(self) -> None:
        """アクションボタン"""
        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 設定を保存", key="save_settings"):
                if self.presenter.save_settings():
                    st.success("設定を保存しました")
                else:
                    st.error("設定の保存に失敗しました")

        with col2:
            if st.button("🔄 リセット", key="reset_workflow"):
                if st.checkbox("本当にリセットしますか？", key="confirm_reset"):
                    # MainPresenterのreset_workflowを呼び出す必要がある
                    # ここではフラグを立てるだけ
                    st.session_state["reset_requested"] = True
                    st.rerun()

    def _render_footer(self) -> None:
        """フッター"""
        st.markdown("---")

        # ヘルプ
        if st.button("❓ ヘルプ", key="help_button"):
            self.view_model.toggle_help_dialog()

        if self.view_model.show_help_dialog:
            with st.expander("ヘルプ", expanded=True):
                st.markdown(
                    """
                ### 使い方
                1. **動画を選択**: 編集したい動画ファイルを選択
                2. **文字起こし**: 音声を自動的にテキストに変換
                3. **テキスト編集**: 必要な部分を選択・編集
                4. **エクスポート**: 動画やFCPXMLとして出力
                
                ### トラブルシューティング
                - **エラーが発生した場合**: リカバリー機能で復元
                - **処理が遅い場合**: モデルサイズを小さくする
                - **APIを使いたい場合**: OpenAI APIキーを設定
                
                ### サポート
                - GitHub: https://github.com/your-repo/textffcut
                - Issues: バグ報告や機能要望
                """
                )

        # バージョン情報
        st.caption("TextffCut v1.0.0")
        st.caption("© 2025 TextffCut Team")

    def update(self) -> None:
        """ViewModelの変更を反映"""
        # Streamlitは自動的に再レンダリングするため、
        # 特別な処理は不要
        pass
