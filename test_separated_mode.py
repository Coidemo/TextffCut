#!/usr/bin/env python
"""
分離モードのテストスクリプト

ローカルモードで長時間動画や低メモリ環境での
文字起こし・アライメント分離処理をテストします。
"""

import os
import sys
import time
import json
import tempfile
import psutil
from pathlib import Path
from typing import Dict, Any

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils.logging import get_logger
from core.transcription import Transcriber

logger = get_logger(__name__)


def create_test_config(force_separated: bool = False) -> Config:
    """テスト用の設定を作成"""
    config = Config()
    
    # ローカルモードの設定
    config.transcription.use_api = False
    config.transcription.model_size = "base"  # テスト用に小さいモデル
    config.transcription.language = "ja"
    config.transcription.chunk_seconds = 30
    config.transcription.local_align_chunk_seconds = 60
    config.transcription.force_separated_mode = force_separated
    config.transcription.batch_size = 4
    config.transcription.num_workers = 2
    
    return config


def log_memory_usage(label: str):
    """メモリ使用量をログ出力"""
    process = psutil.Process()
    mem_info = process.memory_info()
    mem_mb = mem_info.rss / 1024 / 1024
    
    vm = psutil.virtual_memory()
    available_gb = vm.available / (1024 ** 3)
    
    logger.info(f"{label}: プロセスメモリ={mem_mb:.1f}MB, 利用可能メモリ={available_gb:.1f}GB")


def test_transcription_only(video_path: str, config: Config):
    """文字起こしのみのテスト"""
    logger.info("=== 文字起こしのみモードのテスト ===")
    
    transcriber = Transcriber(config)
    
    # 進捗コールバック
    def progress_callback(progress: float, message: str):
        logger.info(f"進捗: {progress:.1%} - {message}")
    
    log_memory_usage("開始前")
    
    start_time = time.time()
    
    # 文字起こしのみ実行（アライメントをスキップ）
    result = transcriber.transcribe(
        video_path=video_path,
        model_size="base",
        progress_callback=progress_callback,
        use_cache=False,
        save_cache=False,
        skip_alignment=True
    )
    
    elapsed = time.time() - start_time
    
    log_memory_usage("文字起こし完了後")
    
    logger.info(f"文字起こし完了: {elapsed:.1f}秒")
    logger.info(f"セグメント数: {len(result.segments)}")
    
    # wordsフィールドの確認
    has_words = sum(1 for seg in result.segments if seg.words and len(seg.words) > 0)
    logger.info(f"words情報を持つセグメント: {has_words}/{len(result.segments)}")
    
    return result


def test_alignment_processing(segments: list, video_path: str, language: str, config: Config):
    """アライメント処理のテスト"""
    logger.info("=== アライメント処理のテスト ===")
    
    from core.alignment_processor import AlignmentProcessor
    from core.models import TranscriptionSegmentV2
    
    # V2形式のセグメントに変換
    v2_segments = []
    for i, seg in enumerate(segments):
        v2_segment = TranscriptionSegmentV2(
            id=f"seg_{i}",
            text=seg['text'] if isinstance(seg, dict) else seg.text,
            start=seg['start'] if isinstance(seg, dict) else seg.start,
            end=seg['end'] if isinstance(seg, dict) else seg.end,
            words=None,  # アライメント前なのでNone
            language=language,
            transcription_completed=True,
            alignment_completed=False
        )
        v2_segments.append(v2_segment)
    
    alignment_processor = AlignmentProcessor(config)
    
    # 進捗コールバック
    def progress_callback(progress: float, message: str):
        logger.info(f"アライメント進捗: {progress:.1%} - {message}")
    
    log_memory_usage("アライメント開始前")
    
    start_time = time.time()
    
    # アライメント実行
    aligned_segments = alignment_processor.align(
        v2_segments,
        video_path,
        language,
        progress_callback
    )
    
    elapsed = time.time() - start_time
    
    log_memory_usage("アライメント完了後")
    
    logger.info(f"アライメント完了: {elapsed:.1f}秒")
    
    # アライメント結果の確認
    aligned_count = sum(1 for seg in aligned_segments if seg.alignment_completed)
    words_count = sum(len(seg.words) if seg.words else 0 for seg in aligned_segments)
    
    logger.info(f"アライメント成功セグメント: {aligned_count}/{len(aligned_segments)}")
    logger.info(f"総word数: {words_count}")
    
    return aligned_segments


