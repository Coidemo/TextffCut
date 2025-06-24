"""
TranscriptionWorker - プロセス分離版実装

文字起こしワーカーをマルチプロセスで実行する実装。
メモリリークを防ぐため、各ワーカーは独立したプロセスで動作。
"""

import gc
import sys
import time
from multiprocessing import Queue
from pathlib import Path
from typing import Any

import psutil

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from core.error_handling import ValidationError
from orchestrator.process_communication import MessageType, ProcessCommunicator, ProcessMessage
from orchestrator.transcription_worker import TranscriptionWorker as BaseWorker
from utils.logging import get_logger

logger = get_logger(__name__)


class ProcessTranscriptionWorker(BaseWorker):
    """プロセス分離版の文字起こしワーカー"""

    def __init__(self, config: Config, communicator: ProcessCommunicator) -> None:
        """初期化

        Args:
            config: 設定オブジェクト
            communicator: プロセス間通信オブジェクト
        """
        super().__init__(config)
        self.communicator = communicator
        self.process = psutil.Process()
        self._last_memory_report = time.time()
        self._memory_report_interval = 10.0  # 10秒ごとにメモリ報告

    def run(self) -> None:
        """ワーカーのメインループ"""
        logger.info(f"Worker {self.communicator.worker_id} starting")
        self.communicator.start()

        try:
            while True:
                # メモリ状況を定期的に報告
                self._report_memory_if_needed()

                # タスクを待機
                msg = self.communicator.receive_task(timeout=1.0)

                if msg is None:
                    continue

                if msg.msg_type == MessageType.WORKER_SHUTDOWN:
                    logger.info(f"Worker {self.communicator.worker_id} received shutdown signal")
                    break

                if msg.msg_type == MessageType.TASK_REQUEST:
                    self._process_task(msg)

        except Exception as e:
            logger.error(f"Worker {self.communicator.worker_id} error: {e}")
        finally:
            self.cleanup()
            self.communicator.stop()
            logger.info(f"Worker {self.communicator.worker_id} stopped")

    def _process_task(self, msg: ProcessMessage) -> None:
        """タスクを処理

        Args:
            msg: タスクメッセージ
        """
        task_id = msg.task_id
        task_data = msg.data or {}

        try:
            logger.info(f"Processing task {task_id}")

            # タスクタイプに応じて処理
            task_type = task_data.get("type")

            if task_type == "initialize":
                self._handle_initialize(task_id, task_data)
            elif task_type == "transcribe_segment":
                self._handle_transcribe_segment(task_id, task_data)
            elif task_type == "batch_transcribe":
                self._handle_batch_transcribe(task_id, task_data)
            else:
                raise ValidationError(f"Unknown task type: {task_type}")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.communicator.send_error(task_id, e)

    def _handle_initialize(self, task_id: str, task_data: dict[str, Any]) -> None:
        """エンジン初期化タスクを処理"""
        try:
            model_size = task_data.get("model_size", "medium")
            language = task_data.get("language", "ja")
            device = task_data.get("device", "auto")
            compute_type = task_data.get("compute_type", "int8")

            # 初期化前のメモリチェック
            memory_before = self._get_memory_usage()

            self.initialize_transcriber(
                model_size=model_size, language=language, device=device, compute_type=compute_type
            )

            # 初期化後のメモリチェック
            memory_after = self._get_memory_usage()
            model_memory = memory_after - memory_before

            result = {"status": "initialized", "model_memory_mb": model_memory, "current_memory_mb": memory_after}

            self.communicator.send_result(task_id, result)
            logger.info(f"Initialized with {model_size} model, using {model_memory:.1f}MB")

        except Exception as e:
            self.communicator.send_error(task_id, e)

    def _handle_transcribe_segment(self, task_id: str, task_data: dict[str, Any]) -> None:
        """単一セグメントの文字起こしタスクを処理"""
        try:
            segment_data = task_data.get("segment")
            audio_path = task_data.get("audio_path")
            chunk_duration = task_data.get("chunk_duration")

            # 進捗通知
            self.communicator.send_progress(task_id, 0.1, "セグメントを処理中")

            # 処理実行
            result = self.process_segment(
                segment_data=segment_data, audio_path=audio_path, chunk_duration=chunk_duration
            )

            # 結果送信
            self.communicator.send_result(task_id, result)

            # メモリ解放
            gc.collect()

        except Exception as e:
            self.communicator.send_error(task_id, e)

    def _handle_batch_transcribe(self, task_id: str, task_data: dict[str, Any]) -> None:
        """バッチ文字起こしタスクを処理"""
        try:
            segments = task_data.get("segments", [])
            audio_path = task_data.get("audio_path")
            chunk_duration = task_data.get("chunk_duration")

            results = []

            for i, segment in enumerate(segments):
                # 進捗通知
                progress = (i + 1) / len(segments)
                self.communicator.send_progress(task_id, progress, f"セグメント {i+1}/{len(segments)} を処理中")

                # セグメント処理
                result = self.process_segment(
                    segment_data=segment, audio_path=audio_path, chunk_duration=chunk_duration
                )
                results.append(result)

                # メモリチェック
                if self._check_memory_pressure():
                    logger.warning("Memory pressure detected, forcing GC")
                    gc.collect()
                    time.sleep(0.1)  # 短い休憩

            # バッチ結果を送信
            batch_result = {"results": results, "processed_count": len(results)}
            self.communicator.send_result(task_id, batch_result)

        except Exception as e:
            self.communicator.send_error(task_id, e)

    def _get_memory_usage(self) -> float:
        """現在のメモリ使用量を取得（MB）"""
        return self.process.memory_info().rss / 1024 / 1024

    def _check_memory_pressure(self) -> bool:
        """メモリ圧迫をチェック"""
        memory_mb = self._get_memory_usage()
        memory_percent = self.process.memory_percent()

        # 2GB以上または50%以上使用している場合は圧迫と判定
        return memory_mb > 2048 or memory_percent > 50

    def _report_memory_if_needed(self) -> None:
        """必要に応じてメモリ状況を報告"""
        current_time = time.time()

        if current_time - self._last_memory_report > self._memory_report_interval:
            # 詳細なメモリ情報を収集
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = self.process.memory_percent()
            
            # メモリステータスメッセージを送信
            msg = ProcessMessage(
                msg_type=MessageType.MEMORY_STATUS,
                worker_id=self.communicator.worker_id,
                data={
                    "pid": self.process.pid,
                    "memory_mb": memory_mb,
                    "memory_percent": memory_percent,
                    "memory_usage": memory_percent  # 互換性のため
                }
            )
            self.communicator.response_queue.put(msg)
            self._last_memory_report = current_time

            # メモリ警告
            if memory_percent > 80:
                logger.warning(f"High memory usage: {memory_percent:.1f}%")
                self.communicator.send_progress(
                    task_id="memory_warning",
                    progress=memory_percent / 100,
                    message=f"メモリ使用率が高くなっています: {memory_percent:.1f}%",
                )


