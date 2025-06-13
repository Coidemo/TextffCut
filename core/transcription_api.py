"""
API版文字起こしモジュール
"""
import os
import sys
import json
import time
import tempfile
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests
from dataclasses import dataclass
import openai
import numpy as np

from .transcription import TranscriptionResult, TranscriptionSegment
from config import Config
from utils.logging import get_logger
from utils.performance_tracker import PerformanceTracker
from utils.exceptions import TranscriptionError

logger = get_logger(__name__)


class APITranscriber:
    """API版文字起こしクラス"""
    
    # デフォルト値（自動最適化で動的に変更される）
    DEFAULT_API_CHUNK_SECONDS = 600  # 10分
    DEFAULT_API_MAX_WORKERS = 3
    
    def __init__(self, config: Config):
        self.config = config
        self.api_config = config.transcription
        self.skip_alignment = False  # アライメント処理をスキップするフラグ
        
        # 無音検出のパラメータ
        self.SILENCE_THRESH = -40  # dB
        self.MIN_SILENCE_LEN = 0.3  # 秒
    
    def transcribe(self, audio_path: str, model_size: str = None, 
                  progress_callback: Optional[callable] = None) -> TranscriptionResult:
        """
        APIを使用して音声ファイルを文字起こし
        
        Args:
            audio_path: 音声ファイルパス
            model_size: モデルサイズ（API版では一部のみ有効）
            progress_callback: 進捗コールバック
            
        Returns:
            TranscriptionResult: 文字起こし結果
        """
        if progress_callback:
            progress_callback(0.1, "APIに接続中...")
        
        # OpenAI API専用
        if self.api_config.api_provider == "openai":
            result = self._transcribe_openai(audio_path, progress_callback)
        else:
            raise ValueError(f"Unsupported API provider: {self.api_config.api_provider}. Only 'openai' is supported.")
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        logger.info(f"API文字起こし完了 - セグメント数: {len(result.segments) if result and result.segments else 0}")
        if result and result.segments:
            logger.info(f"最初のセグメント: {result.segments[0].text[:50] if result.segments[0].text else '(空)'}")
        else:
            logger.warning("文字起こし結果が空です")
        
        return result
    
    def _transcribe_openai(self, audio_path: str, 
                          progress_callback: Optional[callable] = None) -> TranscriptionResult:
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
                result = self._transcribe_with_chunks(client, audio, audio_path, progress_callback, perf_tracker, video_info.duration)
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
                               perf_tracker: Optional[PerformanceTracker] = None,
                               video_duration: float = 0.0) -> TranscriptionResult:
        """スマート境界検出を使用したチャンク並列処理"""
        import tempfile
        import soundfile as sf
        import numpy as np
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        start_time = time.time()
        logger.info("スマート境界検出を使用したAPI処理")
        
        # トラッキング開始
        if perf_tracker:
            metrics = perf_tracker.start_tracking("normal", "whisper-1", True, video_duration)
        
        # チャンク処理のパラメータを設定
        chunk_seconds = self.DEFAULT_API_CHUNK_SECONDS  # デフォルト値を使用
        sample_rate = self.config.transcription.sample_rate
        
        # 理想的な分割点を計算
        ideal_boundaries = []
        current_pos = 0
        while current_pos < len(audio):
            next_pos = current_pos + chunk_seconds * sample_rate
            if next_pos < len(audio):
                ideal_boundaries.append(next_pos / sample_rate)
            current_pos = next_pos
        
        # 各境界で最適な分割点を探す
        actual_boundaries = [0.0]  # 開始点
        
        for ideal_boundary in ideal_boundaries:
            # 境界前後30秒の範囲で無音を検出
            search_window = 30.0  # 秒
            search_start = max(0, ideal_boundary - search_window)
            search_end = min(len(audio) / sample_rate, ideal_boundary + search_window)
            
            # この範囲の無音を検出
            silences = self._detect_silence_in_range(
                audio, search_start, search_end, sample_rate
            )
            
            if silences:
                # 理想的な境界に最も近い無音の中心を選択
                best_silence = min(silences, 
                    key=lambda s: abs((s['start'] + s['end']) / 2 - ideal_boundary))
                split_point = (best_silence['start'] + best_silence['end']) / 2
                logger.info(f"境界 {ideal_boundary:.1f}s → 無音検出 {split_point:.1f}s")
            else:
                # 無音が見つからない場合は理想的な境界を使用
                split_point = ideal_boundary
                logger.info(f"境界 {ideal_boundary:.1f}s で無音なし、そのまま使用")
            
            actual_boundaries.append(split_point)
        
        # 最後まで含める
        actual_boundaries.append(len(audio) / sample_rate)
        
        # 実際のチャンクを作成
        chunks = []
        MIN_CHUNK_DURATION = 1.0  # 1秒未満のチャンクは結合
        
        for i in range(len(actual_boundaries) - 1):
            start_pos = int(actual_boundaries[i] * sample_rate)
            end_pos = int(actual_boundaries[i + 1] * sample_rate)
            
            chunk_audio = audio[start_pos:end_pos]
            duration = len(chunk_audio) / sample_rate
            
            # 短すぎるチャンクは前のチャンクと結合
            if duration < MIN_CHUNK_DURATION and chunks:
                last_chunk = chunks[-1]
                combined_audio = np.concatenate([last_chunk["array"], chunk_audio])
                chunks[-1] = {
                    "array": combined_audio,
                    "start": last_chunk["start"],
                    "duration": len(combined_audio) / sample_rate
                }
                logger.info(f"短いチャンク({duration:.1f}秒)を前のチャンクと結合")
            else:
                chunks.append({
                    "array": chunk_audio,
                    "start": actual_boundaries[i],
                    "duration": duration
                })
        
        total_chunks = len(chunks)
        logger.info(f"音声をチャンク分割: {total_chunks}個のチャンク（{chunk_seconds}秒ずつ）")
        
        if progress_callback:
            progress_callback(0.15, f"チャンク分割完了: {total_chunks}個のチャンク")
        
        # アライメント処理を分離するかどうか
        if self.config.transcription.api_align_in_subprocess:
            return self._transcribe_with_separated_alignment(
                client, audio, original_audio_path, chunks,
                progress_callback, perf_tracker, start_time
            )
        
        # 従来の処理（API+アライメントを同時実行）
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
            
            # 並列でAPI処理（設定値を使用）
            max_workers = min(self.DEFAULT_API_MAX_WORKERS, len(chunk_files))
            all_segments = []
            completed_chunks = 0
            
            logger.info(f"並列処理設定: max_workers={max_workers}, チャンク数={len(chunk_files)}")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # アライメントモデルを事前に読み込み（全チャンクで共有）
                align_model = None
                align_meta = None
                try:
                    import whisperx
                    
                    # transformersのバージョンによる互換性問題を回避
                    import transformers
                    from packaging import version
                    
                    # transformersのバージョンをチェック
                    transformers_version = version.parse(transformers.__version__)
                    logger.info(f"transformersバージョン: {transformers.__version__}")
                    
                    # 新しいバージョンの場合でも、アライメントモデルを読み込む
                    try:
                        align_model, align_meta = whisperx.load_align_model(
                            language_code=self.api_config.language,
                            device="cpu"
                        )
                        logger.info("アライメントモデルを読み込みました")
                        
                        # transformers 4.30.0以降の場合、互換性の警告を表示
                        if transformers_version >= version.parse("4.30.0"):
                            logger.warning(f"transformers {transformers.__version__} で実行中。エラーが発生する可能性があります")
                    except Exception as e:
                        logger.error(f"アライメントモデルの読み込みエラー: {e}")
                        align_model = None
                        align_meta = None
                except ImportError as e:
                    logger.warning(f"必要なライブラリがインストールされていません: {e}")
                    align_model = None
                    align_meta = None
                except Exception as e:
                    logger.warning(f"アライメントモデルの読み込みに失敗: {e}")
                    align_model = None
                    align_meta = None
                
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
                logger.info(f"APIチャンク処理開始: {len(futures)}個のfutureを待機中")
                logger.info(f"最大ワーカー数: {max_workers}")
                
                # futureとチャンク情報のマッピング
                future_to_chunk = {futures[i]: (chunk_files[i], i) for i in range(len(futures))}
                
                for future in as_completed(futures):
                    chunk_info, idx = future_to_chunk[future]
                    try:
                        segments = future.result()
                        all_segments.extend(segments)
                        completed_chunks += 1
                        
                        logger.info(f"チャンク[{idx}]完了 {completed_chunks}/{len(chunk_files)}: {len(segments)}セグメント取得")
                        
                        if progress_callback:
                            progress = 0.2 + (0.7 * completed_chunks / len(chunk_files))
                            progress_callback(progress, f"チャンク {completed_chunks}/{len(chunk_files)} 完了")
                    
                    except openai.RateLimitError as e:
                        logger.warning(f"チャンク[{idx}] レート制限エラー: {e}")
                        completed_chunks += 1
                        # レート制限の場合は空のリストを追加
                        all_segments.extend([])
                    except openai.APIError as e:
                        logger.warning(f"チャンク[{idx}] API エラー: {e}")
                        completed_chunks += 1
                        # APIエラーの場合も空のリストを追加
                        all_segments.extend([])
                    except Exception as e:
                        logger.warning(f"チャンク[{idx}] 処理失敗: {e}")
                        import traceback
                        logger.error(f"詳細なエラー: {traceback.format_exc()}")
                        completed_chunks += 1
                        # その他のエラーも空のリストを追加
                        all_segments.extend([])
                
                logger.info(f"すべてのAPIチャンク処理完了: 合計{len(all_segments)}セグメント")
            
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
            
            # アライメント処理を追加（ローカル版と同等の精度）
            if self.skip_alignment:
                # アライメントをスキップ
                aligned_segments = validated_segments
                if progress_callback:
                    progress_callback(1.0, "チャンク並列処理完了（アライメントスキップ）")
            else:
                # アライメント処理はチャンクごとに実行済み
                if progress_callback:
                    progress_callback(0.95, "結果を統合中...")
                
                aligned_segments = validated_segments  # 既にアライメント済み
                
                if progress_callback:
                    progress_callback(1.0, "チャンク並列処理完了")
            
            # 処理時間を計算
            processing_time = time.time() - start_time
            
            logger.info(f"_transcribe_with_chunks完了 - 最終セグメント数: {len(aligned_segments)}")
            if aligned_segments:
                logger.info(f"最初のセグメント: {aligned_segments[0].text[:50] if aligned_segments[0].text else '(空)'}")
            
            # トラッキング終了
            if perf_tracker:
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
        logger.info(f"[開始] チャンク[{chunk_idx}] API処理開始 (offset: {start_offset:.1f}s, file: {os.path.basename(chunk_file)})")
        try:
            # ファイルサイズを確認
            file_size_mb = os.path.getsize(chunk_file) / (1024 * 1024)
            logger.info(f"チャンク[{chunk_idx}] ファイルサイズ: {file_size_mb:.2f}MB")
            
            with open(chunk_file, 'rb') as audio_file:
                logger.info(f"チャンク[{chunk_idx}] OpenAI APIを呼び出し中...")
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=self.api_config.language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )
                logger.info(f"チャンク[{chunk_idx}] API応答受信 - 成功")
            
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
                logger.info(f"チャンク {chunk_idx} アライメント処理開始")
                try:
                    # チャンクファイルから音声データを読み込み
                    import whisperx
                    chunk_audio = whisperx.load_audio(chunk_file)
                    logger.info(f"チャンク {chunk_idx} 音声データ読み込み完了")
                    
                    # API結果をWhisperX形式に変換
                    whisperx_segments = []
                    for seg in segments:
                        whisperx_segments.append({
                            "start": seg.start - start_offset,  # チャンク内の相対時間に戻す
                            "end": seg.end - start_offset,
                            "text": seg.text
                        })
                    
                    # チャンクごとのアライメント
                    # エラーハンドリングを強化
                    try:
                        aligned_result = whisperx.align(
                            whisperx_segments,
                            align_model,
                            align_meta,
                            chunk_audio,
                            "cpu",
                            return_char_alignments=True
                        )
                    except TypeError as te:
                        # sampling_rate引数エラーの場合
                        if "sampling_rate" in str(te):
                            logger.warning(f"チャンク {chunk_idx}: アライメント処理でsampling_rateエラー。return_char_alignmentsを無効化して再試行")
                            # return_char_alignmentsを無効化して再試行
                            aligned_result = whisperx.align(
                                whisperx_segments,
                                align_model,
                                align_meta,
                                chunk_audio,
                                "cpu",
                                return_char_alignments=False
                            )
                        else:
                            raise te
                    
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
                                # wordsは辞書のリストなので、直接アクセス可能
                                if isinstance(word, dict):
                                    if "start" in word and word["start"] is not None:
                                        word["start"] += start_offset
                                    if "end" in word and word["end"] is not None:
                                        word["end"] += start_offset
                        aligned_segments.append(aligned_seg)
                    
                    logger.info(f"チャンク {chunk_idx} アライメント完了: {len(aligned_segments)}セグメント")
                    return aligned_segments
                    
                except Exception as e:
                    logger.error(f"チャンク {chunk_idx} のアライメント処理に失敗: {e}")
                    raise RuntimeError(f"文字位置情報の取得に失敗しました。アライメント処理でエラーが発生しました: {str(e)}")
            
            logger.info(f"[完了] チャンク[{chunk_idx}] 処理完了: {len(segments)}セグメント")
            if segments:
                logger.info(f"チャンク[{chunk_idx}] 最初のテキスト: {segments[0].text[:30] if segments[0].text else '(空)'}")
            return segments
        
        except openai.RateLimitError as e:
            logger.error(f"[エラー] チャンク[{chunk_idx}]: レート制限エラー - {e}")
            raise  # エラーを再発生させて、親の処理でキャッチさせる
        except openai.AuthenticationError as e:
            logger.error(f"[エラー] チャンク[{chunk_idx}]: 認証エラー - {e}")
            raise
        except openai.APIError as e:
            logger.error(f"[エラー] チャンク[{chunk_idx}]: API エラー - {e}")
            raise
        except Exception as e:
            logger.error(f"[エラー] チャンク[{chunk_idx}]: 予期しないエラー - {e}")
            import traceback
            logger.error(f"トレースバック:\n{traceback.format_exc()}")
            raise
    
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
    
    def _transcribe_with_separated_alignment(
        self, client, audio, original_audio_path: str,
        chunks: List[Dict], progress_callback: Optional[callable],
        perf_tracker: Optional, start_time: float
    ) -> TranscriptionResult:
        """API処理とアライメント処理を分離した文字起こし"""
        import soundfile as sf
        import numpy as np
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        logger.info("分離型処理モード: API処理とアライメントを別々に実行")
        
        # Step 1: API処理（メインプロセスで並列実行）
        temp_dir = tempfile.mkdtemp(prefix="textffcut_api_separated_")
        
        try:
            # チャンクファイルを作成
            chunk_files = []
            for i, chunk in enumerate(chunks):
                chunk_file = os.path.join(temp_dir, f"chunk_{i:03d}.wav")
                sf.write(chunk_file, chunk["array"], self.config.transcription.sample_rate)
                
                chunk_size = os.path.getsize(chunk_file) / (1024 * 1024)
                if chunk_size > 25:
                    logger.warning(f"チャンク {i} がサイズ制限を超過: {chunk_size:.1f}MB")
                    continue
                
                chunk_files.append((chunk_file, chunk["start"], i))
            
            if progress_callback:
                progress_callback(0.2, f"API処理開始: {len(chunk_files)}個のチャンク")
            
            # API並列処理（アライメントなし）
            api_segments = []
            completed_chunks = 0
            max_workers = min(self.DEFAULT_API_MAX_WORKERS, len(chunk_files))
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = []
                for chunk_file, start_offset, chunk_idx in chunk_files:
                    future = executor.submit(
                        self._transcribe_chunk_api_only,  # アライメントなしのAPI処理
                        client, chunk_file, start_offset, chunk_idx
                    )
                    futures.append(future)
                
                for future in as_completed(futures):
                    try:
                        segments = future.result()
                        api_segments.extend(segments)
                        completed_chunks += 1
                        
                        if progress_callback:
                            progress = 0.2 + (0.4 * completed_chunks / len(chunk_files))
                            progress_callback(progress, f"API処理: {completed_chunks}/{len(chunk_files)} 完了")
                    
                    except Exception as e:
                        logger.error(f"APIチャンク処理エラー: {e}")
                        completed_chunks += 1
            
            # API結果をソート
            api_segments.sort(key=lambda s: s['start'])
            
            logger.info(f"API処理完了: {len(api_segments)}セグメント")
            
            if not api_segments:
                raise ValueError("API処理結果が空です")
            
            # Step 2: アライメント処理（サブプロセスで実行）
            if progress_callback:
                progress_callback(0.6, "アライメント処理を開始...")
            
            aligned_segments = self._align_in_subprocess(
                original_audio_path,
                api_segments,
                progress_callback
            )
            
            # TranscriptionSegmentオブジェクトに変換
            final_segments = []
            for seg in aligned_segments:
                # wordsフィールドの検証
                if not seg.get('words'):
                    raise TranscriptionError(
                        f"アライメント処理に失敗しました。文字位置情報（words）が生成されませんでした。\n"
                        f"セグメント: {seg.get('text', '')[:50]}..."
                    )
                
                segment = TranscriptionSegment(
                    start=seg['start'],
                    end=seg['end'],
                    text=seg['text'],
                    words=seg.get('words'),
                    chars=seg.get('chars')
                )
                final_segments.append(segment)
            
            # 処理時間を計算
            processing_time = time.time() - start_time
            
            # トラッキング終了
            if perf_tracker:
                perf_tracker.end_tracking(
                    segments_processed=len(final_segments),
                    api_chunks=len(chunks),
                    alignment_chunks=len(final_segments)
                )
            
            if progress_callback:
                progress_callback(1.0, "処理完了")
            
            # 最終的な結果の作成
            result = TranscriptionResult(
                language=self.api_config.language,
                segments=final_segments,
                original_audio_path=original_audio_path,
                model_size="whisper-1_api",
                processing_time=processing_time
            )
            
            # wordsフィールドの最終確認
            is_valid, errors = result.validate_has_words()
            if not is_valid:
                raise TranscriptionError(
                    "文字起こしは完了しましたが、文字位置情報（words）の生成に失敗しました。\n"
                    + "\n".join(errors)
                )
            
            return result
            
        finally:
            # クリーンアップ
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
    
    def _transcribe_chunk_api_only(
        self, client, chunk_file: str, start_offset: float, chunk_idx: int
    ) -> List[Dict[str, Any]]:
        """APIのみでチャンク処理（アライメントなし）"""
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
                            'start': seg['start'] + start_offset,
                            'end': seg['end'] + start_offset,
                            'text': seg['text']
                        }
                    else:
                        segment = {
                            'start': seg.start + start_offset,
                            'end': seg.end + start_offset,
                            'text': seg.text
                        }
                    segments.append(segment)
            elif response.text.strip():
                # セグメント情報がない場合
                estimated_duration = len(response.text) / 20
                segment = {
                    'start': start_offset,
                    'end': start_offset + estimated_duration,
                    'text': response.text
                }
                segments.append(segment)
            
            logger.info(f"APIチャンク {chunk_idx} 完了: {len(segments)}セグメント")
            return segments
            
        except Exception as e:
            logger.error(f"APIチャンク {chunk_idx} エラー: {e}")
            return []
    
    def _align_in_subprocess(
        self, audio_path: str, api_segments: List[Dict],
        progress_callback: Optional[callable] = None
    ) -> List[Dict[str, Any]]:
        """サブプロセスでアライメント処理を実行"""
        work_dir = tempfile.mkdtemp(prefix="textffcut_align_")
        
        try:
            # APIセグメントをV2形式に変換
            v2_segments = []
            for i, seg in enumerate(api_segments):
                v2_segment = {
                    'id': f'seg_{i:03d}',  # IDを生成
                    'text': seg['text'],
                    'start': seg['start'],
                    'end': seg['end'],
                    'words': None,  # アライメント前なのでNone
                    'chars': None,
                    'transcription_completed': True,
                    'alignment_completed': False,
                    'alignment_error': None,
                    'metadata': {}
                }
                v2_segments.append(v2_segment)
            
            # 設定をJSON形式で保存
            config_data = {
                'audio_path': audio_path,
                'segments': v2_segments,  # V2形式のセグメント
                'language': self.api_config.language,
                'model_size': 'base',  # APIモードではbaseモデル相当のメモリ使用量を想定
                'config': {
                    'transcription': {
                        'language': self.config.transcription.language,
                        'compute_type': self.config.transcription.compute_type
                        # batch_sizeは自動最適化で管理されるため削除
                    }
                }
            }
            
            config_path = os.path.join(work_dir, 'config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            
            result_path = os.path.join(work_dir, 'align_result.json')
            
            # ワーカープロセスを実行
            cmd = [
                sys.executable,
                os.path.join(os.path.dirname(__file__), '..', 'worker_align.py'),
                config_path
            ]
            
            logger.info(f"アライメントワーカーを起動: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # プログレス監視
            try:
                # stdoutとstderrの両方を読み取る
                stdout_lines = []
                stderr_lines = []
                
                for line in process.stdout:
                    line = line.strip()
                    stdout_lines.append(line)
                    
                    if line.startswith('PROGRESS:'):
                        try:
                            parts = line.split('|', 1)
                            progress = float(parts[0].split(':')[1])
                            message = parts[1] if len(parts) > 1 else ""
                            
                            if progress_callback:
                                # アライメントは全体の40%を占める（0.6-1.0）
                                adjusted_progress = 0.6 + (progress * 0.4)
                                progress_callback(adjusted_progress, message)
                                
                        except Exception as e:
                            logger.warning(f"プログレス解析エラー: {e}")
                    
                    elif line.startswith('ERROR:'):
                        logger.error(f"アライメントワーカーエラー: {line}")
                    
                    elif line.startswith('TRACEBACK:'):
                        logger.error(f"アライメントワーカートレースバック: {line}")
                
                # プロセス終了を待つ
                return_code = process.wait()
                
                if return_code != 0:
                    stderr = process.stderr.read()
                    logger.error(f"アライメントワーカーが異常終了: {stderr}")
                    
                    # エラー出力を詳細に記録
                    error_details = f"Exit code: {return_code}\nStderr: {stderr}"
                    
                    # 結果ファイルが部分的に作成されている可能性をチェック
                    if os.path.exists(result_path):
                        try:
                            with open(result_path, 'r', encoding='utf-8') as f:
                                error_result = json.load(f)
                            if not error_result.get('success'):
                                error_msg = error_result.get('error', '不明なエラー')
                                error_details += f"\n詳細エラー: {error_msg}"
                        except:
                            pass
                    
                    # エラー時は例外を発生させる
                    raise RuntimeError(f"アライメント処理に失敗しました: ワーカープロセスが異常終了しました。\n{error_details}")
                
                # 結果を読み込み
                if os.path.exists(result_path):
                    with open(result_path, 'r', encoding='utf-8') as f:
                        result_data = json.load(f)
                    
                    if result_data.get('success'):
                        aligned_segments = result_data.get('segments', [])
                        # wordsが正しく生成されているか確認
                        for seg in aligned_segments:
                            if not seg.get('words'):
                                logger.error(f"アライメント結果にwordsがありません: {seg.get('text', '')[:50]}...")
                                raise RuntimeError("アライメント処理は成功しましたが、文字位置情報（words）が生成されませんでした")
                        return aligned_segments
                    else:
                        error_msg = result_data.get('error', '不明なエラー')
                        logger.error(f"アライメントエラー: {error_msg}")
                        raise RuntimeError(f"アライメント処理に失敗しました: {error_msg}")
                else:
                    logger.error("アライメント結果ファイルが見つかりません")
                    raise RuntimeError("アライメント結果ファイルが見つかりません")
                    
            except subprocess.TimeoutExpired:
                logger.error("アライメントプロセスがタイムアウトしました")
                process.kill()
                raise RuntimeError("アライメント処理がタイムアウトしました。処理時間が長すぎる可能性があります。")
                
        except Exception as e:
            logger.error(f"アライメントサブプロセスエラー: {e}")
            # RuntimeErrorはそのまま再発生させる
            if isinstance(e, RuntimeError):
                raise
            # その他の例外も詳細なエラーメッセージと共に発生させる
            raise RuntimeError(f"アライメント処理中に予期しないエラーが発生しました: {str(e)}")
            
        finally:
            # クリーンアップ
            try:
                shutil.rmtree(work_dir)
            except:
                pass
    
    
    def _detect_silence_in_range(self, audio: np.ndarray, start: float, end: float, sample_rate: int) -> List[Dict[str, float]]:
        """指定範囲の無音を検出"""
        import numpy as np
        
        # 範囲を切り出し
        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)
        audio_range = audio[start_sample:end_sample]
        
        if len(audio_range) == 0:
            return []
        
        # RMSエネルギーを計算（ウィンドウサイズ: 10ms）
        window_size = int(0.01 * sample_rate)  # 10ms
        hop_size = window_size // 2
        
        # パディング
        pad_size = window_size - (len(audio_range) % window_size)
        if pad_size < window_size:
            audio_range = np.pad(audio_range, (0, pad_size))
        
        # RMS計算
        rms_values = []
        for i in range(0, len(audio_range) - window_size, hop_size):
            window = audio_range[i:i + window_size]
            rms = np.sqrt(np.mean(window ** 2))
            rms_values.append(rms)
        
        if not rms_values:
            return []
        
        # dBに変換
        rms_values = np.array(rms_values)
        # ゼロ除算を避ける
        rms_values = np.where(rms_values > 0, rms_values, 1e-10)
        db_values = 20 * np.log10(rms_values)
        
        # 無音区間を検出
        is_silent = db_values < self.SILENCE_THRESH
        
        # 連続する無音区間をグループ化
        silences = []
        in_silence = False
        silence_start = 0
        
        for i, silent in enumerate(is_silent):
            time_pos = start + (i * hop_size / sample_rate)
            
            if silent and not in_silence:
                # 無音開始
                in_silence = True
                silence_start = time_pos
            elif not silent and in_silence:
                # 無音終了
                in_silence = False
                silence_duration = time_pos - silence_start
                if silence_duration >= self.MIN_SILENCE_LEN:
                    silences.append({
                        'start': silence_start,
                        'end': time_pos
                    })
        
        # 最後が無音の場合
        if in_silence:
            time_pos = start + (len(is_silent) * hop_size / sample_rate)
            silence_duration = time_pos - silence_start
            if silence_duration >= self.MIN_SILENCE_LEN:
                silences.append({
                    'start': silence_start,
                    'end': time_pos
                })
        
        return silences
