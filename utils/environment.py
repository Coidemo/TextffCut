"""
環境判定ユーティリティ
Docker環境とローカル環境の判定を一元管理
"""
import os
from typing import Optional
from functools import lru_cache


@lru_cache(maxsize=1)
def is_docker_environment() -> bool:
    """
    Docker環境で実行されているかを判定
    
    Returns:
        bool: Docker環境の場合True、ローカル環境の場合False
    """
    return os.path.exists('/.dockerenv')


@lru_cache(maxsize=1)
def get_environment_type() -> str:
    """
    実行環境のタイプを取得
    
    Returns:
        str: "docker" または "local"
    """
    return "docker" if is_docker_environment() else "local"


def get_videos_directory() -> str:
    """
    動画ディレクトリのパスを取得
    Docker環境とローカル環境で異なるパスを返す
    
    Returns:
        str: 動画ディレクトリのパス
    """
    if is_docker_environment():
        return "/app/videos"
    else:
        # ローカル環境では動画ファイルごとに異なるため、Noneを返す
        return None


def get_default_output_directory(video_path: Optional[str] = None) -> Optional[str]:
    """
    デフォルトの出力ディレクトリを取得
    
    Args:
        video_path: 動画ファイルのパス（ローカル環境で必要）
        
    Returns:
        str: 出力ディレクトリのパス
    """
    if is_docker_environment():
        return "/app/videos"
    elif video_path:
        # ローカル環境では動画と同じディレクトリ
        from pathlib import Path
        return str(Path(video_path).parent)
    else:
        return None


def get_environment_info() -> dict:
    """
    環境情報を辞書形式で取得
    
    Returns:
        dict: 環境情報
    """
    return {
        "type": get_environment_type(),
        "is_docker": is_docker_environment(),
        "videos_dir": get_videos_directory(),
        "platform": os.name,
        "python_version": os.sys.version,
    }