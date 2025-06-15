#!/usr/bin/env python3
"""
WhisperX mediumモデルとアライメントモデルを事前ダウンロード
Dockerイメージビルド時に実行して、モデルを含める
"""
import os
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def download_models():
    """mediumモデルと日本語アライメントモデルをダウンロード"""
    try:
        import whisperx
        import torch
        
        logger.info("=== TextffCut モデルダウンロード開始 ===")
        logger.info("mediumモデル（高速・高精度）と日本語アライメントモデルをダウンロードします")
        
        # 環境変数を設定（HuggingFaceのキャッシュディレクトリを指定）
        os.environ['HF_HOME'] = '/home/appuser/.cache/huggingface'
        os.environ['TRANSFORMERS_CACHE'] = '/home/appuser/.cache/huggingface'
        os.environ['HF_DATASETS_CACHE'] = '/home/appuser/.cache/huggingface/datasets'
        os.environ['TORCH_HOME'] = '/home/appuser/.cache/torch'
        # WhisperX用の環境変数も設定
        os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
        
        logger.info(f"HF_HOME: {os.environ['HF_HOME']}")
        logger.info(f"TRANSFORMERS_CACHE: {os.environ['TRANSFORMERS_CACHE']}")
        
        # キャッシュディレクトリ確認
        cache_dirs = [
            "/home/appuser/.cache/torch/hub",
            "/home/appuser/.cache/huggingface",
            "/home/appuser/.cache/huggingface/hub",
            "/home/appuser/.cache/whisperx",
            "/home/appuser/.cache/whisper",
        ]
        
        for cache_dir in cache_dirs:
            os.makedirs(cache_dir, exist_ok=True)
            logger.info(f"キャッシュディレクトリ作成: {cache_dir}")
        
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
            # transformersのロギングを有効化
            import transformers
            transformers.logging.set_verbosity_info()
            
            logger.info(f"HF_HOME環境変数: {os.environ.get('HF_HOME', '未設定')}")
            logger.info(f"TRANSFORMERS_CACHE環境変数: {os.environ.get('TRANSFORMERS_CACHE', '未設定')}")
            
            # WhisperXがモデルをダウンロードする前にキャッシュディレクトリを確認
            cache_dir = "/home/appuser/.cache/huggingface/hub"
            logger.info(f"アライメントモデルのキャッシュディレクトリ: {cache_dir}")
            
            model, metadata = whisperx.load_align_model(
                language_code="ja",
                device="cpu"
            )
            logger.info("✓ 日本語アライメントモデル: ダウンロード成功")
            
            # ダウンロードされたファイルを確認
            logger.info("\n=== アライメントモデルファイル確認 ===")
            if os.path.exists(cache_dir):
                for root, dirs, files in os.walk(cache_dir):
                    for file in files:
                        if file.endswith(('.bin', '.safetensors')):
                            file_path = os.path.join(root, file)
                            file_size = os.path.getsize(file_path) / (1024**3)
                            logger.info(f"  - {file}: {file_size:.2f} GB")
            
            del model
            del metadata
            torch.cuda.empty_cache() if torch.cuda.is_available() else None
        except Exception as e:
            logger.error(f"✗ 日本語アライメントモデル: ダウンロード失敗 - {e}")
            import traceback
            traceback.print_exc()
            return False
        
        # キャッシュサイズを確認（詳細表示）
        total_size = 0
        file_count = 0
        model_files = []
        
        for cache_dir in cache_dirs:
            if os.path.exists(cache_dir):
                logger.info(f"\nキャッシュディレクトリ: {cache_dir}")
                for dirpath, dirnames, filenames in os.walk(cache_dir):
                    for f in filenames:
                        if f.endswith(('.bin', '.pt', '.safetensors', '.json')):
                            fp = os.path.join(dirpath, f)
                            if os.path.exists(fp):
                                file_size = os.path.getsize(fp)
                                total_size += file_size
                                file_count += 1
                                # 重要なモデルファイルのみ表示
                                if file_size > 100 * 1024 * 1024:  # 100MB以上
                                    model_files.append(f"  - {f}: {file_size / (1024**3):.2f} GB")
        
        # モデルファイルを表示
        if model_files:
            logger.info("\n=== ダウンロードされたモデルファイル ===")
            for mf in model_files:
                logger.info(mf)
        
        logger.info("\n=== ダウンロード完了 ===")
        logger.info(f"✓ Whisper mediumモデル（高速・高精度）")
        logger.info(f"✓ 日本語アライメントモデル")
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