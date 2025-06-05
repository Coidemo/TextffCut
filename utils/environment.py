"""
Docker環境用の定数定義
"""
import os

# Docker環境の固定パス
VIDEOS_DIR = "/app/videos"
OUTPUT_DIR = "/app/videos"
LOGS_DIR = "/app/logs"
TEMP_DIR = "/app/temp"

# デフォルト値
# Docker環境では環境変数から取得、なければ/app/videosを使用
# ローカル環境では./videosを使用
if os.path.exists('/.dockerenv'):
    DEFAULT_HOST_PATH = os.getenv('HOST_VIDEOS_PATH', '/app/videos')
else:
    DEFAULT_HOST_PATH = os.path.join(os.getcwd(), 'videos')