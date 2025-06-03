"""
超最適化版のパフォーマンステストスクリプト
"""
import os
import sys
import time
import psutil
import threading
from datetime import datetime
from pathlib import Path

from config import Config
from core.transcription import Transcriber
from utils.logging import get_logger

logger = get_logger(__name__)

class PerformanceMonitor:
    """パフォーマンスモニタリングクラス"""
    
    def __init__(self):
        self.monitoring = False
        self.memory_usage = []
        self.cpu_usage = []
        self.process = psutil.Process()
        
    def start_monitoring(self):
        """モニタリング開始"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources)
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        """モニタリング終了"""
        self.monitoring = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join()
            
    def _monitor_resources(self):
        """リソース使用状況を監視"""
        while self.monitoring:
            try:
                # メモリ使用量（MB）
                mem_info = self.process.memory_info()
                mem_mb = mem_info.rss / (1024 * 1024)
                self.memory_usage.append(mem_mb)
                
                # CPU使用率
                cpu_percent = self.process.cpu_percent(interval=0.1)
                self.cpu_usage.append(cpu_percent)
                
                time.sleep(1)  # 1秒ごとに測定
            except:
                pass
                
    def get_stats(self):
        """統計情報を取得"""
        if not self.memory_usage:
            return None
            
        return {
            "max_memory_mb": max(self.memory_usage),
            "avg_memory_mb": sum(self.memory_usage) / len(self.memory_usage),
            "min_memory_mb": min(self.memory_usage),
            "max_cpu_percent": max(self.cpu_usage) if self.cpu_usage else 0,
            "avg_cpu_percent": sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
        }


def test_transcription_performance(video_path: str, use_api: bool = True, force_ultra_mode: bool = False):
    """文字起こしのパフォーマンステスト"""
    print("\n" + "="*80)
    print(f"パフォーマンステスト開始: {Path(video_path).name}")
    print(f"モード: {'API' if use_api else 'ローカル'} ({'超最適化強制' if force_ultra_mode else '自動選択'})")
    print("="*80)
    
    # 設定
    config = Config()
    config.transcription.use_api = use_api
    
    # 超最適化モードを強制する場合
    if force_ultra_mode and use_api:
        # システムスペックを低スペックに偽装してテスト
        os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"
    
    # モニター開始
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    # 進捗コールバック
    progress_history = []
    def progress_callback(progress: float, status: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        progress_history.append({
            "time": timestamp,
            "progress": progress,
            "status": status
        })
        print(f"[{timestamp}] {progress:.1%} - {status}")
    
    try:
        # APIキーを設定（テスト用）
        if use_api:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                print("エラー: OPENAI_API_KEYが設定されていません")
                return
            config.transcription.api_key = api_key
        
        # Transcriberを初期化
        transcriber = Transcriber(config)
        
        # キャッシュをクリア（公正なテストのため）
        cache_path = transcriber.get_cache_path(video_path, "whisper-1_api" if use_api else "base")
        if cache_path.exists():
            print(f"既存のキャッシュを削除: {cache_path}")
            os.remove(cache_path)
        
        # 文字起こし実行
        start_time = time.time()
        result = transcriber.transcribe(
            video_path,
            model_size="whisper-1" if use_api else "base",
            progress_callback=progress_callback,
            use_cache=False,  # キャッシュ無効
            save_cache=True
        )
        end_time = time.time()
        
        # モニター終了
        monitor.stop_monitoring()
        
        # 結果表示
        processing_time = end_time - start_time
        stats = monitor.get_stats()
        
        print("\n" + "-"*80)
        print("テスト結果:")
        print("-"*80)
        print(f"処理時間: {processing_time:.1f}秒 ({processing_time/60:.1f}分)")
        print(f"セグメント数: {len(result.segments)}")
        print(f"最大メモリ使用量: {stats['max_memory_mb']:.1f}MB")
        print(f"平均メモリ使用量: {stats['avg_memory_mb']:.1f}MB")
        print(f"最大CPU使用率: {stats['max_cpu_percent']:.1f}%")
        print(f"平均CPU使用率: {stats['avg_cpu_percent']:.1f}%")
        
        # 進捗履歴から重要なイベントを抽出
        print("\n重要なイベント:")
        important_events = []
        for i, event in enumerate(progress_history):
            if i == 0 or "完了" in event["status"] or "フェーズ" in event["status"] or i == len(progress_history) - 1:
                important_events.append(event)
        
        for event in important_events[-10:]:  # 最後の10イベント
            print(f"  [{event['time']}] {event['progress']:.1%} - {event['status']}")
        
        return {
            "processing_time": processing_time,
            "segments_count": len(result.segments),
            "memory_stats": stats,
            "success": True
        }
        
    except Exception as e:
        monitor.stop_monitoring()
        print(f"\nエラー発生: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        # 環境変数をクリーンアップ
        if "TEXTFFCUT_FORCE_LOW_SPEC" in os.environ:
            del os.environ["TEXTFFCUT_FORCE_LOW_SPEC"]


def main():
    """メインテスト実行"""
    # テスト対象の動画
    test_video = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）世界は保守かリベラルか？ではなくて変革か維持か？で2つに分かれてる.mp4"
    
    if not Path(test_video).exists():
        print(f"エラー: テスト動画が見つかりません: {test_video}")
        return
    
    # 1. 超最適化版のテスト（API + アライメント）
    print("\n" + "="*80)
    print("テスト1: 超最適化版（API + アライメント）")
    print("="*80)
    result1 = test_transcription_performance(test_video, use_api=True, force_ultra_mode=True)
    
    # 少し待機
    time.sleep(5)
    
    # 2. 通常版のテスト（比較用、短い動画で）
    short_video = "/Users/naoki/myProject/TextffCut/videos/test.mp4"
    if Path(short_video).exists():
        print("\n" + "="*80)
        print("テスト2: 通常版（比較用、短い動画）")
        print("="*80)
        result2 = test_transcription_performance(short_video, use_api=True, force_ultra_mode=False)
    
    # 結果サマリー
    print("\n" + "="*80)
    print("パフォーマンステスト完了")
    print("="*80)
    
    if result1["success"]:
        print(f"\n超最適化版（65分動画）:")
        print(f"  処理時間: {result1['processing_time']:.1f}秒")
        print(f"  メモリ使用量: 最大 {result1['memory_stats']['max_memory_mb']:.1f}MB")
        print(f"  セグメント数: {result1['segments_count']}")


if __name__ == "__main__":
    main()