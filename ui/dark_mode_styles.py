"""
ダークモード対応のスタイル定義
"""


def get_dark_mode_styles() -> str:
    """テーマに応じたCSSスタイルを返す（v0.9.6のアプローチとThemeDetectorを併用）"""
    return """
    <style>
    /* インラインスタイルのハイライトを上書きするため、属性セレクタを使用 */
    /* ライトモードでの緑ハイライトを見やすく */
    @media (prefers-color-scheme: light) {
        /* 緑色ハイライト（マッチした部分）をより見やすく */
        .stApp .highlight-match,
        .stApp span.highlight-match,
        .stApp span[style*="background-color: #e6ffe6"] {
            background-color: #28a745;  /* はっきりした緑 */
            color: #ffffff;  /* 白文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        /* インラインスタイルを持つ要素に対してより高い特異性 */
        .stApp div[style*="overflow"] span[style*="background-color: #e6ffe6"] {
            background-color: #28a745 !important;  /* この場合のみ!important使用 */
            color: #ffffff !important;
        }
    }
    
    /* ダークモード検出 */
    @media (prefers-color-scheme: dark) {
        /* ハイライト色の調整 */
        
        /* 緑色ハイライト（マッチした部分）をより見やすく */
        .stApp .highlight-match,
        .stApp span.highlight-match,
        .stApp span[style*="background-color: #e6ffe6"] {
            background-color: #1a4d1a;  /* 暗い緑 */
            color: #90ee90;  /* 明るい緑の文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        /* 赤色ハイライト（追加文字）をより見やすく */
        .stApp .highlight-addition,
        .stApp span.highlight-addition,
        .stApp span[style*="background-color: #ffe6e6"] {
            background-color: #4d1a1a;  /* 暗い赤 */
            color: #ff9999;  /* 明るい赤の文字 */
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        /* ダイアログ内のテキスト表示エリア - より具体的なセレクタ */
        .stApp .edited-text-viewer,
        .stApp .diff-viewer,
        .stApp div.edited-text-viewer,
        .stApp div.diff-viewer {
            background-color: #1e1e1e;
            color: #e0e0e0;
            border-color: #444;
        }
        
        /* インラインスタイルを持つダイアログ要素 */
        .stApp div[style*="background-color: #f9f9f9"] {
            background-color: #1e1e1e !important;  /* インラインスタイルの上書きに必要 */
            color: #e0e0e0 !important;
            border-color: #444 !important;
        }
    }
    
    /* 共通のスタイル改善 */
    /* ハイライト表示の改善 */
    .stApp div[style*="overflow-y: auto"] span,
    .stApp div[style*="overflow"] span {
        transition: background-color 0.2s ease;
    }
    
    /* モノスペースフォントの読みやすさ改善 */
    .stApp div[style*="font-family: monospace"],
    .stApp pre,
    .stApp code {
        font-size: 14px;
        line-height: 1.6;
    }
    </style>
    """


def apply_dark_mode_styles() -> None:
    """ダークモード対応のスタイルを適用"""
    import streamlit as st

    st.markdown(get_dark_mode_styles(), unsafe_allow_html=True)
