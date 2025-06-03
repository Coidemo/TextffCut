"""
Producer-Consumerパターンによるキュー管理システム
APIタスクとアライメントタスクを効率的に並列処理する
"""
import queue
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable
from concurrent.futures import ThreadPoolExecutor
import time

from utils.logging import get_logger
from utils.system_resources import system_resource_manager

logger = get_logger(__name__)


@dataclass
class APITask:
    """API処理タスク"""
    chunk_idx: int
    chunk_file: str
    start_offset: float
    priority: int = 0  # 優先度（小さいほど優先）


@dataclass
class AlignmentTask:
    """アライメント処理タスク"""
    chunk_idx: int
    segments: List[Dict[str, Any]]
    chunk_file: str
    start_offset: float
    priority: int = 0


@dataclass
class ProcessingResult:
    """処理結果"""
    chunk_idx: int
    segments: List[Any]
    success: bool
    error: Optional[str] = None


class TaskQueueManager:
    """タスクキュー管理クラス"""
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        # キュー
        self.api_queue = queue.PriorityQueue()
        self.alignment_queue = queue.PriorityQueue()
        self.result_queue = queue.Queue()
        
        # 進捗管理
        self.total_chunks = 0
        self.completed_api_tasks = 0
        self.completed_align_tasks = 0
        self.progress_callback = progress_callback
        
        # スレッド管理
        self.api_executor = None
        self.align_executor = None
        self.shutdown_event = threading.Event()
        
        # エラー管理
        self.errors = []
        
        # システムスペック
        self.system_spec = system_resource_manager.get_system_spec()
    
    def initialize_workers(self, api_workers: Optional[int] = None, align_workers: Optional[int] = None):
        """ワーカープールを初期化"""
        # ワーカー数の決定
        if api_workers is None:
            api_workers = self.system_spec.recommended_api_workers
        if align_workers is None:
            align_workers = self.system_spec.recommended_align_workers
        
        # 範囲制限
        api_workers = max(1, min(api_workers, 20))
        align_workers = max(1, min(align_workers, 5))
        
        logger.info(f"ワーカープール初期化: API={api_workers}, アライメント={align_workers}")
        
        self.api_executor = ThreadPoolExecutor(
            max_workers=api_workers,
            thread_name_prefix="API-Worker"
        )
        self.align_executor = ThreadPoolExecutor(
            max_workers=align_workers,
            thread_name_prefix="Align-Worker"
        )
    
    def add_api_tasks(self, tasks: List[APITask]):
        """APIタスクを追加"""
        self.total_chunks = len(tasks)
        for task in tasks:
            # 優先度付きキューに追加（chunk_idx順）
            self.api_queue.put((task.priority, task))
    
    def process_api_task(self, api_func: Callable, align_model: Any, align_meta: Any):
        """APIタスクを処理するワーカー"""
        while not self.shutdown_event.is_set():
            try:
                # タスクを取得（タイムアウト付き）
                priority, task = self.api_queue.get(timeout=0.5)
                
                # メモリ圧迫チェック
                if system_resource_manager.check_memory_pressure():
                    logger.warning(f"メモリ圧迫検出。チャンク {task.chunk_idx} を遅延処理")
                    time.sleep(2)  # 少し待機
                
                # API処理実行
                try:
                    segments = api_func(task.chunk_file, task.start_offset, task.chunk_idx)
                    
                    # 成功したらアライメントキューに追加
                    if segments:
                        align_task = AlignmentTask(
                            chunk_idx=task.chunk_idx,
                            segments=segments,
                            chunk_file=task.chunk_file,
                            start_offset=task.start_offset,
                            priority=task.priority
                        )
                        self.alignment_queue.put((align_task.priority, align_task))
                    
                    self.completed_api_tasks += 1
                    self._update_progress()
                    
                except Exception as e:
                    logger.error(f"APIタスク {task.chunk_idx} でエラー: {e}")
                    self.errors.append(f"API chunk {task.chunk_idx}: {str(e)}")
                    
            except queue.Empty:
                # キューが空の場合は少し待機
                if self.api_queue.empty():
                    break
                continue
    
    def process_alignment_task(self, align_func: Callable):
        """アライメントタスクを処理するワーカー"""
        while not self.shutdown_event.is_set():
            try:
                # タスクを取得
                priority, task = self.alignment_queue.get(timeout=0.5)
                
                # アライメント処理実行
                try:
                    aligned_segments = align_func(
                        task.segments,
                        task.chunk_file,
                        task.start_offset,
                        task.chunk_idx
                    )
                    
                    # 結果を保存
                    result = ProcessingResult(
                        chunk_idx=task.chunk_idx,
                        segments=aligned_segments,
                        success=True
                    )
                    self.result_queue.put(result)
                    
                    self.completed_align_tasks += 1
                    self._update_progress()
                    
                except Exception as e:
                    logger.error(f"アライメントタスク {task.chunk_idx} でエラー: {e}")
                    # エラーでも結果を保存（元のセグメントを使用）
                    result = ProcessingResult(
                        chunk_idx=task.chunk_idx,
                        segments=task.segments,
                        success=False,
                        error=str(e)
                    )
                    self.result_queue.put(result)
                    self.completed_align_tasks += 1
                    
            except queue.Empty:
                # APIタスクが全て完了していて、アライメントキューも空なら終了
                if self.completed_api_tasks >= self.total_chunks and self.alignment_queue.empty():
                    break
                continue
    
    def start_processing(self, api_func: Callable, align_func: Callable, 
                        align_model: Any, align_meta: Any) -> List[ProcessingResult]:
        """並列処理を開始"""
        logger.info(f"並列処理開始: {self.total_chunks}チャンク")
        
        # APIワーカーを起動
        api_futures = []
        for i in range(self.api_executor._max_workers):
            future = self.api_executor.submit(
                self.process_api_task, api_func, align_model, align_meta
            )
            api_futures.append(future)
        
        # アライメントワーカーを起動
        align_futures = []
        for i in range(self.align_executor._max_workers):
            future = self.align_executor.submit(
                self.process_alignment_task, align_func
            )
            align_futures.append(future)
        
        # 全ワーカーの完了を待つ
        for future in api_futures:
            future.result()
        
        for future in align_futures:
            future.result()
        
        # 結果を収集
        results = []
        while not self.result_queue.empty():
            results.append(self.result_queue.get())
        
        # チャンクインデックス順にソート
        results.sort(key=lambda x: x.chunk_idx)
        
        logger.info(f"並列処理完了: 成功={len([r for r in results if r.success])}, 失敗={len([r for r in results if not r.success])}")
        
        return results
    
    def _update_progress(self):
        """進捗を更新"""
        if self.progress_callback and self.total_chunks > 0:
            # API処理とアライメント処理の進捗を合算
            api_progress = self.completed_api_tasks / self.total_chunks * 0.5
            align_progress = self.completed_align_tasks / self.total_chunks * 0.5
            total_progress = api_progress + align_progress
            
            status = f"API: {self.completed_api_tasks}/{self.total_chunks}, アライメント: {self.completed_align_tasks}/{self.total_chunks}"
            self.progress_callback(total_progress, status)
    
    def shutdown(self):
        """処理を停止"""
        logger.info("キューマネージャーをシャットダウン中...")
        self.shutdown_event.set()
        
        if self.api_executor:
            self.api_executor.shutdown(wait=True)
        if self.align_executor:
            self.align_executor.shutdown(wait=True)