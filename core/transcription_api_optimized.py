"""
最適化されたAPI版文字起こしモジュール
Producer-Consumerパターンによる高速化実装
"""
import os
import json
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from dataclasses import dataclass
import openai
import numpy as np
import soundfile as sf
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .transcription import TranscriptionResult, TranscriptionSegment
from config import Config
from utils.logging import get_logger
from utils.system_resources import system_resource_manager
from core.queue_manager import TaskQueueManager, APITask
from core.segment_splitter import SegmentSplitter

logger = get_logger(__name__)


class OptimizedAPITranscriber:
    """最適化されたAPI版文字起こしクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_config = config.transcription
        self.segment_splitter = SegmentSplitter()
    
    def _transcribe_with_chunks_optimized(self, client, audio, original_audio_path: str,
                                         progress_callback: Optional[callable] = None) -> TranscriptionResult:
        """Producer-Consumerパターンによる最適化されたチャンク並列処理"""
        start_time = time.time()
        
        # システムスペックに基づいてチャンクサイズを決定
        system_spec = system_resource_manager.get_system_spec()
        if self.api_config.adaptive_workers:
            chunk_seconds = system_spec.recommended_chunk_seconds
            logger.info(f"適応的チャンクサイズ: {chunk_seconds}秒 (スペック: {system_spec.spec_level})")
        else:
            chunk_seconds = self.api_config.chunk_seconds
        
        sample_rate = 16000
        step = chunk_seconds * sample_rate
        
        # チャンクを作成（既存のロジックを使用）
        chunks = self._create_chunks(audio, step, sample_rate)
        
        # 一時ディレクトリを作成
        temp_dir = tempfile.mkdtemp(prefix="textffcut_api_chunks_")
        
        try:
            # チャンクファイルを作成
            chunk_files = self._save_chunk_files(chunks, temp_dir, sample_rate)
            
            if progress_callback:
                progress_callback(0.1, f"チャンク作成完了: {len(chunk_files)}個")
            
            # アライメントモデルを事前に読み込み
            align_model, align_meta = self._load_alignment_model()
            
            # Producer-Consumerパターンで処理
            queue_manager = TaskQueueManager(progress_callback)
            
            # ワーカー数を初期化（システムスペックに基づく）
            if self.api_config.adaptive_workers:
                api_workers = min(system_spec.recommended_api_workers, 10)  # OpenAIのレート制限対策
                align_workers = system_spec.recommended_align_workers
            else:
                api_workers = 5
                align_workers = 2
            
            queue_manager.initialize_workers(api_workers, align_workers)
            
            # APIタスクを作成
            api_tasks = []
            for chunk_file, start_offset, chunk_idx in chunk_files:
                task = APITask(
                    chunk_idx=chunk_idx,
                    chunk_file=chunk_file,
                    start_offset=start_offset,
                    priority=chunk_idx  # 順番通りに処理
                )
                api_tasks.append(task)
            
            queue_manager.add_api_tasks(api_tasks)
            
            # API処理関数
            def api_processor(chunk_file: str, start_offset: float, chunk_idx: int) -> List[Dict[str, Any]]:
                return self._call_api_and_split_segments(client, chunk_file, start_offset, chunk_idx, chunk_seconds)
            
            # アライメント処理関数
            def align_processor(segments: List[Dict[str, Any]], chunk_file: str, 
                              start_offset: float, chunk_idx: int) -> List[TranscriptionSegment]:
                return self._align_segments(segments, chunk_file, start_offset, chunk_idx, 
                                          align_model, align_meta)
            
            # 並列処理を開始
            results = queue_manager.start_processing(
                api_processor, align_processor, align_model, align_meta
            )
            
            # 結果を統合
            all_segments = []
            for result in results:
                all_segments.extend(result.segments)
            
            # セグメントをソート
            all_segments.sort(key=lambda x: x.start)
            
            processing_time = time.time() - start_time
            logger.info(f"最適化処理完了: {len(all_segments)}セグメント, 処理時間: {processing_time:.1f}秒")
            
            return TranscriptionResult(
                language=self.api_config.language,
                segments=all_segments,
                original_audio_path=original_audio_path,
                model_size="whisper-1_api_optimized",
                processing_time=processing_time
            )
        
        finally:
            # クリーンアップ
            queue_manager.shutdown()
            self._cleanup_temp_dir(temp_dir)
    
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
    
    def _save_chunk_files(self, chunks, temp_dir, sample_rate):
        """チャンクをファイルに保存"""
        chunk_files = []
        for i, chunk in enumerate(chunks):
            chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.wav")
            sf.write(chunk_file, chunk["array"], sample_rate)
            
            chunk_size = os.path.getsize(chunk_file) / (1024 * 1024)
            if chunk_size > 25:
                logger.warning(f"チャンク {i} がサイズ制限を超過: {chunk_size:.1f}MB")
                continue
            
            chunk_files.append((chunk_file, chunk["start"], i))
        
        return chunk_files
    
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
    
    def _call_api_and_split_segments(self, client, chunk_file: str, start_offset: float, 
                                    chunk_idx: int, chunk_duration: float) -> List[Dict[str, Any]]:
        """API呼び出しとセグメント分割"""
        try:
            with open(chunk_file, 'rb') as audio_file:
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
                            "start": seg['start'] + start_offset,
                            "end": seg['end'] + start_offset,
                            "text": seg['text']
                        }
                    else:
                        segment = {
                            "start": seg.start + start_offset,
                            "end": seg.end + start_offset,
                            "text": seg.text
                        }
                    segments.append(segment)
            elif response.text.strip():
                segment = {
                    "start": start_offset,
                    "end": start_offset + chunk_duration,
                    "text": response.text
                }
                segments.append(segment)
            
            # 長いセグメントを分割
            if segments:
                segments = self.segment_splitter.split_segments(segments, chunk_duration)
            
            logger.debug(f"チャンク {chunk_idx}: API完了, {len(segments)}セグメント")
            return segments
            
        except Exception as e:
            logger.error(f"チャンク {chunk_idx} API処理エラー: {e}")
            return []
    
    def _align_segments(self, segments: List[Dict[str, Any]], chunk_file: str,
                       start_offset: float, chunk_idx: int, align_model, align_meta) -> List[TranscriptionSegment]:
        """セグメントのアライメント処理"""
        if not align_model or not align_meta or not segments:
            # アライメントなしで返す
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
            chunk_audio = whisperx.load_audio(chunk_file)
            
            # WhisperX形式に変換（チャンク内相対時間）
            whisperx_segments = []
            for seg in segments:
                whisperx_segments.append({
                    "start": seg["start"] - start_offset,
                    "end": seg["end"] - start_offset,
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
                    start=seg["start"] + start_offset,
                    end=seg["end"] + start_offset,
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars")
                )
                
                # wordsのタイムスタンプも調整
                if aligned_seg.words:
                    for word in aligned_seg.words:
                        if "start" in word:
                            word["start"] += start_offset
                        if "end" in word:
                            word["end"] += start_offset
                
                aligned_segments.append(aligned_seg)
            
            logger.debug(f"チャンク {chunk_idx}: アライメント成功")
            return aligned_segments
            
        except Exception as e:
            logger.warning(f"チャンク {chunk_idx} アライメント失敗: {e}")
            # アライメント失敗時は元のセグメントを返す
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
    
    def _cleanup_temp_dir(self, temp_dir):
        """一時ディレクトリをクリーンアップ"""
        import shutil
        try:
            shutil.rmtree(temp_dir)
        except:
            pass