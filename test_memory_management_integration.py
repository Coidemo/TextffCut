"""
メモリ管理統合テスト

プロセス分離環境でのメモリ監視と最適化機能の
統合テストを実行する。
"""

import multiprocessing as mp
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.memory_manager import ProcessMemoryManager
from orchestrator.process_communication import MessageType, ProcessPool
from orchestrator.transcription_worker_process import transcription_worker_process
from utils.logging import get_logger

logger = get_logger(__name__)


def run_memory_management_test():
    """メモリ管理統合テストを実行"""
    print("=== Memory Management Integration Test ===")

    # メモリマネージャーを初期化
    memory_manager = ProcessMemoryManager()

    # プロセスプールを作成（3ワーカー）
    pool = ProcessPool(num_workers=3)
    pool.start_workers(transcription_worker_process)

    # ワーカー準備完了を待つ
    ready_count = 0
    while ready_count < pool.num_workers:
        msg = pool.get_result(timeout=5.0)
        if msg and msg.msg_type == MessageType.WORKER_READY:
            ready_count += 1
            print(f"✓ {msg.worker_id} is ready")

    # 初期化タスクを送信
    print("\n--- Initialize Workers ---")
    init_task = {
        "type": "initialize",
        "model_size": "medium",
        "language": "ja",
        "device": "cpu",
        "compute_type": "int8",
    }

    for i in range(pool.num_workers):
        pool.submit_task(f"init_{i}", init_task)

    # 初期化結果とメモリレポートを収集
    init_complete = 0
    memory_reports = []

    print("\n--- Collecting Memory Reports ---")
    start_time = time.time()
    timeout = 30.0

    while init_complete < pool.num_workers and time.time() - start_time < timeout:
        msg = pool.get_result(timeout=1.0)

        if msg:
            if msg.msg_type == MessageType.TASK_RESULT:
                init_complete += 1
                print(f"← Worker initialized: {msg.data}")

            elif msg.msg_type == MessageType.MEMORY_STATUS:
                # メモリレポートを処理
                optimization_result = memory_manager.process_memory_report(msg)
                memory_reports.append(msg)

                print(
                    f"← Memory report from {msg.worker_id}: "
                    f"{msg.data.get('memory_mb', 0):.1f}MB "
                    f"({msg.data.get('memory_percent', 0):.1f}%)"
                )

                if optimization_result:
                    print(f"  → Optimization performed: {optimization_result.get('actions_taken', [])}")
                    if optimization_result.get("restart_required"):
                        print(f"  ⚠️ Worker {msg.worker_id} needs restart!")

    # メモリ集約的なタスクをシミュレート
    print("\n--- Simulating Memory-Intensive Tasks ---")

    # バッチ処理タスクを送信（メモリ使用量が増える想定）
    large_batch_task = {
        "type": "batch_transcribe",
        "segments": [
            {
                "start": i * 10.0,
                "end": (i + 1) * 10.0,
                "text": f"これはテストセグメント{i}です。" * 100,  # 大きなテキスト
            }
            for i in range(10)
        ],
        "audio_path": "/path/to/dummy/audio.wav",
        "chunk_duration": 10.0,
    }

    for i in range(pool.num_workers):
        pool.submit_task(f"batch_{i}", large_batch_task)
        print(f"→ Submitted large batch task to worker {i}")

    # メモリレポートを監視
    print("\n--- Monitoring Memory During Processing ---")
    processing_time = 15.0
    monitor_start = time.time()

    while time.time() - monitor_start < processing_time:
        msg = pool.get_result(timeout=0.5)

        if msg:
            if msg.msg_type == MessageType.MEMORY_STATUS:
                # メモリレポートを処理
                optimization_result = memory_manager.process_memory_report(msg)

                worker_status = memory_manager.monitor.worker_status.get(msg.worker_id)
                if worker_status:
                    print(
                        f"[{time.time() - monitor_start:.1f}s] {msg.worker_id}: "
                        f"{worker_status.memory_mb:.1f}MB "
                        f"({worker_status.memory_percent:.1f}%) "
                        f"- {worker_status.pressure_level.value}"
                    )

                    # 最適化提案を表示
                    suggestions = memory_manager.monitor.suggest_memory_optimization(msg.worker_id)
                    if suggestions:
                        for suggestion in suggestions[:1]:  # 最初の1つだけ表示
                            print(f"  💡 {suggestion}")

            elif msg.msg_type == MessageType.PROGRESS_UPDATE:
                if "メモリ" in msg.data.get("message", ""):
                    print(f"  ⚠️ {msg.data.get('message', '')}")

            elif msg.msg_type == MessageType.TASK_ERROR:
                print(f"  ✗ Task error: {msg.error}")

    # 最終メモリレポート
    print("\n--- Final Memory Report ---")
    final_report = memory_manager.get_memory_report()

    print(f"System Memory: {final_report['system']['percent']:.1f}%")
    print(f"Total Workers: {final_report['total_workers']}")
    print(f"Workers Under Pressure: {final_report['workers_under_pressure']}")

    print("\nWorker Details:")
    for worker in final_report["workers"]:
        print(f"\n{worker['worker_id']}:")
        print(f"  Memory: {worker['memory_mb']:.1f}MB ({worker['memory_percent']:.1f}%)")
        print(f"  Pressure Level: {worker['pressure_level']}")
        print(f"  GC Count: {worker['gc_count']}")
        print(f"  Restart Count: {worker['restart_count']}")

        if worker["suggestions"]:
            print("  Suggestions:")
            for suggestion in worker["suggestions"]:
                print(f"    - {suggestion}")

    # シャットダウン
    print("\n--- Shutdown ---")
    pool.shutdown()
    print("✓ Test completed!")

    # テスト結果のサマリー
    print("\n=== Test Summary ===")
    print(f"Memory reports received: {len(memory_reports)}")
    print(f"Workers requiring action: {final_report['workers_under_pressure']}")

    # 成功判定
    success = final_report["workers_under_pressure"] < pool.num_workers
    return success


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method("spawn", force=True)

    # テスト実行
    success = run_memory_management_test()

    # 終了コード
    sys.exit(0 if success else 1)
