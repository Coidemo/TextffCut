"""
文字起こし処理モジュール
"""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import TranscriptionResultV2

import numpy as np

try:
    import torch
    import whisperx

    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TranscriptionSegment:
    """文字起こしセグメント"""

    start: float
    end: float
    text: str
    words: list[dict[str, Any]] | None = None
    chars: list[dict[str, Any]] | None = None


@dataclass
class TranscriptionResult:
    """文字起こし結果"""

    language: str
    segments: list[TranscriptionSegment]
    original_audio_path: str | Path
    model_size: str
    processing_time: float

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "language": self.language,
            "segments": [
                {"start": seg.start, "end": seg.end, "text": seg.text, "words": seg.words, "chars": seg.chars}
                for seg in self.segments
            ],
            "original_audio_path": self.original_audio_path,
            "model_size": self.model_size,
            "processing_time": self.processing_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptionResult":
        """辞書形式から生成"""
        segments = [
            TranscriptionSegment(
                start=seg["start"], end=seg["end"], text=seg["text"], words=seg.get("words"), chars=seg.get("chars")
            )
            for seg in data["segments"]
        ]
        return cls(
            language=data["language"],
            segments=segments,
            original_audio_path=data.get("original_audio_path", ""),
            model_size=data.get("model_size", ""),
            processing_time=data.get("processing_time", 0.0),
        )

    def get_full_text(self) -> str:
        """全セグメントのテキストを結合（wordsベース必須）"""
        full_text = ""
        for seg in self.segments:
            # words が必須 - ない場合はエラー
            if not seg.words or len(seg.words) == 0:
                from utils.exceptions import VideoProcessingError

                raise VideoProcessingError(
                    "文字起こし結果に詳細な文字位置情報がありません。" "文字起こしを再実行してください。"
                )
            # wordsが辞書のリストかWordInfoオブジェクトのリストかを判定
            if seg.words and len(seg.words) > 0:
                if hasattr(seg.words[0], "word"):
                    # WordInfoオブジェクトの場合
                    text = "".join(word.word for word in seg.words)  # type: ignore
                else:
                    # 辞書の場合
                    text = "".join(word["word"] for word in seg.words)
            else:
                text = ""
            full_text += text
        return full_text.strip()

    def validate_has_words(self) -> tuple[bool, list[str]]:
        """
        全セグメントがwords情報を持っているか検証

        Returns:
            (有効かどうか, エラーメッセージのリスト)
        """
        errors = []
        segments_without_words = []

        for i, seg in enumerate(self.segments):
            if not seg.words or len(seg.words) == 0:
                segments_without_words.append(i)
                errors.append(f"セグメント {i + 1}: '{seg.text[:30]}...' にwords情報がありません")

        if segments_without_words:
            errors.insert(0, f"{len(segments_without_words)}個のセグメントでwords情報が欠落しています")
            return False, errors

        return True, []

    def to_v2_format(self) -> "TranscriptionResultV2":
        """
        新しいV2形式に変換

        Returns:
            TranscriptionResultV2インスタンス
        """
        from .models import (
            ProcessingMetadata,
            ProcessingStatus,
            TranscriptionResultV2,
            TranscriptionSegmentV2,
        )

        # メタデータの作成
        metadata = ProcessingMetadata(
            video_path=self.original_audio_path,
            video_duration=sum(seg.end - seg.start for seg in self.segments) if self.segments else 0,
            processing_mode="local",  # 既存の結果はローカルモードと仮定
            model_size=self.model_size,
            language=self.language,
            total_processing_time=self.processing_time,
        )

        # セグメントの変換
        v2_segments = []
        for i, seg in enumerate(self.segments):
            # Word情報の変換
            words = None
            if seg.words:
                # WordInfoは辞書形式で統一する
                # 複雑な処理は、異なるソース（API/ローカル）からのデータ形式を統一するため
                words = [
                    (
                        w
                        if isinstance(w, dict)
                        else (
                            w.to_dict()
                            if hasattr(w, "to_dict")
                            else {
                                "word": w.get("word", ""),
                                "start": w.get("start"),
                                "end": w.get("end"),
                                "confidence": w.get("score"),
                            }
                        )
                    )
                    for w in seg.words
                ]

            v2_segment = TranscriptionSegmentV2(
                id=f"seg_{i}",
                text=seg.text,
                start=seg.start,
                end=seg.end,
                words=words,
                language=self.language,
                transcription_completed=True,
                alignment_completed=bool(words and len(words) > 0),
            )
            v2_segments.append(v2_segment)

        # 結果の作成
        result = TranscriptionResultV2(
            segments=v2_segments,
            metadata=metadata,
            transcription_status=ProcessingStatus.COMPLETED,
            alignment_status=(
                ProcessingStatus.COMPLETED
                if all(s.alignment_completed for s in v2_segments)
                else ProcessingStatus.FAILED
            ),
        )

        return result


