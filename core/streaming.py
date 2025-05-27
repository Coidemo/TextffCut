"""
ストリーミング処理モジュール（メモリ効率化）
"""
import subprocess
import threading
import queue
from typing import Optional, Callable, Generator, Tuple
from pathlib import Path
import psutil

from utils import logger, FFmpegError, MemoryError


class StreamingVideoProcessor:
    """ストリーミング方式の動画処理クラス（メモリ効率重視）"""
    
    def __init__(self, memory_limit_gb: float = 2.0):
        """
        Args:
            memory_limit_gb: メモリ使用量の上限（GB）
        """
        self.memory_limit_gb = memory_limit_gb
        self.check_memory_availability()
    
    def check_memory_availability(self):
        """利用可能なメモリをチェック"""
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024 ** 3)
        
        if available_gb < self.memory_limit_gb:
            logger.warning(f"利用可能なメモリが少ない: {available_gb:.1f}GB")
            raise MemoryError(required_memory=self.memory_limit_gb)
    
    def stream_extract_segment(
        self,
        input_path: str,
        start: float,
        end: float,
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """
        ストリーミング方式でセグメントを抽出（メモリ効率的）
        
        Args:
            input_path: 入力動画パス
            start: 開始時間
            end: 終了時間
            output_path: 出力パス
            progress_callback: 進捗コールバック
            
        Returns:
            成功したかどうか
        """
        try:
            # 出力ディレクトリを確保
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            # ストリーミング用のFFmpegコマンド
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),  # シーク位置を入力前に指定（高速化）
                "-i", str(input_path),
                "-t", str(end - start),  # 期間を指定
                "-c:v", "h264",  # ハードウェアエンコーディングが使える場合は使用
                "-preset", "superfast",  # より高速なプリセット
                "-c:a", "aac",
                "-b:a", "128k",  # 音声ビットレートを下げてメモリ節約
                "-movflags", "+faststart",  # ストリーミング対応
                "-avoid_negative_ts", "1",
                str(output_path)
            ]
            
            logger.info(f"セグメント抽出開始: {start:.1f}s - {end:.1f}s")
            
            # プロセスを開始
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1  # ラインバッファリング
            )
            
            # 進捗を監視
            if progress_callback:
                self._monitor_streaming_progress(
                    process, end - start, progress_callback
                )
            else:
                stdout, stderr = process.communicate()
                if process.returncode != 0:
                    raise FFmpegError(' '.join(cmd), stderr)
            
            logger.info(f"セグメント抽出完了: {output_path}")
            return process.returncode == 0
            
        except Exception as e:
            logger.error(f"ストリーミング抽出エラー: {str(e)}")
            raise
    
    def _monitor_streaming_progress(
        self,
        process: subprocess.Popen,
        duration: float,
        progress_callback: Callable[[float, str], None]
    ):
        """ストリーミング処理の進捗を監視"""
        def read_stderr():
            while True:
                line = process.stderr.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    stderr_queue.put(line.strip())
        
        stderr_queue = queue.Queue()
        stderr_thread = threading.Thread(target=read_stderr)
        stderr_thread.daemon = True
        stderr_thread.start()
        
        last_time = 0.0
        
        while process.poll() is None:
            try:
                line = stderr_queue.get(timeout=0.1)
                
                if "time=" in line:
                    # 時間情報を抽出
                    time_str = line.split("time=")[1].split()[0]
                    try:
                        hours, minutes, seconds = time_str.split(":")
                        current_time = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                        
                        # メモリ使用量をチェック
                        memory = psutil.virtual_memory()
                        memory_percent = memory.percent
                        
                        # 進捗を計算
                        progress = min(current_time / duration, 1.0)
                        status = f"処理中... メモリ使用率: {memory_percent:.0f}%"
                        
                        progress_callback(progress, status)
                        last_time = current_time
                        
                    except (ValueError, IndexError):
                        pass
                        
            except queue.Empty:
                continue
        
        # プロセス終了後のチェック
        if process.returncode != 0:
            stderr_output = '\n'.join(list(stderr_queue.queue))
            raise FFmpegError(' '.join(process.args), stderr_output)
    
    def stream_process_large_video(
        self,
        input_path: str,
        segments: Generator[Tuple[float, float], None, None],
        output_dir: str,
        batch_size: int = 5,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> Generator[str, None, None]:
        """
        大きな動画を効率的に処理（バッチ処理）
        
        Args:
            input_path: 入力動画パス
            segments: セグメントのジェネレータ
            output_dir: 出力ディレクトリ
            batch_size: 同時処理するセグメント数
            progress_callback: 進捗コールバック
            
        Yields:
            処理済みファイルのパス
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # バッチ処理用のキュー
        segment_queue = queue.Queue(maxsize=batch_size * 2)
        result_queue = queue.Queue()
        
        def process_batch():
            """バッチ処理ワーカー"""
            while True:
                item = segment_queue.get()
                if item is None:
                    break
                    
                idx, (start, end) = item
                output_path = output_dir / f"segment_{idx:04d}.mp4"
                
                try:
                    success = self.stream_extract_segment(
                        input_path,
                        start,
                        end,
                        str(output_path)
                    )
                    
                    if success:
                        result_queue.put((idx, str(output_path)))
                    else:
                        result_queue.put((idx, None))
                        
                except Exception as e:
                    logger.error(f"セグメント処理エラー: {e}")
                    result_queue.put((idx, None))
                finally:
                    segment_queue.task_done()
        
        # ワーカースレッドを開始
        workers = []
        for _ in range(min(batch_size, 3)):  # 最大3並列
            t = threading.Thread(target=process_batch)
            t.daemon = True
            t.start()
            workers.append(t)
        
        # セグメントをキューに追加
        segment_count = 0
        for idx, segment in enumerate(segments):
            segment_queue.put((idx, segment))
            segment_count += 1
        
        # 終了シグナル
        for _ in workers:
            segment_queue.put(None)
        
        # 結果を収集
        processed = 0
        while processed < segment_count:
            idx, path = result_queue.get()
            processed += 1
            
            if path:
                yield path
                
            if progress_callback:
                progress = processed / segment_count
                status = f"セグメント処理中... ({processed}/{segment_count})"
                progress_callback(progress, status)
        
        # ワーカーの終了を待つ
        for t in workers:
            t.join()


def estimate_memory_usage(video_path: str, duration: float) -> float:
    """
    動画処理に必要なメモリ使用量を推定
    
    Args:
        video_path: 動画ファイルパス
        duration: 処理する時間（秒）
        
    Returns:
        推定メモリ使用量（GB）
    """
    try:
        # 動画情報を取得
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=bit_rate",
            "-of", "json",
            str(video_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            bit_rate = int(info.get('format', {}).get('bit_rate', 8000000))  # デフォルト8Mbps
            
            # メモリ使用量を推定（ビットレート × 時間 × バッファ係数）
            memory_bytes = (bit_rate / 8) * duration * 2.5  # 2.5倍のバッファ
            memory_gb = memory_bytes / (1024 ** 3)
            
            return memory_gb
        
    except Exception as e:
        logger.warning(f"メモリ使用量の推定に失敗: {e}")
    
    # デフォルト値を返す
    return 0.5  # 500MB