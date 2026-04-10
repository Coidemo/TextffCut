"""
Docker/ローカル環境統一のパス定義
"""

import os
import platform
from pathlib import Path

# 環境判定
IS_DOCKER = os.path.exists("/.dockerenv")
IS_APPLE_SILICON = platform.system() == "Darwin" and platform.machine() == "arm64"


def _check_mlx_whisper() -> bool:
    """mlx-whisperが利用可能か判定"""
    if IS_DOCKER or not IS_APPLE_SILICON:
        return False
    try:
        import mlx_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _check_mlx_aligner() -> bool:
    """mlx-forced-alignerが利用可能か判定"""
    if IS_DOCKER or not IS_APPLE_SILICON:
        return False
    try:
        from mlx_forced_aligner import ForcedAligner  # noqa: F401

        return True
    except ImportError:
        return False


MLX_WHISPER_AVAILABLE = _check_mlx_whisper()
MLX_ALIGNER_AVAILABLE = _check_mlx_aligner()
MLX_AVAILABLE = MLX_WHISPER_AVAILABLE and MLX_ALIGNER_AVAILABLE

# 基準パスの設定
if IS_DOCKER:
    # Docker環境の固定パス
    VIDEOS_DIR = "/app/videos"
    OUTPUT_DIR = "/app/videos"
    LOGS_DIR = "/app/logs"
    TEMP_DIR = "/app/temp"
    CACHE_DIR = "/app/cache"
else:
    # ローカル環境の相対パス
    BASE_DIR = os.getcwd()
    VIDEOS_DIR = os.path.join(BASE_DIR, "videos")
    OUTPUT_DIR = os.path.join(BASE_DIR, "videos")
    LOGS_DIR = os.path.join(BASE_DIR, "logs")
    TEMP_DIR = os.path.join(BASE_DIR, "temp")
    CACHE_DIR = os.path.join(BASE_DIR, "cache")

# ホストパス表示用（Docker環境の場合は環境変数から取得）
if IS_DOCKER:
    DEFAULT_HOST_PATH = os.getenv("HOST_VIDEOS_PATH", "/app/videos")
else:
    DEFAULT_HOST_PATH = os.path.join(os.getcwd(), "videos")


def ensure_directories() -> None:
    """必要なディレクトリを作成"""
    for dir_path in [VIDEOS_DIR, LOGS_DIR, TEMP_DIR, CACHE_DIR]:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
