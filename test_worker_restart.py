"""
ワーカー自動再起動テスト

メモリ圧迫やクラッシュ時の自動再起動機能をテストする。
"""

import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.worker_lifecycle_manager import WorkerLifecycleManager
from orchestrator.transcription_worker_process import transcription_worker_process
from utils.logging import get_logger

logger = get_logger(__name__)


def run_restart_test():
    """再起動テストを実行"""
    print("=== Worker Auto-Restart Test ===")
    
    # ライフサイクルマネージャーを作成
    manager = WorkerLifecycleManager(
        worker_func=transcription_worker_process,
        num_workers=2,
        max_restart_count=3,
        heartbeat_timeout=10.0  # 短めに設定してテスト
    )
    
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
    print(f"Processed {len(messages)} initialization messages")
    
    # 初期ステータス
    print("\n--- Initial Status ---")
    status = manager.get_status()
    for worker in status['workers']:
        print(f"{worker['worker_id']}: PID={worker['pid']}, state={worker['state']}")
    
    # テストシナリオ1: プロセスを強制終了してクラッシュをシミュレート
    print("\n--- Test 1: Simulating Worker Crash ---")
    worker_0_info = manager.workers.get("worker_0")
    if worker_0_info and worker_0_info.process.pid:
        original_pid = worker_0_info.process.pid
        print(f"Killing worker_0 (PID: {original_pid})")
        
        try:
            os.kill(original_pid, signal.SIGKILL)
        except ProcessLookupError:
            print("Process already terminated")
        
        # 監視サイクルを待つ
        print("Waiting for automatic restart...")
        time.sleep(7)
        
        # メッセージ処理（監視トリガー）
        messages = manager.process_messages(timeout=1.0)
        
        # 再起動確認
        time.sleep(3)
        messages = manager.process_messages(timeout=1.0)
        
        status = manager.get_status()
        new_worker_0 = next((w for w in status['workers'] if w['worker_id'] == 'worker_0'), None)
        
        if new_worker_0:
            print(f"Worker_0 restarted: new PID={new_worker_0['pid']}, "
                  f"restarts={new_worker_0['restart_count']}")
        else:
            print("Worker_0 not found in status")
    
    # テストシナリオ2: メモリ圧迫をシミュレート
    print("\n--- Test 2: Simulating Memory Pressure ---")
    
    # メモリ集約的なタスクを送信
    memory_intensive_task = {
        "type": "batch_transcribe",
        "segments": [
            {
                "start": i * 10.0,
                "end": (i + 1) * 10.0,
                "text": "メモリ圧迫テスト" * 1000  # 大量のテキスト
            }
            for i in range(50)  # 多数のセグメント
        ],
        "audio_path": "/dummy/path.wav",
        "chunk_duration": 10.0
    }
    
    print("Sending memory-intensive tasks...")
    for i in range(5):  # 複数のタスクを送信
        manager.submit_task(f"memory_test_{i}", memory_intensive_task)
    
    # メモリ監視を待つ
    print("Monitoring memory pressure...")
    for i in range(10):
        time.sleep(2)
        messages = manager.process_messages(timeout=0.5)
        
        # メモリ状態を確認
        status = manager.get_status()
        memory_info = status.get('memory', {})
        if memory_info.get('workers_under_pressure', 0) > 0:
            print(f"Workers under memory pressure: {memory_info['workers_under_pressure']}")
            
            # 詳細表示
            for worker in memory_info.get('workers', []):
                if worker['pressure_level'] != 'normal':
                    print(f"  {worker['worker_id']}: {worker['pressure_level']} "
                          f"({worker['memory_percent']:.1f}%)")
    
    # テストシナリオ3: ハートビートタイムアウト
    print("\n--- Test 3: Heartbeat Timeout Test ---")
    print("Waiting for heartbeat timeout...")
    
    # 長時間メッセージ処理をしない（ハートビートが更新されない）
    time.sleep(15)
    
    # 監視をトリガー
    messages = manager.process_messages(timeout=0.5)
    
    # 最終ステータス
    print("\n--- Final Status ---")
    final_status = manager.get_status()
    print(f"Total workers: {final_status['total_workers']}")
    print(f"Active workers: {final_status['active_workers']}")
    print(f"Failed workers: {final_status['failed_workers']}")
    
    for worker in final_status['workers']:
        print(f"\n{worker['worker_id']}:")
        print(f"  State: {worker['state']}")
        print(f"  PID: {worker['pid']}")
        print(f"  Tasks: {worker['task_count']}")
        print(f"  Errors: {worker['error_count']}")
        print(f"  Restarts: {worker['restart_count']}")
    
    # メモリ状態も表示
    memory_report = final_status.get('memory', {})
    if memory_report:
        print(f"\nMemory Status:")
        print(f"  System: {memory_report['system']['percent']:.1f}%")
        print(f"  Workers under pressure: {memory_report['workers_under_pressure']}")
    
    # シャットダウン
    print("\n--- Shutdown ---")
    manager.shutdown()
    print("✓ Test completed!")
    
    # 成功判定
    success = all(w['restart_count'] > 0 for w in final_status['workers'])
    return success


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method('spawn', force=True)
    
    # テスト実行
    success = run_restart_test()
    
    # 終了コード
    sys.exit(0 if success else 1)