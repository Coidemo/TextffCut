"""
アプリケーションヘッダーコンポーネント

タイトル、サブタイトル、バージョン情報などの
ヘッダー部分の表示を管理する。
"""

import streamlit as st

from ui.constants import ICON_SVG


def show_app_title(version: str = "v1.0.0") -> None:
    """
    アプリケーションのタイトルとサブタイトルを表示

    SVGアイコン、タイトル（TextffCut）、バージョン情報、
    サブタイトルを含むヘッダーを表示する。

    Args:
        version: 表示するバージョン文字列

    Note:
        タイトルの"ff"部分は赤色イタリック体で強調表示される。
        バージョンは灰色の小さい文字で表示される。
    """
    # タイトルテキストの構築（元の実装と同じ）
    title_text = (
        f'Text<span style="color: red; font-style: italic;">ff</span>Cut '
        f'<span style="color: #666; font-size: 1rem;">{version}</span>'
    )
    subtitle_text = "動画の文字起こしと切り抜きを効率化するツール"

    # SVGが表示されない場合のフォールバック処理
    try:
        # まずSVGを試す
        st.markdown(
            f'{ICON_SVG}<span style="font-size: 3rem; font-weight: bold; vertical-align: middle;">{title_text}</span>',
            unsafe_allow_html=True,
        )
    except:
        # SVGが表示されない場合は、タイトルのみ表示
        st.markdown(
            f'<span style="font-size: 3rem; font-weight: bold;">{title_text}</span>',
            unsafe_allow_html=True,
        )
    
    # サブタイトル
    st.markdown(
        f'<p style="margin-top: -10px; margin-bottom: 20px; color: #666; font-size: 1.1rem;">{subtitle_text}</p>',
        unsafe_allow_html=True,
    )


def show_simple_title(text: str, icon: str = "") -> None:
    """
    シンプルなタイトルを表示

    Args:
        text: 表示するタイトルテキスト
        icon: オプションのアイコン絵文字

    Examples:
        >>> show_simple_title("設定", "⚙️")
        >>> show_simple_title("処理中...")
    """
    if icon:
        st.markdown(f"# {icon} {text}")
    else:
        st.markdown(f"# {text}")


def show_version_info(version: str, show_details: bool = False) -> None:
    """
    バージョン情報を表示

    Args:
        version: バージョン文字列
        show_details: 詳細情報を表示するかどうか

    Note:
        show_detailsがTrueの場合、ビルド日時やコミットハッシュなど
        の追加情報も表示する（将来の拡張用）。
    """
    st.caption(f"Version: {version}")

    if show_details:
        # 将来の拡張用：ビルド情報などを表示
        pass
