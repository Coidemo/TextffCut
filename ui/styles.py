"""
UIスタイル定義

アプリケーション全体のCSSスタイルを管理。
フォントサイズ、レイアウト、ダークモード対応などの
スタイル定義を一元化する。
"""


def get_custom_css() -> str:
    """
    カスタムCSSスタイルを取得
    
    アプリケーション全体に適用されるCSSスタイルを返す。
    フォントサイズの調整、サイドバーのスタイル、
    画像表示の最適化などを含む。
    
    Returns:
        str: CSSスタイル文字列
        
    Note:
        このCSSはStreamlitのmarkdownで直接適用される。
        st.markdown(get_custom_css(), unsafe_allow_html=True)
        の形式で使用する。
    """
    return """
<style>
    /* 全体的なフォントサイズを小さく */
    .stApp {
        font-size: 14px;
    }

    /* 見出しのサイズ調整 */
    h1 {
        font-size: 2rem !important;
    }
    h2 {
        font-size: 1.5rem !important;
    }
    h3 {
        font-size: 1.25rem !important;
    }
    h4 {
        font-size: 1.1rem !important;
    }

    /* テキスト入力やセレクトボックスのフォントサイズ */
    .stSelectbox > div > div {
        font-size: 14px !important;
    }

    /* ボタンのフォントサイズ */
    .stButton > button {
        font-size: 14px !important;
    }

    /* キャプションのフォントサイズ */
    .caption {
        font-size: 12px !important;
    }

    /* サイドバーのフォントサイズ調整 */
    .sidebar .sidebar-content {
        font-size: 14px !important;
    }

    /* サイドバーの見出し */
    .sidebar h1, .sidebar h2, .sidebar h3, .sidebar h4 {
        font-size: 1rem !important;
    }

    /* サイドバーのボタン */
    .sidebar .stButton > button {
        font-size: 13px !important;
    }

    /* サイドバーのタブ */
    .sidebar .stTabs [data-baseweb="tab-list"] button {
        font-size: 13px !important;
    }

    /* サイドバーのセレクトボックス */
    .sidebar .stSelectbox {
        font-size: 13px !important;
    }

    /* 画像の表示品質を向上 */
    img {
        image-rendering: auto;
        image-rendering: -webkit-optimize-contrast;
        max-width: 100%;
        height: auto;
    }
</style>
"""


def get_font_sizes() -> dict[str, str]:
    """
    フォントサイズの設定を辞書形式で取得
    
    Returns:
        dict[str, str]: 要素名とフォントサイズのマッピング
        
    Examples:
        >>> sizes = get_font_sizes()
        >>> print(sizes["h1"])
        "2rem"
    """
    return {
        "body": "14px",
        "h1": "2rem",
        "h2": "1.5rem",
        "h3": "1.25rem",
        "h4": "1.1rem",
        "button": "14px",
        "caption": "12px",
        "sidebar": "13px",
    }


def get_image_optimization_css() -> str:
    """
    画像表示最適化用のCSSを取得
    
    Returns:
        str: 画像最適化用のCSSスタイル
    """
    return """
    img {
        image-rendering: auto;
        image-rendering: -webkit-optimize-contrast;
        max-width: 100%;
        height: auto;
    }
    """