"""
API版文字起こしモジュール
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import numpy as np
import openai

from config import Config
from utils.exceptions import TranscriptionError
from utils.logging import get_logger
from utils.performance_tracker import PerformanceTracker

from .transcription import TranscriptionResult, TranscriptionSegment

logger = get_logger(__name__)


class APITranscriber:
    """API版文字起こしクラス"""

    # デフォルト値（自動最適化で動的に変更される）
    DEFAULT_API_CHUNK_SECONDS = 600  # 10分
    DEFAULT_API_MAX_WORKERS = 3

    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_config = config.transcription
        self.skip_alignment = False  # アライメント処理をスキップするフラグ

        # 無音検出のパラメータ
        self.SILENCE_THRESH = -40  # dB
        self.MIN_SILENCE_LEN = 0.3  # 秒

    def transcribe(
        self,
        audio_path: str | Path,
        model_size: str | None = None,  # noqa: ARG002
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> TranscriptionResult:
        """
        APIを使用して音声ファイルを文字起こし

        Args:
            audio_path: 音声ファイルパス
            model_size: モデルサイズ（API版では一部のみ有効）
            progress_callback: 進捗コールバック

        Returns:
            TranscriptionResult: 文字起こし結果
        """
        logger.info(f"APITranscriber.transcribe開始 - audio_path: {audio_path}")
        logger.info(
            f"api_provider: {self.api_config.api_provider}, api_key: {'設定済み' if self.api_config.api_key else '未設定'}"
        )

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

    def _transcribe_openai(
        self, audio_path: str | Path, progress_callback: Callable[[float, str], None] | None = None
    ) -> TranscriptionResult:
        """OpenAI Whisper APIを使用（ローカル版と同じチャンク並列処理）"""
        # パフォーマンストラッキング開始
        from core.video import VideoInfo

        video_info = VideoInfo.from_file(audio_path)
        perf_tracker = PerformanceTracker(audio_path)

        # トラッキング開始（実際に使用されるモードは後で決定）

        try:
            from openai import OpenAI

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
                if "PROXY" in key.upper() or "proxy" in key:
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

            # API用に音声を圧縮（メモリ効率化）
            from core.audio_optimizer import IntelligentAudioOptimizer
            optimizer = IntelligentAudioOptimizer()
            
            if progress_callback:
                progress_callback(0.05, "API送信用に音声を圧縮中...")
            
            # API送信用に音声を圧縮（MP3形式、32kbps）
            compressed_path = optimizer.prepare_audio_for_api(Path(audio_path))
            compressed_size = os.path.getsize(compressed_path) / (1024 * 1024)
            
            if progress_callback:
                progress_callback(0.1, f"音声圧縮完了（{original_size:.1f}MB → {compressed_size:.1f}MB）")
            
            try:
                # 圧縮された音声ファイルで文字起こし（チャンク処理でアライメントも実行）
                import whisperx
                audio = whisperx.load_audio(str(compressed_path))
                
                # チャンク処理でアライメントも含めて実行
                # 重要: original_audio_pathは元の動画ファイルパスを使用
                result = self._transcribe_with_chunks(
                    client, audio, audio_path, progress_callback, perf_tracker, video_info.duration
                )
                return result
            finally:
                # 一時ファイルを削除
                if compressed_path.exists():
                    compressed_path.unlink()

        except ImportError as e:
            from utils.exceptions import TranscriptionError

            raise TranscriptionError("必要なライブラリが見つかりません。インストールを確認してください。") from e
        except openai.RateLimitError as e:
            from utils.exceptions import TranscriptionError

            raise TranscriptionError("API利用制限に達しました。しばらく待ってから再試行してください。") from e
        except openai.AuthenticationError as e:
            from utils.exceptions import TranscriptionError

            raise TranscriptionError("APIキーが無効です。設定を確認してください。") from e
        except openai.APIConnectionError as e:
            from utils.exceptions import TranscriptionError

            raise TranscriptionError("API接続エラーです。ネットワーク接続を確認してください。") from e
        except openai.BadRequestError as e:
            from utils.exceptions import TranscriptionError

            error_message = str(e)
            if "Audio file is too short" in error_message:
                raise TranscriptionError("動画ファイルが短すぎます。") from e
            elif "larger than the maximum" in error_message:
                raise TranscriptionError(
                    "ファイルサイズが上限（25MB）を超えています。動画を圧縮するか、ローカルモードを使用してください。"
                ) from e
            else:
                raise TranscriptionError(f"APIリクエストエラー: {error_message}") from e
        except Exception as e:
            from utils.exceptions import TranscriptionError

            raise TranscriptionError(f"文字起こしエラー: {str(e)}") from e

    def _transcribe_with_chunks(
        self,
        client,
        audio,
        original_audio_path: str | Path,
        progress_callback: Callable[[float, str], None] | None = None,
        perf_tracker: PerformanceTracker | None = None,
        video_duration: float = 0.0,
    ) -> TranscriptionResult:
        """スマート境界検出を使用したチャンク並列処理"""
        import tempfile
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        import numpy as np
        import soundfile as sf

        start_time = time.time()
        logger.info("スマート境界検出を使用したAPI処理")

        # トラッキング開始
        if perf_tracker:
            perf_tracker.start_tracking("normal", "whisper-1", True, video_duration)

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
            silences = self._detect_silence_in_range(audio, search_start, search_end, sample_rate)

            if silences:
                # 理想的な境界に最も近い無音の中心を選択
                best_silence = min(silences, key=lambda s: abs((s["start"] + s["end"]) / 2 - ideal_boundary))
                split_point = (best_silence["start"] + best_silence["end"]) / 2
                logger.info(f"境界 {ideal_boundary:.1f}s → 無音検出 {split_point:.1f}s")
            else:
                # 無音が見つからない場合は理想的な境界を使用
                split_point = ideal_boundary
                logger.info(f"境界 {ideal_boundary:.1f}s で無音なし、そのまま使用")

            actual_boundaries.append(split_point)

        # 最後まで含める
        actual_boundaries.append(len(audio) / sample_rate)

        # 実際のチャンクを作成
        chunks: list[dict[str, Any]] = []
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
                    "duration": len(combined_audio) / sample_rate,
                }
                logger.info(f"短いチャンク({duration:.1f}秒)を前のチャンクと結合")
            else:
                chunks.append({"array": chunk_audio, "start": actual_boundaries[i], "duration": duration})

        total_chunks = len(chunks)
        logger.info(f"音声をチャンク分割: {total_chunks}個のチャンク（{chunk_seconds}秒ずつ）")

        if progress_callback:
            progress_callback(0.15, f"チャンク分割完了: {total_chunks}個のチャンク")


        # デフォルト処理（API+アライメントを同一プロセスで実行 - 高速・安定）
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
                    # transformersのバージョンによる互換性問題を回避
                    import transformers
                    import whisperx
                    from packaging import version

                    # transformersのバージョンをチェック
                    transformers_version = version.parse(transformers.__version__)
                    logger.info(f"transformersバージョン: {transformers.__version__}")

                    # 新しいバージョンの場合でも、アライメントモデルを読み込む
                    try:
                        align_model, align_meta = whisperx.load_align_model(
                            language_code=self.api_config.language, device="cpu"
                        )
                        logger.info("アライメントモデルを読み込みました")

                        # transformers 4.30.0以降の場合、互換性の警告を表示
                        if transformers_version >= version.parse("4.30.0"):
                            logger.warning(
                                f"transformers {transformers.__version__} で実行中。エラーが発生する可能性があります"
                            )
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

                # 各チャンクのAPI処理を送信（アライメントなしで）
                futures = []
                for chunk_file, start_offset, chunk_idx in chunk_files:
                    future = executor.submit(
                        self._transcribe_chunk_api, client, chunk_file, start_offset, chunk_idx, None, None
                    )
                    futures.append(future)

                # 完了したものから結果を取得
                logger.info(f"APIチャンク処理開始: {len(futures)}個のfutureを待機中")
                logger.info(f"最大ワーカー数: {max_workers}")

                # futureとチャンク情報のマッピング
                future_to_chunk = {futures[i]: (chunk_files[i], i) for i in range(len(futures))}

                # API処理結果を一時保存（アライメント前）
                api_results = {}

                for future in as_completed(futures):
                    chunk_info, idx = future_to_chunk[future]
                    try:
                        segments = future.result()
                        api_results[idx] = (chunk_info, segments)
                        completed_chunks += 1

                        logger.info(
                            f"チャンク[{idx}]完了 {completed_chunks}/{len(chunk_files)}: {len(segments)}セグメント取得"
                        )

                        if progress_callback:
                            progress = 0.2 + (0.4 * completed_chunks / len(chunk_files))
                            progress_callback(progress, f"API処理 {completed_chunks}/{len(chunk_files)} 完了")

                    except openai.RateLimitError as e:
                        logger.warning(f"チャンク[{idx}] レート制限エラー: {e}")
                        api_results[idx] = (chunk_info, [])
                        completed_chunks += 1
                    except openai.APIError as e:
                        logger.warning(f"チャンク[{idx}] API エラー: {e}")
                        api_results[idx] = (chunk_info, [])
                        completed_chunks += 1
                    except Exception as e:
                        logger.warning(f"チャンク[{idx}] 処理失敗: {e}")
                        import traceback

                        logger.error(f"詳細なエラー: {traceback.format_exc()}")
                        api_results[idx] = (chunk_info, [])
                        completed_chunks += 1

                logger.info("すべてのAPIチャンク処理完了")

                # アライメント処理（順次実行）
                if align_model is not None and align_meta is not None:
                    logger.info("アライメント処理を開始（順次実行）")
                    aligned_chunks = 0
                    # インデックス順にソート
                    for idx in sorted(api_results.keys()):
                        chunk_info, segments = api_results[idx]
                        chunk_file, start_offset, chunk_idx = chunk_info

                        if segments and len(segments) > 0:
                            try:
                                # チャンクの音声を読み込み
                                chunk_audio, sr = self._load_audio_chunk(chunk_file)

                                # アライメント実行
                                aligned_segments = self._align_chunk(
                                    segments, chunk_audio, align_model, align_meta, start_offset, chunk_idx
                                )
                                all_segments.extend(aligned_segments)
                                aligned_chunks += 1

                                if progress_callback:
                                    progress = 0.6 + (0.3 * aligned_chunks / len(api_results))
                                    progress_callback(
                                        progress, f"アライメント {aligned_chunks}/{len(api_results)} 完了"
                                    )

                            except Exception as e:
                                logger.warning(f"チャンク {chunk_idx} のアライメント失敗: {e}")
                                # アライメント失敗時は元のセグメントを使用
                                all_segments.extend(segments)
                        else:
                            all_segments.extend(segments)
                else:
                    # アライメントなしの場合は、API結果をそのまま使用
                    for idx in sorted(api_results.keys()):
                        _, segments = api_results[idx]
                        all_segments.extend(segments)

                logger.info(f"統合処理完了: 合計{len(all_segments)}セグメント")

            if progress_callback:
                progress_callback(0.9, "結果を統合中...")

            # すべてのセグメントがTranscriptionSegmentオブジェクトであることを確認
            validated_segments = []
            for seg in all_segments:
                if isinstance(seg, TranscriptionSegment):
                    validated_segments.append(seg)
                elif isinstance(seg, dict):
                    # dictの場合はTranscriptionSegmentに変換
                    validated_segments.append(
                        TranscriptionSegment(
                            start=seg.get("start", 0),
                            end=seg.get("end", 0),
                            text=seg.get("text", ""),
                            words=seg.get("words"),
                            chars=seg.get("chars"),
                        )
                    )

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
                logger.info(
                    f"最初のセグメント: {aligned_segments[0].text[:50] if aligned_segments[0].text else '(空)'}"
                )

            # トラッキング終了
            if perf_tracker:
                perf_tracker.end_tracking(
                    segments_processed=len(aligned_segments),
                    api_chunks=len(chunks),
                    alignment_chunks=len(aligned_segments),
                )

            return TranscriptionResult(
                language=self.api_config.language,
                segments=aligned_segments,
                original_audio_path=original_audio_path,
                model_size="whisper-1",
                processing_time=processing_time,
            )

        finally:
            # 一時ファイルをクリーンアップ
            import shutil

            # 一時ディレクトリの削除エラーは無視（権限不足や使用中の場合）
            with suppress(OSError):
                shutil.rmtree(temp_dir)

    def _transcribe_chunk_api(
        self, client, chunk_file: str, start_offset: float, chunk_idx: int, align_model=None, align_meta=None
    ) -> list[TranscriptionSegment]:
        """単一チャンクのAPI処理"""
        logger.info(
            f"[開始] チャンク[{chunk_idx}] API処理開始 "
            f"(offset: {start_offset:.1f}s, file: {os.path.basename(chunk_file)})"
        )
        try:
            # ファイルサイズを確認
            file_size_mb = os.path.getsize(chunk_file) / (1024 * 1024)
            logger.info(f"チャンク[{chunk_idx}] ファイルサイズ: {file_size_mb:.2f}MB")

            with open(chunk_file, "rb") as audio_file:
                logger.info(f"チャンク[{chunk_idx}] OpenAI APIを呼び出し中...")
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language=self.api_config.language,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
                logger.info(f"チャンク[{chunk_idx}] API応答受信 - 成功")

            segments = []
            if hasattr(response, "segments") and response.segments:
                for seg in response.segments:
                    # seg がdictの場合とオブジェクトの場合の両方に対応
                    if isinstance(seg, dict):
                        segment = TranscriptionSegment(
                            start=seg["start"] + start_offset,
                            end=seg["end"] + start_offset,
                            text=seg["text"],
                            words=None,  # アライメント処理なしの場合は None に設定
                        )
                    else:
                        segment = TranscriptionSegment(
                            start=seg.start + start_offset,
                            end=seg.end + start_offset,
                            text=seg.text,
                            words=None,  # アライメント処理なしの場合は None に設定
                        )
                    segments.append(segment)
            elif response.text.strip():
                # セグメント情報がない場合
                estimated_duration = len(response.text) / 20
                segment = TranscriptionSegment(
                    start=start_offset,
                    end=start_offset + estimated_duration,
                    text=response.text,
                    words=None,  # アライメント処理なしの場合は None に設定
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
                        whisperx_segments.append(
                            {
                                "start": seg.start - start_offset,  # チャンク内の相対時間に戻す
                                "end": seg.end - start_offset,
                                "text": seg.text,
                            }
                        )

                    # チャンクごとのアライメント
                    # エラーハンドリングを強化
                    try:
                        aligned_result = whisperx.align(
                            whisperx_segments, align_model, align_meta, chunk_audio, "cpu", return_char_alignments=True
                        )
                    except TypeError as te:
                        # sampling_rate引数エラーの場合
                        if "sampling_rate" in str(te):
                            logger.warning(
                                f"チャンク {chunk_idx}: アライメント処理でsampling_rateエラー。"
                                f"return_char_alignmentsを無効化して再試行"
                            )
                            # return_char_alignmentsを無効化して再試行
                            aligned_result = whisperx.align(
                                whisperx_segments,
                                align_model,
                                align_meta,
                                chunk_audio,
                                "cpu",
                                return_char_alignments=False,
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
                            chars=seg.get("chars"),
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
                    raise RuntimeError(
                        f"文字位置情報の取得に失敗しました。アライメント処理でエラーが発生しました: {str(e)}"
                    ) from e

            logger.info(f"[完了] チャンク[{chunk_idx}] 処理完了: {len(segments)}セグメント")
            if segments:
                logger.info(
                    f"チャンク[{chunk_idx}] 最初のテキスト: {segments[0].text[:30] if segments[0].text else '(空)'}"
                )
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









    def _detect_silence_in_range(
        self, audio: np.ndarray, start: float, end: float, sample_rate: int
    ) -> list[dict[str, float]]:
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
        rms_values: list[float] = []
        for i in range(0, len(audio_range) - window_size, hop_size):
            window = audio_range[i : i + window_size]
            rms = np.sqrt(np.mean(window**2))
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
                silence_start = float(time_pos)
            elif not silent and in_silence:
                # 無音終了
                in_silence = False
                silence_duration = time_pos - silence_start
                if silence_duration >= self.MIN_SILENCE_LEN:
                    silences.append({"start": silence_start, "end": time_pos})

        # 最後が無音の場合
        if in_silence:
            time_pos = start + (len(is_silent) * hop_size / sample_rate)
            silence_duration = time_pos - silence_start
            if silence_duration >= self.MIN_SILENCE_LEN:
                silences.append({"start": silence_start, "end": time_pos})

        return silences

    def _estimate_word_timestamps(self, text: str, start: float, end: float) -> list[dict[str, Any]]:
        """単語のタイムスタンプを推定"""
        if not text:
            return []

        # 日本語の場合は文字単位で分割
        if self.api_config.language == "ja":
            # スペースと句読点で分割
            import re

            parts = re.split(r"([、。！？\s]+)", text)
            words = [part for part in parts if part and not part.isspace()]
        else:
            # その他の言語は単語単位
            words = text.split()

        if not words:
            return []

        # 各単語に均等に時間を割り当て
        duration = end - start
        word_duration = duration / len(words)

        estimated_words = []
        current_time = start

        for word in words:
            word_info = {
                "word": word,
                "start": current_time,
                "end": min(current_time + word_duration, end),
                "confidence": 0.5,  # 推定値なので低い信頼度
            }
            estimated_words.append(word_info)
            current_time += word_duration

        return estimated_words

    def _load_audio_chunk(self, chunk_file: str) -> tuple[np.ndarray, int]:
        """チャンクファイルから音声データを読み込む"""
        from pydub import AudioSegment

        audio = AudioSegment.from_file(chunk_file)
        samples = np.array(audio.get_array_of_samples())
        if audio.channels == 2:
            samples = samples.reshape((-1, 2))
            samples = samples.mean(axis=1)
        samples = samples.astype(np.float32) / 32768.0

        return samples, audio.frame_rate

    def _align_chunk(
        self,
        segments: list[TranscriptionSegment],
        chunk_audio: np.ndarray,
        align_model,
        align_meta,
        start_offset: float,
        chunk_idx: int,
    ) -> list[TranscriptionSegment]:
        """チャンクのアライメント処理（順次実行用）"""
        import whisperx

        try:
            # TranscriptionSegmentをWhisperX形式に変換
            whisperx_segments = []
            for seg in segments:
                whisperx_seg = {
                    "start": seg.start - start_offset,  # チャンク相対時間に変換
                    "end": seg.end - start_offset,
                    "text": seg.text,
                }
                whisperx_segments.append(whisperx_seg)

            # アライメント実行
            aligned_result = whisperx.align(
                whisperx_segments,
                align_model,
                align_meta,
                chunk_audio,
                "cpu",
                return_char_alignments=True,
            )

            # 結果を元の形式に戻す
            aligned_segments = []
            for seg in aligned_result["segments"]:
                aligned_seg = TranscriptionSegment(
                    start=seg["start"] + start_offset,  # 絶対時間に戻す
                    end=seg["end"] + start_offset,
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars"),
                )
                # wordsのタイムスタンプも調整
                if aligned_seg.words:
                    for word in aligned_seg.words:
                        if isinstance(word, dict):
                            if "start" in word and word["start"] is not None:
                                word["start"] += start_offset
                            if "end" in word and word["end"] is not None:
                                word["end"] += start_offset
                aligned_segments.append(aligned_seg)

            logger.info(f"チャンク {chunk_idx} アライメント完了: {len(aligned_segments)}セグメント")
            return aligned_segments

        except Exception as e:
            logger.error(f"チャンク {chunk_idx} のアライメント中にエラー: {e}")
            raise
