"""
タイムライン編集のダークモード表示を修正
Plotlyグラフを完全に黒背景にする
"""

import streamlit as st


def inject_dark_mode_css() -> None:
    """
    ダークモード用のCSSを注入
    Plotlyグラフの背景を確実に黒くする
    """
    st.markdown(
        """
    <style>
    /* ダークモード時のPlotlyグラフの背景を黒に */
    [data-testid="stAppViewContainer"][data-theme="dark"] .js-plotly-plot .plotly {
        background-color: #0E1117 !important;
    }

    [data-testid="stAppViewContainer"][data-theme="dark"] .js-plotly-plot .main-svg {
        background-color: #0E1117 !important;
    }

    /* Plotlyのモーダルダイアログも黒背景に */
    [data-testid="stAppViewContainer"][data-theme="dark"] .modebar {
        background-color: #262730 !important;
    }

    [data-testid="stAppViewContainer"][data-theme="dark"] .modebar-btn path {
        fill: #FAFAFA !important;
    }

    /* タイムライン編集セクション内のPlotlyグラフ */
    [data-testid="stAppViewContainer"][data-theme="dark"] .stPlotlyChart {
        background-color: transparent !important;
    }

    /* Plotlyのツールチップ */
    [data-testid="stAppViewContainer"][data-theme="dark"] .hoverlayer .hovertext {
        background-color: #262730 !important;
        border-color: #464853 !important;
    }

    [data-testid="stAppViewContainer"][data-theme="dark"] .hoverlayer .hovertext text {
        fill: #FAFAFA !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )
