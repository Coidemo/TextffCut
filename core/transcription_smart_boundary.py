"""
スマート境界検出による文字起こしモジュール
分割したい境界付近のみを無音検出してメモリ効率的に処理
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import List, Tuple, Optional, Callable, TYPE_CHECKING
import json

from .transcription import Transcriber, TranscriptionResult, TranscriptionSegment
from .video import SilenceInfo, VideoProcessor
from utils.logging import get_logger

# 循環インポートを避けるため、型チェック時のみインポート
if TYPE_CHECKING:
    from .auto_optimizer import AutoOptimizer
    from .memory_monitor import MemoryMonitor

logger = get_logger(__name__)


class SmartBoundaryTranscriber(Transcriber):
    """スマート境界検出による文字起こしクラス"""
    
    # 基本設定
    TARGET_DURATION = 20 * 60  # 20分を目標
    BOUNDARY_WINDOW = 30       # 境界前後30秒を検査
    MIN_SILENCE_LEN = 0.5      # 最小無音長（秒）
    SILENCE_THRESH = -35       # 無音閾値（dB）
    
    def __init__(self, config, optimizer: Optional['AutoOptimizer'] = None, 
                 memory_monitor: Optional['MemoryMonitor'] = None):
        """初期化"""
        super().__init__(config)
        self.temp_dir = None
        self.optimizer = optimizer
        self.memory_monitor = memory_monitor
        self._segment_count = 0  # 処理済みセグメント数
    
    def transcribe(
        self,
        video_path: str,
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False
    ) -> TranscriptionResult:
        """
        スマート境界検出による文字起こし
        """
        # APIモードの場合は親クラスの処理
        if self.config.transcription.use_api:
            return super().transcribe(video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment)
        
        # キャッシュ確認
        model_size = model_size or self.config.transcription.model_size
        cache_path = self.get_cache_path(video_path, f"{model_size}_boundary")
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
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_boundary_")
        
        try:
            if progress_callback:
                progress_callback(0.1, "最適な分割点を検出中...")
            
            # スマート境界検出で分割点を決定
            split_points = self._find_smart_boundaries(video_path, duration)
            logger.info(f"分割点: {[f'{p/60:.1f}分' for p in split_points]}")
            
            # セグメントに分割
            segments = []
            for i in range(len(split_points) - 1):
                segments.append((split_points[i], split_points[i + 1]))
            
            # 各セグメントを処理
            all_results = []
            for i, (start, end) in enumerate(segments):
                if progress_callback:
                    base_progress = 0.2 + (0.7 * i / len(segments))
                    progress_callback(base_progress, f"セグメント {i+1}/{len(segments)} を処理中...")
                
                # セグメントを処理
                segment_result = self._process_segment(
                    video_path, start, end, model_size, i
                )
                all_results.extend(segment_result)
            
            # 結果を作成
            result = TranscriptionResult(
                language=self.config.transcription.language,
                segments=all_results,
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
            # クリーンアップ
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
    
    def _find_smart_boundaries(self, video_path: str, duration: float) -> List[float]:
        """スマートに境界を検出"""
        boundaries = [0.0]  # 開始点
        
        # 理想的な分割点を計算
        ideal_points = []
        current = self.TARGET_DURATION
        while current < duration:
            ideal_points.append(current)
            current += self.TARGET_DURATION
        
        # 各理想点の周辺で無音を探す
        for ideal_point in ideal_points:
            try:
                # 検査範囲を決定（前後30秒）
                search_start = max(0, ideal_point - self.BOUNDARY_WINDOW)
                search_end = min(duration, ideal_point + self.BOUNDARY_WINDOW)
                
                logger.info(f"境界検索: {search_start/60:.1f}分 - {search_end/60:.1f}分")
                
                # この範囲の無音を検出
                silence_in_window = self._detect_silence_in_range(
                    video_path, search_start, search_end
                )
                
                if silence_in_window:
                    # 理想点に最も近い無音を選択
                    best_silence = min(
                        silence_in_window,
                        key=lambda s: abs((s.start + s.end) / 2 - ideal_point)
                    )
                    boundary = (best_silence.start + best_silence.end) / 2
                    boundaries.append(boundary)
                    logger.info(f"境界を発見: {boundary/60:.1f}分")
                else:
                    # 無音がなければ理想点をそのまま使用
                    boundaries.append(ideal_point)
                    logger.info(f"無音なし、理想点を使用: {ideal_point/60:.1f}分")
            except Exception as e:
                logger.error(f"境界検出エラー（理想点 {ideal_point/60:.1f}分）: {str(e)}")
                # エラーが発生した場合は理想点を使用
                boundaries.append(ideal_point)
        
        boundaries.append(duration)  # 終了点
        return boundaries
    
    def _detect_silence_in_range(
        self,
        video_path: str,
        start: float,
        end: float
    ) -> List[SilenceInfo]:
        """指定範囲の無音を検出"""
        # 一時WAVファイルを作成
        temp_wav = os.path.join(self.temp_dir, f"range_{start}_{end}.wav")
        
        try:
            # 指定範囲の音声を抽出
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", video_path,
                "-t", str(end - start),
                "-vn",
                "-ar", "16000",  # サンプリングレート下げてメモリ節約
                "-ac", "1",      # モノラル
                "-f", "wav",
                temp_wav
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg エラー: {result.stderr}")
                return []  # エラー時は空のリストを返す
            
            # 無音検出
            from .video import VideoProcessor
            processor = VideoProcessor(self.config)
            silences = processor.detect_silence_from_wav(
                temp_wav,
                noise_threshold=self.SILENCE_THRESH,
                min_silence_duration=self.MIN_SILENCE_LEN
            )
            
            # オフセットを適用
            for silence in silences:
                silence.start += start
                silence.end += start
            
            return silences
            
        except Exception as e:
            logger.error(f"無音検出エラー（範囲 {start:.1f}s-{end:.1f}s）: {str(e)}")
            return []  # エラー時は空のリストを返す
            
        finally:
            # 一時ファイルを削除
            if os.path.exists(temp_wav):
                os.unlink(temp_wav)
    
    def _process_segment(
        self,
        video_path: str,
        start: float,
        end: float,
        model_size: str,
        segment_index: int
    ) -> List[TranscriptionSegment]:
        """セグメントを処理"""
        # 動的メモリ最適化
        if self.optimizer and self.memory_monitor:
            try:
                # 現在のメモリ使用率を取得
                current_memory = self.memory_monitor.get_memory_usage()
                logger.info(f"セグメント {segment_index} 処理前 - メモリ使用率: {current_memory:.1f}%")
                
                # 最適なパラメータを取得
                optimal_params = self.optimizer.get_optimal_params(current_memory)
                
                # TARGET_DURATIONを動的に調整
                old_duration = self.TARGET_DURATION
                self.TARGET_DURATION = optimal_params['chunk_seconds']
                
                # バッチサイズも記録（後で使用）
                self._dynamic_batch_size = optimal_params['batch_size']
                
                # 診断フェーズかどうかを確認
                if hasattr(self.optimizer, 'diagnostic_mode') and self.optimizer.diagnostic_mode:
                    logger.info(f"診断フェーズ {self.optimizer.diagnostic_chunks_processed + 1}/{self.optimizer.DIAGNOSTIC_CHUNKS_COUNT}: "
                              f"チャンク={self.TARGET_DURATION}秒, バッチサイズ={self._dynamic_batch_size}")
                else:
                    logger.info(f"動的パラメータ調整: TARGET_DURATION {old_duration}秒 → {self.TARGET_DURATION}秒, バッチサイズ: {self._dynamic_batch_size}")
                
            except Exception as e:
                logger.warning(f"動的最適化でエラー: {e}")
                # エラーが発生してもデフォルト値で継続
                self._dynamic_batch_size = 16
        else:
            # オプティマイザがない場合はデフォルト値
            self._dynamic_batch_size = 16
        
        # セグメントのWAVファイルを作成
        segment_wav = os.path.join(self.temp_dir, f"segment_{segment_index}.wav")
        
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
            # WhisperXで処理
            import whisperx
            
            # 音声を読み込み
            audio = whisperx.load_audio(segment_wav)
            
            # モデルを読み込み
            model = whisperx.load_model(
                model_size,
                self.device,
                compute_type=self.config.transcription.compute_type,
                language=self.config.transcription.language
            )
            
            # 動的バッチサイズを使用（設定されていない場合はデフォルト）
            batch_size = getattr(self, '_dynamic_batch_size', 16)
            
            # 文字起こし（VAD有効）
            result = model.transcribe(
                audio,
                batch_size=batch_size,
                language=self.config.transcription.language
            )
            
            # アライメント処理（必須）
            try:
                align_model, metadata = whisperx.load_align_model(
                    language_code=self.config.transcription.language,
                    device=self.device
                )
                
                aligned_result = whisperx.align(
                    result["segments"],
                    align_model,
                    metadata,
                    audio,
                    self.device,
                    return_char_alignments=True
                )
                segments_data = aligned_result["segments"]
            except Exception as e:
                logger.error(f"アライメント処理に失敗しました: {str(e)}")
                raise RuntimeError(f"文字位置情報の取得に失敗しました。アライメント処理でエラーが発生しました: {str(e)}")
            
            # セグメントを変換（オフセット適用）
            segments = []
            for seg in segments_data:
                segment = TranscriptionSegment(
                    start=seg["start"] + start,
                    end=seg["end"] + start,
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars")
                )
                segments.append(segment)
            
            # メモリ使用状況を記録
            if self.memory_monitor:
                try:
                    post_memory = self.memory_monitor.get_memory_usage()
                    logger.info(f"セグメント {segment_index} 処理後 - メモリ使用率: {post_memory:.1f}%")
                    
                    # メモリ逼迫時の警告
                    if post_memory > 85:
                        logger.warning(f"メモリ使用率が高い状態です: {post_memory:.1f}%")
                        # メモリが90%を超えたら緊急措置
                        if post_memory > 90:
                            logger.error(f"メモリ使用率が危険域に達しました: {post_memory:.1f}%")
                            # ガベージコレクションを強制実行
                            import gc
                            gc.collect()
                            # モデルをアンロード（次回読み込み直し）
                            del model
                            if 'align_model' in locals():
                                del align_model
                            
                            # さらにメモリが逼迫している場合は処理を中断
                            if post_memory > 95:
                                raise MemoryError(f"メモリ使用率が限界に達しました: {post_memory:.1f}% - 処理を中断します")
                except Exception as e:
                    logger.warning(f"メモリ監視でエラー: {e}")
            
            return segments
            
        finally:
            # セグメントファイルを削除
            if os.path.exists(segment_wav):
                os.unlink(segment_wav)