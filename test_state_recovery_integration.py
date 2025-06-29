"""
状態復旧機能の統合テスト

ProcessingStateManagerとTranscriptionWorkerの
統合動作を確認する。
"""

import multiprocessing as mp
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from orchestrator.process_communication import MessageType, ProcessPool
from orchestrator.processing_state_manager import ProcessingStateManager, check_and_recover_on_startup
from orchestrator.transcription_worker_with_recovery import ProcessTranscriptionWorkerWithRecovery
from utils.logging import get_logger

logger = get_logger(__name__)


def recovery_worker_process(request_queue, response_queue, worker_id, config_path=None) -> None:
    """リカバリー機能付きワーカープロセスのエントリーポイント"""
    try:
        from orchestrator.process_communication import ProcessCommunicator

        # 設定を読み込み
        config = Config(config_path) if config_path else Config()

        # 通信オブジェクトを作成
        communicator = ProcessCommunicator(request_queue, response_queue, worker_id)

        # リカバリー機能付きワーカーを作成して実行
        worker = ProcessTranscriptionWorkerWithRecovery(config, communicator)
        worker.run()

    except Exception as e:
        logger.error(f"Recovery worker process {worker_id} failed: {e}")


def test_basic_state_recovery() -> None:
    """基本的な状態復旧のテスト"""
    print("=== Basic State Recovery Test ===")

    # 状態マネージャーを初期化
    state_manager = ProcessingStateManager()

    # プロセスプールを作成（1ワーカー）
    pool = ProcessPool(num_workers=1)
    pool.start_workers(recovery_worker_process)

    # ワーカー準備完了を待つ
    msg = pool.get_result(timeout=5.0)
    if msg and msg.msg_type == MessageType.WORKER_READY:
        print(f"✓ Worker ready: {msg.worker_id}")

    # 1. 初期化タスクを送信
    print("\n--- Initialize Worker ---")
    init_task = {
        "type": "initialize",
        "model_size": "medium",
        "language": "ja",
        "device": "cpu",
        "compute_type": "int8",
    }

    pool.submit_task("init_task", init_task)
    result = pool.get_result(timeout=30.0)
    if result and result.msg_type == MessageType.TASK_RESULT:
        print(f"✓ Initialized: memory={result.data.get('current_memory_mb', 0):.1f}MB")

    # 2. バッチ処理を開始（途中で中断する）
    print("\n--- Start Batch Processing ---")
    test_video_path = "/test/videos/sample.mp4"

    # ダミーセグメントを作成
    segments = [{"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"Segment {i}"} for i in range(5)]

    batch_task = {
        "type": "batch_transcribe",
        "video_path": test_video_path,  # 状態保存のために動画パスを追加
        "segments": segments,
        "audio_path": "/tmp/dummy_audio.wav",
        "chunk_duration": 10.0,
    }

    pool.submit_task("batch_task", batch_task)
    print("→ Batch task submitted")

    # 少し処理を進めてから中断
    time.sleep(2.0)

    # 3. リカバリーチェック（処理中の状態を確認）
    print("\n--- Check Recovery Status ---")
    recovery_check_task = {
        "type": "recovery_check",
        "video_path": test_video_path,
    }

    pool.submit_task("recovery_check", recovery_check_task)

    # 結果を収集（タイムアウト短めで）
    recovery_result = None
    start_time = time.time()
    while time.time() - start_time < 5.0:
        msg = pool.get_result(timeout=0.5)
        if msg:
            if msg.msg_type == MessageType.TASK_RESULT and msg.task_id == "recovery_check":
                recovery_result = msg.data
                break
            elif msg.msg_type == MessageType.PROGRESS_UPDATE:
                print(f"  Progress: {msg.data.get('progress', 0):.0%} - {msg.data.get('message', '')}")

    if recovery_result and recovery_result.get("recoverable"):
        print("✓ Recovery info found:")
        info = recovery_result["recovery_info"]
        print(f"  State: {info['state']}")
        print(f"  Progress: {info['progress']:.0%}")
        print(f"  Message: {info['message']}")
    else:
        print("ℹ No recovery info found (processing may have completed)")

    # 4. シャットダウン
    print("\n--- Shutdown ---")
    pool.shutdown()

    # 5. 状態ファイルの確認
    print("\n--- Verify State Files ---")
    states = state_manager.list_states()
    print(f"Remaining state files: {len(states)}")
    for state in states:
        print(f"  - {Path(state['video_path']).name}: {state['state']} ({state['progress']:.0%})")

    # クリーンアップ
    if test_video_path:
        state_manager.clear_state(test_video_path)

    print("\n✓ Basic recovery test completed!")


def test_startup_recovery_flow() -> None:
    """起動時のリカバリーフローのテスト"""
    print("\n=== Startup Recovery Flow Test ===")

    state_manager = ProcessingStateManager()

    # 1. 中断された処理の状態を作成
    print("\n--- Create Interrupted States ---")
    interrupted_videos = [
        {
            "path": "/videos/video1.mp4",
            "state": "transcribing",
            "progress": 0.3,
            "data": {
                "total_chunks": 10,
                "chunks": [{"data": f"chunk_{i}"} for i in range(3)],
                "audio_path": "/tmp/video1_audio.wav",
            },
        },
        {
            "path": "/videos/video2.mp4",
            "state": "processing",
            "progress": 0.7,
            "data": {
                "step": "silence_removal",
                "segments_processed": 7,
                "total_segments": 10,
            },
        },
    ]

    for video_info in interrupted_videos:
        state_manager.save_state(video_info["path"], video_info["state"], video_info["data"], video_info["progress"])
        print(f"✓ Created state for {Path(video_info['path']).name}")

    # 2. 起動時のリカバリーチェック
    print("\n--- Check Startup Recovery ---")
    recoverable = check_and_recover_on_startup()

    print(f"✓ Found {len(recoverable)} recoverable processes:")
    for rec in recoverable:
        print(f"  - {Path(rec['video_path']).name}: " f"{rec['state']} ({rec['progress']:.0%})")
        print(f"    {rec['message']}")

    # 3. プロセスプールを開始してリカバリー処理
    print("\n--- Start Recovery Processing ---")
    pool = ProcessPool(num_workers=2)
    pool.start_workers(recovery_worker_process)

    # ワーカー準備完了を待つ
    ready_count = 0
    while ready_count < pool.num_workers:
        msg = pool.get_result(timeout=5.0)
        if msg and msg.msg_type == MessageType.WORKER_READY:
            ready_count += 1
            print(f"✓ Worker {msg.worker_id} ready")

    # 各リカバリー可能なプロセスに対してリカバリータスクを送信
    for i, rec in enumerate(recoverable):
        print(f"\n→ Submitting recovery for {Path(rec['video_path']).name}")

        # リカバリー情報に基づいてタスクを作成
        if rec["state"] == "transcribing":
            # 文字起こしの再開
            pending_chunks = list(range(len(rec["data"].get("chunks", [])), rec["data"].get("total_chunks", 10)))
            print(f"  Pending chunks: {pending_chunks}")

            # ダミータスクとして処理
            recovery_task = {
                "type": "batch_transcribe",
                "video_path": rec["video_path"],
                "segments": [
                    {"start": i * 10.0, "end": (i + 1) * 10.0, "text": f"Chunk {i}"}
                    for i in pending_chunks[:3]  # 最初の3つだけ処理
                ],
                "audio_path": rec["data"].get("audio_path", "/tmp/audio.wav"),
                "chunk_duration": 10.0,
            }
            pool.submit_task(f"recovery_{i}", recovery_task)

    # 処理結果を待つ
    print("\n--- Collect Recovery Results ---")
    results_collected = 0
    start_time = time.time()

    while results_collected < len(recoverable) and time.time() - start_time < 15.0:
        msg = pool.get_result(timeout=1.0)
        if msg:
            if msg.msg_type == MessageType.TASK_RESULT:
                results_collected += 1
                print("✓ Recovery task completed")
            elif msg.msg_type == MessageType.TASK_ERROR:
                results_collected += 1
                print(f"✗ Recovery task failed: {msg.error}")
            elif msg.msg_type == MessageType.PROGRESS_UPDATE:
                print(f"  Progress: {msg.data.get('message', '')}")

    # 4. シャットダウン
    print("\n--- Shutdown ---")
    pool.shutdown()

    # 5. 最終状態の確認
    print("\n--- Final State Check ---")
    final_states = state_manager.list_states()
    print(f"Remaining states: {len(final_states)}")

    # クリーンアップ
    for video_info in interrupted_videos:
        state_manager.clear_state(video_info["path"])

    print("\n✓ Startup recovery flow test completed!")


def test_cleanup_task() -> None:
    """クリーンアップタスクのテスト"""
    print("\n=== Cleanup Task Test ===")

    # プロセスプールを作成
    pool = ProcessPool(num_workers=1)
    pool.start_workers(recovery_worker_process)

    # ワーカー準備完了を待つ
    msg = pool.get_result(timeout=5.0)
    if msg and msg.msg_type == MessageType.WORKER_READY:
        print(f"✓ Worker ready: {msg.worker_id}")

    # クリーンアップタスクを送信
    print("\n--- Submit Cleanup Task ---")
    cleanup_task = {
        "type": "cleanup_states",
    }

    pool.submit_task("cleanup", cleanup_task)

    # 結果を待つ
    result = pool.get_result(timeout=5.0)
    if result and result.msg_type == MessageType.TASK_RESULT:
        deleted_count = result.data.get("deleted_count", 0)
        print(f"✓ Cleanup completed: {deleted_count} old states deleted")

    # シャットダウン
    pool.shutdown()
    print("\n✓ Cleanup task test completed!")


def run_all_tests() -> None:
    """すべてのテストを実行"""
    print("=== State Recovery Integration Tests ===\n")

    tests = [
        ("Basic State Recovery", test_basic_state_recovery),
        ("Startup Recovery Flow", test_startup_recovery_flow),
        ("Cleanup Task", test_cleanup_task),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ {test_name} failed: {e}")
            import traceback

            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 50)
    print(f"Tests passed: {passed}/{len(tests)}")
    print(f"Tests failed: {failed}/{len(tests)}")

    return failed == 0


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method("spawn", force=True)

    # テスト実行
    success = run_all_tests()

    # 終了コード
    sys.exit(0 if success else 1)
