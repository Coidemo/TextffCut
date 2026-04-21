"""
ワーカーライフサイクル管理モジュール

ワーカープロセスの自動再起動とライフサイクル管理を行う。
メモリリークやクラッシュからの自動復旧を実現。
"""

import multiprocessing as mp
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.memory_manager import ProcessMemoryManager
from orchestrator.process_communication import MessageType, ProcessMessage, ProcessPool
from utils.logging import get_logger

logger = get_logger(__name__)


class WorkerState(Enum):
    """ワーカーの状態"""

    INITIALIZING = "initializing"
    READY = "ready"
    PROCESSING = "processing"
    RESTARTING = "restarting"
    TERMINATED = "terminated"
    FAILED = "failed"


@dataclass
class WorkerInfo:
    """ワーカー情報"""

    worker_id: str
    process: mp.Process
    state: WorkerState
    started_at: datetime
    task_count: int = 0
    error_count: int = 0
    restart_count: int = 0
    last_heartbeat: datetime | None = None
    current_task_id: str | None = None


class WorkerLifecycleManager:
    """ワーカーのライフサイクル管理"""

    def __init__(
        self,
        worker_func: Callable,
        worker_args: tuple = (),
        num_workers: int = 2,
        max_restart_count: int = 3,
        heartbeat_timeout: float = 30.0,
    ) -> None:
        """
        初期化

        Args:
            worker_func: ワーカー関数
            worker_args: ワーカーに渡す追加引数
            num_workers: ワーカー数
            max_restart_count: 最大再起動回数
            heartbeat_timeout: ハートビートタイムアウト（秒）
        """
        self.worker_func = worker_func
        self.worker_args = worker_args
        self.num_workers = num_workers
        self.max_restart_count = max_restart_count
        self.heartbeat_timeout = heartbeat_timeout

        # プロセスプールとメモリマネージャー
        self.pool = ProcessPool(num_workers=num_workers)
        self.memory_manager = ProcessMemoryManager()

        # ワーカー情報
        self.workers: dict[str, WorkerInfo] = {}
        self.failed_workers: set[str] = set()

        # 監視設定
        self.monitoring_interval = 5.0
        self.last_monitor_time = time.time()

        logger.info(f"WorkerLifecycleManager initialized with {num_workers} workers")

    def start(self):
        """ワーカーを起動"""
        logger.info("Starting worker lifecycle manager")

        # 初期ワーカーを起動
        for i in range(self.num_workers):
            worker_id = f"worker_{i}"
            self._start_worker(worker_id)

        # 準備完了を待つ
        self._wait_for_workers_ready()

    def _start_worker(self, worker_id: str) -> bool:
        """個別ワーカーを起動"""
        try:
            # プロセスを作成
            args = (self.pool.request_queue, self.pool.response_queue, worker_id) + self.worker_args
            process = mp.Process(target=self.worker_func, args=args, name=worker_id)
            process.start()

            # ワーカー情報を記録
            worker_info = WorkerInfo(
                worker_id=worker_id, process=process, state=WorkerState.INITIALIZING, started_at=datetime.now()
            )

            # 既存のワーカー情報があれば一部引き継ぐ
            if worker_id in self.workers:
                old_info = self.workers[worker_id]
                worker_info.restart_count = old_info.restart_count + 1
                worker_info.task_count = old_info.task_count
                worker_info.error_count = old_info.error_count

            self.workers[worker_id] = worker_info
            self.pool.workers[worker_id] = process

            logger.info(f"Started worker {worker_id} (PID: {process.pid})")
            return True

        except Exception as e:
            logger.error(f"Failed to start worker {worker_id}: {e}")
            self.failed_workers.add(worker_id)
            return False

    def _wait_for_workers_ready(self, timeout: float = 30.0):
        """ワーカーの準備完了を待つ"""
        start_time = time.time()
        ready_workers = set()

        while len(ready_workers) < len(self.workers) and time.time() - start_time < timeout:
            msg = self.pool.get_result(timeout=1.0)

            if msg and msg.msg_type == MessageType.WORKER_READY:
                worker_id = msg.worker_id
                if worker_id in self.workers:
                    self.workers[worker_id].state = WorkerState.READY
                    self.workers[worker_id].last_heartbeat = datetime.now()
                    ready_workers.add(worker_id)
                    logger.info(f"Worker {worker_id} is ready")

        if len(ready_workers) < len(self.workers):
            logger.warning(f"Only {len(ready_workers)}/{len(self.workers)} workers became ready")

    def submit_task(self, task_id: str, task_data: dict[str, Any]):
        """タスクを投入"""
        self.pool.submit_task(task_id, task_data)

    def process_messages(self, timeout: float = 0.1) -> list[ProcessMessage]:
        """メッセージを処理"""
        messages = []
        processed_messages = []

        # メッセージを収集
        while True:
            msg = self.pool.get_result(timeout=timeout)
            if msg is None:
                break
            messages.append(msg)

        # メッセージを処理
        for msg in messages:
            self._process_message(msg)
            processed_messages.append(msg)

        # 定期監視
        if self._should_monitor():
            self._monitor_workers()

        return processed_messages

    def _process_message(self, msg: ProcessMessage):
        """個別メッセージを処理"""
        worker_id = msg.worker_id

        if worker_id and worker_id in self.workers:
            worker_info = self.workers[worker_id]

            # ハートビート更新
            worker_info.last_heartbeat = datetime.now()

            # メッセージタイプに応じた処理
            if msg.msg_type == MessageType.TASK_RESULT:
                worker_info.state = WorkerState.READY
                worker_info.current_task_id = None
                worker_info.task_count += 1

            elif msg.msg_type == MessageType.TASK_ERROR:
                worker_info.error_count += 1
                worker_info.state = WorkerState.READY
                worker_info.current_task_id = None

            elif msg.msg_type == MessageType.MEMORY_STATUS:
                # メモリ状態を処理
                optimization_result = self.memory_manager.process_memory_report(msg)

                if optimization_result and optimization_result.get("restart_required"):
                    logger.warning(f"Worker {worker_id} requires restart due to memory pressure")
                    self._schedule_restart(worker_id, "memory_pressure")

            elif msg.msg_type == MessageType.TASK_REQUEST:
                # ワーカーがタスクを開始
                worker_info.state = WorkerState.PROCESSING
                worker_info.current_task_id = msg.task_id

    def _should_monitor(self) -> bool:
        """監視が必要かどうか"""
        current_time = time.time()
        if current_time - self.last_monitor_time >= self.monitoring_interval:
            self.last_monitor_time = current_time
            return True
        return False

    def _monitor_workers(self):
        """ワーカーを監視"""
        current_time = datetime.now()

        for worker_id, worker_info in self.workers.items():
            # プロセスの生存確認
            if not worker_info.process.is_alive():
                if worker_info.state != WorkerState.TERMINATED:
                    logger.error(f"Worker {worker_id} died unexpectedly")
                    self._handle_worker_failure(worker_id, "process_died")
                continue

            # ハートビートタイムアウトチェック
            if worker_info.last_heartbeat:
                time_since_heartbeat = (current_time - worker_info.last_heartbeat).total_seconds()
                if time_since_heartbeat > self.heartbeat_timeout:
                    logger.warning(f"Worker {worker_id} heartbeat timeout ({time_since_heartbeat:.1f}s)")
                    self._handle_worker_failure(worker_id, "heartbeat_timeout")

            # メモリ圧迫チェック
            if self.memory_manager.optimizer.should_restart_worker(worker_id):
                logger.warning(f"Worker {worker_id} needs restart due to memory issues")
                self._schedule_restart(worker_id, "memory_optimization")

    def _handle_worker_failure(self, worker_id: str, reason: str):
        """ワーカー障害を処理"""
        if worker_id not in self.workers:
            return

        worker_info = self.workers[worker_id]

        # 再起動回数をチェック
        if worker_info.restart_count >= self.max_restart_count:
            logger.error(f"Worker {worker_id} exceeded max restart count ({self.max_restart_count})")
            self._terminate_worker(worker_id)
            self.failed_workers.add(worker_id)
            return

        # 再起動をスケジュール
        self._schedule_restart(worker_id, reason)

    def _schedule_restart(self, worker_id: str, reason: str):
        """ワーカーの再起動をスケジュール"""
        if worker_id not in self.workers:
            return

        worker_info = self.workers[worker_id]

        if worker_info.state == WorkerState.RESTARTING:
            logger.info(f"Worker {worker_id} is already restarting")
            return

        logger.info(f"Scheduling restart for worker {worker_id} (reason: {reason})")
        worker_info.state = WorkerState.RESTARTING

        # プロセスを終了
        self._terminate_worker(worker_id, graceful=True)

        # 少し待ってから再起動
        time.sleep(1.0)

        # 再起動
        if self._start_worker(worker_id):
            logger.info(f"Worker {worker_id} restarted successfully")
        else:
            logger.error(f"Failed to restart worker {worker_id}")

    def _terminate_worker(self, worker_id: str, graceful: bool = True):
        """ワーカーを終了"""
        if worker_id not in self.workers:
            return

        worker_info = self.workers[worker_id]
        process = worker_info.process

        if process.is_alive():
            if graceful:
                # グレースフルシャットダウン
                msg = ProcessMessage(msg_type=MessageType.WORKER_SHUTDOWN)
                self.pool.request_queue.put(msg)

                # 終了を待つ
                process.join(timeout=5.0)

            # 強制終了
            if process.is_alive():
                logger.warning(f"Force terminating worker {worker_id}")
                process.terminate()
                process.join(timeout=5.0)

                if process.is_alive():
                    process.kill()

        worker_info.state = WorkerState.TERMINATED

    def get_status(self) -> dict[str, Any]:
        """ステータスを取得"""
        active_workers = sum(1 for w in self.workers.values() if w.state in [WorkerState.READY, WorkerState.PROCESSING])

        worker_details = []
        for worker_id, worker_info in self.workers.items():
            uptime = (datetime.now() - worker_info.started_at).total_seconds()

            worker_details.append(
                {
                    "worker_id": worker_id,
                    "state": worker_info.state.value,
                    "pid": worker_info.process.pid if worker_info.process else None,
                    "uptime_seconds": uptime,
                    "task_count": worker_info.task_count,
                    "error_count": worker_info.error_count,
                    "restart_count": worker_info.restart_count,
                    "current_task": worker_info.current_task_id,
                }
            )

        # メモリレポートを含める
        memory_report = self.memory_manager.get_memory_report()

        return {
            "total_workers": len(self.workers),
            "active_workers": active_workers,
            "failed_workers": len(self.failed_workers),
            "workers": worker_details,
            "memory": memory_report,
        }

    def shutdown(self, timeout: float = 30.0):
        """シャットダウン"""
        logger.info("Shutting down worker lifecycle manager")

        # すべてのワーカーを終了
        for worker_id in list(self.workers.keys()):
            self._terminate_worker(worker_id, graceful=True)

        # プールをシャットダウン
        self.pool.shutdown(timeout=timeout)

        logger.info("Worker lifecycle manager shutdown complete")


