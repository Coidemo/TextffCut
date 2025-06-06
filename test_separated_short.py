#!/usr/bin/env python
"""
短い動画での分離モードテスト
"""

import os
import sys
import time
import psutil

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils.logging import get_logger
from core.transcription import Transcriber
from core.video import VideoInfo

logger = get_logger(__name__)


def log_memory(label: str):
    """メモリ使用量をログ出力"""
    process = psutil.Process()
    mem_mb = process.memory_info().rss / 1024 / 1024
    logger.info(f"{label}: {mem_mb:.1f}MB")


def test_with_video(video_path: str, force_separated: bool):
    """指定された動画でテスト"""
    
    # 動画情報
    video_info = VideoInfo.from_file(video_path)
    duration_sec = video_info.duration
    logger.info(f"\n動画: {os.path.basename(video_path)}")
    logger.info(f"時間: {duration_sec:.1f}秒 ({duration_sec/60:.1f}分)")
    
    # 設定
    config = Config()
    config.transcription.use_api = False
    config.transcription.model_size = "base"
    config.transcription.language = "ja"
    config.transcription.chunk_seconds = 30
    config.transcription.local_align_chunk_seconds = 60
    config.transcription.force_separated_mode = force_separated
    
    # メモリ状態
    mem_gb = psutil.virtual_memory().available / (1024**3)
    logger.info(f"利用可能メモリ: {mem_gb:.1f}GB")
    
    # 分離モード判定（worker_transcribe.pyと同じロジック）
    should_separate = (
        config.transcription.force_separated_mode or
        duration_sec / 60 > 30 or
        mem_gb < 6
    )
    
    logger.info(f"分離モード判定: {should_separate} (強制={force_separated})")
    
    log_memory("処理開始前")
    
    transcriber = Transcriber(config)
    
    def progress_callback(progress: float, message: str):
        if int(progress * 100) % 20 == 0:  # 20%ごと
            log_memory(f"進捗 {progress:.0%}")
        logger.info(f"進捗: {progress:.1%} - {message}")
    
    start_time = time.time()
    
    try:
        # 分離モードを強制する場合は、まず文字起こしのみ
        if force_separated:
            logger.info("\n=== ステップ1: 文字起こしのみ ===")
            result = transcriber.transcribe(
                video_path=video_path,
                progress_callback=progress_callback,
                use_cache=False,
                save_cache=False,
                skip_alignment=True
            )
            
            log_memory("文字起こし完了")
            
            # 結果確認
            logger.info(f"セグメント数: {len(result.segments)}")
            has_words = sum(1 for seg in result.segments if seg.words)
            logger.info(f"words情報を持つセグメント: {has_words}/{len(result.segments)}")
            
            if has_words == 0:
                logger.info("\n=== ステップ2: アライメント処理 ===")
                # アライメントを別途実行
                from core.alignment_processor import AlignmentProcessor
                
                processor = AlignmentProcessor(config)
                v2_result = result.to_v2_format()
                
                aligned_segments = processor.align(
                    v2_result.segments,
                    video_path,
                    result.language,
                    progress_callback
                )
                
                log_memory("アライメント完了")
                
                # 結果確認
                aligned_count = sum(1 for seg in aligned_segments if seg.alignment_completed)
                logger.info(f"アライメント成功: {aligned_count}/{len(aligned_segments)}")
        else:
            # 通常処理
            logger.info("\n=== 通常モード（文字起こし＋アライメント） ===")
            result = transcriber.transcribe(
                video_path=video_path,
                progress_callback=progress_callback,
                use_cache=False,
                save_cache=False
            )
            
            log_memory("処理完了")
            
            # 結果確認
            logger.info(f"セグメント数: {len(result.segments)}")
            has_words = sum(1 for seg in result.segments if seg.words)
            logger.info(f"words情報を持つセグメント: {has_words}/{len(result.segments)}")
    
    except Exception as e:
        logger.error(f"エラー: {e}")
        import traceback
        traceback.print_exc()
    
    elapsed = time.time() - start_time
    logger.info(f"\n処理時間: {elapsed:.1f}秒")
    log_memory("最終")


def main():
    """メイン処理"""
    logger.info("短い動画での分離モードテスト\n")
    
    # テスト動画（短い順）
    test_videos = [
        "videos/test_short_30s.mp4",
        "videos/test_medium_1m.mp4",
        "videos/test_long_5m.mp4"
    ]
    
    # 利用可能な動画を確認
    available_videos = []
    for video in test_videos:
        if os.path.exists(video):
            available_videos.append(video)
    
    if not available_videos:
        # 代替動画を探す
        logger.info("テスト動画が見つかりません。利用可能な動画を探します...")
        for file in os.listdir("videos"):
            if file.endswith(".mp4") and not file.startswith("（"):
                path = os.path.join("videos", file)
                available_videos.append(path)
                if len(available_videos) >= 3:
                    break
    
    if not available_videos:
        logger.error("テスト可能な動画が見つかりません")
        return
    
    # 最初の動画でテスト
    video = available_videos[0]
    
    logger.info("=" * 60)
    logger.info("通常モードのテスト")
    logger.info("=" * 60)
    test_with_video(video, force_separated=False)
    
    logger.info("\n" + "=" * 60)
    logger.info("強制分離モードのテスト")
    logger.info("=" * 60)
    test_with_video(video, force_separated=True)
    
    logger.info("\nテスト完了")


if __name__ == "__main__":
    main()