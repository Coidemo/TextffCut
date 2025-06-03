"""
超最適化版API文字起こしモジュール
真のProducer-Consumerパターンでメモリ効率を最大化
"""
import os
import time
from typing import Dict, Any, Optional, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import queue

import openai
import numpy as np

from .transcription import TranscriptionResult, TranscriptionSegment
from .disk_cache_manager import DiskCacheManager
from config import Config
from utils.logging import get_logger
from utils.system_resources import system_resource_manager
from core.segment_splitter import SegmentSplitter

logger = get_logger(__name__)


class UltraOptimizedAPITranscriber:
    """超最適化版API文字起こしクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_config = config.transcription
        self.segment_splitter = SegmentSplitter()
    
    def transcribe_ultra_optimized(self, client, audio, original_audio_path: str,
                                  progress_callback: Optional[Callable] = None) -> TranscriptionResult:
        """超最適化版の文字起こし処理"""
        start_time = time.time()
        
        # システムスペック取得
        system_spec = system_resource_manager.get_system_spec()
        chunk_seconds = system_spec.recommended_chunk_seconds if self.api_config.adaptive_workers else self.api_config.chunk_seconds
        
        logger.info(f"超最適化モード: チャンク={chunk_seconds}秒, メモリ={system_spec.available_memory_gb:.1f}GB")
        
        # ディスクキャッシュマネージャー
        disk_cache = DiskCacheManager()
        
        try:
            # チャンク作成と保存
            chunks_info = self._prepare_chunks(audio, chunk_seconds, disk_cache, progress_callback)
            
            # 3つの独立したフェーズで処理
            # Phase 1: API呼び出し（高並列）
            self._phase1_api_calls(client, chunks_info, disk_cache, system_spec, progress_callback)
            
            # Phase 2: セグメント分割（中並列）
            self._phase2_segment_splitting(chunks_info, chunk_seconds, disk_cache, progress_callback)
            
            # Phase 3: アライメント処理（低並列、メモリ制約）
            all_segments = self._phase3_alignment(chunks_info, disk_cache, system_spec, progress_callback)
            
            # 結果を統合
            processing_time = time.time() - start_time
            logger.info(f"超最適化処理完了: {len(all_segments)}セグメント, 処理時間: {processing_time:.1f}秒")
            
            return TranscriptionResult(
                language=self.api_config.language,
                segments=all_segments,
                original_audio_path=original_audio_path,
                model_size="whisper-1_api_ultra",
                processing_time=processing_time
            )
            
        finally:
            # クリーンアップ
            disk_cache.cleanup()
    
    def _prepare_chunks(self, audio, chunk_seconds, disk_cache, progress_callback):
        """チャンクを準備してディスクに保存"""
        import soundfile as sf
        import tempfile
        
        sample_rate = 16000
        step = chunk_seconds * sample_rate
        
        # チャンク作成（既存ロジック使用）
        chunks = self._create_chunks(audio, step, sample_rate)
        
        # チャンクファイルを保存
        chunks_info = []
        temp_dir = tempfile.mkdtemp(prefix="textffcut_chunks_")
        
        for i, chunk in enumerate(chunks):
            # WAVファイルとして保存
            chunk_file = os.path.join(temp_dir, f"chunk_{i:04d}.wav")
            sf.write(chunk_file, chunk["array"], sample_rate)
            
            # チャンク情報
            chunk_info = {
                "idx": i,
                "file": chunk_file,
                "start": chunk["start"],
                "duration": chunk["duration"]
            }
            chunks_info.append(chunk_info)
            
            # 音声データもキャッシュ（アライメント用）
            disk_cache.save_audio_chunk(i, chunk["array"])
        
        if progress_callback:
            progress_callback(0.05, f"チャンク準備完了: {len(chunks_info)}個")
        
        return chunks_info
    
    def _phase1_api_calls(self, client, chunks_info, disk_cache, system_spec, progress_callback):
        """Phase 1: API呼び出し（高並列）"""
        # API並列数（レート制限考慮）
        api_workers = min(system_spec.recommended_api_workers, 10)
        if system_spec.available_memory_gb < 2:
            api_workers = min(api_workers, 3)
        
        logger.info(f"Phase 1: API呼び出し開始 (並列数: {api_workers})")
        
        completed = 0
        total = len(chunks_info)
        
        with ThreadPoolExecutor(max_workers=api_workers) as executor:
            futures = {}
            
            for chunk_info in chunks_info:
                future = executor.submit(
                    self._call_api_single,
                    client, chunk_info
                )
                futures[future] = chunk_info["idx"]
            
            for future in as_completed(futures):
                chunk_idx = futures[future]
                try:
                    segments = future.result()
                    # 結果をディスクに保存（メモリ解放）
                    disk_cache.save_api_result(chunk_idx, segments)
                    completed += 1
                    
                    if progress_callback:
                        progress = 0.05 + (0.3 * completed / total)
                        progress_callback(progress, f"API呼び出し: {completed}/{total}")
                        
                except Exception as e:
                    logger.error(f"API呼び出しエラー (チャンク {chunk_idx}): {e}")
                    disk_cache.save_api_result(chunk_idx, [])  # 空の結果を保存
                    completed += 1
    
    def _phase2_segment_splitting(self, chunks_info, chunk_seconds, disk_cache, progress_callback):
        """Phase 2: セグメント分割（中並列）"""
        logger.info("Phase 2: セグメント分割開始")
        
        for i, chunk_info in enumerate(chunks_info):
            # API結果を読み込み
            segments = disk_cache.load_api_result(chunk_info["idx"])
            if not segments:
                continue
            
            # 長いセグメントを分割
            split_segments = self.segment_splitter.split_segments(segments, chunk_seconds)
            
            # 分割結果を保存（元の結果を上書き）
            disk_cache.save_api_result(chunk_info["idx"], split_segments)
            
            if progress_callback and i % 10 == 0:
                progress = 0.35 + (0.15 * i / len(chunks_info))
                progress_callback(progress, f"セグメント分割: {i}/{len(chunks_info)}")
    
    def _phase3_alignment(self, chunks_info, disk_cache, system_spec, progress_callback):
        """Phase 3: アライメント処理（低並列、メモリ制約）"""
        # アライメントモデルを読み込み
        align_model, align_meta = self._load_alignment_model()
        if not align_model:
            # アライメントなしで結果を返す
            return self._collect_results_without_alignment(chunks_info, disk_cache)
        
        # アライメント並列数（メモリ制約）
        align_workers = system_spec.recommended_align_workers
        if system_spec.available_memory_gb < 4:
            align_workers = 1  # 低メモリでは1つのみ
        
        logger.info(f"Phase 3: アライメント開始 (並列数: {align_workers})")
        
        completed = 0
        total = len(chunks_info)
        
        with ThreadPoolExecutor(max_workers=align_workers) as executor:
            futures = {}
            
            for chunk_info in chunks_info:
                future = executor.submit(
                    self._align_single_chunk,
                    chunk_info, disk_cache, align_model, align_meta
                )
                futures[future] = chunk_info["idx"]
            
            for future in as_completed(futures):
                chunk_idx = futures[future]
                try:
                    aligned_segments = future.result()
                    # アライメント結果を保存
                    disk_cache.save_aligned_result(chunk_idx, aligned_segments)
                    completed += 1
                    
                    if progress_callback:
                        progress = 0.5 + (0.45 * completed / total)
                        progress_callback(progress, f"アライメント: {completed}/{total}")
                        
                except Exception as e:
                    logger.warning(f"アライメントエラー (チャンク {chunk_idx}): {e}")
                    # 失敗時は元のセグメントを使用
                    segments = disk_cache.load_api_result(chunk_idx)
                    if segments:
                        aligned_segments = [
                            TranscriptionSegment(
                                start=seg["start"],
                                end=seg["end"],
                                text=seg["text"],
                                words=None,
                                chars=None
                            )
                            for seg in segments
                        ]
                        disk_cache.save_aligned_result(chunk_idx, aligned_segments)
                    completed += 1
        
        # 全結果を収集
        return self._collect_all_results(chunks_info, disk_cache)
    
    def _call_api_single(self, client, chunk_info):
        """単一チャンクのAPI呼び出し"""
        with open(chunk_info["file"], 'rb') as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=self.api_config.language,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        
        segments = []
        if hasattr(response, 'segments') and response.segments:
            for seg in response.segments:
                if isinstance(seg, dict):
                    segment = {
                        "start": seg['start'] + chunk_info["start"],
                        "end": seg['end'] + chunk_info["start"],
                        "text": seg['text']
                    }
                else:
                    segment = {
                        "start": seg.start + chunk_info["start"],
                        "end": seg.end + chunk_info["start"],
                        "text": seg.text
                    }
                segments.append(segment)
        elif response.text.strip():
            segment = {
                "start": chunk_info["start"],
                "end": chunk_info["start"] + chunk_info["duration"],
                "text": response.text
            }
            segments.append(segment)
        
        return segments
    
    def _align_single_chunk(self, chunk_info, disk_cache, align_model, align_meta):
        """単一チャンクのアライメント"""
        # セグメントを読み込み
        segments = disk_cache.load_api_result(chunk_info["idx"])
        if not segments:
            return []
        
        # 音声データを読み込み
        chunk_audio = disk_cache.load_audio_chunk(chunk_info["idx"])
        if chunk_audio is None:
            # 音声データがない場合はアライメントなしで返す
            return [
                TranscriptionSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"],
                    words=None,
                    chars=None
                )
                for seg in segments
            ]
        
        try:
            import whisperx
            
            # WhisperX形式に変換（チャンク内相対時間）
            whisperx_segments = []
            for seg in segments:
                whisperx_segments.append({
                    "start": seg["start"] - chunk_info["start"],
                    "end": seg["end"] - chunk_info["start"],
                    "text": seg["text"]
                })
            
            # アライメント実行
            aligned_result = whisperx.align(
                whisperx_segments,
                align_model,
                align_meta,
                chunk_audio,
                "cpu",
                return_char_alignments=True
            )
            
            # 結果を変換
            aligned_segments = []
            for seg in aligned_result["segments"]:
                aligned_seg = TranscriptionSegment(
                    start=seg["start"] + chunk_info["start"],
                    end=seg["end"] + chunk_info["start"],
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars")
                )
                
                # wordsのタイムスタンプも調整
                if aligned_seg.words:
                    for word in aligned_seg.words:
                        if "start" in word:
                            word["start"] += chunk_info["start"]
                        if "end" in word:
                            word["end"] += chunk_info["start"]
                
                aligned_segments.append(aligned_seg)
            
            return aligned_segments
            
        except Exception as e:
            logger.warning(f"アライメント失敗: {e}")
            raise
    
    def _load_alignment_model(self):
        """アライメントモデルを読み込み"""
        try:
            import whisperx
            align_model, align_meta = whisperx.load_align_model(
                language_code=self.api_config.language,
                device="cpu"
            )
            logger.info("アライメントモデルを読み込みました")
            return align_model, align_meta
        except Exception as e:
            logger.warning(f"アライメントモデルの読み込みに失敗: {e}")
            return None, None
    
    def _collect_results_without_alignment(self, chunks_info, disk_cache):
        """アライメントなしで結果を収集"""
        all_segments = []
        
        for chunk_info in chunks_info:
            segments = disk_cache.load_api_result(chunk_info["idx"])
            if segments:
                for seg in segments:
                    segment = TranscriptionSegment(
                        start=seg["start"],
                        end=seg["end"],
                        text=seg["text"],
                        words=None,
                        chars=None
                    )
                    all_segments.append(segment)
        
        all_segments.sort(key=lambda x: x.start)
        return all_segments
    
    def _collect_all_results(self, chunks_info, disk_cache):
        """全結果を収集"""
        all_segments = []
        
        for chunk_info in chunks_info:
            # アライメント結果を優先
            aligned_segments = disk_cache.load_aligned_result(chunk_info["idx"])
            if aligned_segments:
                all_segments.extend(aligned_segments)
            else:
                # アライメント結果がない場合はAPI結果を使用
                segments = disk_cache.load_api_result(chunk_info["idx"])
                if segments:
                    for seg in segments:
                        segment = TranscriptionSegment(
                            start=seg["start"],
                            end=seg["end"],
                            text=seg["text"],
                            words=None,
                            chars=None
                        )
                        all_segments.append(segment)
        
        all_segments.sort(key=lambda x: x.start)
        return all_segments
    
    def _create_chunks(self, audio, step, sample_rate):
        """チャンクを作成（既存のロジック）"""
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