#!/usr/bin/env python
"""
サブプロセス分離のテストスクリプト
"""

import os
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from core.transcription_subprocess import SubprocessTranscriber
from utils.logging import logger


def main():
    """テストメイン処理"""
    # テスト用ビデオファイル
    test_video = "videos/30.1.mp4"  # より短い動画でテスト
    
    if not os.path.exists(test_video):
        logger.error(f"テストビデオが見つかりません: {test_video}")
        return
    
    # 分離モードを強制的にsubprocessに設定
    config.transcription.isolation_mode = "subprocess"
    
    # TranscriberをAPIモードで初期化（WhisperXを避けるため）
    config.transcription.use_api = False
    config.transcription.model_size = "base"
    
    logger.info(f"サブプロセス分離モードのテストを開始: {config.transcription.isolation_mode}")
    
    # Transcriberを作成
    transcriber = SubprocessTranscriber(config)
    
    # プログレスコールバック
    def progress_callback(progress: float, message: str):
        print(f"[{progress:.1%}] {message}")
    
    # 文字起こし実行
    logger.info(f"文字起こしを実行: {test_video}")
    
    try:
        result = transcriber.transcribe(
            test_video,
            model_size="base",
            progress_callback=progress_callback,
            use_cache=False,
            save_cache=False
        )
        
        logger.info(f"文字起こし完了: {len(result.segments)}セグメント")
        
        # 結果を表示
        print("\n=== 文字起こし結果 ===")
        for i, segment in enumerate(result.segments[:5]):  # 最初の5セグメントを表示
            print(f"{i+1}. [{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}")
        
        if len(result.segments) > 5:
            print(f"... 他 {len(result.segments) - 5} セグメント")
        
        print(f"\n処理時間: {result.processing_time:.1f}秒")
        
        # メモリ使用量を確認
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            print(f"親プロセスのメモリ使用量: {mem_mb:.1f}MB")
        except:
            pass
        
    except Exception as e:
        logger.error(f"テスト失敗: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()