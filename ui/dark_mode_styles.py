"""
ダークモード対応のスタイル定義
"""


def get_dark_mode_styles() -> str:
    """テーマに応じたCSSスタイルを返す"""
    from utils.theme_detector import ThemeDetector
    
    is_dark = ThemeDetector.is_dark_mode()
    
    if is_dark:
        # ダークモード用スタイル
        return """
        <style>
        /* ダークモード用スタイル */
        .highlight-match,
        span[style*="background-color: #e6ffe6"] {
            background-color: #2d5a2d !important;
            color: #b8e7b8 !important;
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        .highlight-addition,
        span[style*="background-color: #ffe6e6"] {
            background-color: #5a2d2d !important;
            color: #ffb3b3 !important;
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
        
        /* モノスペースフォントの読みやすさ改善 */
        div[style*="font-family: monospace"] {
            font-size: 14px;
            line-height: 1.6;
        }
        </style>
        """
    else:
        # ライトモード用スタイル
        return """
        <style>
        /* ライトモード用スタイル */
        .highlight-match,
        span[style*="background-color: #e6ffe6"] {
            background-color: #28a745 !important;
            color: #ffffff !important;
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        .highlight-addition,
        span[style*="background-color: #ffe6e6"] {
            background-color: #dc3545 !important;
            color: #ffffff !important;
            padding: 2px 4px;
            border-radius: 3px;
        }
        
        /* ダイアログ内のテキスト表示エリア */
        .edited-text-viewer,
        .diff-viewer,
        div[style*="background-color: #f9f9f9"] {
            background-color: #f9f9f9 !important;
            color: #262730 !important;
            border-color: #ddd !important;
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
