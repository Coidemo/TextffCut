"""
プロセス間通信の基盤実装

orchestratorのプロセス分離実装に必要な通信機構を提供します。
multiprocessing.Queueを使用したメッセージパッシングを実装。
"""

import multiprocessing as mp
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from multiprocessing import Queue
from pathlib import Path
from typing import Any

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging import get_logger

logger = get_logger(__name__)


class MessageType(Enum):
    """メッセージタイプの定義"""

    # タスク関連
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    TASK_ERROR = "task_error"

    # 制御関連
    WORKER_READY = "worker_ready"
    WORKER_SHUTDOWN = "worker_shutdown"
    HEARTBEAT = "heartbeat"

    # 進捗関連
    PROGRESS_UPDATE = "progress_update"
    STATUS_UPDATE = "status_update"

    # メモリ管理
    MEMORY_STATUS = "memory_status"
    MEMORY_WARNING = "memory_warning"


@dataclass
class ProcessMessage:
    """プロセス間で送受信するメッセージ"""

    msg_type: MessageType
    worker_id: str | None = None
    task_id: str | None = None
    data: dict[str, Any] | None = None
    error: str | None = None
    timestamp: float = None

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "msg_type": self.msg_type.value,
            "worker_id": self.worker_id,
            "task_id": self.task_id,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProcessMessage":
        """辞書から復元"""
        return cls(
            msg_type=MessageType(data["msg_type"]),
            worker_id=data.get("worker_id"),
            task_id=data.get("task_id"),
            data=data.get("data"),
            error=data.get("error"),
            timestamp=data.get("timestamp"),
        )


class ProcessCommunicator:
    """プロセス間通信を管理するクラス"""

    def __init__(self, request_queue: Queue, response_queue: Queue, worker_id: str) -> None:
        """初期化

        Args:
            request_queue: タスクリクエストを受け取るキュー
            response_queue: 結果を送信するキュー
            worker_id: ワーカーの識別子
        """
        self.request_queue = request_queue
        self.response_queue = response_queue
        self.worker_id = worker_id
        self._running = False

    def send_ready(self) -> None:
        """ワーカー準備完了を通知"""
        msg = ProcessMessage(msg_type=MessageType.WORKER_READY, worker_id=self.worker_id)
        self.response_queue.put(msg)
        logger.info(f"Worker {self.worker_id} ready")

    def send_result(self, task_id: str, result: dict[str, Any]) -> None:
        """処理結果を送信"""
        msg = ProcessMessage(msg_type=MessageType.TASK_RESULT, worker_id=self.worker_id, task_id=task_id, data=result)
        self.response_queue.put(msg)

    def send_error(self, task_id: str, error: Exception) -> None:
        """エラーを送信"""
        msg = ProcessMessage(
            msg_type=MessageType.TASK_ERROR,
            worker_id=self.worker_id,
            task_id=task_id,
            error=str(error),
            data={"traceback": traceback.format_exc()},
        )
        self.response_queue.put(msg)

    def send_progress(self, task_id: str, progress: float, message: str) -> None:
        """進捗を送信"""
        msg = ProcessMessage(
            msg_type=MessageType.PROGRESS_UPDATE,
            worker_id=self.worker_id,
            task_id=task_id,
            data={"progress": progress, "message": message},
        )
        self.response_queue.put(msg)

    def send_memory_status(self, memory_usage: float) -> None:
        """メモリ使用状況を送信"""
        msg = ProcessMessage(
            msg_type=MessageType.MEMORY_STATUS, worker_id=self.worker_id, data={"memory_usage": memory_usage}
        )
        self.response_queue.put(msg)

    def receive_task(self, timeout: float | None = None) -> ProcessMessage | None:
        """タスクを受信

        Args:
            timeout: タイムアウト秒数

        Returns:
            受信したメッセージ（タイムアウト時はNone）
        """
        try:
            if timeout:
                return self.request_queue.get(timeout=timeout)
            else:
                return self.request_queue.get()
        except mp.queues.Empty:
            return None
        except Exception as e:
            logger.error(f"Error receiving task: {e}")
            return None

    def start(self) -> None:
        """通信開始"""
        self._running = True
        self.send_ready()

    def stop(self) -> None:
        """通信停止"""
        self._running = False
        msg = ProcessMessage(msg_type=MessageType.WORKER_SHUTDOWN, worker_id=self.worker_id)
        self.response_queue.put(msg)


