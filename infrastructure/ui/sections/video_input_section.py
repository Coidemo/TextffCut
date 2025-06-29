"""
動画入力セクション

既存のshow_video_input関数をラップして、
セッション状態管理を改善する。
"""

import streamlit as st
from typing import Optional

from ui import show_video_input as legacy_show_video_input
from infrastructure.ui.session_manager import get_session_manager


def show_video_input_section() -> Optional[str]:
    """
    動画入力セクションを表示
    
    Returns:
        選択された動画のパス（なければNone）
    """
    # セッション管理
    session = get_session_manager()
    
    # 既存の動画入力UIを使用
    video_path = legacy_show_video_input()
    
    # 動画が変更された場合の処理
    if video_path and video_path != session.get_video_path():
        # 動画が変更されたら、関連する状態をクリア
        _handle_video_change(video_path, session)
    
    return video_path


def _handle_video_change(video_path: str, session):
    """動画変更時の処理（main.pyのロジックを移植）"""
    # 既存のmain.pyと同じクリア処理
    session_keys_to_clear = [
        "transcription_result",
        "edited_text",
        "original_edited_text",
        "show_modal",
        "show_error_and_delete",
        "transcription_confirmed",
        "should_run_transcription",
        "show_confirmation_modal",
        "confirmation_info",
        "last_modal_settings",
        "modal_dismissed",
        "modal_button_pressed",
        "transcription_in_progress",
        "cancel_transcription",
        "previous_transcription_mode",
        "previous_transcription_model",
    ]
    
    for key in session_keys_to_clear:
        session.delete(key)
    
    # 新しい動画パスを設定
    session.set_video_path(video_path)
    # session.set_video_pathが両方のキーを設定するので、以下は不要
    # session.set("current_video_path", video_path)
    # session.set("video_path", video_path)