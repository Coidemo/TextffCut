"""
ダークモード対応のスタイル定義
"""


def get_dark_mode_styles() -> str:
    """ダークモード対応のCSSスタイルを返す"""
    return """
    <style>
    /* Streamlitのダークモードクラスも考慮 */
    /* ライトモード */
    .main:not(.st-emotion-cache-dark) .highlight-match,
    .main:not(.st-emotion-cache-dark) span[style*="background-color: #e6ffe6"] {
        background-color: #28a745 !important;  /* はっきりした緑 */
        color: #ffffff !important;  /* 白文字 */
        padding: 2px 4px;
        border-radius: 3px;
    }

    /* ダークモード - Streamlitのダークモードクラスとメディアクエリの両方に対応 */
    .st-emotion-cache-dark .highlight-match,
    .st-emotion-cache-dark span[style*="background-color: #e6ffe6"],
    [data-testid="stAppViewContainer"][data-theme="dark"] .highlight-match,
    [data-testid="stAppViewContainer"][data-theme="dark"] span[style*="background-color: #e6ffe6"] {
        background-color: #2d5a2d !important;  /* 見やすい緑背景 */
        color: #b8e7b8 !important;  /* 明るい緑の文字 */
        padding: 2px 4px;
        border-radius: 3px;
    }

    .st-emotion-cache-dark .highlight-addition,
    .st-emotion-cache-dark span[style*="background-color: #ffe6e6"],
    [data-testid="stAppViewContainer"][data-theme="dark"] .highlight-addition,
    [data-testid="stAppViewContainer"][data-theme="dark"] span[style*="background-color: #ffe6e6"] {
        background-color: #5a2d2d !important;  /* 見やすい赤背景 */
        color: #ffb3b3 !important;  /* 明るい赤の文字 */
        padding: 2px 4px;
        border-radius: 3px;
    }

    /* メディアクエリによる検出も残す（フォールバック） */
    @media (prefers-color-scheme: dark) {
        /* 緑色ハイライト（マッチした部分）をより見やすく */
        .highlight-match,
        span[style*="background-color: #e6ffe6"] {
            background-color: #2d5a2d !important;  /* 見やすい緑背景 */
            color: #b8e7b8 !important;  /* 明るい緑の文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }

        /* 赤色ハイライト（追加文字）をより見やすく */
        .highlight-addition,
        span[style*="background-color: #ffe6e6"] {
            background-color: #5a2d2d !important;  /* 見やすい赤背景 */
            color: #ffb3b3 !important;  /* 明るい赤の文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }

        /* ダイアログ内のテキスト表示エリア */
        .edited-text-viewer,
        .diff-viewer,
        div[style*="background-color: #f9f9f9"] {
            background-color: #1e1e1e !important;
            color: #e0e0e0 !important;
            border-color: #444 !important;
        }

    }

    /* 共通のスタイル改善 */
    /* ハイライト表示の改善 */
    div[style*="overflow-y: auto"] span {
        transition: background-color 0.2s ease;
    }

    /* モノスペースフォントの読みやすさ改善 */
    div[style*="font-family: monospace"] {
        font-size: 14px;
        line-height: 1.6;
    }
    </style>
    """


def apply_dark_mode_styles() -> None:
    """ダークモード対応のスタイルを適用"""
    import streamlit as st

    st.markdown(get_dark_mode_styles(), unsafe_allow_html=True)
