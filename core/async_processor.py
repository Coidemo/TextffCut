"""
非同期処理モジュール
"""
import asyncio
import concurrent.futures
from typing import List, Callable, Optional, Any, Coroutine
from pathlib import Path
import time

from utils import logger, ProgressTracker
from .video import VideoProcessor, VideoSegment
from .transcription import Transcriber
from .streaming import StreamingVideoProcessor


class AsyncProcessor:
    """非同期処理を管理するクラス"""
    
    def __init__(self, max_workers: int = 4):
        """
        Args:
            max_workers: 最大ワーカー数
        """
        self.max_workers = max_workers
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers)
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.executor.shutdown(wait=True)
    
    async def process_segments_async(
        self,
        video_processor: VideoProcessor,
        input_path: str,
        segments: List[VideoSegment],
        output_dir: str,
        progress_tracker: Optional[ProgressTracker] = None
    ) -> List[str]:
        """
        セグメントを非同期で処理
        
        Args:
            video_processor: 動画処理インスタンス
            input_path: 入力動画パス
            segments: 処理するセグメント
            output_dir: 出力ディレクトリ
            progress_tracker: プログレストラッカー
            
        Returns:
            処理済みファイルパスのリスト
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # タスクを作成
        tasks = []
        for i, segment in enumerate(segments):
            output_path = output_dir / f"segment_{i+1:03d}.mp4"
            task = self._process_segment_task(
                video_processor,
                input_path,
                segment,
                str(output_path),
                i,
                len(segments),
                progress_tracker
            )
            tasks.append(task)
        
        # 非同期で実行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 成功したファイルのみを返す
        output_files = []
        for i, result in enumerate(results):
            if isinstance(result, str) and Path(result).exists():
                output_files.append(result)
            else:
                logger.error(f"セグメント {i+1} の処理に失敗: {result}")
        
        return output_files
    
    async def _process_segment_task(
        self,
        video_processor: VideoProcessor,
        input_path: str,
        segment: VideoSegment,
        output_path: str,
        index: int,
        total: int,
        progress_tracker: Optional[ProgressTracker] = None
    ) -> str:
        """個別のセグメント処理タスク"""
        loop = asyncio.get_event_loop()
        
        # プログレス更新
        if progress_tracker:
            progress_tracker.update_progress(
                index / total,
                f"セグメント {index+1}/{total} を処理中..."
            )
        
        # ブロッキング処理を別スレッドで実行
        result = await loop.run_in_executor(
            self.executor,
            video_processor.extract_segment,
            input_path,
            segment.start,
            segment.end,
            output_path
        )
        
        if result:
            logger.info(f"セグメント {index+1} 完了: {output_path}")
            return output_path
        else:
            raise Exception(f"セグメント {index+1} の抽出に失敗")
    
    async def batch_process_videos(
        self,
        video_paths: List[str],
        process_func: Callable[[str], Any],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[Any]:
        """
        複数の動画をバッチ処理
        
        Args:
            video_paths: 動画パスのリスト
            process_func: 各動画に適用する処理関数
            progress_callback: 進捗コールバック (completed, total, current_file)
            
        Returns:
            処理結果のリスト
        """
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def process_with_semaphore(index: int, video_path: str) -> Any:
            async with semaphore:
                if progress_callback:
                    progress_callback(index, len(video_paths), Path(video_path).name)
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor,
                    process_func,
                    video_path
                )
                
                if progress_callback:
                    progress_callback(index + 1, len(video_paths), "")
                
                return result
        
        # 全タスクを作成
        tasks = [
            process_with_semaphore(i, path)
            for i, path in enumerate(video_paths)
        ]
        
        # 非同期実行
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # エラーチェック
        successful_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"動画 {video_paths[i]} の処理エラー: {result}")
            else:
                successful_results.append(result)
        
        return successful_results


class AsyncTranscriber:
    """非同期文字起こし処理"""
    
    def __init__(self, transcriber: Transcriber, max_concurrent: int = 2):
        """
        Args:
            transcriber: 文字起こしインスタンス
            max_concurrent: 同時実行数
        """
        self.transcriber = transcriber
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def transcribe_multiple_async(
        self,
        video_paths: List[str],
        model_size: str,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> dict:
        """
        複数の動画を非同期で文字起こし
        
        Args:
            video_paths: 動画パスのリスト
            model_size: Whisperモデルサイズ
            progress_callback: 進捗コールバック
            
        Returns:
            {video_path: TranscriptionResult} の辞書
        """
        results = {}
        
        async def transcribe_single(video_path: str) -> tuple:
            async with self.semaphore:
                logger.info(f"文字起こし開始: {video_path}")
                
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    self.transcriber.transcribe,
                    video_path,
                    model_size,
                    None,  # progress_callback
                    True   # use_cache
                )
                
                return video_path, result
        
        # タスクを作成
        tasks = [transcribe_single(path) for path in video_paths]
        
        # プログレス付きで実行
        completed = 0
        for coro in asyncio.as_completed(tasks):
            video_path, result = await coro
            results[video_path] = result
            completed += 1
            
            if progress_callback:
                progress = completed / len(video_paths)
                progress_callback(
                    f"文字起こし完了 ({completed}/{len(video_paths)})",
                    progress
                )
        
        return results


def run_async(coro: Coroutine) -> Any:
    """
    非同期関数を同期的に実行するヘルパー
    
    Args:
        coro: 実行するコルーチン
        
    Returns:
        コルーチンの結果
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()