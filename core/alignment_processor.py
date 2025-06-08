"""
TextffCut アライメント処理実装

文字起こし結果に対して高精度な文字位置情報（タイムスタンプ）を
付与するアライメント処理を実装します。
"""

import os
import time
import tempfile
import subprocess
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any, Tuple
import numpy as np
import gc

from config import Config
from utils.logging import get_logger
from .exceptions import AlignmentError
from core.memory_monitor import MemoryMonitor

from .interfaces import IAlignmentProcessor
from .models import (
    TranscriptionSegmentV2,
    WordInfo,
    CharInfo
)
logger = get_logger(__name__)


class AlignmentProcessor(IAlignmentProcessor):
    """
    アライメント処理の実装
    
    特徴:
    - WhisperXのアライメントモデルを使用
    - 日本語の音素ベースアライメントに対応
    - タイムスタンプ欠落時の推定処理
    - バッチ処理による効率化
    """
    
    # デフォルト値
    DEFAULT_BATCH_SIZE = 8
    
    def __init__(self, config: Config, batch_size: Optional[int] = None):
        """初期化
        
        Args:
            config: 設定オブジェクト
            batch_size: バッチサイズ（Noneの場合はデフォルト値を使用）
        """
        self.config = config
        self.device = "cuda" if self._check_cuda_available() else "cpu"
        self.align_model = None
        self.metadata = None
        self.temp_dir = None
        self.batch_size = batch_size if batch_size is not None else self.DEFAULT_BATCH_SIZE
        
        logger.info(f"アライメントプロセッサー初期化: device={self.device}, batch_size={self.batch_size}")
    
    def run_diagnostic(self, audio_path: str, language: str, 
                       sample_segments: Optional[List[TranscriptionSegmentV2]] = None,
                       progress_callback: Optional[Callable[[float, str], None]] = None) -> Dict[str, Any]:
        """
        アライメント処理の診断を実行し、最適なパラメータを推定
        
        Args:
            audio_path: 音声ファイルのパス
            language: 言語コード
            sample_segments: テスト用のサンプルセグメント（Noneの場合はダミーを生成）
            progress_callback: 進捗報告用コールバック
            
        Returns:
            診断結果（最適バッチサイズ、メモリ使用量など）
        """
        logger.info("アライメント診断フェーズ開始")
        memory_monitor = MemoryMonitor()
        
        # 初期メモリ
        initial_memory = memory_monitor.get_memory_usage()
        logger.info(f"診断開始時メモリ: {initial_memory:.1f}%")
        
        diagnostic_result = {
            'initial_memory': initial_memory,
            'model_memory': 0,
            'audio_memory': 0,
            'batch_memory_per_segment': 0,
            'optimal_batch_size': self.DEFAULT_BATCH_SIZE,
            'max_safe_batch_size': self.DEFAULT_BATCH_SIZE,
            'diagnostic_completed': False
        }
        
        try:
            # Step 1: アライメントモデルのロード
            if progress_callback:
                progress_callback(0.2, "アライメントモデルを読み込み中...")
            
            self._load_align_model(language)
            gc.collect()  # 明示的なガベージコレクション
            
            model_loaded_memory = memory_monitor.get_memory_usage()
            diagnostic_result['model_memory'] = model_loaded_memory - initial_memory
            logger.info(f"モデルロード後メモリ: {model_loaded_memory:.1f}% (増加: {diagnostic_result['model_memory']:.1f}%)")
            
            # Step 2: 音声データの読み込み（部分的）
            if progress_callback:
                progress_callback(0.4, "音声データを読み込み中...")
            
            # 最初の60秒分だけ読み込んでメモリ使用量を推定
            try:
                import subprocess
                self.temp_dir = tempfile.mkdtemp(prefix="textffcut_align_diag_")
                temp_audio_path = os.path.join(self.temp_dir, "diagnostic_audio.wav")
                
                # 最初の60秒を抽出
                cmd = [
                    "ffmpeg", "-y", "-i", audio_path,
                    "-t", "60",  # 60秒
                    "-ar", "16000", "-ac", "1",
                    "-f", "wav", temp_audio_path
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                
                # 部分音声を読み込み
                test_audio = self._load_audio(temp_audio_path)
                gc.collect()
                
                audio_loaded_memory = memory_monitor.get_memory_usage()
                audio_memory_60s = audio_loaded_memory - model_loaded_memory
                
                # 全体の音声時間を取得して比率計算
                duration_result = subprocess.run(
                    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                     "-of", "csv=p=0", audio_path],
                    capture_output=True, text=True
                )
                total_duration = float(duration_result.stdout.strip()) if duration_result.stdout else 3600
                
                # 全音声データのメモリ使用量を推定
                diagnostic_result['audio_memory'] = (audio_memory_60s * total_duration) / 60
                logger.info(f"音声メモリ推定: {diagnostic_result['audio_memory']:.1f}% (60秒分: {audio_memory_60s:.1f}%)")
                
                # テスト用音声を削除してメモリ解放
                del test_audio
                if os.path.exists(temp_audio_path):
                    os.unlink(temp_audio_path)
                gc.collect()
                
            except Exception as e:
                logger.warning(f"音声メモリ推定エラー: {e}")
                # エラー時は保守的な推定値を使用
                diagnostic_result['audio_memory'] = 10.0  # 10%と仮定
            
            # Step 3: バッチ処理のテスト
            if progress_callback:
                progress_callback(0.6, "バッチ処理をテスト中...")
            
            # サンプルセグメントがない場合はダミーを生成
            if not sample_segments:
                sample_segments = self._generate_dummy_segments(10)  # 10個のダミーセグメント
            
            # 小規模バッチでテスト（1, 2, 4セグメント）
            test_batch_sizes = [1, 2, 4]
            memory_increases = []
            
            # 全音声データを読み込み（実際の診断のため）
            full_audio = self._load_audio(audio_path)
            base_memory = memory_monitor.get_memory_usage()
            
            for test_size in test_batch_sizes:
                if test_size > len(sample_segments):
                    continue
                    
                try:
                    # バッチ処理を実行
                    test_batch = sample_segments[:test_size]
                    start_memory = memory_monitor.get_memory_usage()
                    
                    # 実際にアライメント処理を実行（エラーは無視）
                    try:
                        self._process_batch(test_batch, full_audio, language)
                    except Exception:
                        pass  # アライメントエラーは無視（メモリ測定が目的）
                    
                    end_memory = memory_monitor.get_memory_usage()
                    memory_increase = end_memory - start_memory
                    memory_increases.append(memory_increase / test_size)  # 1セグメントあたり
                    
                    logger.info(f"バッチサイズ {test_size}: メモリ増加 {memory_increase:.1f}% ({memory_increase/test_size:.1f}%/セグメント)")
                    
                    # メモリが高すぎる場合は中断
                    if end_memory > 85:
                        logger.warning("メモリ使用率が高いため診断を中断")
                        break
                        
                except Exception as e:
                    logger.warning(f"バッチテストエラー (size={test_size}): {e}")
            
            # メモリ増加率から最適バッチサイズを計算
            if memory_increases:
                avg_memory_per_segment = sum(memory_increases) / len(memory_increases)
                diagnostic_result['batch_memory_per_segment'] = avg_memory_per_segment
                
                # 現在のメモリ使用量
                current_total_memory = base_memory
                
                # 利用可能なメモリ（目標75%まで）
                available_memory = 75.0 - current_total_memory
                
                # 最大安全バッチサイズを計算
                if avg_memory_per_segment > 0:
                    max_safe_batch = int(available_memory / avg_memory_per_segment)
                    max_safe_batch = max(1, min(max_safe_batch, 16))  # 1-16の範囲
                else:
                    max_safe_batch = 8
                
                # 最適バッチサイズ（安全マージンを考慮）
                optimal_batch = max(1, max_safe_batch // 2)  # 50%マージン
                
                diagnostic_result['max_safe_batch_size'] = max_safe_batch
                diagnostic_result['optimal_batch_size'] = optimal_batch
                
                logger.info(f"診断結果: 1セグメントあたり{avg_memory_per_segment:.1f}%のメモリ使用")
                logger.info(f"推奨バッチサイズ: {optimal_batch} (最大安全: {max_safe_batch})")
            
            # クリーンアップ
            del full_audio
            gc.collect()
            
            diagnostic_result['diagnostic_completed'] = True
            
            if progress_callback:
                progress_callback(1.0, "診断完了")
                
        except Exception as e:
            logger.error(f"診断エラー: {e}")
            # エラー時は保守的なデフォルト値を使用
            diagnostic_result['optimal_batch_size'] = 4
            diagnostic_result['diagnostic_completed'] = False
        
        finally:
            # 音声データのクリーンアップ
            if 'full_audio' in locals():
                del full_audio
            if 'test_audio' in locals():
                del test_audio
            gc.collect()
            
            # 一時ディレクトリのクリーンアップ
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
                self.temp_dir = None
        
        return diagnostic_result
    
    def _generate_dummy_segments(self, count: int) -> List[TranscriptionSegmentV2]:
        """診断用のダミーセグメントを生成"""
        segments = []
        for i in range(count):
            segment = TranscriptionSegmentV2(
                id=f"dummy_{i}",
                text=f"これはテスト用のダミーテキストです。セグメント番号{i}。" * 5,  # 適度な長さ
                start=i * 10.0,
                end=(i + 1) * 10.0
            )
            segments.append(segment)
        return segments
    
    def align(
        self,
        segments: List[TranscriptionSegmentV2],
        audio_path: str,
        language: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> List[TranscriptionSegmentV2]:
        """
        文字起こしセグメントに対してアライメントを実行
        
        Args:
            segments: アライメント前のセグメント
            audio_path: 音声ファイルのパス
            language: 言語コード
            progress_callback: 進捗報告用コールバック
            
        Returns:
            アライメント済みセグメントのリスト
        """
        if not segments:
            return []
        
        logger.info(f"アライメント開始: {len(segments)}セグメント, 言語={language}")
        
        # 一時ディレクトリの作成
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_align_")
        
        try:
            # アライメントモデルの読み込み
            self._load_align_model(language)
            
            # 音声データの読み込み
            audio_data = self._load_audio(audio_path)
            
            # バッチ処理の準備
            batch_size = self.batch_size  # インスタンス変数を使用
            total_batches = (len(segments) + batch_size - 1) // batch_size
            
            aligned_segments = []
            
            for batch_idx in range(total_batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, len(segments))
                batch_segments = segments[start_idx:end_idx]
                
                # 進捗報告
                if progress_callback:
                    progress = (batch_idx / total_batches) * 0.9
                    progress_callback(
                        progress,
                        f"バッチ {batch_idx + 1}/{total_batches} を処理中"
                    )
                
                # バッチ処理
                batch_aligned = self._process_batch(
                    batch_segments,
                    audio_data,
                    language
                )
                
                aligned_segments.extend(batch_aligned)
            
            # 後処理
            aligned_segments = self._post_process_alignment(aligned_segments)
            
            # 検証
            success_count = sum(1 for s in aligned_segments if s.has_valid_alignment())
            logger.info(
                f"アライメント完了: 成功={success_count}/{len(aligned_segments)}"
            )
            
            if progress_callback:
                progress_callback(1.0, "アライメント完了")
            
            return aligned_segments
            
        except Exception as e:
            logger.error(f"アライメントエラー: {str(e)}")
            # エラー時は推定処理でフォールバック
            return self._fallback_alignment(segments, audio_path)
            
        finally:
            # クリーンアップ
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                try:
                    shutil.rmtree(self.temp_dir)
                except:
                    pass
    
    def align_single_segment(
        self,
        segment: TranscriptionSegmentV2,
        audio_data: Any,
        language: str
    ) -> TranscriptionSegmentV2:
        """単一セグメントのアライメントを実行"""
        try:
            # WhisperXのアライメントを実行
            import whisperx
            
            # セグメントデータの準備
            segment_data = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text
            }
            
            # アライメント実行
            aligned_result = whisperx.align(
                [segment_data],
                self.align_model,
                self.metadata,
                audio_data,
                self.device,
                return_char_alignments=True  # 日本語の場合は文字レベルも取得
            )
            
            # 結果の処理
            if aligned_result and "segments" in aligned_result and aligned_result["segments"]:
                aligned_seg = aligned_result["segments"][0]
                
                # Word情報の抽出（辞書形式で保持）
                words = []
                if "words" in aligned_seg and aligned_seg["words"]:
                    for word_data in aligned_seg["words"]:
                        # WordInfoオブジェクトではなく辞書として保持
                        word = {
                            "word": word_data.get("word", ""),
                            "start": word_data.get("start"),
                            "end": word_data.get("end"),
                            "confidence": word_data.get("score")
                        }
                        words.append(word)
                
                # 文字情報の抽出（日本語の場合）
                chars = []
                if language == "ja" and "chars" in aligned_seg and aligned_seg["chars"]:
                    for char_data in aligned_seg["chars"]:
                        # CharInfoオブジェクトではなく辞書として保持
                        char = {
                            "char": char_data.get("char", ""),
                            "start": char_data.get("start"),
                            "end": char_data.get("end"),
                            "confidence": char_data.get("score")
                        }
                        chars.append(char)
                
                # セグメントの更新（辞書形式）
                segment.words = words
                segment.chars = chars
                segment.alignment_completed = True
                segment.confidence = aligned_seg.get("score")
                
            else:
                # アライメント失敗
                raise AlignmentError("アライメント結果が空です")
            
        except Exception as e:
            logger.warning(f"セグメントアライメントエラー: {str(e)}")
            segment.alignment_error = str(e)
            # 推定処理でフォールバック
            segment = self._estimate_segment_timestamps(segment)
        
        return segment
    
    def estimate_timestamps(
        self,
        text: str,
        start_time: float,
        end_time: float
    ) -> List[Dict[str, Any]]:
        """タイムスタンプが取得できない場合の推定処理"""
        words = text.split()
        if not words:
            return []
        
        # 各単語に均等に時間を割り当て
        duration = end_time - start_time
        word_duration = duration / len(words)
        
        estimated_words = []
        current_time = start_time
        
        for word in words:
            word_info = {
                "word": word,
                "start": current_time,
                "end": current_time + word_duration
            }
            estimated_words.append(word_info)
            current_time += word_duration
        
        return estimated_words
    
    def _check_cuda_available(self) -> bool:
        """CUDAが利用可能かチェック"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
    
    def _load_align_model(self, language: str):
        """アライメントモデルを読み込み"""
        try:
            import whisperx
            
            logger.info(f"アライメントモデルを読み込み中: 言語={language}")
            
            self.align_model, self.metadata = whisperx.load_align_model(
                language_code=language,
                device=self.device
            )
            
            logger.info("アライメントモデルの読み込み完了")
            
        except Exception as e:
            logger.error(f"アライメントモデルの読み込みエラー: {str(e)}")
            raise AlignmentError(f"アライメントモデルの読み込みに失敗: {str(e)}")
    
    def _load_audio(self, audio_path: str) -> Any:
        """音声データを読み込み"""
        try:
            import whisperx
            
            # WhisperX形式で音声を読み込み
            audio = whisperx.load_audio(audio_path)
            return audio
            
        except Exception as e:
            logger.error(f"音声読み込みエラー: {str(e)}")
            # FFmpegで変換を試みる
            return self._load_audio_with_ffmpeg(audio_path)
    
    def _load_audio_with_ffmpeg(self, audio_path: str) -> Any:
        """FFmpegを使用して音声を読み込み"""
        temp_wav = os.path.join(self.temp_dir, "temp_audio.wav")
        
        cmd = [
            "ffmpeg", "-y",
            "-i", audio_path,
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            temp_wav
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AlignmentError(f"音声変換エラー: {result.stderr}")
        
        import whisperx
        return whisperx.load_audio(temp_wav)
    
    def _process_batch(
        self,
        segments: List[TranscriptionSegmentV2],
        audio_data: Any,
        language: str
    ) -> List[TranscriptionSegmentV2]:
        """バッチ単位でアライメント処理"""
        aligned_segments = []
        
        for segment in segments:
            aligned_segment = self.align_single_segment(
                segment,
                audio_data,
                language
            )
            aligned_segments.append(aligned_segment)
        
        return aligned_segments
    
    def _post_process_alignment(
        self,
        segments: List[TranscriptionSegmentV2]
    ) -> List[TranscriptionSegmentV2]:
        """アライメント結果の後処理"""
        for i, segment in enumerate(segments):
            if not segment.alignment_completed:
                continue
            
            # タイムスタンプの連続性チェック
            if segment.words:
                self._fix_word_continuity(segment.words)
            
            # セグメント境界の調整
            if i > 0 and segments[i-1].alignment_completed:
                self._adjust_segment_boundary(segments[i-1], segment)
        
        return segments
    
    def _fix_word_continuity(self, words: List[Any]):
        """単語タイムスタンプの連続性を修正"""
        for i in range(1, len(words)):
            # 辞書形式に対応
            prev_word = words[i-1]
            curr_word = words[i]
            
            if isinstance(prev_word, dict) and isinstance(curr_word, dict):
                prev_end = prev_word.get('end')
                curr_start = curr_word.get('start')
                
                if prev_end and curr_start:
                    # 前の単語の終了時刻が次の単語の開始時刻より後の場合
                    if prev_end > curr_start:
                        # 中間点で分割
                        mid_point = (prev_end + curr_start) / 2
                        prev_word['end'] = mid_point
                        curr_word['start'] = mid_point
            else:
                # WordInfoオブジェクトの場合（レガシー対応）
                if hasattr(prev_word, 'end') and hasattr(curr_word, 'start'):
                    if prev_word.end and curr_word.start:
                        if prev_word.end > curr_word.start:
                            mid_point = (prev_word.end + curr_word.start) / 2
                            prev_word.end = mid_point
                            curr_word.start = mid_point
    
    def _adjust_segment_boundary(
        self,
        prev_segment: TranscriptionSegmentV2,
        curr_segment: TranscriptionSegmentV2
    ):
        """セグメント境界を調整"""
        # 前のセグメントの最後の単語
        prev_end = prev_segment.end
        if prev_segment.words and len(prev_segment.words) > 0:
            last_word = prev_segment.words[-1]
            if isinstance(last_word, dict):
                if last_word.get('end'):
                    prev_end = last_word.get('end')
            elif hasattr(last_word, 'end') and last_word.end:
                prev_end = last_word.end
        
        # 現在のセグメントの最初の単語
        curr_start = curr_segment.start
        if curr_segment.words and len(curr_segment.words) > 0:
            first_word = curr_segment.words[0]
            if isinstance(first_word, dict):
                if first_word.get('start'):
                    curr_start = first_word.get('start')
            elif hasattr(first_word, 'start') and first_word.start:
                curr_start = first_word.start
        
        # オーバーラップがある場合は調整
        if prev_end > curr_start:
            mid_point = (prev_end + curr_start) / 2
            
            # 前のセグメントの調整
            if prev_segment.words and len(prev_segment.words) > 0:
                last_word = prev_segment.words[-1]
                if isinstance(last_word, dict):
                    last_word['end'] = mid_point
                elif hasattr(last_word, 'end'):
                    last_word.end = mid_point
            prev_segment.end = mid_point
            
            # 現在のセグメントの調整
            if curr_segment.words and len(curr_segment.words) > 0:
                first_word = curr_segment.words[0]
                if isinstance(first_word, dict):
                    first_word['start'] = mid_point
                elif hasattr(first_word, 'start'):
                    first_word.start = mid_point
            curr_segment.start = mid_point
    
    def _estimate_segment_timestamps(
        self,
        segment: TranscriptionSegmentV2
    ) -> TranscriptionSegmentV2:
        """セグメントのタイムスタンプを推定"""
        logger.info(f"セグメント {segment.id} のタイムスタンプを推定")
        
        # 単語に分割（簡易的な実装）
        words = segment.text.split()
        if not words:
            return segment
        
        # 均等に時間を割り当て
        duration = segment.end - segment.start
        word_duration = duration / len(words)
        
        estimated_words = []
        current_time = segment.start
        
        for word in words:
            # 辞書形式で作成
            word_info = {
                "word": word,
                "start": current_time,
                "end": current_time + word_duration,
                "confidence": 0.5  # 推定値なので低い信頼度
            }
            estimated_words.append(word_info)
            current_time += word_duration
        
        segment.words = estimated_words
        segment.alignment_completed = True
        segment.alignment_error = "推定値を使用"
        
        return segment
    
    def _fallback_alignment(
        self,
        segments: List[TranscriptionSegmentV2],
        audio_path: str
    ) -> List[TranscriptionSegmentV2]:
        """エラー時のフォールバック処理"""
        logger.warning("アライメントエラーのため、推定処理を実行")
        
        for segment in segments:
            segment = self._estimate_segment_timestamps(segment)
        
        return segments