class ProcessPool:
    """ワーカープロセスのプールを管理"""

    def __init__(self, num_workers: int = None) -> None:
        """初期化

        Args:
            num_workers: ワーカー数（Noneの場合は自動決定）
        """
        if num_workers is None:
            num_workers = min(mp.cpu_count() - 1, 4)  # 最大4プロセス

        self.num_workers = max(1, num_workers)
        self.request_queue = mp.Queue()
        self.response_queue = mp.Queue()
        self.workers: dict[str, mp.Process] = {}
        self._running = False

        logger.info(f"ProcessPool initialized with {self.num_workers} workers")

    def start_workers(self, worker_func: Callable, worker_args: tuple = ()) -> None:
        """ワーカープロセスを起動

        Args:
            worker_func: ワーカー関数
            worker_args: ワーカーに渡す追加引数
        """
        self._running = True

        for i in range(self.num_workers):
            worker_id = f"worker_{i}"
            args = (self.request_queue, self.response_queue, worker_id) + worker_args

            process = mp.Process(target=worker_func, args=args, name=worker_id)
            process.start()
            self.workers[worker_id] = process

        logger.info(f"Started {len(self.workers)} worker processes")

    def submit_task(self, task_id: str, task_data: dict[str, Any]) -> None:
        """タスクを投入

        Args:
            task_id: タスクID
            task_data: タスクデータ
        """
        msg = ProcessMessage(msg_type=MessageType.TASK_REQUEST, task_id=task_id, data=task_data)
        self.request_queue.put(msg)

    def get_result(self, timeout: float | None = None) -> ProcessMessage | None:
        """結果を取得

        Args:
            timeout: タイムアウト秒数

        Returns:
            結果メッセージ
        """
        try:
            if timeout:
                return self.response_queue.get(timeout=timeout)
            else:
                return self.response_queue.get()
        except mp.queues.Empty:
            return None

    def shutdown(self, timeout: float = 30) -> None:
        """プロセスプールをシャットダウン

        Args:
            timeout: シャットダウンタイムアウト
        """
        if not self._running:
            return

        self._running = False

        # シャットダウンメッセージを送信
        for _ in range(len(self.workers)):
            msg = ProcessMessage(msg_type=MessageType.WORKER_SHUTDOWN)
            self.request_queue.put(msg)

        # ワーカーの終了を待つ
        start_time = time.time()
        for worker_id, process in self.workers.items():
            remaining_time = max(0, timeout - (time.time() - start_time))
            process.join(timeout=remaining_time)

            if process.is_alive():
                logger.warning(f"Force terminating worker {worker_id}")
                process.terminate()
                process.join(timeout=5)

        self.workers.clear()
        logger.info("ProcessPool shutdown complete")


def echo_worker(request_queue: Queue, response_queue: Queue, worker_id: str) -> None:
    """テスト用のエコーワーカー"""
    communicator = ProcessCommunicator(request_queue, response_queue, worker_id)
    communicator.start()

    try:
        while True:
            msg = communicator.receive_task(timeout=1.0)

            if msg is None:
                continue

            if msg.msg_type == MessageType.WORKER_SHUTDOWN:
                break

            if msg.msg_type == MessageType.TASK_REQUEST:
                # エコー処理
                result = {"echo": msg.data.get("message", ""), "worker": worker_id, "timestamp": time.time()}
                communicator.send_result(msg.task_id, result)

    except Exception as e:
        logger.error(f"Echo worker error: {e}")
    finally:
        communicator.stop()


# テスト用関数
def test_process_communication() -> None:
    """プロセス間通信の動作確認"""
    print("=== Process Communication Test ===")

    # プロセスプールを作成
    pool = ProcessPool(num_workers=2)
    pool.start_workers(echo_worker)

    # ワーカー準備完了を待つ
    ready_count = 0
    while ready_count < pool.num_workers:
        msg = pool.get_result(timeout=5.0)
        if msg and msg.msg_type == MessageType.WORKER_READY:
            ready_count += 1
            print(f"✓ {msg.worker_id} is ready")

    # テストタスクを送信
    test_messages = ["Hello", "World", "Process", "Communication"]
    for i, message in enumerate(test_messages):
        task_id = f"test_task_{i}"
        pool.submit_task(task_id, {"message": message})
        print(f"→ Submitted: {task_id} - {message}")

    # 結果を受信
    results_received = 0
    while results_received < len(test_messages):
        msg = pool.get_result(timeout=5.0)
        if msg and msg.msg_type == MessageType.TASK_RESULT:
            results_received += 1
            echo = msg.data.get("echo", "")
            worker = msg.data.get("worker", "")
            print(f"← Received: {msg.task_id} - {echo} (from {worker})")

    # シャットダウン
    pool.shutdown()
    print("✓ Test completed successfully!")


if __name__ == "__main__":
    # 動作確認テストを実行
    test_process_communication()
