#!/usr/bin/env python3
"""
WhisperX mediumモデルとアライメントモデルを事前ダウンロード
Dockerイメージビルド時に実行して、モデルを含める
"""
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_models():
    """mediumモデルと日本語アライメントモデルをダウンロード"""
    try:
        import torch
        import whisperx

        logger.info("=== TextffCut モデルダウンロード開始 ===")
        logger.info("mediumモデル（高速・高精度）と日本語アライメントモデルをダウンロードします")

        # キャッシュディレクトリ確認
        cache_dirs = [
            os.path.expanduser("~/.cache/torch/hub"),
            os.path.expanduser("~/.cache/huggingface"),
            os.path.expanduser("~/.cache/whisperx"),
        ]

        for cache_dir in cache_dirs:
            os.makedirs(cache_dir, exist_ok=True)

        # 1. Whisper mediumモデルをダウンロード
        logger.info("\n1. Whisper mediumモデルをダウンロード中...")
        try:
            import whisper

            model = whisper.load_model("medium", device="cpu", download_root="/home/appuser/.cache/whisper")
            logger.info("✓ Whisper mediumモデル: ダウンロード成功")
            del model
        except Exception as e:
            logger.error(f"✗ Whisper mediumモデル: ダウンロード失敗 - {e}")
            return False

        # 2. 日本語アライメントモデルをダウンロード
        logger.info("\n2. 日本語アライメントモデルをダウンロード中...")
        try:
            model, metadata = whisperx.load_align_model(language_code="ja", device="cpu")
            logger.info("✓ 日本語アライメントモデル: ダウンロード成功")
            del model
            del metadata
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
        except Exception as e:
            logger.error(f"✗ 日本語アライメントモデル: ダウンロード失敗 - {e}")
            return False

        # キャッシュサイズを確認
        total_size = 0
        file_count = 0
        all_cache_dirs = cache_dirs + [os.path.expanduser("~/.cache/whisper")]

        for cache_dir in all_cache_dirs:
            if os.path.exists(cache_dir):
                for dirpath, dirnames, filenames in os.walk(cache_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.exists(fp):
                            total_size += os.path.getsize(fp)
                            file_count += 1

        logger.info("\n=== ダウンロード完了 ===")
        logger.info("✓ Whisper mediumモデル（高速・高精度）")
        logger.info("✓ 日本語アライメントモデル")
        logger.info(f"キャッシュサイズ: {total_size / (1024**3):.2f} GB ({file_count} ファイル)")
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
