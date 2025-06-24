"""
TranscriptionWorker with Recovery - リカバリー機能付き文字起こしワーカー

ProcessingStateManagerを統合し、処理中断時の自動復旧を可能にする。
"""

import gc
import sys
import time
from pathlib import Path
from typing import Any

import psutil

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import Config
from orchestrator.gc_optimizer import optimize_for_transcription
from orchestrator.process_communication import MessageType, ProcessCommunicator, ProcessMessage
from orchestrator.processing_state_manager import ProcessingStateManager, TranscriptionRecovery
from orchestrator.transcription_worker_process import ProcessTranscriptionWorker
from utils.logging import get_logger

logger = get_logger(__name__)


class ProcessTranscriptionWorkerWithRecovery(ProcessTranscriptionWorker):
    """リカバリー機能付きプロセス分離版文字起こしワーカー"""

    def __init__(self, config: Config, communicator: ProcessCommunicator) -> None:
        """初期化

        Args:
            config: 設定オブジェクト
            communicator: プロセス間通信オブジェクト
        """
        super().__init__(config, communicator)
        
        # 状態管理を初期化
        self.state_manager = ProcessingStateManager()
        self.recovery = TranscriptionRecovery(self.state_manager)
        
        # 現在処理中の動画パス
        self.current_video_path: str | None = None
        
        logger.info(f"ProcessTranscriptionWorkerWithRecovery initialized for worker {communicator.worker_id}")

    def _handle_transcribe_segment(self, task_id: str, task_data: dict[str, Any]) -> None:
        """単一セグメントの文字起こしタスクを処理（状態保存付き）"""
        try:
            segment_data = task_data.get("segment")
            audio_path = task_data.get("audio_path")
            chunk_duration = task_data.get("chunk_duration")
            video_path = task_data.get("video_path")
            
            # 動画パスが指定されている場合は状態を保存
            if video_path:
                self.current_video_path = video_path
                segment_index = task_data.get("segment_index", 0)
                total_segments = task_data.get("total_segments", 1)
                
                # 処理開始前に状態を保存
                self.state_manager.save_state(
                    video_path,
                    "transcribing",
                    {
                        "task_id": task_id,
                        "segment_index": segment_index,
                        "total_segments": total_segments,
                        "audio_path": audio_path,
                        "chunk_duration": chunk_duration,
                    },
                    progress=segment_index / total_segments
                )

            # 進捗通知
            self.communicator.send_progress(task_id, 0.1, "セグメントを処理中")

            # 処理実行
            result = self.process_segment(
                segment_data=segment_data, audio_path=audio_path, chunk_duration=chunk_duration
            )

            # 結果送信
            self.communicator.send_result(task_id, result)
            
            # 成功した場合、チャンク進捗を保存
            if video_path and "segment_index" in task_data:
                self.recovery.save_chunk_progress(
                    video_path,
                    task_data["segment_index"],
                    task_data.get("total_segments", 1),
                    result
                )

            # メモリ解放
            gc.collect()

        except Exception as e:
            self.communicator.send_error(task_id, e)
            
            # エラー時も状態を保存（リカバリー用）
            if self.current_video_path:
                self.state_manager.save_state(
                    self.current_video_path,
                    "error",
                    {
                        "task_id": task_id,
                        "error": str(e),
                        "segment_data": segment_data,
                    },
                    progress=task_data.get("segment_index", 0) / task_data.get("total_segments", 1)
                )

    def _handle_batch_transcribe(self, task_id: str, task_data: dict[str, Any]) -> None:
        """バッチ文字起こしタスクを処理（状態保存付き）"""
        try:
            segments = task_data.get("segments", [])
            audio_path = task_data.get("audio_path")
            chunk_duration = task_data.get("chunk_duration")
            video_path = task_data.get("video_path")
            
            # リカバリーチェック
            pending_indices = None
            if video_path:
                self.current_video_path = video_path
                
                # リカバリー情報をチェック
                recovery_info = self.recovery.check_recovery(video_path)
                if recovery_info and recovery_info.get("can_resume"):
                    # 未処理のセグメントインデックスを取得
                    pending_indices = self.recovery.get_pending_chunks(video_path, len(segments))
                    logger.info(f"Resuming batch processing: {len(pending_indices)} pending segments")
                else:
                    # 新規処理の場合、初期状態を保存
                    self.state_manager.save_state(
                        video_path,
                        "transcribing",
                        {
                            "task_id": task_id,
                            "total_segments": len(segments),
                            "audio_path": audio_path,
                            "chunk_duration": chunk_duration,
                            "chunks": [],
                        },
                        progress=0.0
                    )

            results = []
            
            # 処理するセグメントのインデックスを決定
            indices_to_process = pending_indices if pending_indices is not None else range(len(segments))

            for idx, i in enumerate(indices_to_process):
                if i >= len(segments):
                    continue
                    
                segment = segments[i]
                
                # 進捗通知
                actual_progress = (len(segments) - len(indices_to_process) + idx + 1) / len(segments)
                self.communicator.send_progress(
                    task_id, 
                    actual_progress, 
                    f"セグメント {i+1}/{len(segments)} を処理中"
                )

                # セグメント処理
                result = self.process_segment(
                    segment_data=segment, audio_path=audio_path, chunk_duration=chunk_duration
                )
                results.append(result)
                
                # チャンク進捗を保存
                if video_path:
                    self.recovery.save_chunk_progress(video_path, i, len(segments), result)

                # メモリチェックとGC最適化
                if self._check_memory_pressure():
                    logger.warning("Memory pressure detected, optimizing GC")
                    memory_percent = self.process.memory_percent()
                    gc_metrics = self.gc_optimizer.optimize_based_on_memory_pressure(memory_percent)
                    if gc_metrics:
                        logger.info(f"GC collected {gc_metrics.collected} objects in {gc_metrics.duration:.1f}ms")
                    time.sleep(0.1)  # 短い休憩

            # バッチ結果を送信
            batch_result = {"results": results, "processed_count": len(results)}
            self.communicator.send_result(task_id, batch_result)
            
            # 処理完了時に状態をクリア
            if video_path:
                self.state_manager.clear_state(video_path)

        except Exception as e:
            self.communicator.send_error(task_id, e)
            
            # エラー時の状態保存
            if self.current_video_path:
                self.state_manager.save_state(
                    self.current_video_path,
                    "error",
                    {
                        "task_id": task_id,
                        "error": str(e),
                        "batch_info": {
                            "total_segments": len(segments),
                            "processed": len(results) if 'results' in locals() else 0,
                        }
                    },
                    progress=len(results) / len(segments) if 'results' in locals() else 0.0
                )

    def _handle_recovery_check(self, task_id: str, task_data: dict[str, Any]) -> None:
        """リカバリーチェックタスクを処理"""
        try:
            video_path = task_data.get("video_path")
            
            if not video_path:
                self.communicator.send_result(task_id, {"recoverable": False})
                return
            
            # リカバリー情報をチェック
            recovery_info = self.recovery.check_recovery(video_path)
            
            if recovery_info:
                self.communicator.send_result(task_id, {
                    "recoverable": True,
                    "recovery_info": recovery_info
                })
            else:
                self.communicator.send_result(task_id, {"recoverable": False})
                
        except Exception as e:
            self.communicator.send_error(task_id, e)

    def _process_task(self, msg: ProcessMessage) -> None:
        """タスクを処理（拡張版）"""
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
            elif task_type == "recovery_check":
                self._handle_recovery_check(task_id, task_data)
            elif task_type == "cleanup_states":
                # 古い状態ファイルのクリーンアップ
                deleted = self.state_manager.cleanup_old_states()
                self.communicator.send_result(task_id, {"deleted_count": deleted})
            else:
                raise ValidationError(f"Unknown task type: {task_type}")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            self.communicator.send_error(task_id, e)

    def cleanup(self) -> None:
        """リソースのクリーンアップ（拡張版）"""
        # 現在処理中の状態があれば保存
        if self.current_video_path:
            self.state_manager.save_state(
                self.current_video_path,
                "interrupted",
                {
                    "worker_id": self.communicator.worker_id,
                    "timestamp": time.time(),
                },
                progress=-1  # 中断を示す特別な値
            )
        
        # 親クラスのクリーンアップを実行
        super().cleanup()


# テスト用関数
def test_recovery_worker():
    """リカバリー機能付きワーカーのテスト"""
    from multiprocessing import Queue
    from orchestrator.process_communication import ProcessCommunicator
    
    print("=== Recovery Worker Test ===")
    
    # キューを作成
    request_queue = Queue()
    response_queue = Queue()
    
    # 通信オブジェクトを作成
    communicator = ProcessCommunicator(request_queue, response_queue, "test_worker")
    
    # 設定を作成
    config = Config()
    
    # ワーカーを作成
    worker = ProcessTranscriptionWorkerWithRecovery(config, communicator)
    
    print("✓ Recovery worker created successfully")
    
    # リカバリーチェックタスクをシミュレート
    test_msg = ProcessMessage(
        msg_type=MessageType.TASK_REQUEST,
        task_id="recovery_test",
        data={
            "type": "recovery_check",
            "video_path": "/test/video.mp4"
        }
    )
    
    worker._process_task(test_msg)
    print("✓ Recovery check processed")
    
    # クリーンアップ
    worker.cleanup()
    print("✓ Test completed!")


if __name__ == "__main__":
    test_recovery_worker()