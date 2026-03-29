"""
文字起こし処理モジュール
"""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
            "original_audio_path": str(self.original_audio_path),  # PosixPathを文字列に変換
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
        """全セグメントのテキストを結合（words or charsベース）"""
        segment_texts = []
        for seg in self.segments:
            # words または chars から文字列を構築
            text = self._extract_text_from_segment(seg)
            if text:
                segment_texts.append(text)
            elif seg.text:
                # フォールバック: segmentのtextフィールドを使用
                segment_texts.append(seg.text)
        # セグメント間にスペースを入れずに結合
        # 日本語のテキストでは通常スペースは不要
        return "".join(segment_texts)

    @staticmethod
    def _extract_text_from_segment(seg: "TranscriptionSegment") -> str:
        """セグメントからwords/charsのテキストを抽出"""
        # wordsから抽出（優先）
        if seg.words and len(seg.words) > 0:
            if hasattr(seg.words[0], "word"):
                return "".join(word.word for word in seg.words)  # type: ignore
            else:
                return "".join(word["word"] for word in seg.words)
        # charsから抽出（MLXモードのフォールバック）
        if seg.chars and len(seg.chars) > 0:
            if hasattr(seg.chars[0], "char"):
                return "".join(c.char for c in seg.chars)  # type: ignore
            else:
                return "".join(c["char"] for c in seg.chars)
        return ""

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

    def __init__(self, config: Config) -> None:
        self.config = config
        self.api_transcriber: Any | None = None
        self.device: str | None = None

        logger.info(f"Transcriber初期化開始 - use_api: {self.config.transcription.use_api}")
        logger.info(f"api_key: {'設定済み' if self.config.transcription.api_key else '未設定'}")

        # APIモードかローカルモードかを判定
        if self.config.transcription.use_api:
            # API版を使用
            logger.info("APITranscriberをインポート")
            from .transcription_api import APITranscriber

            logger.info("APITranscriberインスタンスを作成")
            self.api_transcriber = APITranscriber(config)
            self.device = None
            logger.info(f"APIモードで初期化完了: {self.config.transcription.api_provider}")
        else:
            # ローカル版を使用（MLX優先、WhisperXフォールバック）
            from utils.environment import MLX_AVAILABLE

            self.use_mlx = MLX_AVAILABLE and config.transcription.use_mlx_whisper

            if self.use_mlx:
                self.device = None  # MLXはdevice指定不要
                logger.info("MLXモードで初期化（Apple Silicon高速モード）")
            elif WHISPERX_AVAILABLE:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
                logger.info(f"WhisperXモードで初期化: デバイス={self.device}")
            else:
                raise ImportError(
                    "WhisperXもMLXも利用できません。いずれかをインストールしてください。\n"
                    "pip install whisperx  # または\n"
                    "pip install mlx-whisper mlx-forced-aligner  # Apple Silicon Mac"
                )

    def get_cache_path(self, video_path: str | Path, model_size: str) -> Path:
        """キャッシュファイルのパスを取得（TextffCutフォルダ内のtranscriptions/）"""
        from utils.file_utils import get_safe_filename

        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)

        # TextffCutフォルダ内のtranscriptions/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"

        # model_sizeに既に_apiが含まれている場合は、そのまま使用
        if model_size.endswith("_api"):
            return cache_dir / f"{model_size}.json"
        
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

                # バズクリップのキャッシュファイルは除外
                if "_buzz_" in filename:
                    continue

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
                        "actual_filename": filename,  # 実際のファイル名（拡張子なし）を保持
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

        # バズクリップのキャッシュファイルは読み込まない
        if "_buzz_" in cache_path.stem:
            logger.warning(
                f"バズクリップのキャッシュファイルを文字起こしキャッシュとして読み込もうとしました: {cache_path}"
            )
            return None

        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)

            # バズクリップのデータ構造でないことを確認
            if "transcription_model" in data or "candidates" in data.get("results", {}):
                logger.warning(f"バズクリップのデータ構造が検出されました: {cache_path}")
                return None

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
        logger.info(f"Transcriber.transcribe開始 - APIモード: {self.config.transcription.use_api}")
        logger.info(f"video_path: {video_path}, model_size: {model_size}")

        # APIモードの場合はAPITranscriberに委譲
        if self.config.transcription.use_api:
            logger.info("APIモードで処理開始 (_transcribe_api)")
            return self._transcribe_api(video_path, model_size, progress_callback, use_cache, save_cache)
        elif getattr(self, 'use_mlx', False):
            logger.info("MLXモードで処理開始 (_transcribe_mlx)")
            try:
                return self._transcribe_mlx(video_path, model_size, progress_callback, use_cache, save_cache)
            except Exception as e:
                logger.warning(f"MLXモードでエラー発生、WhisperXにフォールバック: {e}")
                self.use_mlx = False
                if WHISPERX_AVAILABLE:
                    self.device = "cpu"
                    return self._transcribe_local(
                        video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment
                    )
                raise
        else:
            logger.info("WhisperXモードで処理開始 (_transcribe_local)")
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
        logger.info("_transcribe_api開始")
        model_size = model_size or self.config.transcription.model_size

        # キャッシュ確認
        # APIモードでは model_size を使用（デフォルトは "whisper-1"）
        cache_path = self.get_cache_path(video_path, model_size or "whisper-1")
        if use_cache:
            logger.info(f"キャッシュ確認: {cache_path}")
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                logger.info("キャッシュが見つかりました")
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result

        # APIで文字起こし実行
        logger.info(f"APITranscriber.transcribe呼び出し - api_transcriber: {self.api_transcriber}")
        if not self.api_transcriber:
            logger.error("api_transcriberが初期化されていません！")
            raise RuntimeError("APITranscriberが初期化されていません")

        result = self.api_transcriber.transcribe(video_path, model_size, progress_callback)

        # キャッシュに保存
        if save_cache:
            # 結果のmodel_sizeを使用してキャッシュパスを更新
            cache_path = self.get_cache_path(video_path, result.model_size)
            self.save_to_cache(result, cache_path)

        return result

    # MLXモデル名マッピング
    MLX_MODEL_MAP = {
        "large-v3": "mlx-community/whisper-large-v3-mlx",
        "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
        "medium": "mlx-community/whisper-medium-mlx",
        "small": "mlx-community/whisper-small-mlx",
        "base": "mlx-community/whisper-base-mlx",
    }

    def _transcribe_mlx(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
    ) -> TranscriptionResult:
        """MLX版の文字起こし（mlx-whisper + mlx-forced-aligner）"""
        import mlx_whisper
        from mlx_forced_aligner import ForcedAligner

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

        # MLXモデル名に変換
        mlx_model = self.MLX_MODEL_MAP.get(model_size, f"mlx-community/whisper-{model_size}")

        # 1. mlx-whisperで文字起こし
        if progress_callback:
            progress_callback(0.1, f"MLX文字起こし中 ({model_size})...")

        logger.info(f"mlx-whisperで文字起こし開始: {mlx_model}")
        whisper_result = mlx_whisper.transcribe(
            str(video_path),
            path_or_hf_repo=mlx_model,
            language=self.config.transcription.language,
        )
        logger.info(f"mlx-whisper完了: {len(whisper_result.get('segments', []))}セグメント")

        if progress_callback:
            progress_callback(0.7, "アライメント処理中...")

        # 2. mlx-forced-alignerでアライメント（words/chars付き）
        logger.info("mlx-forced-alignerでアライメント開始")
        # ForcedAlignerをキャッシュ（wav2vec2モデル1.2GBの再ロードを防止）
        if not hasattr(self, '_mlx_aligner'):
            self._mlx_aligner = ForcedAligner()
        aligner = self._mlx_aligner
        segments_for_align = [
            {"start": s["start"], "end": s["end"], "text": s.get("text", "").strip()}
            for s in whisper_result["segments"]
            if s.get("text", "").strip()
        ]

        align_result = aligner.align(str(video_path), "", segments=segments_for_align)
        logger.info(f"アライメント完了: {len(align_result.segments)}セグメント")

        if progress_callback:
            progress_callback(0.9, "アライメント完了")

        # 3. TranscriptionResultに変換（_transcribe_localと同じ形式）
        # mlx-forced-alignerのscoreはlog-probability（Domain層でNoneにリセットされる）
        transcription_segments = []
        for seg in align_result.segments:
            transcription_segments.append(
                TranscriptionSegment(
                    start=seg["start"],
                    end=seg["end"],
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars"),
                )
            )

        processing_time = time.time() - start_time
        transcription_result = TranscriptionResult(
            segments=transcription_segments,
            language=self.config.transcription.language,
            processing_time=processing_time,
            original_audio_path=str(video_path),
            model_size=model_size,
        )

        # キャッシュに保存
        if save_cache:
            self.save_to_cache(transcription_result, cache_path)
            if progress_callback:
                progress_callback(1.0, "処理完了")

        logger.info(f"MLX文字起こし完了: {len(transcription_segments)}セグメント, {processing_time:.1f}秒")

        return transcription_result

    def _transcribe_local(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False,
    ) -> TranscriptionResult:
        """ローカル版の文字起こし（WhisperXに処理を任せる）"""
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

        # WhisperXに処理を任せる（手動チャンク分割なし）
        if progress_callback:
            progress_callback(0.1, "文字起こしを開始中...")
        
        logger.info("WhisperXで音声全体を処理（内部VADベースチャンク処理）")
        
        # バッチサイズの設定（レガシー処理用のデフォルト値）
        # 注：OptimizedTranscriptionGatewayAdapterではAutoOptimizerが動的に決定
        batch_size = getattr(self, 'DEFAULT_BATCH_SIZE', 8)
        
        # WhisperXのtranscribeメソッドを直接呼び出し
        result = asr_model.transcribe(
            audio,
            batch_size=batch_size,
            language=self.config.transcription.language,
            task="transcribe",
        )
        
        if progress_callback:
            progress_callback(0.7, "文字起こし完了、アライメント処理中...")
        
        # アライメント処理
        if not skip_alignment:
            try:
                align_model, align_meta = whisperx.load_align_model(
                    language_code=self.config.transcription.language,
                    device=self.device
                )
                
                result = whisperx.align(
                    result["segments"],
                    align_model,
                    align_meta,
                    audio,
                    self.device,
                    return_char_alignments=True
                )
                
                if progress_callback:
                    progress_callback(0.9, "アライメント完了")
                    
            except Exception as e:
                logger.warning(f"アライメント処理でエラー: {e}")
                # アライメントエラーは致命的ではないので続行
        
        # 結果を整形
        segments = result.get("segments", [])
        
        # TranscriptionResultに変換
        processing_time = time.time() - start_time
        
        # セグメントをTranscriptionSegmentオブジェクトに変換
        transcription_segments = []
        for seg in segments:
            transcription_segments.append(
                TranscriptionSegment(
                    start=seg.get("start", 0),
                    end=seg.get("end", 0),
                    text=seg.get("text", ""),
                    words=seg.get("words"),
                    chars=seg.get("chars")
                )
            )
        
        transcription_result = TranscriptionResult(
            segments=transcription_segments,
            language=self.config.transcription.language,
            processing_time=processing_time,
            original_audio_path=str(video_path),  # 必須引数を追加
            model_size=model_size,  # 必須引数を追加
        )
        
        # キャッシュに保存
        if save_cache:
            self.save_to_cache(transcription_result, cache_path)
            if progress_callback:
                progress_callback(1.0, "処理完了")
        
        logger.info(f"文字起こし完了: {len(segments)}セグメント, {processing_time:.1f}秒")
        
        return transcription_result
