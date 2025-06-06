#!/usr/bin/env python
"""
メモリ使用量比較テスト

通常モードと分離モードのメモリ使用量を比較します。
"""

import os
import sys
import time
import gc
import psutil
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Tuple
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from utils.logging import get_logger
from core.transcription import Transcriber

logger = get_logger(__name__)


class MemoryMonitor:
    """メモリ使用量を監視するクラス"""
    
    def __init__(self):
        self.process = psutil.Process()
        self.memory_usage = []
        self.timestamps = []
        self.markers = []  # イベントマーカー
    
    def record(self, label: str = ""):
        """現在のメモリ使用量を記録"""
        mem_mb = self.process.memory_info().rss / 1024 / 1024
        timestamp = time.time()
        
        self.memory_usage.append(mem_mb)
        self.timestamps.append(timestamp)
        
        if label:
            self.markers.append((timestamp, mem_mb, label))
            logger.info(f"{label}: {mem_mb:.1f}MB")
    
    def get_peak_memory(self) -> float:
        """ピークメモリ使用量を取得"""
        return max(self.memory_usage) if self.memory_usage else 0
    
    def plot(self, title: str, filename: str):
        """メモリ使用量のグラフを作成"""
        if not self.memory_usage:
            return
        
        plt.figure(figsize=(12, 6))
        
        # 時間軸を相対時間に変換
        start_time = self.timestamps[0]
        relative_times = [(t - start_time) for t in self.timestamps]
        
        # メモリ使用量をプロット
        plt.plot(relative_times, self.memory_usage, 'b-', linewidth=2)
        
        # マーカーを追加
        for timestamp, mem_mb, label in self.markers:
            rel_time = timestamp - start_time
            plt.annotate(label, xy=(rel_time, mem_mb), 
                        xytext=(rel_time, mem_mb + 50),
                        arrowprops=dict(arrowstyle='->', color='red'),
                        fontsize=8, ha='center')
        
        plt.xlabel('時間 (秒)')
        plt.ylabel('メモリ使用量 (MB)')
        plt.title(title)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # グラフを保存
        plt.savefig(filename, dpi=150)
        plt.close()
        
        logger.info(f"グラフを保存: {filename}")


def test_normal_mode(video_path: str, model_size: str = "base") -> Tuple[float, float]:
    """通常モード（文字起こし＋アライメント同時実行）のテスト"""
    logger.info("=== 通常モードのテスト ===")
    
    config = Config()
    config.transcription.use_api = False
    config.transcription.model_size = model_size
    config.transcription.language = "ja"
    config.transcription.chunk_seconds = 30
    config.transcription.batch_size = 4
    config.transcription.num_workers = 2
    config.transcription.force_separated_mode = False  # 分離モードを無効化
    
    monitor = MemoryMonitor()
    monitor.record("開始")
    
    transcriber = Transcriber(config)
    
    def progress_callback(progress: float, message: str):
        if progress % 0.2 < 0.01:  # 20%ごとに記録
            monitor.record(f"{message} ({progress:.0%})")
    
    start_time = time.time()
    
    result = transcriber.transcribe(
        video_path=video_path,
        model_size=model_size,
        progress_callback=progress_callback,
        use_cache=False,
        save_cache=False
    )
    
    elapsed = time.time() - start_time
    monitor.record("完了")
    
    peak_memory = monitor.get_peak_memory()
    
    # グラフを作成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    monitor.plot(
        f"通常モード - メモリ使用量 (ピーク: {peak_memory:.1f}MB)",
        f"memory_normal_{timestamp}.png"
    )
    
    logger.info(f"通常モード完了: 処理時間={elapsed:.1f}秒, ピークメモリ={peak_memory:.1f}MB")
    
    # メモリを解放
    del transcriber
    del result
    gc.collect()
    time.sleep(2)  # GCが完了するまで待機
    
    return elapsed, peak_memory


