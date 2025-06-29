"""
デバッグ用ヘルパー関数

開発時のデバッグやログ出力を支援するユーティリティ関数を提供。
"""

from typing import Any

from utils.logging import get_logger


def debug_words_status(result: Any, logger_name: str = __name__) -> None:
    """
    wordsフィールドの状態を詳細に出力（デバッグ用）
    
    文字起こし結果のセグメントに含まれるwordsフィールドの状態を
    ログに出力する。単語レベルのタイムスタンプが正しく取得できているか
    確認するために使用。
    
    Args:
        result: 文字起こし結果オブジェクト（segmentsフィールドを持つ）
        logger_name: ログ出力に使用するロガー名（デフォルトは現在のモジュール名）
        
    Examples:
        >>> from core.transcription import TranscriptionResult
        >>> result = transcriber.transcribe(video_path)
        >>> debug_words_status(result)
        Words状態: 45/50 セグメント
          セグメント0: 15words - こんにちは、今日は...
          セグメント1: 20words - 天気がいいですね...
          セグメント2: wordsなし! - えーと、その...
    """
    logger = get_logger(logger_name)
    
    if hasattr(result, "segments"):
        total_segments = len(result.segments)
        segments_with_words = sum(1 for seg in result.segments if hasattr(seg, "words") and seg.words)
        logger.info(f"Words状態: {segments_with_words}/{total_segments} セグメント")
        
        # 最初の数セグメントの詳細
        for i, seg in enumerate(result.segments[:3]):
            if hasattr(seg, "words") and seg.words:
                logger.info(f"  セグメント{i}: {len(seg.words)}words - {seg.text[:30]}...")
            else:
                logger.warning(f"  セグメント{i}: wordsなし! - {seg.text[:30]}...")
    else:
        logger.warning("結果オブジェクトにsegmentsフィールドがありません")


def debug_memory_usage(logger_name: str = __name__) -> None:
    """
    現在のメモリ使用状況をログに出力
    
    Args:
        logger_name: ログ出力に使用するロガー名
    """
    import psutil
    
    logger = get_logger(logger_name)
    
    process = psutil.Process()
    memory_info = process.memory_info()
    memory_mb = memory_info.rss / 1024 / 1024
    
    system_memory = psutil.virtual_memory()
    system_percent = system_memory.percent
    
    logger.info(f"プロセスメモリ使用量: {memory_mb:.1f}MB")
    logger.info(f"システムメモリ使用率: {system_percent:.1f}%")


def debug_file_info(file_path: str, logger_name: str = __name__) -> None:
    """
    ファイル情報をログに出力
    
    Args:
        file_path: 情報を出力するファイルのパス
        logger_name: ログ出力に使用するロガー名
    """
    from pathlib import Path
    import os
    
    logger = get_logger(logger_name)
    
    path = Path(file_path)
    if path.exists():
        stat = path.stat()
        size_mb = stat.st_size / 1024 / 1024
        logger.info(f"ファイル: {path.name}")
        logger.info(f"  サイズ: {size_mb:.1f}MB")
        logger.info(f"  最終更新: {Path(file_path).stat().st_mtime}")
    else:
        logger.warning(f"ファイルが存在しません: {file_path}")