def test_separated_mode_auto(video_path: str):
    """自動分離モードのテスト（長時間動画や低メモリで自動的に分離）"""
    logger.info("=== 自動分離モードのテスト ===")
    
    config = create_test_config(force_separated=False)
    
    # サブプロセス経由で実行（実際の使用環境を再現）
    from utils.subprocess_utils import run_worker_process
    
    # ワーカー設定を作成
    config_data = {
        'video_path': video_path,
        'model_size': 'base',
        'use_cache': False,
        'save_cache': False,
        'config': config.__dict__,
        'task_type': 'full'  # フル処理（自動判定あり）
    }
    
    # 一時ディレクトリに設定を保存
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = os.path.join(temp_dir, 'config.json')
        with open(config_path, 'w') as f:
            json.dump(config_data, f, default=str)
        
        log_memory_usage("ワーカー実行前")
        
        # ワーカープロセスを実行
        success, result_data = run_worker_process(
            'worker_transcribe.py',
            config_path,
            timeout=600  # 10分のタイムアウト
        )
        
        log_memory_usage("ワーカー実行後")
        
        if success:
            logger.info("ワーカープロセス成功")
            
            # 結果を確認
            if 'segments' in result_data:
                segments = result_data['segments']
                logger.info(f"セグメント数: {len(segments)}")
                
                # words情報の確認
                has_words = sum(1 for seg in segments if seg.get('words'))
                logger.info(f"words情報を持つセグメント: {has_words}/{len(segments)}")
        else:
            logger.error(f"ワーカープロセス失敗: {result_data.get('error', 'Unknown error')}")


def test_forced_separated_mode(video_path: str):
    """強制分離モードのテスト"""
    logger.info("=== 強制分離モードのテスト ===")
    
    config = create_test_config(force_separated=True)
    
    transcriber = Transcriber(config)
    
    # 進捗コールバック
    def progress_callback(progress: float, message: str):
        logger.info(f"進捗: {progress:.1%} - {message}")
    
    log_memory_usage("開始前")
    
    # まず文字起こしのみ
    logger.info("ステップ1: 文字起こし")
    result = test_transcription_only(video_path, config)
    
    # 次にアライメント
    logger.info("ステップ2: アライメント")
    aligned_segments = test_alignment_processing(
        result.segments,
        video_path,
        result.language,
        config
    )
    
    log_memory_usage("全処理完了後")
    
    return aligned_segments


def main():
    """メイン処理"""
    logger.info("分離モードテストを開始")
    
    # テスト用動画のパス（適宜変更してください）
    video_path = "videos/test_video.mp4"
    
    if not os.path.exists(video_path):
        logger.error(f"テスト用動画が見つかりません: {video_path}")
        logger.info("videos/フォルダにテスト用動画を配置してください")
        return
    
    # 動画情報を取得
    from core.video import VideoInfo
    video_info = VideoInfo.from_file(video_path)
    duration_minutes = video_info.duration / 60
    
    logger.info(f"テスト動画: {video_path}")
    logger.info(f"動画時間: {duration_minutes:.1f}分")
    
    # システム情報
    mem_gb = psutil.virtual_memory().total / (1024**3)
    cpu_count = psutil.cpu_count(logical=False) or 4
    logger.info(f"システム: メモリ{mem_gb:.1f}GB, CPU{cpu_count}コア")
    
    # テスト1: 文字起こしのみ
    logger.info("\n" + "="*50)
    config = create_test_config()
    test_transcription_only(video_path, config)
    
    # テスト2: 自動分離モード（30分以上または低メモリで自動的に分離）
    if duration_minutes > 30 or mem_gb < 6:
        logger.info("\n" + "="*50)
        logger.info("長時間動画または低メモリのため、自動的に分離モードを使用")
        test_separated_mode_auto(video_path)
    
    # テスト3: 強制分離モード
    logger.info("\n" + "="*50)
    test_forced_separated_mode(video_path)
    
    logger.info("\n全テスト完了")


if __name__ == "__main__":
    main()