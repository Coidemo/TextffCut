"""
並列処理による高速文字起こしモジュール
メモリ使用量を監視しながら最適な並列数で処理
"""

import os
import psutil
import subprocess
import tempfile
import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Optional, Callable, Dict
import json

from .transcription import Transcriber, TranscriptionResult, TranscriptionSegment
from .transcription_smart_boundary import SmartBoundaryTranscriber
from utils.logging import get_logger

logger = get_logger(__name__)


class ParallelTranscriber(SmartBoundaryTranscriber):
    """並列処理による高速文字起こしクラス"""
    
    def __init__(self, config):
        """初期化"""
        super().__init__(config)
        self.max_workers = self._calculate_optimal_workers()
        logger.info(f"並列処理ワーカー数: {self.max_workers}")
    
    def _calculate_optimal_workers(self) -> int:
        """最適なワーカー数を計算"""
        # システムメモリを取得
        mem_info = psutil.virtual_memory()
        available_gb = mem_info.available / (1024 ** 3)
        total_gb = mem_info.total / (1024 ** 3)
        
        logger.info(f"システムメモリ: {total_gb:.1f}GB (利用可能: {available_gb:.1f}GB)")
        
        # モデルサイズに基づくメモリ使用量推定
        model_size = self.config.transcription.model_size
        mem_per_worker = {
            'base': 1.5,    # 1.5GB/ワーカー
            'small': 2.0,   # 2GB/ワーカー
            'medium': 3.0,  # 3GB/ワーカー
            'large': 4.0,   # 4GB/ワーカー
            'large-v3': 4.5 # 4.5GB/ワーカー
        }
        
        required_per_worker = mem_per_worker.get(model_size, 3.0)
        
        # 利用可能メモリの70%を使用
        max_workers_by_memory = int((available_gb * 0.7) / required_per_worker)
        
        # CPU数による制限
        cpu_count = os.cpu_count() or 4
        max_workers_by_cpu = max(1, cpu_count // 2)  # CPUの半分を使用
        
        # 最終的なワーカー数（最小1、最大4）
        optimal_workers = min(
            max_workers_by_memory,
            max_workers_by_cpu,
            4  # 最大4並列（安定性のため）
        )
        
        return max(1, optimal_workers)
    
    def transcribe(
        self,
        video_path: str,
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True,
        save_cache: bool = True
    ) -> TranscriptionResult:
        """
        並列処理による文字起こし
        """
        # キャッシュ確認
        model_size = model_size or self.config.transcription.model_size
        cache_path = self.get_cache_path(video_path, f"{model_size}_parallel")
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result
        
        start_time = time.time()
        
        # 動画の長さを取得
        duration = self._get_video_duration(video_path)
        logger.info(f"動画時間: {duration/60:.1f}分")
        
        # 一時ディレクトリ作成
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_parallel_")
        
        try:
            if progress_callback:
                progress_callback(0.1, "最適な分割点を検出中...")
            
            # スマート境界検出で分割点を決定
            split_points = self._find_smart_boundaries(video_path, duration)
            logger.info(f"分割点: {[f'{p/60:.1f}分' for p in split_points]}")
            
            # セグメントに分割
            segments = []
            for i in range(len(split_points) - 1):
                segments.append({
                    'index': i,
                    'start': split_points[i],
                    'end': split_points[i + 1],
                    'video_path': video_path,
                    'model_size': model_size,
                    'temp_dir': self.temp_dir,
                    'config': self._serialize_config()
                })
            
            if progress_callback:
                progress_callback(0.2, f"{len(segments)}セグメントを{self.max_workers}並列で処理開始...")
            
            # 並列処理
            all_results = self._process_segments_parallel(segments, progress_callback)
            
            # 結果をソート
            all_results.sort(key=lambda x: x[0])
            merged_segments = []
            for _, segment_results in all_results:
                # 辞書からTranscriptionSegmentオブジェクトに変換
                for seg_dict in segment_results:
                    segment = TranscriptionSegment(
                        start=seg_dict['start'],
                        end=seg_dict['end'],
                        text=seg_dict['text']
                    )
                    merged_segments.append(segment)
            
            # 結果を作成
            result = TranscriptionResult(
                language=self.config.transcription.language,
                segments=merged_segments,
                original_audio_path=video_path,
                model_size=model_size,
                processing_time=time.time() - start_time
            )
            
            # キャッシュに保存
            if save_cache:
                self.save_to_cache(result, cache_path)
            
            if progress_callback:
                progress_callback(1.0, f"完了（処理時間: {result.processing_time:.1f}秒）")
            
            return result
            
        finally:
            # クリーンアップ
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
    
    def _process_segments_parallel(
        self,
        segments: List[Dict],
        progress_callback: Optional[Callable]
    ) -> List[Tuple[int, List[TranscriptionSegment]]]:
        """セグメントを並列処理"""
        results = []
        completed = 0
        total = len(segments)
        
        # プロセスプールで処理
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # ジョブを投入
            future_to_segment = {
                executor.submit(process_segment_worker, seg): seg
                for seg in segments
            }
            
            # 完了したジョブから結果を取得
            for future in as_completed(future_to_segment):
                segment = future_to_segment[future]
                try:
                    index, segment_results = future.result()
                    results.append((index, segment_results))
                    completed += 1
                    
                    if progress_callback:
                        progress = 0.2 + (0.7 * completed / total)
                        progress_callback(
                            progress,
                            f"処理完了: {completed}/{total} セグメント"
                        )
                    
                    # メモリ使用量を監視
                    mem_percent = psutil.virtual_memory().percent
                    if mem_percent > 85:
                        logger.warning(f"メモリ使用率が高い: {mem_percent}%")
                        
                except Exception as e:
                    logger.error(f"セグメント {segment['index']} でエラー: {e}")
                    # 空の結果を追加
                    results.append((segment['index'], []))
        
        return results
    
    def _serialize_config(self) -> Dict:
        """設定をシリアライズ"""
        return {
            'language': self.config.transcription.language,
            'compute_type': self.config.transcription.compute_type,
            'batch_size': self.config.transcription.batch_size,
            'device': 'cpu'  # 並列処理ではCPU固定
        }


def process_segment_worker(segment_data: Dict) -> Tuple[int, List[dict]]:
    """
    ワーカープロセスでセグメントを処理
    （別プロセスで実行されるため、グローバル変数は使えない）
    """
    import whisperx
    import numpy as np
    
    index = segment_data['index']
    start = segment_data['start']
    end = segment_data['end']
    video_path = segment_data['video_path']
    model_size = segment_data['model_size']
    temp_dir = segment_data['temp_dir']
    config = segment_data['config']
    
    # セグメントのWAVファイルを作成
    segment_wav = os.path.join(temp_dir, f"segment_{index}.wav")
    
    # FFmpegで音声を抽出
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", video_path,
        "-t", str(end - start),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        segment_wav
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    
    try:
        # 音声を読み込み
        audio = whisperx.load_audio(segment_wav)
        
        # モデルを読み込み（各プロセスで独立）
        model = whisperx.load_model(
            model_size,
            config['device'],
            compute_type=config['compute_type'],
            language=config['language']
        )
        
        # 文字起こし
        result = model.transcribe(
            audio,
            batch_size=config['batch_size'],
            language=config['language']
        )
        
        # アライメント処理（オプション）
        segments_data = result.get("segments", [])
        
        # セグメントを変換（オフセット適用）
        segments = []
        for seg in segments_data:
            segment = {
                'start': seg["start"] + start,
                'end': seg["end"] + start,
                'text': seg["text"]
            }
            segments.append(segment)
        
        return (index, segments)
        
    finally:
        # セグメントファイルを削除
        if os.path.exists(segment_wav):
            os.unlink(segment_wav)