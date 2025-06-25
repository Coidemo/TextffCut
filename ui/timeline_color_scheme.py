"""
タイムライン編集UIのカラースキーム管理
ダークモードとライトモードの両方に対応
"""

import streamlit as st


class TimelineColorScheme:
    """タイムライン編集のカラースキーム"""

    @staticmethod
    def get_colors(is_dark_mode: bool = None) -> dict:
        """
        ダークモード状態に応じたカラースキームを返す

        Args:
            is_dark_mode: ダークモードかどうか。Noneの場合は自動検出

        Returns:
            カラースキームの辞書
        """
        if is_dark_mode is None:
            is_dark_mode = TimelineColorScheme.is_dark_mode()

        if is_dark_mode:
            return {
                # 波形表示
                "waveform_positive": "#26C6DA",  # より明るいシアン
                "waveform_negative": "#26C6DA",  # より明るいシアン
                "waveform_silence": "#37474F",  # より暗いグレー（コントラスト向上）
                # タイムライン
                "segment_active": "#64B5F6",  # 明るい青
                "segment_inactive": "#37474F",  # ミディアムグレー
                "segment_hover": "#90CAF9",  # より明るい青
                # 境界・マーカー
                "boundary_marker": "#FFB74D",  # 明るいオレンジ
                "playhead": "#FF5252",  # 明るい赤
                # 背景・グリッド
                "background": "#0E1117",  # Streamlitダークモードの背景色
                "grid_lines": "#31333F",  # より暗いグリッド線
                "grid_major": "#464853",  # グリッド主線
                # テキスト
                "text_primary": "#ECEFF1",  # 明るいグレー
                "text_secondary": "#B0BEC5",  # ミディアムグレー
                # ハイライト・選択
                "selection_bg": "rgba(100, 181, 246, 0.2)",  # 半透明の青
                "hover_bg": "rgba(255, 183, 77, 0.1)",  # 半透明のオレンジ
                # Plotlyレイアウト
                "plotly_template": "plotly_dark",
            }
        else:
            # ライトモードのカラースキーム
            return {
                "waveform_positive": "#4CAF50",
                "waveform_negative": "#2196F3",
                "waveform_silence": "#9E9E9E",
                "segment_active": "#2196F3",
                "segment_inactive": "#E0E0E0",
                "segment_hover": "#42A5F5",
                "boundary_marker": "#FF9800",
                "playhead": "#F44336",
                "background": "#FAFAFA",
                "grid_lines": "#E0E0E0",
                "grid_major": "#BDBDBD",
                "text_primary": "#212121",
                "text_secondary": "#757575",
                "selection_bg": "rgba(33, 150, 243, 0.1)",
                "hover_bg": "rgba(255, 152, 0, 0.1)",
                "plotly_template": "plotly_white",
            }

    @staticmethod
    def is_dark_mode() -> bool:
        """
        現在のテーマがダークモードかどうかを検出

        Returns:
            ダークモードの場合True
        """
        # セッション状態で明示的に指定されている場合
        if "dark_mode" in st.session_state:
            return st.session_state.dark_mode

        # Streamlitの暗黙的なテーマ判定
        # dark_mode_styles.pyで使用されているのと同じ判定方法を使用
        try:
            # theme.baseの設定を確認
            theme_base = st.get_option("theme.base")
            return theme_base == "dark"
        except:
            # エラーの場合はデフォルトでライトモード
            return False

    @staticmethod
    def apply_plotly_theme(fig, is_dark_mode: bool = None):
        """
        Plotlyグラフにダークモードテーマを適用

        Args:
            fig: Plotly Figure オブジェクト
            is_dark_mode: ダークモードかどうか。Noneの場合は自動検出

        Returns:
            テーマが適用されたFigureオブジェクト
        """
        colors = TimelineColorScheme.get_colors(is_dark_mode)

        # レイアウトの更新
        layout_update = dict(
            plot_bgcolor=colors["background"],
            paper_bgcolor=colors["background"],
            font=dict(color=colors["text_primary"]),
            xaxis=dict(
                gridcolor=colors["grid_lines"],
                linecolor=colors["grid_major"],
                tickcolor=colors["text_secondary"],
                tickfont=dict(color=colors["text_secondary"]),
                zerolinecolor=colors["grid_major"],
            ),
            yaxis=dict(
                gridcolor=colors["grid_lines"],
                linecolor=colors["grid_major"],
                tickcolor=colors["text_secondary"],
                tickfont=dict(color=colors["text_secondary"]),
                zerolinecolor=colors["grid_major"],
            ),
        )

        # テンプレートを使わず、直接色を設定
        # Plotlyのテンプレートはグラフエリア外の背景色を変更しないことがある
        fig.update_layout(**layout_update)

        return fig
