"""
サイドバーのView

サイドバーのUI表示を担当します。
"""

import streamlit as st

from presentation.presenters.sidebar import SidebarPresenter
from presentation.view_models.sidebar import SidebarViewModel
from presentation.views.base import BaseView
from utils.test_ids import TestIds


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

            # タブ表示
            tab1, tab2 = st.tabs(["🎛️ 設定", "❓ ヘルプ"])

            with tab1:
                # 設定タブ
                self._render_settings_tab()

            with tab2:
                # ヘルプタブ
                self._render_help_tab()

    def _render_settings_tab(self) -> None:
        """設定タブの内容"""
        # 無音削除の詳細設定
        st.markdown("#### 🔇 無音削除の詳細設定")

        # 閾値
        threshold = st.slider(
            "無音判定の閾値 (dB)",
            min_value=-60,
            max_value=-20,
            value=int(self.view_model.silence_threshold),
            step=1,
            help="この値より小さい音量を無音と判定します",
            key=TestIds.SIDEBAR_SILENCE_THRESHOLD,
        )

        if threshold != self.view_model.silence_threshold:
            self.presenter.update_silence_threshold(float(threshold))

        # 詳細設定
        col1, col2 = st.columns(2)

        with col1:
            min_duration = st.number_input(
                "最小無音時間 (秒)",
                min_value=0.10,
                max_value=2.00,
                value=self.view_model.min_silence_duration,
                step=0.05,
                format="%.2f",
                help="この時間以上続く無音のみを削除対象とします",
                key=TestIds.SIDEBAR_MIN_SILENCE_DURATION,
            )

            min_segment = st.number_input(
                "最小セグメント時間 (秒)",
                min_value=0.10,
                max_value=2.00,
                value=self.view_model.min_segment_duration,
                step=0.05,
                format="%.2f",
                help="セグメントとして残す最小の時間",
                key=TestIds.SIDEBAR_MIN_SEGMENT_DURATION,
            )

        with col2:
            pad_start = st.number_input(
                "開始パディング (秒)",
                min_value=0.00,
                max_value=1.00,
                value=self.view_model.silence_pad_start,
                step=0.05,
                format="%.2f",
                help="有音部分の開始前に残す時間",
                key=TestIds.SIDEBAR_SILENCE_PAD + "_start",
            )

            pad_end = st.number_input(
                "終了パディング (秒)",
                min_value=0.00,
                max_value=1.00,
                value=self.view_model.silence_pad_end,
                step=0.05,
                format="%.2f",
                help="有音部分の終了後に残す時間",
                key=TestIds.SIDEBAR_SILENCE_PAD + "_end",
            )

        # 設定が変更されたら更新
        if (
            min_duration != self.view_model.min_silence_duration
            or min_segment != self.view_model.min_segment_duration
            or pad_start != self.view_model.silence_pad_start
            or pad_end != self.view_model.silence_pad_end
        ):
            self.view_model.update_silence_settings(
                enabled=True,
                threshold=float(threshold),
                min_duration=min_duration,
                pad_start=pad_start,
                pad_end=pad_end,
            )
            self.presenter.save_settings()

        st.markdown("---")

        # API設定
        self._render_api_settings()

    def _render_api_settings(self) -> None:
        """API設定"""
        st.markdown("#### 🔑 APIキー設定")

        # 保存されたAPIキーがあるかチェック
        if self.view_model.api_key:
            # マスクされたキーを表示
            masked_key = self._mask_api_key(self.view_model.api_key)
            st.success(f"✅ 保存されたAPIキー: {masked_key}")
            st.caption("🔒 APIキーは暗号化して保存されています")

            # 削除ボタン
            if st.button("🗑️ 保存済みキーを削除", use_container_width=True, key=TestIds.SIDEBAR_API_KEY_DELETE):
                if self.presenter.delete_api_key():
                    st.success("保存されたAPIキーを削除しました")
                    st.rerun()
                else:
                    st.error("APIキーの削除に失敗しました")
        else:
            # APIキー入力
            api_key = st.text_input(
                "OpenAI APIキー",
                type="password",
                help="入力すると自動的に暗号化して保存されます",
                key=TestIds.SIDEBAR_API_KEY_INPUT,
            )

            # APIキーが入力されたら保存
            if api_key and api_key.startswith("sk-"):
                if self.presenter.set_api_key(api_key):
                    st.success("✅ APIキーを暗号化保存しました")
                    st.rerun()

    def _mask_api_key(self, api_key: str) -> str:
        """APIキーをマスク表示"""
        if len(api_key) > 8:
            return api_key[:4] + "*" * (len(api_key) - 8) + api_key[-4:]
        return "*" * len(api_key)

    def _render_help_tab(self) -> None:
        """ヘルプタブの内容"""
        st.markdown("#### ❓ ヘルプ")

        st.markdown(
            """
        詳しい使い方はこちら：
    
        📖 **[TextffCutの使い方 - note](https://note.com/coidemo/n/n8250e4b95daa)**
        """
        )
