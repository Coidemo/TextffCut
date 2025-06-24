"""
orchestratorプロセス分離の統合テスト

実際の文字起こしタスクをプロセス版ワーカーで実行し、
メモリ管理と並列処理の動作を確認する。
"""

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from orchestrator.process_communication import MessageType, ProcessPool
from orchestrator.transcription_worker_process import transcription_worker_process
from utils.logging import get_logger

logger = get_logger(__name__)


def run_integration_test():
    """統合テストを実行"""
    print("=== Orchestrator Integration Test ===")
    
    # テスト用の設定
    config = Config()
    
    # プロセスプールを作成（2ワーカー）
    pool = ProcessPool(num_workers=2)
    pool.start_workers(transcription_worker_process)
    
    # ワーカー準備完了を待つ
    ready_count = 0
    while ready_count < pool.num_workers:
        msg = pool.get_result(timeout=5.0)
        if msg and msg.msg_type == MessageType.WORKER_READY:
            ready_count += 1
            print(f"✓ {msg.worker_id} is ready")
    
    # 1. 初期化タスクを両ワーカーに送信
    print("\n--- Phase 1: Initialize Workers ---")
    init_task = {
        "type": "initialize",
        "model_size": "medium",
        "language": "ja",
        "device": "cpu",  # テスト環境用
        "compute_type": "int8"
    }
    
    for i in range(pool.num_workers):
        pool.submit_task(f"init_{i}", init_task)
        print(f"→ Sent initialization task to worker {i}")
    
    # 初期化結果を待つ
    init_results = []
    for i in range(pool.num_workers):
        result = pool.get_result(timeout=30.0)
        if result and result.msg_type == MessageType.TASK_RESULT:
            init_results.append(result)
            print(f"← Worker initialized: memory={result.data.get('current_memory_mb', 0):.1f}MB")
        elif result and result.msg_type == MessageType.TASK_ERROR:
            print(f"✗ Initialization failed: {result.error}")
            pool.shutdown()
            return
    
    # 2. メモリ状況の確認
    print("\n--- Phase 2: Memory Status Check ---")
    time.sleep(1)  # 少し待機
    
    # メモリ状況を確認（キューに入っているメッセージを取得）
    memory_reports = []
    while True:
        msg = pool.get_result(timeout=0.1)
        if msg is None:
            break
        if msg.msg_type == MessageType.MEMORY_STATUS:
            memory_reports.append(msg)
            print(f"← Memory report from {msg.worker_id}: {msg.data.get('memory_percent', 0):.1f}%")
    
    # 3. ダミーセグメントでの並列処理テスト
    print("\n--- Phase 3: Parallel Processing Test ---")
    
    # ダミーセグメントを作成
    dummy_segments = [
        {
            "segment": {
                "start": i * 10.0,
                "end": (i + 1) * 10.0,
                "text": f"これはテストセグメント{i}です。"
            },
            "audio_path": "/path/to/dummy/audio.wav",  # 実際のファイルは不要（エラーになるがテスト用）
            "chunk_duration": 10.0
        }
        for i in range(4)
    ]
    
    # セグメント処理タスクを送信
    print(f"Submitting {len(dummy_segments)} segment tasks...")
    for i, segment_data in enumerate(dummy_segments):
        task_data = {
            "type": "transcribe_segment",
            **segment_data
        }
        pool.submit_task(f"segment_{i}", task_data)
        print(f"→ Submitted segment {i}")
    
    # 結果を収集
    results = []
    errors = []
    for i in range(len(dummy_segments)):
        result = pool.get_result(timeout=10.0)
        if result:
            if result.msg_type == MessageType.TASK_RESULT:
                results.append(result)
                print(f"← Segment processed by {result.worker_id}")
            elif result.msg_type == MessageType.TASK_ERROR:
                errors.append(result)
                print(f"✗ Segment error: {result.error}")
            elif result.msg_type == MessageType.PROGRESS_UPDATE:
                print(f"  Progress: {result.data.get('progress', 0):.1%} - {result.data.get('message', '')}")
    
    # 4. バッチ処理テスト
    print("\n--- Phase 4: Batch Processing Test ---")
    
    batch_task = {
        "type": "batch_transcribe",
        "segments": dummy_segments[:2],  # 2セグメントのバッチ
        "audio_path": "/path/to/dummy/audio.wav",
        "chunk_duration": 10.0
    }
    
    pool.submit_task("batch_task", batch_task)
    print("→ Submitted batch task")
    
    # バッチ結果を待つ
    batch_result = pool.get_result(timeout=15.0)
    if batch_result:
        if batch_result.msg_type == MessageType.TASK_RESULT:
            print(f"← Batch completed: {batch_result.data.get('processed_count', 0)} segments")
        elif batch_result.msg_type == MessageType.TASK_ERROR:
            print(f"✗ Batch error: {batch_result.error}")
    
    # 5. シャットダウン
    print("\n--- Phase 5: Shutdown ---")
    pool.shutdown()
    print("✓ Test completed!")
    
    # 結果サマリー
    print("\n=== Test Summary ===")
    print(f"Workers initialized: {len(init_results)}")
    print(f"Memory reports received: {len(memory_reports)}")
    print(f"Segments processed: {len(results)}")
    print(f"Errors encountered: {len(errors)}")
    
    return len(errors) == 0


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method('spawn', force=True)
    
    # テスト実行
    success = run_integration_test()
    
    # 終了コード
    sys.exit(0 if success else 1)