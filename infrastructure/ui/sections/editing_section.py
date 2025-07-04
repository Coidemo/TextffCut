"""
編集セクション（プレースホルダー）

Phase 1では実装を簡略化し、既存のロジックを呼び出す。
"""

from typing import Any

import streamlit as st


def show_editing_section(transcription_result: Any) -> tuple[str | None, list[tuple[float, float]] | None]:
    """
    編集セクションを表示（プレースホルダー）

    Args:
        transcription_result: 文字起こし結果

    Returns:
        編集されたテキストと時間範囲のタプル
    """
    # Phase 1では簡略化
    st.info("編集セクションは移行作業中です。")
    return None, None
