"""
実際の動画を使用したパフォーマンステスト
"""
import os
import sys
import time
import psutil
import threading
from datetime import datetime
from pathlib import Path

# APIキーを設定
os.environ["OPENAI_API_KEY"] = sys.argv[1] if len(sys.argv) > 1 else ""

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


def test_transcription_performance(video_path: str, test_name: str, force_ultra_mode: bool = False):
    """文字起こしのパフォーマンステスト"""
    print("\n" + "="*80)
    print(f"パフォーマンステスト: {test_name}")
    print(f"動画: {Path(video_path).name}")
    print(f"モード: API + アライメント ({'超最適化強制' if force_ultra_mode else '自動選択'})")
    print("="*80)
    
    # 設定
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.environ["OPENAI_API_KEY"]
    
    # 超最適化モードを強制する場合
    if force_ultra_mode:
        # システムスペックを低スペックに偽装してテスト
        os.environ["TEXTFFCUT_FORCE_LOW_SPEC"] = "true"
    
    # モニター開始
    monitor = PerformanceMonitor()
    monitor.start_monitoring()
    
    # 進捗コールバック
    progress_history = []
    phase_times = {}
    last_phase = None
    
    def progress_callback(progress: float, status: str):
        nonlocal last_phase
        timestamp = datetime.now().strftime("%H:%M:%S")
        progress_history.append({
            "time": timestamp,
            "progress": progress,
            "status": status
        })
        
        # フェーズ検出
        if "Phase" in status or "フェーズ" in status:
            if last_phase:
                phase_times[last_phase] = time.time() - phase_times[last_phase]
            last_phase = status
            phase_times[status] = time.time()
        
        print(f"[{timestamp}] {progress:.1%} - {status}")
    
    try:
        # Transcriberを初期化
        transcriber = Transcriber(config)
        
        # キャッシュをクリア（公正なテストのため）
        cache_path = transcriber.get_cache_path(video_path, "whisper-1_api")
        if cache_path.exists():
            print(f"既存のキャッシュを削除: {cache_path}")
            os.remove(cache_path)
        
        # 文字起こし実行
        start_time = time.time()
        result = transcriber.transcribe(
            video_path,
            model_size="whisper-1",
            progress_callback=progress_callback,
            use_cache=False,  # キャッシュ無効
            save_cache=True
        )
        end_time = time.time()
        
        # 最後のフェーズの時間を記録
        if last_phase and last_phase in phase_times:
            phase_times[last_phase] = time.time() - phase_times[last_phase]
        
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
        
        # フェーズ別の処理時間
        if phase_times:
            print("\nフェーズ別処理時間:")
            for phase, duration in phase_times.items():
                print(f"  {phase}: {duration:.1f}秒")
        
        return {
            "processing_time": processing_time,
            "segments_count": len(result.segments),
            "memory_stats": stats,
            "phase_times": phase_times,
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
    if not os.environ.get("OPENAI_API_KEY"):
        print("エラー: APIキーが引数として必要です")
        print("使用方法: python performance_test_real.py YOUR_API_KEY")
        return
    
    # テスト1: 短い動画（6分）での通常モード
    short_video = "/Users/naoki/myProject/TextffCut/videos/001_AI活用の始めの一歩：お笑いAIから学ぶ発想術.mp4"
    if Path(short_video).exists():
        result1 = test_transcription_performance(short_video, "6分動画 - 通常モード", force_ultra_mode=False)
        time.sleep(3)
    
    # テスト2: 短い動画（6分）での超最適化モード
    if Path(short_video).exists():
        result2 = test_transcription_performance(short_video, "6分動画 - 超最適化モード", force_ultra_mode=True)
        time.sleep(3)
    
    # テスト3: 長い動画（65分）での超最適化モード
    long_video = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）世界は保守かリベラルか？ではなくて変革か維持か？で2つに分かれてる.mp4"
    if Path(long_video).exists():
        result3 = test_transcription_performance(long_video, "65分動画 - 超最適化モード", force_ultra_mode=True)
    
    # 結果サマリー
    print("\n" + "="*80)
    print("パフォーマンステスト完了 - サマリー")
    print("="*80)
    
    if 'result1' in locals() and result1["success"]:
        print(f"\n6分動画 - 通常モード:")
        print(f"  処理時間: {result1['processing_time']:.1f}秒")
        print(f"  メモリ使用量: 最大 {result1['memory_stats']['max_memory_mb']:.1f}MB")
    
    if 'result2' in locals() and result2["success"]:
        print(f"\n6分動画 - 超最適化モード:")
        print(f"  処理時間: {result2['processing_time']:.1f}秒")
        print(f"  メモリ使用量: 最大 {result2['memory_stats']['max_memory_mb']:.1f}MB")
        
    if 'result3' in locals() and result3["success"]:
        print(f"\n65分動画 - 超最適化モード:")
        print(f"  処理時間: {result3['processing_time']:.1f}秒 ({result3['processing_time']/60:.1f}分)")
        print(f"  メモリ使用量: 最大 {result3['memory_stats']['max_memory_mb']:.1f}MB")


if __name__ == "__main__":
    main()