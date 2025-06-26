from typing import Any

import streamlit as st

from core.waveform_processor import WaveformProcessor
from utils.logging import get_logger

# カスタムコンポーネントのインポートを試みる
try:
    from .custom_components.timeline import timeline_editor
    CUSTOM_COMPONENT_AVAILABLE = True
except Exception as e:
    logger = get_logger(__name__)
    logger.warning(f"カスタムコンポーネントの読み込みに失敗しました: {e}")
    CUSTOM_COMPONENT_AVAILABLE = False

# 静的コンポーネント版をインポート
from .timeline_editor_static import render_timeline_editor_static

logger = get_logger(__name__)


def render_timeline_editor(time_ranges: list[tuple[float, float]], transcription_result: Any, video_path: str) -> None:
    """
    タイムライン編集UI（静的コンポーネント版を使用）

    Args:
        time_ranges: 編集対象の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
    """
    # 静的コンポーネント版を使用
    render_timeline_editor_static(time_ranges, transcription_result, video_path)