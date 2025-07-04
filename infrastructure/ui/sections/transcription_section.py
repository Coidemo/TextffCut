"""
文字起こしセクション（プレースホルダー）

Phase 1では実装を簡略化し、既存のロジックを呼び出す。
"""

from typing import Any

import streamlit as st


def show_transcription_section(video_path: str) -> Any | None:
    """
    文字起こしセクションを表示（プレースホルダー）

    Args:
        video_path: 動画ファイルパス

    Returns:
        文字起こし結果（なければNone）
    """
    # Phase 1では簡略化
    st.info("文字起こしセクションは移行作業中です。")
    return None
