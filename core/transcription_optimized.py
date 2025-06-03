"""
最適化されたローカル版文字起こしモジュール
Producer-Consumerパターンによる高速化実装
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import numpy as np

try:
    import whisperx
    import torch
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

from config import Config
from utils.logging import get_logger
from utils.system_resources import system_resource_manager
from core.queue_manager import TaskQueueManager, APITask, AlignmentTask
from core.segment_splitter import SegmentSplitter
from .transcription import TranscriptionResult, TranscriptionSegment

logger = get_logger(__name__)


class OptimizedLocalTranscriber:
    """最適化されたローカル版文字起こしクラス"""
    
    def __init__(self, config: Config, device: str):
        self.config = config
        self.device = device
        self.segment_splitter = SegmentSplitter()
    
    def transcribe_local_optimized(
        self, 
        video_path: str, 
        model_size: str,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        save_cache: bool = True,
        cache_path: Optional[Path] = None
    ) -> TranscriptionResult:
        """最適化されたローカル文字起こし処理"""
        start_time = time.time()
        
        # システムスペックを取得
        system_spec = system_resource_manager.get_system_spec()
        
        # チャンクサイズを決定
        if self.config.transcription.adaptive_workers:
            chunk_seconds = system_spec.recommended_chunk_seconds
            logger.info(f"適応的チャンクサイズ: {chunk_seconds}秒 (スペック: {system_spec.spec_level})")
        else:
            chunk_seconds = self.config.transcription.chunk_seconds
        
        # 音声の読み込み
        if progress_callback:
            progress_callback(0.0, "音声を読み込み中...")
        
        audio = whisperx.load_audio(video_path)
        
        # モデルの読み込み
        if progress_callback:
            progress_callback(0.05, "モデルを読み込み中...")
        
        asr_model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=self.config.transcription.language
        )
        
        # チャンク作成
        sample_rate = self.config.transcription.sample_rate
        step = chunk_seconds * sample_rate
        chunks = self._create_chunks(audio, step, sample_rate)
        
        if progress_callback:
            progress_callback(0.1, f"チャンク作成完了: {len(chunks)}個")
        
        # アライメントモデルを事前に読み込み
        align_model, align_meta = self._load_alignment_model()
        
        # Producer-Consumerパターンで処理
        queue_manager = TaskQueueManager(progress_callback)
        
        # ワーカー数を決定
        if self.config.transcription.adaptive_workers:
            # 文字起こしワーカー数（CPUコア数に基づく）
            transcribe_workers = min(system_spec.cpu_physical_count, len(chunks))
            align_workers = system_spec.recommended_align_workers
        else:
            transcribe_workers = self.config.transcription.num_workers or 4
            align_workers = 2
        
        # 文字起こしとアライメントでワーカープールを分ける
        logger.info(f"ワーカー設定: 文字起こし={transcribe_workers}, アライメント={align_workers}")
        
        # 並列処理実行
        all_segments = self._process_chunks_parallel(
            chunks, asr_model, align_model, align_meta,
            transcribe_workers, align_workers, progress_callback
        )
        
        # セグメントをソート
        all_segments.sort(key=lambda x: x["start"])
        
        # 結果を構築
        segments = [
            TranscriptionSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                words=seg.get("words"),
                chars=seg.get("chars")
            )
            for seg in all_segments
        ]
        
        processing_time = time.time() - start_time
        logger.info(f"最適化処理完了: {len(segments)}セグメント, 処理時間: {processing_time:.1f}秒")
        
        result = TranscriptionResult(
            language=self.config.transcription.language,
            segments=segments,
            original_audio_path=video_path,
            model_size=model_size,
            processing_time=processing_time
        )
        
        # キャッシュに保存
        if save_cache and cache_path:
            self._save_to_cache(result, cache_path)
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        return result
    
    def _create_chunks(self, audio, step, sample_rate):
        """チャンクを作成"""
        chunks = []
        MIN_CHUNK_DURATION = 1.0
        pending_chunk = None
        
        for i in range(0, len(audio), step):
            chunk_audio = audio[i:i+step]
            start_time = i / sample_rate
            duration = len(chunk_audio) / sample_rate
            
            if pending_chunk is not None:
                combined_audio = np.concatenate([pending_chunk["array"], chunk_audio])
                combined_chunk = {
                    "array": combined_audio,
                    "start": pending_chunk["start"],
                    "duration": len(combined_audio) / sample_rate
                }
                chunks.append(combined_chunk)
                pending_chunk = None
                continue
            
            if duration < MIN_CHUNK_DURATION:
                if chunks:
                    last_chunk = chunks[-1]
                    combined_audio = np.concatenate([last_chunk["array"], chunk_audio])
                    chunks[-1] = {
                        "array": combined_audio,
                        "start": last_chunk["start"],
                        "duration": len(combined_audio) / sample_rate
                    }
                else:
                    pending_chunk = {
                        "array": chunk_audio,
                        "start": start_time,
                        "duration": duration
                    }
                continue
            
            chunks.append({
                "array": chunk_audio,
                "start": start_time,
                "duration": duration
            })
        
        if pending_chunk is not None:
            chunks.append(pending_chunk)
        
        return chunks
    
    def _load_alignment_model(self):
        """アライメントモデルを読み込み"""
        try:
            align_model, align_meta = whisperx.load_align_model(
                self.config.transcription.language,
                device=self.device
            )
            logger.info("アライメントモデルを読み込みました")
            return align_model, align_meta
        except Exception as e:
            logger.warning(f"アライメントモデルの読み込みに失敗: {e}")
            return None, None
    
    def _process_chunks_parallel(self, chunks, asr_model, align_model, align_meta,
                               transcribe_workers, align_workers, progress_callback):
        """並列処理でチャンクを処理"""
        all_segments = []
        total_chunks = len(chunks)
        completed_transcribe = 0
        completed_align = 0
        
        # 文字起こし結果を保持するキュー
        transcribe_results = {}
        align_queue = []
        
        with ThreadPoolExecutor(max_workers=transcribe_workers) as transcribe_executor, \
             ThreadPoolExecutor(max_workers=align_workers) as align_executor:
            
            # 文字起こしタスクを投入
            transcribe_futures = {}
            for i, chunk in enumerate(chunks):
                future = transcribe_executor.submit(
                    self._transcribe_chunk_with_split, chunk, asr_model, i
                )
                transcribe_futures[future] = i
            
            # アライメントタスクを管理
            align_futures = {}
            
            # 文字起こし完了を監視し、アライメントタスクを投入
            while transcribe_futures or align_futures:
                # 文字起こし完了をチェック
                for future in list(transcribe_futures.keys()):
                    if future.done():
                        chunk_idx = transcribe_futures.pop(future)
                        try:
                            segments = future.result()
                            completed_transcribe += 1
                            
                            # アライメントタスクを投入
                            if align_model and align_meta and segments:
                                chunk = chunks[chunk_idx]
                                align_future = align_executor.submit(
                                    self._align_segments_batch,
                                    segments, chunk, align_model, align_meta, chunk_idx
                                )
                                align_futures[align_future] = (chunk_idx, segments)
                            else:
                                # アライメントなしで追加
                                all_segments.extend(segments)
                                completed_align += 1
                            
                            # 進捗更新
                            if progress_callback:
                                transcribe_progress = completed_transcribe / total_chunks * 0.5
                                align_progress = completed_align / total_chunks * 0.5
                                total_progress = 0.1 + transcribe_progress + align_progress
                                status = f"文字起こし: {completed_transcribe}/{total_chunks}, アライメント: {completed_align}/{total_chunks}"
                                progress_callback(total_progress, status)
                        
                        except Exception as e:
                            logger.error(f"文字起こしエラー (チャンク {chunk_idx}): {e}")
                            completed_transcribe += 1
                
                # アライメント完了をチェック
                for future in list(align_futures.keys()):
                    if future.done():
                        chunk_idx, original_segments = align_futures.pop(future)
                        try:
                            aligned_segments = future.result()
                            all_segments.extend(aligned_segments)
                        except Exception as e:
                            logger.warning(f"アライメント失敗 (チャンク {chunk_idx}): {e}")
                            # 失敗時は元のセグメントを使用
                            all_segments.extend(original_segments)
                        
                        completed_align += 1
                        
                        # 進捗更新
                        if progress_callback:
                            transcribe_progress = completed_transcribe / total_chunks * 0.5
                            align_progress = completed_align / total_chunks * 0.5
                            total_progress = 0.1 + transcribe_progress + align_progress
                            status = f"文字起こし: {completed_transcribe}/{total_chunks}, アライメント: {completed_align}/{total_chunks}"
                            progress_callback(total_progress, status)
                
                # 少し待機
                time.sleep(0.01)
        
        return all_segments
    
    def _transcribe_chunk_with_split(self, chunk, asr_model, chunk_idx):
        """チャンクを文字起こしし、必要に応じて分割"""
        # 文字起こし実行
        res = asr_model.transcribe(
            chunk["array"],
            batch_size=self.config.transcription.batch_size,
            language=self.config.transcription.language
        )
        
        # チャンクのオフセットを適用
        for seg in res["segments"]:
            seg["start"] += chunk["start"]
            seg["end"] += chunk["start"]
        
        # 長いセグメントを分割
        segments = self.segment_splitter.split_segments(res["segments"], chunk["duration"])
        
        logger.debug(f"チャンク {chunk_idx}: 文字起こし完了, {len(segments)}セグメント")
        return segments
    
    def _align_segments_batch(self, segments, chunk, align_model, align_meta, chunk_idx):
        """セグメントのバッチアライメント"""
        try:
            # チャンク内の相対時間に変換
            whisperx_segments = []
            for seg in segments:
                whisperx_segments.append({
                    "start": seg["start"] - chunk["start"],
                    "end": seg["end"] - chunk["start"],
                    "text": seg["text"]
                })
            
            # アライメント実行
            aligned_result = whisperx.align(
                whisperx_segments,
                align_model,
                align_meta,
                chunk["array"],
                self.device,
                return_char_alignments=True
            )
            
            # 絶対時間に戻す
            aligned_segments = aligned_result["segments"]
            for seg in aligned_segments:
                seg["start"] += chunk["start"]
                seg["end"] += chunk["start"]
                if "words" in seg and seg["words"]:
                    for word in seg["words"]:
                        if "start" in word:
                            word["start"] += chunk["start"]
                        if "end" in word:
                            word["end"] += chunk["start"]
            
            logger.debug(f"チャンク {chunk_idx}: アライメント成功")
            return aligned_segments
            
        except Exception as e:
            logger.warning(f"チャンク {chunk_idx} アライメント失敗: {e}")
            raise
    
    def _save_to_cache(self, result: TranscriptionResult, cache_path: Path):
        """キャッシュに保存"""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)