def transcription_worker_process(
    request_queue: Queue, response_queue: Queue, worker_id: str, config_path: str | None = None
) -> None:
    """文字起こしワーカープロセスのエントリーポイント

    Args:
        request_queue: リクエストキュー
        response_queue: レスポンスキュー
        worker_id: ワーカーID
        config_path: 設定ファイルパス
    """
    try:
        # 設定を読み込み
        config = Config(config_path) if config_path else Config()

        # 通信オブジェクトを作成
        communicator = ProcessCommunicator(request_queue, response_queue, worker_id)

        # ワーカーを作成して実行
        worker = ProcessTranscriptionWorker(config, communicator)
        worker.run()

    except Exception as e:
        logger.error(f"Worker process {worker_id} failed: {e}")


# テスト用関数
def test_process_worker() -> None:
    """プロセス版ワーカーの動作確認"""
    from orchestrator.process_communication import ProcessPool

    print("=== Process Worker Test ===")

    # プロセスプールを作成
    pool = ProcessPool(num_workers=1)
    pool.start_workers(transcription_worker_process)

    # ワーカー準備完了を待つ
    msg = pool.get_result(timeout=5.0)
    if msg and msg.msg_type == MessageType.WORKER_READY:
        print(f"✓ Worker ready: {msg.worker_id}")

    # 初期化タスクを送信
    init_task = {"type": "initialize", "model_size": "medium", "language": "ja"}
    pool.submit_task("init_task", init_task)
    print("→ Sent initialization task")

    # 結果を待つ
    result = pool.get_result(timeout=30.0)
    if result and result.msg_type == MessageType.TASK_RESULT:
        print(f"← Initialization complete: {result.data}")
    elif result and result.msg_type == MessageType.TASK_ERROR:
        print(f"✗ Initialization failed: {result.error}")

    # シャットダウン
    pool.shutdown()
    print("✓ Test completed!")


if __name__ == "__main__":
    test_process_worker()
