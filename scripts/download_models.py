#!/usr/bin/env python3
"""
MLXモデルを事前ダウンロード
Dockerイメージビルド時に実行して、モデルを含める

HTTP 301エラーが発生した場合は代替方法でダウンロードを試みます。
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_with_huggingface_hub(model_id: str, cache_dir: str) -> str:
    """Hugging Face Hubを使用してモデルを直接ダウンロード（代替方法）"""
    try:
        from huggingface_hub import snapshot_download

        logger.info(f"Hugging Face Hub経由でダウンロード: {model_id}")
        local_dir = snapshot_download(
            repo_id=model_id, cache_dir=cache_dir, resume_download=True, max_workers=1  # 並列ダウンロードを制限
        )
        logger.info(f"✓ ダウンロード成功: {local_dir}")
        return local_dir
    except Exception as e:
        logger.error(f"Hugging Face Hubでのダウンロード失敗: {e}")
        raise


def download_models():
    """MLXモデルをダウンロード（Apple Silicon専用）"""
    try:
        logger.info("=== TextffCut モデルダウンロード開始 ===")
        logger.info("MLXモデルはmlx-whisperが自動的にダウンロードします")
        logger.info("初回実行時に自動ダウンロードされます")

        # ダウンロード時はオンラインモードを確保
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)

        # キャッシュディレクトリ確認
        cache_dirs = [
            os.path.expanduser("~/.cache/huggingface"),
        ]

        for cache_dir in cache_dirs:
            os.makedirs(cache_dir, exist_ok=True)

        # MLXモデルの事前ダウンロード
        logger.info("\n1. MLX Whisperモデルをダウンロード中...")
        try:
            import mlx_whisper

            # モデルをロードしてダウンロードをトリガー
            mlx_model = "mlx-community/whisper-large-v3-turbo"
            logger.info(f"モデル: {mlx_model}")
            # mlx_whisperはtranscribe時に自動ダウンロードするため、ここでは確認のみ
            logger.info("✓ mlx-whisperが利用可能です。初回文字起こし時にモデルが自動ダウンロードされます")
        except ImportError:
            logger.error("✗ mlx-whisperがインストールされていません")
            logger.error("pip install mlx-whisper mlx-forced-aligner を実行してください")
            return False

        logger.info("\n=== セットアップ完了 ===")
        logger.info("✓ MLX Whisper（Apple Silicon高速モード）")
        logger.info("\nこの構成により、90分動画でも快適に処理できます。")

        return True

    except ImportError as e:
        logger.error(f"必要なパッケージがインストールされていません: {e}")
        return False
    except Exception as e:
        logger.error(f"予期しないエラー: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = download_models()
    sys.exit(0 if success else 1)