# テスト用関数
def test_lifecycle_manager():
    """ライフサイクル管理のテスト"""
    from orchestrator.transcription_worker_process import transcription_worker_process

    print("=== Worker Lifecycle Manager Test ===")

    # マネージャーを作成
    manager = WorkerLifecycleManager(
        worker_func=transcription_worker_process, num_workers=2, max_restart_count=2, heartbeat_timeout=20.0
    )

    # ワーカーを起動
    manager.start()

    # 初期化タスクを送信
    print("\n--- Initializing Workers ---")
    for i in range(manager.num_workers):
        init_task = {"type": "initialize", "model_size": "large-v3", "language": "ja"}
        manager.submit_task(f"init_{i}", init_task)

    # メッセージ処理とステータス表示
    print("\n--- Processing Messages ---")
    test_duration = 30.0
    start_time = time.time()
    message_count = 0

    while time.time() - start_time < test_duration:
        # メッセージを処理
        messages = manager.process_messages(timeout=0.5)
        message_count += len(messages)

        # 定期的にステータスを表示
        if int(time.time() - start_time) % 5 == 0:
            status = manager.get_status()
            print(f"\n[{time.time() - start_time:.0f}s] Status:")
            print(f"  Active workers: {status['active_workers']}/{status['total_workers']}")
            print(f"  Failed workers: {status['failed_workers']}")

            for worker in status["workers"]:
                print(
                    f"  {worker['worker_id']}: {worker['state']} "
                    f"(tasks: {worker['task_count']}, errors: {worker['error_count']}, "
                    f"restarts: {worker['restart_count']})"
                )

        time.sleep(1.0)

    # 最終ステータス
    print("\n--- Final Status ---")
    final_status = manager.get_status()
    print(f"Total messages processed: {message_count}")
    print(f"Active workers: {final_status['active_workers']}")
    print(f"Failed workers: {final_status['failed_workers']}")

    # シャットダウン
    print("\n--- Shutdown ---")
    manager.shutdown()
    print("✓ Test completed!")


if __name__ == "__main__":
    # マルチプロセシングの開始方法を設定
    mp.set_start_method("spawn", force=True)

    # テスト実行
    test_lifecycle_manager()
