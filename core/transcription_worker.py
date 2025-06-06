"""
TextffCut ローカル文字起こし専用実装

2段階処理アーキテクチャに特化した文字起こし処理。
アライメント処理を別工程として分離。
"""

import os
import time
import tempfile
from typing import List, Optional, Callable, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

try:
    import whisperx
    import torch
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

from config import Config
from utils.logging import get_logger
from .models import TranscriptionSegmentV2
from .interfaces import ITranscriptionProcessor

logger = get_logger(__name__)


class LocalTranscriptionWorker(ITranscriptionProcessor):
    """
    ローカル文字起こし処理の実装
    
    特徴:
    - アライメント処理を完全に分離
    - 効率的なチャンク処理
    - メモリ使用量の最適化
    """
    
    def __init__(self, config: Config):
        """初期化"""
        self.config = config
        
        if not WHISPERX_AVAILABLE:
            raise ImportError("WhisperXが利用できません")
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"ローカル文字起こしワーカー初期化: device={self.device}")
    
    def transcribe(
        self,
        audio_path: str,
        language: str,
        model_size: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[TranscriptionSegmentV2]:
        """
        音声ファイルから文字起こしを実行（アライメントなし）
        
        Args:
            audio_path: 音声ファイルのパス
            language: 言語コード
            model_size: モデルサイズ
            progress_callback: 進捗報告用コールバック
            
        Returns:
            文字起こしセグメントのリスト（アライメント情報なし）
        """
        logger.info(f"文字起こし開始: {audio_path}")
        start_time = time.time()
        
        if progress_callback:
            progress_callback(0.0, "音声を読み込み中...")
        
        # 音声を読み込み
        audio = whisperx.load_audio(audio_path)
        audio_duration = len(audio) / 16000  # 16kHz
        logger.info(f"音声時間: {audio_duration:.1f}秒")
        
        if progress_callback:
            progress_callback(0.05, "モデルを読み込み中...")
        
        # モデルを読み込み
        asr_model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=language
        )
        
        # チャンク処理の準備
        chunk_sec = self.config.transcription.chunk_seconds
        sr = 16000  # サンプリングレート
        step = chunk_sec * sr
        
        chunks = self._create_chunks(audio, step, sr)
        logger.info(f"チャンク数: {len(chunks)}")
        
        if progress_callback:
            progress_callback(0.1, f"{len(chunks)}個のチャンクを処理中...")
        
        # 並列処理で文字起こし
        segments_all = []
        total_chunks = len(chunks)
        completed_chunks = 0
        
        # ワーカー数の調整（メモリ効率を考慮）
        num_workers = min(self.config.transcription.num_workers, 4)
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = []
            for i, chunk in enumerate(chunks):
                future = executor.submit(
                    self._transcribe_chunk,
                    chunk,
                    asr_model,
                    language,
                    i
                )
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    segments = future.result()
                    segments_all.extend(segments)
                    completed_chunks += 1
                    
                    if progress_callback:
                        progress = 0.1 + (0.8 * completed_chunks / total_chunks)
                        status = f"文字起こし処理中... ({completed_chunks}/{total_chunks} チャンク)"
                        progress_callback(progress, status)
                        
                except Exception as e:
                    logger.error(f"チャンク処理エラー: {str(e)}")
                    # エラーが発生してもその他のチャンクは処理を続ける
        
        # セグメントをソート
        segments_all.sort(key=lambda x: x.start)
        
        # 処理時間
        processing_time = time.time() - start_time
        logger.info(
            f"文字起こし完了: {len(segments_all)}セグメント, "
            f"処理時間: {processing_time:.1f}秒"
        )
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        return segments_all
    
    def _create_chunks(self, audio: np.ndarray, step: int, sr: int) -> List[Dict[str, Any]]:
        """音声をチャンクに分割"""
        chunks = []
        MIN_CHUNK_DURATION = 1.0  # 最小チャンク長（秒）
        
        pending_chunk = None
        
        for i in range(0, len(audio), step):
            chunk_audio = audio[i:i+step]
            start_time = i / sr
            duration = len(chunk_audio) / sr
            
            # 短いチャンクの処理
            if pending_chunk is not None:
                # 前の短いチャンクと結合
                combined_audio = np.concatenate([pending_chunk["array"], chunk_audio])
                combined_chunk = {
                    "array": combined_audio,
                    "start": pending_chunk["start"],
                    "duration": len(combined_audio) / sr
                }
                chunks.append(combined_chunk)
                pending_chunk = None
                continue
            
            if duration < MIN_CHUNK_DURATION:
                if chunks:
                    # 前のチャンクに結合
                    last_chunk = chunks[-1]
                    combined_audio = np.concatenate([last_chunk["array"], chunk_audio])
                    chunks[-1] = {
                        "array": combined_audio,
                        "start": last_chunk["start"],
                        "duration": len(combined_audio) / sr
                    }
                else:
                    # 最初のチャンクが短い場合は保留
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
        
        # 最後の保留チャンクを追加
        if pending_chunk is not None:
            chunks.append(pending_chunk)
        
        return chunks
    
    def _transcribe_chunk(
        self,
        chunk: Dict[str, Any],
        asr_model: Any,
        language: str,
        chunk_idx: int
    ) -> List[TranscriptionSegmentV2]:
        """チャンクを文字起こし（アライメントなし）"""
        try:
            # WhisperXで文字起こし
            result = asr_model.transcribe(
                chunk["array"],
                batch_size=self.config.transcription.batch_size,
                language=language
            )
            
            # セグメントを変換
            segments = []
            for seg in result["segments"]:
                # タイムスタンプのオフセットを適用
                segment = TranscriptionSegmentV2(
                    id=f"chunk{chunk_idx}_seg{len(segments)}",
                    text=seg["text"],
                    start=seg["start"] + chunk["start"],
                    end=seg["end"] + chunk["start"],
                    language=language,
                    transcription_completed=True,
                    alignment_completed=False,  # アライメントは別途
                    confidence=seg.get("score")
                )
                segments.append(segment)
            
            logger.debug(f"チャンク {chunk_idx}: {len(segments)}セグメント")
            return segments
            
        except Exception as e:
            logger.error(f"チャンク {chunk_idx} の文字起こしエラー: {str(e)}")
            raise
    
    def validate_requirements(self) -> bool:
        """処理に必要な要件を検証"""
        # WhisperXが利用可能か
        if not WHISPERX_AVAILABLE:
            return False
        
        # GPUメモリの確認（CUDA使用時）
        if self.device == "cuda":
            try:
                import torch
                if not torch.cuda.is_available():
                    return False
                # メモリが十分かチェック（簡易的）
                mem_gb = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if mem_gb < 2.0:  # 最低2GB
                    logger.warning("GPU メモリが不足している可能性があります")
            except:
                pass
        
        return True
    
    def get_estimated_memory_usage(self, duration_seconds: float) -> float:
        """推定メモリ使用量を取得（MB）"""
        # 基本的な推定値
        base_memory = 500  # モデル読み込み
        
        # 音声データのメモリ
        audio_memory = (duration_seconds * 16000 * 4) / (1024 * 1024)  # 16kHz, float32
        
        # チャンク処理のオーバーヘッド
        chunk_count = max(1, duration_seconds / self.config.transcription.chunk_seconds)
        chunk_overhead = chunk_count * 50  # チャンクあたり50MB
        
        # GPU使用時は追加メモリ
        if self.device == "cuda":
            gpu_overhead = 1000  # 1GB
        else:
            gpu_overhead = 0
        
        total_memory = base_memory + audio_memory + chunk_overhead + gpu_overhead
        
        return total_memory