def test_separated_mode(video_path: str, model_size: str = "base") -> Tuple[float, float]:
    """分離モード（文字起こし→アライメント）のテスト"""
    logger.info("=== 分離モードのテスト ===")
    
    config = Config()
    config.transcription.use_api = False
    config.transcription.model_size = model_size
    config.transcription.language = "ja"
    config.transcription.chunk_seconds = 30
    config.transcription.local_align_chunk_seconds = 60
    config.transcription.batch_size = 4
    config.transcription.num_workers = 2
    config.transcription.force_separated_mode = True  # 分離モードを強制
    
    monitor = MemoryMonitor()
    monitor.record("開始")
    
    start_time = time.time()
    total_time = 0
    
    # ステップ1: 文字起こしのみ
    logger.info("ステップ1: 文字起こし")
    monitor.record("文字起こし開始")
    
    transcriber = Transcriber(config)
    
    def transcribe_progress(progress: float, message: str):
        if progress % 0.2 < 0.01:
            monitor.record(f"[文字起こし] {message} ({progress:.0%})")
    
    result = transcriber.transcribe(
        video_path=video_path,
        model_size=model_size,
        progress_callback=transcribe_progress,
        use_cache=False,
        save_cache=False,
        skip_alignment=True
    )
    
    transcribe_time = time.time() - start_time
    monitor.record("文字起こし完了")
    
    # メモリを解放
    del transcriber
    gc.collect()
    time.sleep(2)
    
    monitor.record("GC後（文字起こし）")
    
    # ステップ2: アライメント
    logger.info("ステップ2: アライメント")
    monitor.record("アライメント開始")
    
    from core.alignment_processor import AlignmentProcessor
    from core.models import TranscriptionSegmentV2
    
    # V2形式のセグメントに変換
    v2_result = result.to_v2_format()
    
    alignment_processor = AlignmentProcessor(config)
    
    def alignment_progress(progress: float, message: str):
        if progress % 0.2 < 0.01:
            monitor.record(f"[アライメント] {message} ({progress:.0%})")
    
    alignment_start = time.time()
    
    aligned_segments = alignment_processor.align(
        v2_result.segments,
        video_path,
        result.language,
        alignment_progress
    )
    
    alignment_time = time.time() - alignment_start
    total_time = time.time() - start_time
    
    monitor.record("アライメント完了")
    
    # メモリを解放
    del alignment_processor
    del aligned_segments
    gc.collect()
    time.sleep(2)
    
    monitor.record("GC後（アライメント）")
    
    peak_memory = monitor.get_peak_memory()
    
    # グラフを作成
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    monitor.plot(
        f"分離モード - メモリ使用量 (ピーク: {peak_memory:.1f}MB)",
        f"memory_separated_{timestamp}.png"
    )
    
    logger.info(f"分離モード完了: 総時間={total_time:.1f}秒 (文字起こし={transcribe_time:.1f}秒, アライメント={alignment_time:.1f}秒), ピークメモリ={peak_memory:.1f}MB")
    
    return total_time, peak_memory


def compare_memory_usage(normal_data: dict, separated_data: dict):
    """メモリ使用量の比較結果を表示"""
    logger.info("\n" + "="*60)
    logger.info("メモリ使用量比較結果")
    logger.info("="*60)
    
    # 表形式で表示
    logger.info(f"{'モード':<15} {'処理時間':<15} {'ピークメモリ':<15} {'メモリ削減率'}")
    logger.info("-"*60)
    
    normal_time = normal_data['time']
    normal_memory = normal_data['memory']
    separated_time = separated_data['time']
    separated_memory = separated_data['memory']
    
    memory_reduction = (1 - separated_memory / normal_memory) * 100 if normal_memory > 0 else 0
    
    logger.info(f"{'通常モード':<15} {f'{normal_time:.1f}秒':<15} {f'{normal_memory:.1f}MB':<15} {'-'}")
    logger.info(f"{'分離モード':<15} {f'{separated_time:.1f}秒':<15} {f'{separated_memory:.1f}MB':<15} {f'{memory_reduction:.1f}%'}")
    
    logger.info("\n分析:")
    if memory_reduction > 0:
        logger.info(f"✅ 分離モードはメモリ使用量を {memory_reduction:.1f}% 削減しました")
    else:
        logger.info("❌ 分離モードでメモリ削減効果が見られませんでした")
    
    time_overhead = (separated_time / normal_time - 1) * 100 if normal_time > 0 else 0
    if time_overhead > 0:
        logger.info(f"⏱️ 処理時間は {time_overhead:.1f}% 増加しました")
    else:
        logger.info(f"⏱️ 処理時間は {-time_overhead:.1f}% 短縮されました")


def main():
    """メイン処理"""
    logger.info("メモリ使用量比較テストを開始")
    
    # テスト用動画のパス
    video_path = "videos/test_video.mp4"
    
    if not os.path.exists(video_path):
        logger.error(f"テスト用動画が見つかりません: {video_path}")
        logger.info("videos/フォルダにテスト用動画を配置してください")
        return
    
    # 動画情報
    from core.video import VideoInfo
    video_info = VideoInfo.from_file(video_path)
    duration_minutes = video_info.duration / 60
    
    logger.info(f"テスト動画: {video_path}")
    logger.info(f"動画時間: {duration_minutes:.1f}分")
    
    # システム情報
    mem_gb = psutil.virtual_memory().total / (1024**3)
    cpu_count = psutil.cpu_count(logical=False) or 4
    logger.info(f"システム: メモリ{mem_gb:.1f}GB, CPU{cpu_count}コア")
    
    # モデルサイズ
    model_size = "base"  # テスト用に小さいモデルを使用
    
    # 通常モードのテスト
    logger.info("\n" + "="*50)
    normal_time, normal_memory = test_normal_mode(video_path, model_size)
    
    # メモリが落ち着くまで待機
    time.sleep(5)
    gc.collect()
    
    # 分離モードのテスト
    logger.info("\n" + "="*50)
    separated_time, separated_memory = test_separated_mode(video_path, model_size)
    
    # 比較結果を表示
    normal_data = {'time': normal_time, 'memory': normal_memory}
    separated_data = {'time': separated_time, 'memory': separated_memory}
    compare_memory_usage(normal_data, separated_data)
    
    logger.info("\nテスト完了")
    logger.info("memory_normal_*.png と memory_separated_*.png にグラフが保存されました")


if __name__ == "__main__":
    main()