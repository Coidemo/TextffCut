"""
ガベージコレクション最適化統合テスト

プロセス分離環境でのGC最適化機能の動作を確認する。
"""

import multiprocessing as mp
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.worker_lifecycle_manager import WorkerLifecycleManager
from orchestrator.transcription_worker_process import transcription_worker_process
from utils.logging import get_logger

logger = get_logger(__name__)


def run_gc_optimization_test():
    """GC最適化統合テストを実行"""
    print("=== GC Optimization Integration Test ===")
    
    # ライフサイクルマネージャーを作成（メモリ監視を頻繁に）
    manager = WorkerLifecycleManager(
        worker_func=transcription_worker_process,
        num_workers=2,
        max_restart_count=3,
        heartbeat_timeout=30.0
    )
    
    # メモリ報告間隔を短くする（テスト用）
    for worker in manager.workers.values():
        if hasattr(worker, '_memory_report_interval'):
            worker._memory_report_interval = 3.0
    
    # ワーカーを起動
    print("\n--- Starting Workers ---")
    manager.start()
    
    # 初期化
    print("\n--- Initializing Workers ---")
    for i in range(manager.num_workers):
        init_task = {
            "type": "initialize",
            "model_size": "medium",
            "language": "ja"
        }
        manager.submit_task(f"init_{i}", init_task)
    
    # 初期化完了を待つ
    time.sleep(3)
    messages = manager.process_messages(timeout=1.0)
    
    # メモリ負荷をかけるタスクを作成
    print("\n--- Generating Memory Load ---")
    
    # 段階的にメモリ負荷を増やす
    load_levels = [
        ("Low", 10, 100),      # 低負荷: 10セグメント、100文字
        ("Medium", 50, 500),   # 中負荷: 50セグメント、500文字
        ("High", 100, 1000),   # 高負荷: 100セグメント、1000文字
    ]
    
    for level_name, segment_count, text_size in load_levels:
        print(f"\n--- {level_name} Memory Load Test ---")
        
        # タスクを作成
        task = {
            "type": "batch_transcribe",
            "segments": [
                {
                    "start": i * 10.0,
                    "end": (i + 1) * 10.0,
                    "text": "テスト" * text_size
                }
                for i in range(segment_count)
            ],
            "audio_path": "/dummy/path.wav",
            "chunk_duration": 10.0
        }
        
        # 各ワーカーにタスクを送信
        for i in range(manager.num_workers):
            manager.submit_task(f"{level_name}_task_{i}", task)
        
        # メモリレポートを収集
        print(f"Monitoring GC behavior for {level_name} load...")
        gc_reports = []
        
        for _ in range(5):  # 5回チェック
            time.sleep(2)
            messages = manager.process_messages(timeout=0.5)
            
            for msg in messages:
                if msg.msg_type.value == "memory_status":
                    data = msg.data or {}
                    gc_metrics = data.get("gc_metrics")
                    
                    if gc_metrics:
                        gc_reports.append({
                            "worker": msg.worker_id,
                            "memory_percent": data.get("memory_percent", 0),
                            "collected": gc_metrics.get("collected", 0),
                            "duration_ms": gc_metrics.get("duration_ms", 0),
                            "strategy": gc_metrics.get("strategy", "unknown")
                        })
                        
                        print(f"  {msg.worker_id}: "
                              f"memory={data.get('memory_percent', 0):.1f}%, "
                              f"GC collected={gc_metrics.get('collected', 0)}, "
                              f"strategy={gc_metrics.get('strategy', 'unknown')}")
        
        # GCレポートのサマリー
        if gc_reports:
            total_collected = sum(r["collected"] for r in gc_reports)
            avg_duration = sum(r["duration_ms"] for r in gc_reports) / len(gc_reports)
            strategies = set(r["strategy"] for r in gc_reports)
            
            print(f"\n{level_name} Load Summary:")
            print(f"  Total objects collected: {total_collected}")
            print(f"  Average GC duration: {avg_duration:.1f}ms")
            print(f"  Strategies used: {', '.join(strategies)}")
    
    # 最終ステータス
    print("\n--- Final Status ---")
    final_status = manager.get_status()
    
    print(f"Active workers: {final_status['active_workers']}/{final_status['total_workers']}")
    
    # GC統計を表示
    print("\nGC Statistics by Worker:")
    for worker in final_status['workers']:
        print(f"\n{worker['worker_id']}:")
        print(f"  State: {worker['state']}")
        print(f"  Tasks completed: {worker['task_count']}")
        print(f"  Errors: {worker['error_count']}")
    
    # メモリ状態
    memory_report = final_status.get('memory', {})
    if memory_report:
        print(f"\nMemory Status:")
        print(f"  System: {memory_report['system']['percent']:.1f}%")
        
        for worker_mem in memory_report.get('workers', []):
            print(f"  {worker_mem['worker_id']}: "
                  f"{worker_mem['memory_mb']:.1f}MB "
                  f"({worker_mem['memory_percent']:.1f}%)")
    
    # シャットダウン
    print("\n--- Shutdown ---")
    manager.shutdown()
    print("✓ Test completed!")
    
    return True


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method('spawn', force=True)
    
    # テスト実行
    success = run_gc_optimization_test()
    
    # 終了コード
    sys.exit(0 if success else 1)