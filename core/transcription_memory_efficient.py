"""
メモリ効率的な文字起こしモジュール
音声ファイルを小さなチャンクに分けて処理し、メモリ使用量を最小化
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Callable
import json

from .transcription import Transcriber, TranscriptionResult, TranscriptionSegment
from utils.logging import get_logger

logger = get_logger(__name__)


class MemoryEfficientTranscriber(Transcriber):
    """メモリ効率的な文字起こしクラス"""
    
    # チャンクサイズ（秒）
    CHUNK_DURATION = 300  # 5分ずつ処理
    
    def __init__(self, config):
        """初期化"""
        super().__init__(config)
        self.temp_dir = None
    
    def transcribe(
        self,
        video_path: str,
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True,
        save_cache: bool = True
    ) -> TranscriptionResult:
        """
        メモリ効率的な文字起こし
        """
        # APIモードの場合は親クラスの処理を使用
        if self.config.transcription.use_api:
            return super().transcribe(video_path, model_size, progress_callback, use_cache, save_cache)
        
        # キャッシュ確認
        model_size = model_size or self.config.transcription.model_size
        cache_path = self.get_cache_path(video_path, f"{model_size}_efficient")
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
        
        # 一時ディレクトリを作成
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_efficient_")
        
        try:
            # チャンクごとに処理
            all_segments = []
            num_chunks = int((duration + self.CHUNK_DURATION - 1) / self.CHUNK_DURATION)
            
            for i in range(num_chunks):
                chunk_start = i * self.CHUNK_DURATION
                chunk_end = min((i + 1) * self.CHUNK_DURATION, duration)
                
                if progress_callback:
                    base_progress = i / num_chunks
                    progress_callback(base_progress, f"チャンク {i+1}/{num_chunks} を処理中...")
                
                # チャンクを抽出して処理
                chunk_segments = self._process_chunk(
                    video_path, chunk_start, chunk_end, model_size, i
                )
                
                # オフセットを適用
                for seg in chunk_segments:
                    seg.start += chunk_start
                    seg.end += chunk_start
                
                all_segments.extend(chunk_segments)
                
                # メモリクリーンアップ
                import gc
                gc.collect()
            
            # 結果を作成
            result = TranscriptionResult(
                language=self.config.transcription.language,
                segments=all_segments,
                original_audio_path=video_path,
                model_size=model_size,
                processing_time=time.time() - start_time
            )
            
            # キャッシュに保存
            if save_cache:
                self.save_to_cache(result, cache_path)
            
            if progress_callback:
                progress_callback(1.0, "完了")
            
            return result
            
        finally:
            # 一時ファイルをクリーンアップ
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir)
    
    def _get_video_duration(self, video_path: str) -> float:
        """動画の長さを取得"""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())
    
    def _process_chunk(
        self,
        video_path: str,
        start: float,
        end: float,
        model_size: str,
        chunk_index: int
    ) -> List[TranscriptionSegment]:
        """チャンクを処理"""
        # チャンクのWAVファイルを作成
        chunk_wav = os.path.join(self.temp_dir, f"chunk_{chunk_index}.wav")
        
        # FFmpegで音声を抽出（16kHz, モノラル）
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", video_path,
            "-t", str(end - start),
            "-vn",
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            chunk_wav
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        
        try:
            # WhisperXで処理（メモリ効率モード）
            import whisperx
            
            # 音声を読み込み
            audio = whisperx.load_audio(chunk_wav)
            
            # モデルを読み込み（キャッシュされる）
            model = whisperx.load_model(
                model_size,
                self.device,
                compute_type=self.config.transcription.compute_type,
                language=self.config.transcription.language
            )
            
            # 文字起こし（バッチサイズを小さく）
            result = model.transcribe(
                audio,
                batch_size=4,  # さらに小さく
                language=self.config.transcription.language
            )
            
            # セグメントを変換
            segments = []
            for seg in result.get("segments", []):
                segment = TranscriptionSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"]
                )
                segments.append(segment)
            
            return segments
            
        finally:
            # チャンクファイルを削除
            if os.path.exists(chunk_wav):
                os.unlink(chunk_wav)