"""
API版文字起こしモジュール
"""
import os
import json
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from dataclasses import dataclass
import openai

from .transcription import TranscriptionResult, TranscriptionSegment
from config import Config
from utils.logging import get_logger
from utils.performance_tracker import PerformanceTracker

logger = get_logger(__name__)


class APITranscriber:
    """API版文字起こしクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.api_config = config.transcription
    
    def transcribe(self, audio_path: str, model_size: str = None, 
                  progress_callback: Optional[callable] = None,
                  optimization_mode: str = "auto") -> TranscriptionResult:
        """
        APIを使用して音声ファイルを文字起こし
        
        Args:
            audio_path: 音声ファイルパス
            model_size: モデルサイズ（API版では一部のみ有効）
            progress_callback: 進捗コールバック
            optimization_mode: 最適化モード ("auto", "normal", "optimized", "ultra")
            
        Returns:
            TranscriptionResult: 文字起こし結果
        """
        if progress_callback:
            progress_callback(0.1, "APIに接続中...")
        
        # OpenAI API専用
        if self.api_config.api_provider == "openai":
            result = self._transcribe_openai(audio_path, progress_callback, optimization_mode)
        else:
            raise ValueError(f"Unsupported API provider: {self.api_config.api_provider}. Only 'openai' is supported.")
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        return result
    
    def _transcribe_openai(self, audio_path: str, 
                          progress_callback: Optional[callable] = None,
                          optimization_mode: str = "auto") -> TranscriptionResult:
        """OpenAI Whisper APIを使用（ローカル版と同じチャンク並列処理）"""
        # パフォーマンストラッキング開始
        from core.video import VideoInfo
        video_info = VideoInfo.from_file(audio_path)
        perf_tracker = PerformanceTracker(audio_path)
        
        # トラッキング開始（実際に使用されるモードは後で決定）
        start_time = time.time()
        
        try:
            from openai import OpenAI
            import tempfile
            import numpy as np
            import soundfile as sf
            
            if not self.api_config.api_key:
                raise ValueError("OpenAI API key is required")
            
            # デバッグ: 環境変数を確認
            import os
            import sys
            logger.info("=== OpenAI Client Debug Info ===")
            logger.info(f"Python version: {sys.version}")
            logger.info(f"OpenAI module: {openai}")
            logger.info(f"OpenAI version: {openai.__version__}")
            logger.info(f"OpenAI file: {openai.__file__}")
            
            # 環境変数を確認
            for key in os.environ:
                if 'PROXY' in key.upper() or 'proxy' in key:
                    logger.info(f"{key}: {os.environ[key]}")
            
            # OpenAI クライアントを初期化
            try:
                # OpenAIクラスの属性を確認
                logger.info(f"OpenAI class: {OpenAI}")
                logger.info(f"OpenAI.__init__ signature: {OpenAI.__init__.__code__.co_varnames}")
                
                client = OpenAI(api_key=self.api_config.api_key)
                logger.info("OpenAI client initialized successfully")
            except TypeError as e:
                logger.error(f"TypeError during OpenAI init: {str(e)}")
                logger.error(f"Available OpenAI init params: {OpenAI.__init__.__code__.co_varnames}")
                raise
            except Exception as e:
                logger.error(f"OpenAI client initialization error: {type(e).__name__}: {str(e)}")
                import traceback
                logger.error(f"Traceback: {traceback.format_exc()}")
                raise
            
            # 元ファイルサイズをチェック
            original_size = os.path.getsize(audio_path) / (1024 * 1024)
            
            if progress_callback:
                progress_callback(0.05, f"音声を読み込み中（元サイズ: {original_size:.1f}MB）...")
            
            # WhisperXと同じ方法で音声を読み込み
            try:
                import whisperx
                audio = whisperx.load_audio(audio_path)
                
                if progress_callback:
                    progress_callback(0.1, "音声データを最適化完了、チャンク分割中...")
                
                # ローカル版と同じチャンク分割処理
                result = self._transcribe_with_chunks(client, audio, audio_path, progress_callback, optimization_mode, perf_tracker, video_info.duration)
                return result
                        
            except ImportError:
                # WhisperXが利用できない場合はFFmpegで変換
                logger.warning("WhisperXが利用できないため、FFmpegで音声変換します")
                result = self._transcribe_with_ffmpeg(client, audio_path, progress_callback)
                # FFmpegの場合もトラッキング
                metrics = perf_tracker.start_tracking("normal", "whisper-1", True, video_info.duration)
                perf_tracker.end_tracking(len(result.segments) if result else 0)
                return result
            
        except ImportError as e:
            from utils.exceptions import TranscriptionError
            raise TranscriptionError("必要なライブラリが見つかりません。インストールを確認してください。")
        except openai.RateLimitError as e:
            from utils.exceptions import TranscriptionError
            raise TranscriptionError("API利用制限に達しました。しばらく待ってから再試行してください。")
        except openai.AuthenticationError as e:
            from utils.exceptions import TranscriptionError
            raise TranscriptionError("APIキーが無効です。設定を確認してください。")
        except openai.APIConnectionError as e:
            from utils.exceptions import TranscriptionError
            raise TranscriptionError("API接続エラーです。ネットワーク接続を確認してください。")
        except openai.BadRequestError as e:
            from utils.exceptions import TranscriptionError
            error_message = str(e)
            if "Audio file is too short" in error_message:
                raise TranscriptionError("動画ファイルが短すぎます。")
            elif "larger than the maximum" in error_message:
                raise TranscriptionError("ファイルサイズが上限（25MB）を超えています。動画を圧縮するか、ローカルモードを使用してください。")
            else:
                raise TranscriptionError(f"APIリクエストエラー: {error_message}")
        except Exception as e:
            from utils.exceptions import TranscriptionError
            raise TranscriptionError(f"文字起こしエラー: {str(e)}")
    
    def _transcribe_with_chunks(self, client, audio, original_audio_path: str,
                               progress_callback: Optional[callable] = None,
                               optimization_mode: str = "auto",
                               perf_tracker: Optional[PerformanceTracker] = None,
                               video_duration: float = 0.0) -> TranscriptionResult:
        """Producer-Consumerパターンによる最適化されたチャンク並列処理"""
        import tempfile
        import soundfile as sf
        import numpy as np
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        start_time = time.time()
        # 最適化モードの選択
        from utils.system_resources import system_resource_manager
        system_spec = system_resource_manager.get_system_spec()
        
        # 手動選択モードか自動選択かを判定
        if optimization_mode == "auto":
            # 自動選択：システムスペックに基づいて最適化レベルを選択
            if system_spec.spec_level == 'low' or system_spec.available_memory_gb < 3:
                selected_mode = "ultra_optimized"
            elif system_spec.spec_level == 'high' and system_spec.available_memory_gb > 8:
                selected_mode = "normal"
            else:
                selected_mode = "optimized"
            logger.info(f"自動選択モード: {selected_mode} (利用可能メモリ: {system_spec.available_memory_gb:.1f}GB)")
        else:
            # 手動選択モード
            selected_mode = optimization_mode
            logger.info(f"手動選択モード: {selected_mode}")
        
        # 選択されたモードに応じて処理を分岐
        if selected_mode == "ultra_optimized":
            from .transcription_api_ultra_optimized import UltraOptimizedAPITranscriber
            logger.info("超最適化モード（ディスクキャッシュ）を使用")
            ultra_transcriber = UltraOptimizedAPITranscriber(self.config)
            
            # トラッキング開始
            if perf_tracker:
                metrics = perf_tracker.start_tracking(selected_mode, "whisper-1", True, video_duration)
            
            result = ultra_transcriber.transcribe_ultra_optimized(client, audio, original_audio_path, progress_callback)
            
            # トラッキング終了
            if perf_tracker:
                perf_tracker.end_tracking(len(result.segments) if result else 0)
            
            return result
        elif selected_mode == "normal":
            # 通常モード：このメソッドの残りの部分で処理
            logger.info("通常モード（高速処理）を使用")
            
            # トラッキング開始
            if perf_tracker:
                metrics = perf_tracker.start_tracking(selected_mode, "whisper-1", True, video_duration)
        else:  # optimized
            from .transcription_api_optimized import OptimizedAPITranscriber
            logger.info("最適化モードを使用")
            optimized_transcriber = OptimizedAPITranscriber(self.config)
            
            # トラッキング開始
            if perf_tracker:
                metrics = perf_tracker.start_tracking(selected_mode, "whisper-1", True, video_duration)
            
            result = optimized_transcriber._transcribe_with_chunks_optimized(client, audio, original_audio_path, progress_callback)
            
            # トラッキング終了
            if perf_tracker:
                perf_tracker.end_tracking(len(result.segments) if result else 0)
            
            return result
        
        # チャンク処理のパラメータを設定
        chunk_seconds = self.config.transcription.chunk_seconds
        sample_rate = self.config.transcription.sample_rate
        step = chunk_seconds * sample_rate
        
        # チャンクを作成
        chunks = []
        MIN_CHUNK_DURATION = 1.0  # 1秒未満のチャンクは結合（安全性とコスト効率のため）
        
        # 短いチャンクを一時保存する変数
        pending_chunk = None
        
        for i in range(0, len(audio), step):
            chunk_audio = audio[i:i+step]
            start_time = i / sample_rate
            duration = len(chunk_audio) / sample_rate
            
            # pending_chunkがある場合は先に結合を試みる
            if pending_chunk is not None:
                # 前の短いチャンクと現在のチャンクを結合
                combined_audio = np.concatenate([pending_chunk["array"], chunk_audio])
                combined_chunk = {
                    "array": combined_audio,
                    "start": pending_chunk["start"],
                    "duration": len(combined_audio) / sample_rate
                }
                chunks.append(combined_chunk)
                logger.info(f"短いチャンクを次のチャンクと結合しました (新しい長さ: {combined_chunk['duration']:.1f}秒)")
                pending_chunk = None
                continue
            
            # 1秒未満のチャンクは処理しない
            if duration < MIN_CHUNK_DURATION:
                logger.warning(f"チャンクが短すぎます ({duration:.3f}秒) - 結合処理を行います")
                # 前のチャンクがある場合は結合
                if chunks:
                    last_chunk = chunks[-1]
                    # 前のチャンクに結合
                    combined_audio = np.concatenate([last_chunk["array"], chunk_audio])
                    chunks[-1] = {
                        "array": combined_audio,
                        "start": last_chunk["start"],
                        "duration": len(combined_audio) / sample_rate
                    }
                    logger.info(f"短いチャンクを前のチャンクに結合しました (新しい長さ: {chunks[-1]['duration']:.1f}秒)")
                else:
                    # 最初のチャンクが短すぎる場合は一時保存して次と結合
                    pending_chunk = {
                        "array": chunk_audio,
                        "start": start_time,
                        "duration": duration
                    }
                    logger.warning(f"最初のチャンクが短いため、次のチャンクと結合します ({duration:.3f}秒)")
                continue
            
            chunks.append({
                "array": chunk_audio,
                "start": start_time,
                "duration": duration
            })
        
        # 最後にpending_chunkが残っている場合（音声全体が短い場合）
        if pending_chunk is not None:
            chunks.append(pending_chunk)
            logger.warning(f"最後の短いチャンクをそのまま追加します ({pending_chunk['duration']:.3f}秒)")
        
        total_chunks = len(chunks)
        logger.info(f"音声をチャンク分割: {total_chunks}個のチャンク（{chunk_seconds}秒ずつ）")
        
        if progress_callback:
            progress_callback(0.15, f"チャンク分割完了: {total_chunks}個のチャンク")
        
        # 一時ディレクトリを作成
        temp_dir = tempfile.mkdtemp(prefix="textffcut_api_chunks_")
        
        try:
            # 各チャンクをWAVファイルとして保存
            chunk_files = []
            for i, chunk in enumerate(chunks):
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.wav")
                sf.write(chunk_file, chunk["array"], sample_rate)
                
                # ファイルサイズチェック（25MB制限）
                chunk_size = os.path.getsize(chunk_file) / (1024 * 1024)
                if chunk_size > 25:
                    logger.warning(f"チャンク {i} がサイズ制限を超過: {chunk_size:.1f}MB")
                    continue
                
                chunk_files.append((chunk_file, chunk["start"], i))
            
            if not chunk_files:
                raise ValueError("有効なチャンクが作成できませんでした")
            
            if progress_callback:
                progress_callback(0.2, f"チャンクファイル作成完了: {len(chunk_files)}個")
            
            # 並列でAPI処理（レート制限考慮で3並列）
            max_workers = min(3, len(chunk_files))
            all_segments = []
            completed_chunks = 0
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # アライメントモデルを事前に読み込み（全チャンクで共有）
                align_model = None
                align_meta = None
                try:
                    import whisperx
                    align_model, align_meta = whisperx.load_align_model(
                        language_code=self.api_config.language,
                        device="cpu"
                    )
                    logger.info("アライメントモデルを読み込みました")
                except Exception as e:
                    logger.warning(f"アライメントモデルの読み込みに失敗: {e}")
                
                # 各チャンクのAPI処理を送信
                futures = []
                for chunk_file, start_offset, chunk_idx in chunk_files:
                    future = executor.submit(
                        self._transcribe_chunk_api, 
                        client, 
                        chunk_file, 
                        start_offset, 
                        chunk_idx,
                        align_model,
                        align_meta
                    )
                    futures.append(future)
                
                # 完了したものから結果を取得
                for future in as_completed(futures):
                    try:
                        segments = future.result()
                        all_segments.extend(segments)
                        completed_chunks += 1
                        
                        if progress_callback:
                            progress = 0.2 + (0.7 * completed_chunks / len(chunk_files))
                            progress_callback(progress, f"チャンク {completed_chunks}/{len(chunk_files)} 完了")
                    
                    except openai.RateLimitError as e:
                        logger.warning(f"レート制限でチャンク失敗、リトライ: {e}")
                        completed_chunks += 1
                        continue
                    except openai.APIError as e:
                        logger.warning(f"API エラーでチャンク失敗: {e}")
                        completed_chunks += 1
                        continue
                    except Exception as e:
                        logger.warning(f"チャンク処理失敗: {e}")
                        completed_chunks += 1
                        continue
            
            if progress_callback:
                progress_callback(0.9, "結果を統合中...")
            
            # すべてのセグメントがTranscriptionSegmentオブジェクトであることを確認
            validated_segments = []
            for seg in all_segments:
                if isinstance(seg, TranscriptionSegment):
                    validated_segments.append(seg)
                elif isinstance(seg, dict):
                    # dictの場合はTranscriptionSegmentに変換
                    validated_segments.append(TranscriptionSegment(
                        start=seg.get('start', 0),
                        end=seg.get('end', 0),
                        text=seg.get('text', ''),
                        words=seg.get('words'),
                        chars=seg.get('chars')
                    ))
            
            # セグメントをソート
            validated_segments.sort(key=lambda x: x.start)
            
            # アライメント処理はチャンクごとに実行済み
            if progress_callback:
                progress_callback(0.95, "結果を統合中...")
            
            aligned_segments = validated_segments  # 既にアライメント済み
            
            if progress_callback:
                progress_callback(1.0, "チャンク並列処理完了")
            
            # 処理時間を計算
            processing_time = time.time() - start_time
            
            # トラッキング終了（通常モードの場合）
            if perf_tracker and selected_mode == "normal":
                perf_tracker.end_tracking(
                    segments_processed=len(aligned_segments),
                    api_chunks=len(chunks),
                    alignment_chunks=len(aligned_segments)
                )
            
            return TranscriptionResult(
                language=self.api_config.language,
                segments=aligned_segments,
                original_audio_path=original_audio_path,
                model_size="whisper-1_api",
                processing_time=processing_time
            )
        
        finally:
            # 一時ファイルをクリーンアップ
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def _transcribe_chunk_api(self, client, chunk_file: str, start_offset: float, chunk_idx: int,
                             align_model=None, align_meta=None) -> List[TranscriptionSegment]:
        """単一チャンクのAPI処理"""
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
                    # seg がdictの場合とオブジェクトの場合の両方に対応
                    if isinstance(seg, dict):
                        segment = TranscriptionSegment(
                            start=seg['start'] + start_offset,
                            end=seg['end'] + start_offset,
                            text=seg['text'],
                            words=None  # アライメント処理なしの場合は None に設定
                        )
                    else:
                        segment = TranscriptionSegment(
                            start=seg.start + start_offset,
                            end=seg.end + start_offset,
                            text=seg.text,
                            words=None  # アライメント処理なしの場合は None に設定
                        )
                    segments.append(segment)
            elif response.text.strip():
                # セグメント情報がない場合
                estimated_duration = len(response.text) / 20
                segment = TranscriptionSegment(
                    start=start_offset,
                    end=start_offset + estimated_duration,
                    text=response.text,
                    words=None  # アライメント処理なしの場合は None に設定
                )
                segments.append(segment)
            
            # アライメント処理
            if align_model and align_meta and len(segments) > 0:
                try:
                    # チャンクファイルから音声データを読み込み
                    import whisperx
                    chunk_audio = whisperx.load_audio(chunk_file)
                    
                    # API結果をWhisperX形式に変換
                    whisperx_segments = []
                    for seg in segments:
                        whisperx_segments.append({
                            "start": seg.start - start_offset,  # チャンク内の相対時間に戻す
                            "end": seg.end - start_offset,
                            "text": seg.text
                        })
                    
                    # チャンクごとのアライメント
                    aligned_result = whisperx.align(
                        whisperx_segments,
                        align_model,
                        align_meta,
                        chunk_audio,
                        "cpu",
                        return_char_alignments=True
                    )
                    
                    # 結果を元の形式に戻す
                    aligned_segments = []
                    for seg in aligned_result["segments"]:
                        aligned_seg = TranscriptionSegment(
                            start=seg["start"] + start_offset,  # 絶対時間に戻す
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
                    
                    logger.info(f"チャンク {chunk_idx} アライメント完了: {len(aligned_segments)}セグメント")
                    return aligned_segments
                    
                except Exception as e:
                    logger.warning(f"チャンク {chunk_idx} のアライメント処理に失敗: {e}")
            
            logger.info(f"チャンク {chunk_idx} 処理完了: {len(segments)}セグメント")
            return segments
        
        except openai.RateLimitError as e:
            logger.error(f"チャンク {chunk_idx}: レート制限エラー - {e}")
            return []
        except openai.AuthenticationError as e:
            logger.error(f"チャンク {chunk_idx}: 認証エラー - {e}")
            return []
        except openai.APIError as e:
            logger.error(f"チャンク {chunk_idx}: API エラー - {e}")
            return []
        except Exception as e:
            logger.error(f"チャンク {chunk_idx}: 予期しないエラー - {e}")
            return []
    
    def _perform_alignment(self, audio, segments: List[TranscriptionSegment], 
                          progress_callback: Optional[callable] = None):
        """ローカル版と同じアライメント処理"""
        try:
            import whisperx
            
            # WhisperXのアライメントモデルを読み込み
            align_model, metadata = whisperx.load_align_model(
                language_code=self.api_config.language, 
                device="cpu"  # API版では基本的にCPU
            )
            
            # API結果をWhisperX形式に変換
            whisperx_segments = []
            for seg in segments:
                whisperx_segments.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text
                })
            
            # アライメント実行（ローカル版と同じ処理）
            aligned_result = whisperx.align(
                whisperx_segments,
                align_model,
                metadata,
                audio,
                "cpu",
                return_char_alignments=True
            )
            
            # 結果をTranscriptionSegment形式に戻す
            aligned_segments = []
            for seg in aligned_result["segments"]:
                segment = TranscriptionSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"],
                    words=seg.get("words", []),
                    chars=seg.get("chars", [])
                )
                aligned_segments.append(segment)
            
            logger.info(f"アライメント処理完了: {len(aligned_segments)}セグメント")
            return aligned_segments
            
        except ImportError:
            logger.warning("WhisperXが利用できないため、アライメント処理をスキップします")
            return segments
        except RuntimeError as e:
            if "CUDA" in str(e) or "memory" in str(e):
                logger.warning(f"メモリ不足でアライメント失敗: {e}")
            else:
                logger.warning(f"ランタイムエラーでアライメント失敗: {e}")
            return segments
        except Exception as e:
            logger.warning(f"アライメント処理に失敗: {e}")
            return segments
    
    def _transcribe_with_ffmpeg(self, client, audio_path: str,
                               progress_callback: Optional[callable] = None) -> TranscriptionResult:
        """FFmpegを使用した音声変換（WhisperX非対応環境用）"""
        import tempfile
        import subprocess
        
        if progress_callback:
            progress_callback(0.1, "FFmpegで音声を変換中...")
        
        # 一時WAVファイルを作成
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
        
        try:
            # FFmpegでWAVに変換
            cmd = [
                'ffmpeg', '-i', audio_path,
                '-vn', '-ar', '16000', '-ac', '1',
                '-y', temp_wav_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"FFmpeg変換に失敗: {result.stderr}")
            
            wav_size = os.path.getsize(temp_wav_path) / (1024 * 1024)
            
            if progress_callback:
                progress_callback(0.3, f"FFmpeg変換完了: {wav_size:.1f}MB")
            
            # FFmpeg版では従来通りファイル全体を処理
            return self._transcribe_single_file(client, temp_wav_path, progress_callback)
        
        finally:
            try:
                os.unlink(temp_wav_path)
            except:
                pass
    
    def _transcribe_single_file(self, client, audio_path: str, 
                               progress_callback: Optional[callable] = None) -> TranscriptionResult:
        """単一ファイルの文字起こし"""
        if progress_callback:
            progress_callback(0.3, "音声ファイルをアップロード中...")
        
        with open(audio_path, 'rb') as audio_file:
            if progress_callback:
                progress_callback(0.5, "文字起こし処理中...")
            
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=self.api_config.language,
                response_format="verbose_json",
                timestamp_granularities=["segment"]
            )
        
        if progress_callback:
            progress_callback(0.8, "結果を処理中...")
        
        return self._process_openai_response(response, audio_path)
    
    def _transcribe_large_file(self, client, audio_path: str,
                              progress_callback: Optional[callable] = None) -> TranscriptionResult:
        """大きなファイルを分割して文字起こし"""
        import tempfile
        import subprocess
        
        # 一時ディレクトリを作成
        temp_dir = tempfile.mkdtemp(prefix="textffcut_split_")
        
        try:
            if progress_callback:
                progress_callback(0.1, "音声ファイルを分割中...")
            
            # FFmpegで10分ごとに分割（約20MBになるように調整）
            chunk_duration = 600  # 10分
            chunk_files = []
            
            # 音声の長さを取得
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', audio_path
            ], capture_output=True, text=True)
            
            try:
                total_duration = float(result.stdout.strip())
            except:
                # 長さが取得できない場合は仮定値
                total_duration = 3600  # 1時間と仮定
            
            num_chunks = int(total_duration / chunk_duration) + 1
            
            for i in range(num_chunks):
                start_time = i * chunk_duration
                if start_time >= total_duration:
                    break
                
                # 残り時間を計算
                remaining_time = total_duration - start_time
                actual_chunk_duration = min(chunk_duration, remaining_time)
                
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.mp4")
                
                # FFmpegで分割
                cmd = [
                    'ffmpeg', '-i', audio_path,
                    '-ss', str(start_time),
                    '-t', str(actual_chunk_duration),
                    '-c', 'copy',
                    '-y', chunk_file
                ]
                
                subprocess.run(cmd, capture_output=True)
                
                if os.path.exists(chunk_file) and os.path.getsize(chunk_file) > 0:
                    chunk_files.append((chunk_file, start_time))
            
            if not chunk_files:
                raise ValueError("音声ファイルの分割に失敗しました")
            
            # 各チャンクを文字起こし
            all_segments = []
            
            for i, (chunk_file, start_offset) in enumerate(chunk_files):
                if progress_callback:
                    progress = 0.2 + (0.7 * i / len(chunk_files))
                    progress_callback(progress, f"チャンク {i+1}/{len(chunk_files)} を処理中...")
                
                # チャンクのサイズをチェック
                chunk_size = os.path.getsize(chunk_file) / (1024 * 1024)
                if chunk_size > 25:
                    raise ValueError(f"チャンク {i+1} が大きすぎます: {chunk_size:.1f}MB。より短い時間で分割する必要があります。")
                
                try:
                    with open(chunk_file, 'rb') as audio_file:
                        response = client.audio.transcriptions.create(
                            model="whisper-1",
                            file=audio_file,
                            language=self.api_config.language,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"]
                        )
                    
                    # セグメントの時間を調整（開始オフセットを追加）
                    if hasattr(response, 'segments') and response.segments:
                        for seg in response.segments:
                            segment = TranscriptionSegment(
                                start=seg.start + start_offset,
                                end=seg.end + start_offset,
                                text=seg.text,
                                words=None  # アライメント処理なしの場合は None に設定
                            )
                            all_segments.append(segment)
                    elif response.text.strip():
                        # セグメント情報がない場合
                        estimated_duration = len(response.text) / 20
                        segment = TranscriptionSegment(
                            start=start_offset,
                            end=start_offset + estimated_duration,
                            text=response.text,
                            words=None  # アライメント処理なしの場合は None に設定
                        )
                        all_segments.append(segment)
                
                except Exception as e:
                    logger.warning(f"チャンク {i+1} の処理に失敗: {e}")
                    continue
            
            if progress_callback:
                progress_callback(0.9, "結果を統合中...")
            
            # セグメントをソート
            all_segments.sort(key=lambda x: x.start)
            
            return TranscriptionResult(
                language=self.api_config.language,
                segments=all_segments,
                original_audio_path=audio_path,
                model_size="whisper-1_api",
                processing_time=0.0
            )
        
        finally:
            # 一時ファイルをクリーンアップ
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def _process_openai_response(self, response, audio_path: str) -> TranscriptionResult:
        """OpenAI APIレスポンスを処理"""
        segments = []
        if hasattr(response, 'segments') and response.segments:
            for seg in response.segments:
                segment = TranscriptionSegment(
                    start=seg.start,
                    end=seg.end,
                    text=seg.text,
                    words=None  # アライメント処理なしの場合は None に設定
                )
                segments.append(segment)
        else:
            # セグメント情報がない場合は全体を1つのセグメントとして扱う
            text_length = len(response.text)
            estimated_duration = max(text_length / 20, 10.0)
            
            segments = [TranscriptionSegment(
                start=0.0,
                end=estimated_duration,
                text=response.text,
                words=None  # アライメント処理なしの場合は None に設定
            )]
        
        return TranscriptionResult(
            language=self.api_config.language,
            segments=segments,
            original_audio_path=audio_path,
            model_size="whisper-1_api",
            processing_time=0.0
        )
    
    
