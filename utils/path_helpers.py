"""
パス関連のヘルパー関数

ファイルパスの表示用変換など、パス操作に関するユーティリティ関数を提供。
"""

import os
from pathlib import Path

from utils.environment import IS_DOCKER, VIDEOS_DIR


def get_display_path(file_path: str | Path) -> str:
    """
    ファイルパスを表示用に変換

    Docker環境では、コンテナ内のパスをホストのパスに変換して表示する。
    これにより、ユーザーは自分の環境でのパスを確認できる。

    Args:
        file_path: 実際のファイルパス

    Returns:
        表示用のパス

    Examples:
        >>> # Docker環境の場合
        >>> get_display_path("/app/videos/sample.mp4")
        "/Users/username/project/videos/sample.mp4"

        >>> # ローカル環境の場合
        >>> get_display_path("/Users/username/project/videos/sample.mp4")
        "/Users/username/project/videos/sample.mp4"
    """
    if IS_DOCKER:
        # Docker環境：ホストパスに変換
        host_base = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "/app") + "/videos")
        # /app/videos/xxx を host_path/xxx に変換
        relative_path = str(file_path).replace(VIDEOS_DIR + "/", "")
        if relative_path == str(file_path):
            # VIDEOS_DIR以外のパスの場合はそのまま返す
            return str(file_path)
        return os.path.join(host_base, relative_path)
    else:
        # ローカル環境：そのまま返す
        return str(file_path)


def get_relative_path(file_path: str | Path, base_path: str | Path | None = None) -> str:
    """
    ファイルパスを相対パスに変換

    Args:
        file_path: 変換するファイルパス
        base_path: 基準となるパス（デフォルトはVIDEOS_DIR）

    Returns:
        相対パス文字列
    """
    file_path = Path(file_path)
    base_path = Path(base_path) if base_path else Path(VIDEOS_DIR)

    try:
        return str(file_path.relative_to(base_path))
    except ValueError:
        # 相対パスに変換できない場合は元のパスを返す
        return str(file_path)


def ensure_absolute_path(file_path: str | Path) -> Path:
    """
    パスを絶対パスに変換

    Args:
        file_path: 変換するファイルパス

    Returns:
        絶対パスのPathオブジェクト
    """
    path = Path(file_path)
    if not path.is_absolute():
        # Docker環境とローカル環境で基準を変える
        if IS_DOCKER:
            return Path("/app") / path
        else:
            return path.resolve()
    return path
