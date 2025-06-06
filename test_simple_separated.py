#!/usr/bin/env python
"""
簡単な分離モード動作確認テスト
"""

import os
import sys
import psutil

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)


def test_config():
    """設定の確認"""
    config = Config()
    
    logger.info("=== 設定確認 ===")
    logger.info(f"local_align_chunk_seconds: {config.transcription.local_align_chunk_seconds}")
    logger.info(f"force_separated_mode: {config.transcription.force_separated_mode}")
    logger.info(f"chunk_seconds: {config.transcription.chunk_seconds}")
    
    # 設定を変更してみる
    config.transcription.force_separated_mode = True
    config.transcription.local_align_chunk_seconds = 120
    
    logger.info("\n=== 設定変更後 ===")
    logger.info(f"local_align_chunk_seconds: {config.transcription.local_align_chunk_seconds}")
    logger.info(f"force_separated_mode: {config.transcription.force_separated_mode}")


def test_memory_detection():
    """メモリ検出の確認"""
    logger.info("\n=== メモリ検出 ===")
    
    mem_gb = psutil.virtual_memory().total / (1024**3)
    available_gb = psutil.virtual_memory().available / (1024**3)
    
    logger.info(f"総メモリ: {mem_gb:.1f}GB")
    logger.info(f"利用可能メモリ: {available_gb:.1f}GB")
    
    # 分離モード判定
    should_separate = available_gb < 6
    logger.info(f"分離モード推奨: {should_separate}")


def test_transcription_import():
    """文字起こしモジュールのインポート確認"""
    logger.info("\n=== Transcriptionモジュール確認 ===")
    
    try:
        from core.transcription import Transcriber
        logger.info("✓ Transcriber インポート成功")
        
        # skip_alignmentパラメータの確認
        import inspect
        sig = inspect.signature(Transcriber.transcribe)
        params = list(sig.parameters.keys())
        
        if 'skip_alignment' in params:
            logger.info("✓ skip_alignmentパラメータが存在")
        else:
            logger.error("✗ skip_alignmentパラメータが見つかりません")
            
    except Exception as e:
        logger.error(f"✗ インポートエラー: {e}")


def test_alignment_processor():
    """アライメントプロセッサーの確認"""
    logger.info("\n=== AlignmentProcessor確認 ===")
    
    try:
        from core.alignment_processor import AlignmentProcessor
        logger.info("✓ AlignmentProcessor インポート成功")
        
        config = Config()
        processor = AlignmentProcessor(config)
        logger.info("✓ AlignmentProcessor インスタンス化成功")
        
        # メソッドの確認
        if hasattr(processor, 'align'):
            logger.info("✓ alignメソッドが存在")
        if hasattr(processor, 'estimate_timestamps'):
            logger.info("✓ estimate_timestampsメソッドが存在")
            
    except Exception as e:
        logger.error(f"✗ エラー: {e}")


def main():
    """メイン処理"""
    logger.info("分離モード動作確認テスト開始\n")
    
    test_config()
    test_memory_detection()
    test_transcription_import()
    test_alignment_processor()
    
    logger.info("\n動作確認テスト完了")


if __name__ == "__main__":
    main()