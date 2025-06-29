import os
from typing import Any

import streamlit.components.v1 as components

# コンポーネントのビルド成果物が配置されるパスを指定
_RELEASE = True  # 本番環境ではTrueに

if not _RELEASE:
    _component_func = components.declare_component(
        "timeline_editor",
        url="http://localhost:3001",  # 開発用サーバー
    )
else:
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    # buildディレクトリではなくfrontendディレクトリを使用
    build_dir = os.path.join(parent_dir, "frontend")
    _component_func = components.declare_component("timeline_editor", path=build_dir)


def timeline_editor(clips_data: list[dict[str, Any]], key=None):
    """
    インタラクティブなタイムライン編集コンポーネント

    Args:
        clips_data: クリップ情報のリスト
        key: Streamlitコンポーネントのユニークキー

    Returns:
        変更された時間範囲
    """
    component_value = _component_func(clips_data=clips_data, key=key, default=None)  # デフォルトの戻り値
    return component_value
