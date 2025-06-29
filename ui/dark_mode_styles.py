"""
ダークモード対応のスタイル定義
"""


def get_dark_mode_styles() -> str:
    """ダークモード対応のCSSスタイルを返す"""
    return """
    <style>
    /* ライトモードでの緑ハイライトを見やすく */
    @media (prefers-color-scheme: light) {
        /* 緑色ハイライト（マッチした部分）をより見やすく */
        .highlight-match,
        span[style*="background-color: #e6ffe6"] {
            background-color: #28a745 !important;  /* はっきりした緑 */
            color: #ffffff !important;  /* 白文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }
    }

    /* ダークモード検出 */
    @media (prefers-color-scheme: dark) {
        /* ハイライト色の調整 */

        /* 緑色ハイライト（マッチした部分）をより見やすく */
        .highlight-match,
        span[style*="background-color: #e6ffe6"] {
            background-color: #1a4d1a !important;  /* 暗い緑 */
            color: #90ee90 !important;  /* 明るい緑の文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }

        /* 赤色ハイライト（追加文字）をより見やすく */
        .highlight-addition,
        span[style*="background-color: #ffe6e6"] {
            background-color: #4d1a1a !important;  /* 暗い赤 */
            color: #ff9999 !important;  /* 明るい赤の文字 */
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
