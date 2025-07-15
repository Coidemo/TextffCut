#!/usr/bin/env python3
"""
WhisperX mediumモデルとアライメントモデルを事前ダウンロード（代替版）
HTTP 301エラーを回避するための代替実装
"""
import logging
import os
import sys
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def download_models():
    """mediumモデルと日本語アライメントモデルをダウンロード"""
    try:
        import torch
        
        logger.info("=== TextffCut モデルダウンロード開始（代替版）===")
        logger.info("mediumモデル（高速・高精度）と日本語アライメントモデルをダウンロードします")
        
        # ダウンロード時はオンラインモードを確保
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)

        # キャッシュディレクトリ確認
        cache_dirs = [
            os.path.expanduser("~/.cache/torch/hub"),
            os.path.expanduser("~/.cache/huggingface"),
            os.path.expanduser("~/.cache/whisperx"),
        ]

        for cache_dir in cache_dirs:
            os.makedirs(cache_dir, exist_ok=True)

        # 1. Hugging Face CLIを使用してモデルを直接ダウンロード
        logger.info("\n1. Whisper mediumモデルをダウンロード中（faster-whisper形式）...")
        try:
            # huggingface-hubを使用して直接ダウンロード
            from huggingface_hub import snapshot_download
            
            model_id = "Systran/faster-whisper-medium"
            logger.info(f"モデルID: {model_id}")
            
            # モデルをダウンロード
            local_dir = snapshot_download(
                repo_id=model_id,
                cache_dir="/home/appuser/.cache/huggingface",
                resume_download=True,
                max_workers=1  # 並列ダウンロードを制限
            )
            logger.info(f"✓ Whisper mediumモデル（faster-whisper形式）: ダウンロード成功")
            logger.info(f"  保存先: {local_dir}")
            
        except Exception as e:
            logger.error(f"✗ Whisper mediumモデル: ダウンロード失敗 - {e}")
            # フォールバック: whisperxのインポート時にダウンロード
            logger.info("フォールバック: whisperxインポート時のダウンロードを試行")
            try:
                import whisperx
                # モデルをロードしてダウンロードをトリガー
                model = whisperx.load_model(
                    "medium",
                    device="cpu",
                    compute_type="float32",
                    language="ja",
                    download_root="/home/appuser/.cache"
                )
                del model
                logger.info("✓ フォールバック成功")
            except Exception as fallback_error:
                logger.error(f"✗ フォールバックも失敗: {fallback_error}")
                return False

        # 2. 日本語アライメントモデルをダウンロード
        logger.info("\n2. 日本語アライメントモデルをダウンロード中...")
        try:
            import whisperx
            model, metadata = whisperx.load_align_model(language_code="ja", device="cpu")
            logger.info("✓ 日本語アライメントモデル: ダウンロード成功")
            del model
            del metadata
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
        except Exception as e:
            logger.error(f"✗ 日本語アライメントモデル: ダウンロード失敗 - {e}")
            return False

        # 3. ダウンロードしたモデルの検証
        logger.info("\n3. モデルファイルの存在を確認中...")
        faster_whisper_path = os.path.expanduser("~/.cache/huggingface/hub")
        model_found = False
        
        # faster-whisperモデルの存在確認
        for dirpath, dirnames, filenames in os.walk(faster_whisper_path):
            if "faster-whisper-medium" in dirpath:
                model_files = [f for f in filenames if f.endswith(('.bin', '.txt', '.json'))]
                if model_files:
                    logger.info(f"✓ faster-whisperモデルファイルを確認: {len(model_files)}個のファイル")
                    model_found = True
                    break
        
        if not model_found:
            logger.warning("⚠️  faster-whisperモデルファイルが見つかりません")

        # キャッシュサイズを確認
        total_size = 0
        file_count = 0
        all_cache_dirs = cache_dirs

        for cache_dir in all_cache_dirs:
            if os.path.exists(cache_dir):
                for dirpath, _, filenames in os.walk(cache_dir):
                    for f in filenames:
                        fp = os.path.join(dirpath, f)
                        if os.path.exists(fp):
                            total_size += os.path.getsize(fp)
                            file_count += 1

        logger.info("\n=== ダウンロード完了 ===")
        logger.info("✓ Whisper mediumモデル（faster-whisper形式）")
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