class Transcriber:
    """文字起こし処理クラス（ローカル/API統合版）"""

    # デフォルト値（自動最適化で動的に変更される）
    DEFAULT_BATCH_SIZE = 8
    DEFAULT_CHUNK_SECONDS = 600  # 10分
    DEFAULT_NUM_WORKERS = 2

    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_transcriber: Any | None = None
        self.device: str | None = None

        # APIモードかローカルモードかを判定
        if self.config.transcription.use_api:
            # API版を使用
            from .transcription_api import APITranscriber

            self.api_transcriber = APITranscriber(config)
            self.device = None
            logger.info(f"APIモードで初期化: {self.config.transcription.api_provider}")
        else:
            # ローカル版を使用
            if not WHISPERX_AVAILABLE:
                raise ImportError(
                    "WhisperXが利用できません。API版を使用するか、WhisperXをインストールしてください。\n"
                    "pip install whisperx"
                )
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"ローカルモードで初期化: デバイス={self.device}")

    def get_cache_path(self, video_path: str | Path, model_size: str) -> Path:
        """キャッシュファイルのパスを取得（TextffCutフォルダ内のtranscriptions/）"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のtranscriptions/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"

        # APIモードかどうかで、ファイル名を変える
        if self.config.transcription.use_api:
            # APIモードの場合は_apiサフィックスを追加
            return cache_dir / f"{model_size}_api.json"
        else:
            # ローカルモードの場合はそのまま
            return cache_dir / f"{model_size}.json"

    def get_available_caches(self, video_path: str | Path) -> list[dict[str, Any]]:
        """利用可能なキャッシュファイルのリストを取得"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # 動画と同じディレクトリの {動画名}_TextffCut/transcriptions/ を確認
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"

        if not cache_dir.exists():
            return []

        available_caches = []

        # キャッシュディレクトリ内のすべてのJSONファイルを検索
        for cache_file in cache_dir.glob("*.json"):
            try:
                # ファイル名からモデル情報を抽出
                # 新しい構造では: {モデル名}.json または {モデル名}_api.json
                filename = cache_file.stem

                # キャッシュファイルの情報を読み込み
                with open(cache_file, encoding="utf-8") as f:
                    data = json.load(f)

                # APIモードかローカルモードかを判定
                is_api_mode = filename.endswith("_api")

                if is_api_mode:
                    # _apiを除去してモデル名を取得
                    model_size = filename.replace("_api", "")
                    mode = "API"
                else:
                    # そのままモデル名として使用
                    model_size = filename
                    mode = "ローカル"

                # ファイルの更新時刻を取得
                modified_time = cache_file.stat().st_mtime

                available_caches.append(
                    {
                        "model_size": model_size,
                        "mode": mode,
                        "is_api": is_api_mode,
                        "file_path": cache_file,
                        "modified_time": modified_time,
                        "processing_time": data.get("processing_time", 0.0),
                        "segments_count": len(data.get("segments", [])),
                    }
                )

            except json.JSONDecodeError as e:
                logger.warning(f"キャッシュファイル形式エラー: {cache_file} - {e}")
                continue
            except OSError as e:
                logger.warning(f"キャッシュファイルアクセスエラー: {cache_file} - {e}")
                continue
            except Exception as e:
                logger.warning(f"キャッシュファイル読み込みエラー: {cache_file} - {e}")
                continue

        # 更新時刻でソート（新しい順）
        available_caches.sort(key=lambda x: x["modified_time"], reverse=True)

        return available_caches

    def load_from_cache(self, cache_path: Path) -> TranscriptionResult | None:
        """キャッシュから文字起こし結果を読み込み"""
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return TranscriptionResult.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"キャッシュファイル形式エラー: {cache_path} - {e}")
            return None
        except OSError as e:
            logger.error(f"キャッシュファイルアクセスエラー: {cache_path} - {e}")
            return None
        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {cache_path} - {e}")
            return None

    def save_to_cache(self, result: TranscriptionResult, cache_path: Path) -> None:
        """文字起こし結果をキャッシュに保存"""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)

    def transcribe_chunk(self, chunk: dict[str, Any], asr_model: Any) -> list[dict[str, Any]]:
        """チャンク単位の文字起こし"""
        res = asr_model.transcribe(
            chunk["array"],
            batch_size=self.DEFAULT_BATCH_SIZE,  # デフォルト値を使用
            language=self.config.transcription.language,
        )

        # デバッグ情報
        if res["segments"]:
            print(f"チャンク処理完了: 開始 {chunk['start']:.1f}秒, セグメント数: {len(res['segments'])}")

        # チャンクのオフセットを適用
        for seg in res["segments"]:
            seg["start"] += chunk["start"]
            seg["end"] += chunk["start"]

        return res["segments"]

    def transcribe_chunk_without_alignment(
        self, chunk: dict[str, Any], asr_model: Any, chunk_idx: int
    ) -> list[dict[str, Any]]:
        """チャンクを文字起こしのみ（アライメントなし）"""
        # 文字起こしのみ実行
        segments = self.transcribe_chunk(chunk, asr_model)
        logger.debug(f"チャンク {chunk_idx}: 文字起こし完了 ({len(segments)}セグメント)")
        return segments

    def transcribe_and_align_chunk(
        self, chunk: dict[str, Any], asr_model: Any, align_model: Any, align_meta: Any, chunk_idx: int
    ) -> list[dict[str, Any]]:
        """チャンクを文字起こし＋アライメント処理"""
        # まず文字起こし
        segments = self.transcribe_chunk(chunk, asr_model)

        # アライメント処理が有効でモデルが読み込まれている場合
        if align_model is not None and align_meta is not None and len(segments) > 0:
            try:
                # チャンクの音声データでアライメント
                aligned_result = whisperx.align(
                    segments,
                    align_model,
                    align_meta,
                    chunk["array"],  # チャンクの音声データのみ使用
                    self.device,
                    return_char_alignments=True,
                )

                # アライメント結果のオフセットを調整
                aligned_segments = aligned_result["segments"]
                for seg in aligned_segments:
                    # セグメントのタイムスタンプはalignで再計算されるので調整が必要
                    seg["start"] += chunk["start"]
                    seg["end"] += chunk["start"]
                    # wordsのタイムスタンプも調整
                    if "words" in seg and seg["words"]:
                        for word in seg["words"]:
                            if "start" in word:
                                word["start"] += chunk["start"]
                            if "end" in word:
                                word["end"] += chunk["start"]

                logger.debug(f"チャンク {chunk_idx}: アライメント成功 ({len(aligned_segments)}セグメント)")
                return aligned_segments

            except Exception as e:
                logger.warning(f"チャンク {chunk_idx} のアライメント処理に失敗: {e}")
                # アライメント失敗時は元のセグメントを返す
                return segments

        return segments

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
        動画の文字起こしを実行（API/ローカル自動切り替え）

        Args:
            video_path: 動画ファイルのパス
            model_size: Whisperモデルサイズ
            progress_callback: 進捗コールバック関数 (progress: 0.0-1.0, status: str)
            use_cache: キャッシュを読み込むか
            save_cache: キャッシュに保存するか

        Returns:
            TranscriptionResult: 文字起こし結果
        """
        # APIモードの場合はAPITranscriberに委譲
        if self.config.transcription.use_api:
            return self._transcribe_api(video_path, model_size, progress_callback, use_cache, save_cache)
        else:
            return self._transcribe_local(
                video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment
            )

    def _transcribe_api(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
    ) -> TranscriptionResult:
        """API版の文字起こし"""
        model_size = model_size or self.config.transcription.model_size

        # キャッシュ確認
        cache_path = self.get_cache_path(video_path, f"{model_size}_api")
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result

        # APIで文字起こし実行
        result = self.api_transcriber.transcribe(video_path, model_size, progress_callback)

        # キャッシュに保存
        if save_cache:
            self.save_to_cache(result, cache_path)

        return result

    def _transcribe_local(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False,
    ) -> TranscriptionResult:
        """ローカル版の文字起こし（既存の実装）"""
        start_time = time.time()
        model_size = model_size or self.config.transcription.model_size

        # キャッシュ確認
        cache_path = self.get_cache_path(video_path, model_size)
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result

        # 音声を読み込み
        if progress_callback:
            progress_callback(0.0, "音声を読み込み中...")

        audio = whisperx.load_audio(video_path)

        # モデルを読み込み
        if progress_callback:
            progress_callback(0.05, "モデルを読み込み中...")

        asr_model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=self.config.transcription.language,
        )

        # チャンク分割
        chunk_sec = self.DEFAULT_CHUNK_SECONDS  # デフォルト値を使用
        sr = self.config.transcription.sample_rate
        num_workers = self.DEFAULT_NUM_WORKERS  # デフォルト値を使用

        step = chunk_sec * sr

        # チャンクを作成（APIモードと同じ処理）
        chunks: list[dict[str, Any]] = []
        MIN_CHUNK_DURATION = 1.0  # 1秒未満のチャンクは結合（品質向上のため）

        # 短いチャンクを一時保存する変数
        pending_chunk = None

        for i in range(0, len(audio), step):
            chunk_audio = audio[i : i + step]
            start_time = i / sr
            duration = len(chunk_audio) / sr

            # pending_chunkがある場合は先に結合を試みる
            if pending_chunk is not None:
                # 前の短いチャンクと現在のチャンクを結合
                combined_audio = np.concatenate([pending_chunk["array"], chunk_audio])
                combined_chunk = {
                    "array": combined_audio,
                    "start": pending_chunk["start"],
                    "duration": len(combined_audio) / sr,
                }
                chunks.append(combined_chunk)
                logger.info(
                    f"短いチャンクを次のチャンクと結合しました (新しい長さ: {combined_chunk['duration']:.1f}秒)"
                )
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
                        "duration": len(combined_audio) / sr,
                    }
                    logger.info(
                        f"短いチャンクを前のチャンクに結合しました (新しい長さ: {chunks[-1]['duration']:.1f}秒)"
                    )
                else:
                    # 最初のチャンクが短すぎる場合は一時保存して次と結合
                    pending_chunk = {"array": chunk_audio, "start": start_time, "duration": duration}
                    logger.warning(f"最初のチャンクが短いため、次のチャンクと結合します ({duration:.3f}秒)")
                continue

            chunks.append({"array": chunk_audio, "start": start_time, "duration": duration})

        # 最後にpending_chunkが残っている場合（音声全体が短い場合）
        if pending_chunk is not None:
            chunks.append(pending_chunk)
            logger.warning(f"最後の短いチャンクをそのまま追加します ({pending_chunk['duration']:.3f}秒)")

        # デバッグ情報
        total_audio_duration = len(audio) / sr
        print(f"音声の総時間: {total_audio_duration:.1f}秒, チャンク数: {len(chunks)}, チャンクサイズ: {chunk_sec}秒")

        # 並列処理で文字起こし
        segments_all = []
        total_chunks = len(chunks)
        completed_chunks = 0

        # アライメント処理の準備（skip_alignmentがFalseの場合のみ）
        align_model = None
        align_meta = None
        if not skip_alignment:
            try:
                align_model, align_meta = whisperx.load_align_model(
                    self.config.transcription.language, device=self.device
                )
                logger.info("アライメントモデルを読み込みました")
            except Exception as e:
                logger.warning(f"アライメントモデルの読み込みに失敗: {e}")

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            # チャンクごとに文字起こし（＋アライメント処理）
            futures = []
            for i, chunk in enumerate(chunks):
                if skip_alignment:
                    # アライメントをスキップして文字起こしのみ
                    future = executor.submit(self.transcribe_chunk_without_alignment, chunk, asr_model, i)
                else:
                    # 文字起こし＋アライメント
                    future = executor.submit(
                        self.transcribe_and_align_chunk, chunk, asr_model, align_model, align_meta, i
                    )
                futures.append(future)

            for future in as_completed(futures):
                segments = future.result()
                segments_all.extend(segments)
                completed_chunks += 1

                if progress_callback:
                    progress = 0.1 + (0.8 * completed_chunks / total_chunks)
                    if skip_alignment:
                        status = f"文字起こし処理中... ({completed_chunks}/{total_chunks} チャンク)"
                    else:
                        status = f"文字起こし・アライメント処理中... ({completed_chunks}/{total_chunks} チャンク)"
                    progress_callback(progress, status)

        # セグメントをソート
        segments_all.sort(key=lambda x: x["start"])

        # デバッグ情報
        print(f"文字起こし・アライメント完了: 全セグメント数: {len(segments_all)}")
        if segments_all:
            print(f"最初のセグメント: {segments_all[0]['start']:.1f}秒 - {segments_all[0]['end']:.1f}秒")
            print(f"最後のセグメント: {segments_all[-1]['start']:.1f}秒 - {segments_all[-1]['end']:.1f}秒")

        # 結果を構築
        result_segments = [
            TranscriptionSegment(
                start=seg["start"], end=seg["end"], text=seg["text"], words=seg.get("words"), chars=seg.get("chars")
            )
            for seg in segments_all
        ]

        processing_time = time.time() - start_time

        result = TranscriptionResult(
            language=self.config.transcription.language,
            segments=result_segments,
            original_audio_path=video_path,
            model_size=model_size,
            processing_time=processing_time,
        )

        # wordsフィールドの検証（skip_alignmentがFalseの場合のみ）
        if not skip_alignment:
            is_valid, errors = result.validate_has_words()
            if not is_valid:
                # V2形式に変換して詳細なエラーを生成
                v2_result = result.to_v2_format()
                try:
                    v2_result.require_valid_words()
                except Exception as e:
                    logger.error(f"文字起こし結果の検証に失敗: {str(e)}")
                    raise

        # キャッシュに保存
        if save_cache:
            self.save_to_cache(result, cache_path)

        if progress_callback:
            progress_callback(1.0, "文字起こし完了")

        return result
