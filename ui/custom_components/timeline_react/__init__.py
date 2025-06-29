"""
React製タイムラインエディタのPythonラッパー
"""

import os

import streamlit.components.v1 as components

# 本番環境では False に設定
_DEVELOP_MODE = os.getenv("TEXTFFCUT_COMPONENT_DEV", "false").lower() == "true"

if _DEVELOP_MODE:
    # 開発時はReactの開発サーバーを使用
    _component_func = components.declare_component(
        "timeline_editor_react",
        url="http://localhost:3001",
    )
else:
    # 本番環境ではビルド済みファイルを使用
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    build_dir = os.path.join(parent_dir, "frontend", "build")
    _component_func = components.declare_component("timeline_editor_react", path=build_dir)


def timeline_editor_react(clips_data, key=None):
    """
    React製の高度なタイムラインエディタ

    Args:
        clips_data: クリップデータのリスト
            [{
                "id": "clip_0",
                "start_time": 0.0,
                "end_time": 10.0,
                "waveform": [0.1, 0.2, ...]
            }, ...]
        key: Streamlitコンポーネントのキー

    Returns:
        編集されたクリップデータ（同じ形式）
    """
    component_value = _component_func(clips=clips_data, key=key, default=clips_data)

    return component_value


def is_react_editor_available():
    """React製エディタが利用可能かチェック"""
    if _DEVELOP_MODE:
        # 開発モードでは常に利用可能とする
        return True
    else:
        # ビルド済みファイルの存在をチェック
        parent_dir = os.path.dirname(os.path.abspath(__file__))
        build_dir = os.path.join(parent_dir, "frontend", "build")
        index_path = os.path.join(build_dir, "index.html")
        return os.path.exists(index_path)
