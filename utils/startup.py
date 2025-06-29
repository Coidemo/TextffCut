"""
アプリケーション起動時の初期化処理

起動時のチェックや初期化処理を管理する。
"""

from pathlib import Path
from typing import Optional, Tuple

import streamlit as st

from utils.environment import IS_DOCKER
from utils.version_helpers import get_app_version
from ui.recovery_components import show_startup_recovery


def run_initial_checks() -> Tuple[bool, str]:
    """
    アプリケーション起動時の初期チェックを実行
    
    以下の処理を実行：
    1. Docker環境の判定
    2. バージョン情報の取得
    3. リカバリチェック（自動リカバリが有効な場合）
    
    Returns:
        Tuple[bool, str]: (Docker環境フラグ, バージョン文字列)
        
    Note:
        リカバリ可能な処理が見つかった場合、st.stop()が呼ばれ、
        この関数は値を返さずに処理が停止される。
    """
    # Docker環境判定
    is_docker = IS_DOCKER
    
    # バージョン情報を取得
    version_file = Path(__file__).parent.parent / "VERSION.txt"
    version = get_app_version(version_file)
    
    # 起動時のリカバリーチェック（自動リカバリーが有効な場合）
    if st.session_state.get("auto_recovery", True) and "startup_recovery_checked" not in st.session_state:
        st.session_state["startup_recovery_checked"] = True
        recoverable = show_startup_recovery()
        if recoverable:
            # リカバリー可能な処理があれば停止
            st.stop()
    
    return is_docker, version


def initialize_session_state() -> None:
    """
    セッション状態の初期化
    
    必要なセッション状態変数を初期化する。
    既に初期化されている変数はスキップする。
    """
    # デフォルト値の定義
    defaults = {
        "auto_recovery": True,
        "processing_state": None,
        "transcription_result": None,
        "edited_text": None,
        "time_ranges": None,
        "video_file_path": None,
    }
    
    # 初期化
    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value


def get_version_info() -> str:
    """
    バージョン情報を取得（簡易版）
    
    Returns:
        str: バージョン文字列
    """
    version_file = Path(__file__).parent.parent / "VERSION.txt"
    return get_app_version(version_file)


def check_environment() -> dict:
    """
    実行環境の情報を取得
    
    Returns:
        dict: 環境情報の辞書
            - is_docker: Docker環境かどうか
            - videos_dir: 動画ディレクトリのパス
            - platform: プラットフォーム情報
    """
    import platform
    from utils.environment import VIDEOS_DIR, IS_DOCKER
    
    return {
        "is_docker": IS_DOCKER,
        "videos_dir": VIDEOS_DIR,
        "platform": platform.system(),
        "python_version": platform.python_version(),
    }