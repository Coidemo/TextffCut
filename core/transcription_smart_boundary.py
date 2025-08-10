"""
スマート境界検出による文字起こしモジュール
分割したい境界付近のみを無音検出してメモリ効率的に処理
"""

import os
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from utils.logging import get_logger

from .transcription import Transcriber, TranscriptionResult, TranscriptionSegment
from .video import SilenceInfo

# 循環インポートを避けるため、型チェック時のみインポート
if TYPE_CHECKING:
    from .auto_optimizer import AutoOptimizer
    from .memory_monitor import MemoryMonitor

logger = get_logger(__name__)


class SmartBoundaryTranscriber(Transcriber):
    """スマート境界検出による文字起こしクラス"""

    # 基本設定
    TARGET_DURATION = 30  # 30秒を目標（Whisperの制約）
    MAX_SEGMENT_DURATION = 30  # Whisperの最大セグメント長
    PREFERRED_SEGMENT_DURATION = 20  # 推奨セグメント長
    MIN_SEGMENT_DURATION = 5  # 最小セグメント長
    BOUNDARY_WINDOW = 5  # 境界前後5秒を検査
    MIN_SILENCE_LEN = 0.3  # 最小無音長（秒）
    SILENCE_THRESH = -35  # 無音閾値（dB）

    def __init__(
        self, config, optimizer: Optional["AutoOptimizer"] = None, memory_monitor: Optional["MemoryMonitor"] = None
    ) -> None:
        """初期化"""
        super().__init__(config)
        self.temp_dir = None
        self.optimizer = optimizer
        self.memory_monitor = memory_monitor
        self._segment_count = 0  # 処理済みセグメント数

    def transcribe(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False,
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
        logger.info(f"動画時間: {duration / 60:.1f}分")

        # 一時ディレクトリ作成
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_boundary_")

        try:
            if progress_callback:
                progress_callback(0.05, "音声を抽出中...")
            
            # まず全体の音声を抽出（VAD処理のため）
            temp_audio = os.path.join(self.temp_dir, "audio.wav")
            extract_cmd = [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                temp_audio
            ]
            subprocess.run(extract_cmd, capture_output=True, check=True)
            
            if progress_callback:
                progress_callback(0.1, "音声区間を検出中...")

            # VADベースでセグメントを検出
            segments = self._find_vad_based_segments(temp_audio)
            logger.info(f"VADセグメント数: {len(segments)}, 総時間: {sum(e-s for s,e in segments):.1f}秒")

            # 各セグメントを処理
            all_results = []
            for i, (start, end) in enumerate(segments):
                if progress_callback:
                    base_progress = 0.2 + (0.7 * i / len(segments))
                    progress_callback(base_progress, f"セグメント {i + 1}/{len(segments)} を処理中...")

                # セグメントを処理
                segment_result = self._process_segment(video_path, start, end, model_size, i, skip_alignment)
                all_results.extend(segment_result)

            # 結果を作成
            result = TranscriptionResult(
                language=self.config.transcription.language,
                segments=all_results,
                original_audio_path=video_path,
                model_size=model_size,
                processing_time=time.time() - start_time,
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

    def _get_video_duration(self, video_path: str | Path) -> float:
        """動画の長さを取得"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return float(result.stdout.strip())

    def _find_vad_based_segments(self, audio_path: str) -> list[tuple[float, float]]:
        """VADベースで音声セグメントを検出し、30秒制約で分割"""
        try:
            # 簡易的なVAD実装（ffmpegのsilencedetectを使用）
            # 本来はpyannote.audioなどを使うべきだが、依存関係を最小限にするため
            
            # 音声の長さを取得
            duration_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
                           "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
            result = subprocess.run(duration_cmd, capture_output=True, text=True)
            total_duration = float(result.stdout.strip())
            
            # 無音検出で音声区間を特定
            silence_cmd = [
                "ffmpeg", "-i", audio_path, "-af",
                f"silencedetect=noise={self.SILENCE_THRESH}dB:d={self.MIN_SILENCE_LEN}",
                "-f", "null", "-"
            ]
            result = subprocess.run(silence_cmd, capture_output=True, text=True, stderr=subprocess.STDOUT)
            
            # 無音区間を解析して音声区間を抽出
            vad_segments = []
            current_start = 0.0
            
            import re
            silence_starts = re.findall(r"silence_start: ([\d.]+)", result.stdout)
            silence_ends = re.findall(r"silence_end: ([\d.]+)", result.stdout)
            
            # 無音区間から音声区間を計算
            if silence_starts:
                # 最初の無音開始まで
                if float(silence_starts[0]) > 0.1:
                    vad_segments.append((0.0, float(silence_starts[0])))
                
                # 無音区間の間の音声区間
                for i in range(len(silence_ends)):
                    start = float(silence_ends[i])
                    if i < len(silence_starts) - 1:
                        end = float(silence_starts[i + 1])
                    else:
                        end = total_duration
                    
                    if end - start > 0.1:  # 0.1秒以上の音声区間のみ
                        vad_segments.append((start, end))
            else:
                # 無音が検出されなかった場合は全体を1つのセグメントとして扱う
                vad_segments = [(0.0, total_duration)]
            
            # VADセグメントを30秒以内に分割
            final_segments = []
            for segment in vad_segments:
                start, end = segment  # タプルとして扱う
                
                # セグメントが30秒を超える場合は分割
                if end - start > self.MAX_SEGMENT_DURATION:
                    current_start = start
                    while current_start < end:
                        segment_end = min(current_start + self.PREFERRED_SEGMENT_DURATION, end)
                        final_segments.append((current_start, segment_end))
                        current_start = segment_end
                else:
                    final_segments.append((start, end))
            
            # 短すぎるセグメントを結合
            merged_segments = []
            i = 0
            while i < len(final_segments):
                start, end = final_segments[i]
                
                # 次のセグメントと結合可能か確認
                while i + 1 < len(final_segments):
                    next_start, next_end = final_segments[i + 1]
                    # 間隔が短く、合計時間が30秒以内なら結合
                    if (next_start - end < 0.5 and 
                        next_end - start <= self.MAX_SEGMENT_DURATION):
                        end = next_end
                        i += 1
                    else:
                        break
                
                # 最小長以上なら追加
                if end - start >= self.MIN_SEGMENT_DURATION:
                    merged_segments.append((start, end))
                i += 1
            
            logger.info(f"VAD検出: {len(vad_segments)}個の音声区間 → {len(merged_segments)}個のセグメントに分割")
            return merged_segments
            
        except Exception as e:
            logger.warning(f"VADベース分割に失敗、フォールバック: {e}")
            # フォールバック：固定長分割
            return self._find_fixed_segments(audio_path)
    
    def _find_fixed_segments(self, audio_path: str) -> list[tuple[float, float]]:
        """固定長でセグメントを分割（フォールバック）"""
        # 音声の長さを取得
        cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", 
               "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        duration = float(result.stdout.strip())
        
        segments = []
        current = 0.0
        while current < duration:
            segment_end = min(current + self.PREFERRED_SEGMENT_DURATION, duration)
            segments.append((current, segment_end))
            current = segment_end
            
        return segments

    def _find_smart_boundaries(self, video_path: str | Path, duration: float) -> list[float]:
        """スマートに境界を検出（レガシー実装、互換性のため残す）"""
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

                logger.info(f"境界検索: {search_start / 60:.1f}分 - {search_end / 60:.1f}分")

                # この範囲の無音を検出
                silence_in_window = self._detect_silence_in_range(video_path, search_start, search_end)

                if silence_in_window:
                    # 理想点に最も近い無音を選択
                    best_silence = min(silence_in_window, key=lambda s: abs((s.start + s.end) / 2 - ideal_point))
                    boundary = (best_silence.start + best_silence.end) / 2
                    boundaries.append(boundary)
                    logger.info(f"境界を発見: {boundary / 60:.1f}分")
                else:
                    # 無音がなければ理想点をそのまま使用
                    boundaries.append(ideal_point)
                    logger.info(f"無音なし、理想点を使用: {ideal_point / 60:.1f}分")
            except Exception as e:
                logger.error(f"境界検出エラー（理想点 {ideal_point / 60:.1f}分）: {str(e)}")
                # エラーが発生した場合は理想点を使用
                boundaries.append(ideal_point)

        boundaries.append(duration)  # 終了点
        return boundaries

    def _detect_silence_in_range(self, video_path: str | Path, start: float, end: float) -> list[SilenceInfo]:
        """指定範囲の無音を検出"""
        # 一時WAVファイルを作成
        temp_wav = os.path.join(self.temp_dir, f"range_{start}_{end}.wav")

        try:
            # 指定範囲の音声を抽出
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                video_path,
                "-t",
                str(end - start),
                "-vn",
                "-ar",
                "16000",  # サンプリングレート下げてメモリ節約
                "-ac",
                "1",  # モノラル
                "-f",
                "wav",
                temp_wav,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"FFmpeg エラー: {result.stderr}")
                return []  # エラー時は空のリストを返す

            # 無音検出
            from .video import VideoProcessor

            processor = VideoProcessor(self.config)
            silences = processor.detect_silence_from_wav(
                temp_wav, noise_threshold=self.SILENCE_THRESH, min_silence_duration=self.MIN_SILENCE_LEN
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
        self, video_path: str | Path, start: float, end: float, model_size: str, segment_index: int, skip_alignment: bool = False
    ) -> list[TranscriptionSegment]:
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
                self.TARGET_DURATION = optimal_params["chunk_seconds"]

                # バッチサイズも記録（後で使用）
                self._dynamic_batch_size = optimal_params["batch_size"]
                
                # 動的パラメータを保存（後でモデル読み込み時に使用）
                self._dynamic_compute_type = optimal_params.get("compute_type", self.config.transcription.compute_type)

                # 診断フェーズかどうかを確認
                if hasattr(self.optimizer, "diagnostic_mode") and self.optimizer.diagnostic_mode:
                    logger.info(
                        f"診断フェーズ {self.optimizer.diagnostic_chunks_processed + 1}/{self.optimizer.DIAGNOSTIC_CHUNKS_COUNT}: "
                        f"チャンク={self.TARGET_DURATION}秒, バッチサイズ={self._dynamic_batch_size}, compute_type={self._dynamic_compute_type}"
                    )
                else:
                    logger.info(
                        f"動的パラメータ調整: TARGET_DURATION {old_duration}秒 → {self.TARGET_DURATION}秒, "
                        f"バッチサイズ: {self._dynamic_batch_size}, compute_type: {self._dynamic_compute_type}"
                    )

            except Exception as e:
                logger.warning(f"動的最適化でエラー: {e}")
                # エラーが発生してもデフォルト値で継続
                self._dynamic_batch_size = 16
                self._dynamic_compute_type = self.config.transcription.compute_type
        else:
            # オプティマイザがない場合はデフォルト値
            self._dynamic_batch_size = 16
            self._dynamic_compute_type = self.config.transcription.compute_type

        # セグメントのWAVファイルを作成
        segment_wav = os.path.join(self.temp_dir, f"segment_{segment_index}.wav")

        # FFmpegで音声を抽出
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            video_path,
            "-t",
            str(end - start),
            "-vn",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            segment_wav,
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        try:
            # WhisperXで処理
            import whisperx

            # 音声を読み込み
            audio = whisperx.load_audio(segment_wav)

            # 動的に決定されたcompute_typeを使用
            compute_type = getattr(self, "_dynamic_compute_type", self.config.transcription.compute_type)
            if compute_type != self.config.transcription.compute_type:
                logger.info(f"動的compute_type: {compute_type} (デフォルト: {self.config.transcription.compute_type})")
            
            # モデルを読み込み
            model = whisperx.load_model(
                model_size,
                self.device,
                compute_type=compute_type,
                language=self.config.transcription.language,
            )

            # 動的バッチサイズを使用（設定されていない場合はデフォルト）
            batch_size = getattr(self, "_dynamic_batch_size", 16)

            # 文字起こし（VAD有効）
            result = model.transcribe(audio, batch_size=batch_size, language=self.config.transcription.language)

            # アライメント処理（skip_alignment=Falseの場合のみ実行）
            if not skip_alignment:
                try:
                    align_model, metadata = whisperx.load_align_model(
                        language_code=self.config.transcription.language, device=self.device
                    )

                    aligned_result = whisperx.align(
                        result["segments"], align_model, metadata, audio, self.device, return_char_alignments=True
                    )
                    segments_data = aligned_result["segments"]
                except Exception as e:
                    logger.error(f"アライメント処理に失敗しました: {str(e)}")
                    raise RuntimeError(
                        f"文字位置情報の取得に失敗しました。アライメント処理でエラーが発生しました: {str(e)}"
                    ) from e
            else:
                # アライメントをスキップする場合は、resultのセグメントをそのまま使用
                segments_data = result["segments"]

            # セグメントを変換（オフセット適用）
            segments = []
            for seg in segments_data:
                segment = TranscriptionSegment(
                    start=seg["start"] + start,
                    end=seg["end"] + start,
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars"),
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
                            if "align_model" in locals():
                                del align_model

                            # さらにメモリが逼迫している場合は処理を中断
                            if post_memory > 95:
                                raise MemoryError(
                                    f"メモリ使用率が限界に達しました: {post_memory:.1f}% - 処理を中断します"
                                )
                except Exception as e:
                    logger.warning(f"メモリ監視でエラー: {e}")

            return segments

        finally:
            # セグメントファイルを削除
            if os.path.exists(segment_wav):
                os.unlink(segment_wav)
