#!/usr/bin/env python3
"""
WhisperXモデルを事前に読み込むスクリプト

アプリケーション起動前にこのスクリプトを実行することで、
初回の文字起こし時のモデル読み込み時間を短縮できます。
"""

import logging
import os
import sys
import time
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def preload_whisperx_models():
    """WhisperXモデルを事前に読み込む"""
    try:
        logger.info("WhisperXモデルの事前読み込みを開始します...")
        
        # WhisperXをインポート
        import whisperx
        import torch
        
        # デバイスを決定
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"
        logger.info(f"使用デバイス: {device}, compute_type: {compute_type}")
        
        # モデルサイズ
        model_size = "medium"
        logger.info(f"モデルサイズ: {model_size}")
        
        # 音声認識モデルを読み込み
        start_time = time.time()
        logger.info("音声認識モデルを読み込み中...")
        
        model = whisperx.load_model(
            model_size,
            device=device,
            compute_type=compute_type,
            language="ja"
        )
        
        load_time = time.time() - start_time
        logger.info(f"音声認識モデルの読み込み完了 (所要時間: {load_time:.2f}秒)")
        
        # アライメントモデルも読み込み
        start_time = time.time()
        logger.info("アライメントモデルを読み込み中...")
        
        align_model, align_metadata = whisperx.load_align_model(
            language_code="ja",
            device=device
        )
        
        align_time = time.time() - start_time
        logger.info(f"アライメントモデルの読み込み完了 (所要時間: {align_time:.2f}秒)")
        
        # メモリ使用量を表示
        if device == "cuda":
            gpu_memory = torch.cuda.memory_allocated() / 1024**3
            logger.info(f"GPU メモリ使用量: {gpu_memory:.2f} GB")
        
        logger.info(f"モデルの事前読み込みが完了しました (合計時間: {load_time + align_time:.2f}秒)")
        
        # モデルを削除してメモリを解放
        del model
        del align_model
        if device == "cuda":
            torch.cuda.empty_cache()
        
        return True
        
    except ImportError as e:
        logger.error(f"WhisperXがインストールされていません: {e}")
        logger.info("pip install whisperx でインストールしてください")
        return False
        
    except Exception as e:
        logger.error(f"モデルの読み込みに失敗しました: {e}")
        return False

def check_model_cache():
    """モデルキャッシュの状態を確認"""
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    
    if cache_dir.exists():
        # キャッシュサイズを計算
        total_size = 0
        for file in cache_dir.rglob("*"):
            if file.is_file():
                total_size += file.stat().st_size
        
        size_gb = total_size / (1024**3)
        logger.info(f"Huggingfaceキャッシュディレクトリ: {cache_dir}")
        logger.info(f"キャッシュサイズ: {size_gb:.2f} GB")
        
        # faster-whisperモデルをチェック
        whisper_models = list(cache_dir.glob("models--Systran--faster-whisper-*"))
        if whisper_models:
            logger.info(f"キャッシュ済みWhisperモデル: {len(whisper_models)}個")
            for model in whisper_models:
                logger.info(f"  - {model.name}")
    else:
        logger.info("Huggingfaceキャッシュディレクトリが存在しません")

if __name__ == "__main__":
    logger.info("=== WhisperXモデル事前読み込みツール ===")
    
    # キャッシュ状態を確認
    check_model_cache()
    
    # モデルを事前読み込み
    if preload_whisperx_models():
        logger.info("✅ モデルの事前読み込みが正常に完了しました")
        logger.info("アプリケーションを起動すると、初回の文字起こしが高速に開始されます")
    else:
        logger.error("❌ モデルの事前読み込みに失敗しました")
        sys.exit(1)