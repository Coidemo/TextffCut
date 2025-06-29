"""
スマート分割文字起こしモジュール
動画を20分前後で分割してWhisperXのFull VAD処理を適用
"""

import math
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

try:
    import torch  # noqa: F401
    import whisperx

    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

import psutil

from config import Config
from utils.logging import get_logger

from .transcription import Transcriber, TranscriptionResult, TranscriptionSegment
from .video import SilenceInfo, VideoInfo, VideoProcessor

logger = get_logger(__name__)


class SmartSplitTranscriber(Transcriber):
    """スマート分割文字起こしクラス"""

    # 分割設定（メモリ削減のため小さく設定）
    TARGET_DURATION = 10 * 60  # 10分を目標
    MIN_DURATION = 5 * 60  # 最小5分
    MAX_DURATION = 15 * 60  # 最大15分
    MIN_SPLIT_DURATION = 15 * 60  # 15分以下は分割しない

    def __init__(self, config: Config) -> None:
        """初期化"""
        super().__init__(config)
        self.video_processor = VideoProcessor(config)

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
        スマート分割文字起こしを実行

        Args:
            video_path: 動画ファイルのパス
            model_size: Whisperモデルサイズ
            progress_callback: 進捗コールバック関数
            use_cache: キャッシュを読み込むか
            save_cache: キャッシュに保存するか

        Returns:
            TranscriptionResult: 文字起こし結果
        """
        # APIモードの場合は最適化されたチャンクサイズで処理
        if self.config.transcription.use_api:
            logger.info("APIモード：最適化されたチャンクサイズで処理")
            return self._transcribe_api_optimized(
                video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment
            )

        # キャッシュ確認
        model_size = model_size or self.config.transcription.model_size
        cache_path = self.get_cache_path(video_path, f"{model_size}_smart")
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result

        # 動画情報を取得
        video_info = VideoInfo.from_file(video_path)
        duration = video_info.duration

        logger.info(f"動画時間: {duration / 60:.1f}分")

        # 分割判定
        if duration <= self.MIN_SPLIT_DURATION:
            logger.info(f"{self.MIN_SPLIT_DURATION / 60:.0f}分以下なので分割せずに処理")
            result = self._transcribe_full_vad(video_path, model_size, progress_callback)
        else:
            logger.info("スマート分割処理を開始")
            result = self._transcribe_with_split(video_path, model_size, duration, progress_callback)

        # キャッシュに保存
        if save_cache:
            self.save_to_cache(result, cache_path)

        return result

    def _transcribe_full_vad(
        self, video_path: str | Path, model_size: str, progress_callback: Callable | None = None
    ) -> TranscriptionResult:
        """WhisperXのFull VAD処理で文字起こし"""
        start_time = time.time()

        if progress_callback:
            progress_callback(0.1, "音声を読み込み中...")

        # 音声を読み込み
        audio = whisperx.load_audio(video_path)
        audio = audio.astype(np.float32)  # dtype mismatch エラーを防ぐため

        if progress_callback:
            progress_callback(0.2, "モデルを読み込み中...")

        # モデルを読み込み
        model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=self.config.transcription.language,
        )

        if progress_callback:
            progress_callback(0.3, "文字起こし中（VAD処理含む）...")

        # VADを有効にして文字起こし
        result = model.transcribe(
            audio, batch_size=self._get_optimal_batch_size(), language=self.config.transcription.language, chunk_size=30
        )

        if progress_callback:
            progress_callback(0.7, "アライメント処理中...")

        # アライメント処理
        try:
            align_model, metadata = whisperx.load_align_model(
                language_code=self.config.transcription.language, device=self.device
            )

            aligned_result = whisperx.align(
                result["segments"], align_model, metadata, audio, self.device, return_char_alignments=True
            )

            segments = aligned_result["segments"]
        except Exception as e:
            logger.warning(f"アライメント処理に失敗: {e}")
            segments = result["segments"]

        # 結果を構築
        transcription_segments = [
            TranscriptionSegment(
                start=seg["start"], end=seg["end"], text=seg["text"], words=seg.get("words"), chars=seg.get("chars")
            )
            for seg in segments
        ]

        processing_time = time.time() - start_time

        if progress_callback:
            progress_callback(1.0, "完了")

        return TranscriptionResult(
            language=self.config.transcription.language,
            segments=transcription_segments,
            original_audio_path=video_path,
            model_size=model_size,
            processing_time=processing_time,
        )

    def _transcribe_with_split(
        self, video_path: str | Path, model_size: str, duration: float, progress_callback: Callable | None = None
    ) -> TranscriptionResult:
        """分割して文字起こし"""
        start_time = time.time()

        if progress_callback:
            progress_callback(0.05, "無音部分を検出中...")

        # 無音検出
        silence_regions = self._detect_silence_regions(video_path)

        if progress_callback:
            progress_callback(0.1, "最適な分割点を計算中...")

        # 分割点を計算
        split_points = self._calculate_split_points(duration, silence_regions)
        logger.info(f"{len(split_points)}個のセグメントに分割します")

        # 分割して処理
        results = []
        total_segments = len(split_points)

        for i, (start, end) in enumerate(split_points):
            segment_duration = end - start
            logger.info(
                f"セグメント {i + 1}/{total_segments}: {start / 60:.1f}分 - {end / 60:.1f}分 ({segment_duration / 60:.1f}分)"
            )

            # プログレス計算
            base_progress = 0.1 + (0.85 * i / total_segments)
            segment_progress_weight = 0.85 / total_segments

            # セグメント用のプログレスコールバック
            def segment_callback(progress, status):
                if progress_callback:
                    total_progress = base_progress + (progress * segment_progress_weight)
                    progress_callback(total_progress, f"セグメント {i + 1}/{total_segments}: {status}")

            # セグメントを処理
            segment_result = self._process_segment(video_path, start, end, model_size, segment_callback)
            results.append((i, segment_result))

        if progress_callback:
            progress_callback(0.95, "結果を統合中...")

        # 結果を統合
        merged_result = self._merge_results(results, video_path, model_size)
        merged_result.processing_time = time.time() - start_time

        if progress_callback:
            progress_callback(1.0, "完了")

        return merged_result

    def _detect_silence_regions(self, video_path: str | Path) -> list[SilenceInfo]:
        """無音部分を検出"""
        # メモリ不足対策: 無音検出をスキップするオプション
        if os.environ.get("SKIP_SILENCE_DETECTION", "false").lower() == "true":
            logger.warning("無音検出をスキップします（メモリ節約モード）")
            return []

        # 一時WAVファイルを作成して無音検出
        temp_wav = Path(video_path).parent / f"temp_silence_{Path(video_path).stem}.wav"

        try:
            # 音声を抽出（圧縮して高速化）
            extract_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ar",
                "8000",  # サンプリングレートを下げて高速化
                "-ac",
                "1",  # モノラル
                "-acodec",
                "pcm_s16le",
                str(temp_wav),
            ]

            import subprocess

            subprocess.run(extract_cmd, capture_output=True, check=True)

            # 無音検出
            silences = self.video_processor.detect_silence_from_wav(
                str(temp_wav), noise_threshold=-40, min_silence_duration=2.0  # 少し厳しめの閾値  # 2秒以上の無音
            )

            return silences

        finally:
            # 一時ファイルを削除
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception as e:
                    logger.warning(f"一時ファイル削除失敗: {temp_wav} - {e}")

    def _calculate_split_points(
        self, total_duration: float, silence_regions: list[SilenceInfo]
    ) -> list[tuple[float, float]]:
        """最適な分割点を計算"""
        # 理想的な分割数
        n_splits = math.ceil(total_duration / self.TARGET_DURATION)
        ideal_duration = total_duration / n_splits

        # 18-22分の範囲で調整
        if ideal_duration < 18 * 60:
            n_splits = max(1, n_splits - 1)
            ideal_duration = total_duration / n_splits

        logger.info(f"理想的な分割: {n_splits}個 x {ideal_duration / 60:.1f}分")

        # 分割点を探す
        split_times = [0.0]

        for i in range(1, n_splits):
            target_time = ideal_duration * i

            # ±3分の範囲で最適な無音を探す
            best_silence = self._find_best_silence(silence_regions, target_time, search_window=3 * 60)

            if best_silence is not None:
                split_times.append(best_silence)
                logger.info(f"分割点 {i}: {best_silence / 60:.1f}分（目標: {target_time / 60:.1f}分）")
            else:
                # 無音が見つからない場合は目標時間で分割
                split_times.append(target_time)
                logger.warning(f"分割点 {i}: 無音が見つからないため {target_time / 60:.1f}分で分割")

        split_times.append(total_duration)

        # 分割点のペアを作成
        segments = []
        for i in range(len(split_times) - 1):
            segments.append((split_times[i], split_times[i + 1]))

        return segments

    def _find_best_silence(
        self, silence_regions: list[SilenceInfo], target_time: float, search_window: float
    ) -> float | None:
        """目標時間に最も近い無音の中心を探す"""
        start_search = target_time - search_window
        end_search = target_time + search_window

        best_silence = None
        best_distance = float("inf")

        for silence in silence_regions:
            # 無音の中心
            silence_center = (silence.start + silence.end) / 2

            # 検索範囲内かチェック
            if start_search <= silence_center <= end_search:
                distance = abs(silence_center - target_time)
                if distance < best_distance:
                    best_distance = distance
                    best_silence = silence_center

        return best_silence

    def _process_segment(
        self,
        video_path: str | Path,
        start: float,
        end: float,
        model_size: str,
        progress_callback: Callable | None = None,
    ) -> dict[str, Any]:
        """セグメントを処理"""
        # 音声セグメントを抽出
        segment_audio = self._extract_audio_segment(video_path, start, end)

        # Full VADで処理
        result = self._transcribe_segment_vad(segment_audio, model_size, progress_callback)

        # タイムスタンプを調整
        for segment in result["segments"]:
            segment["start"] += start
            segment["end"] += start
            if "words" in segment:
                for word in segment.get("words", []):
                    if "start" in word:
                        word["start"] += start
                    if "end" in word:
                        word["end"] += start

        return result

    def _extract_audio_segment(self, video_path: str | Path, start: float, end: float) -> np.ndarray:
        """音声セグメントを抽出"""
        import subprocess

        import soundfile as sf

        # 一時ファイル
        temp_wav = Path(video_path).parent / f"temp_segment_{start}_{end}.wav"

        try:
            # FFmpegで抽出
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-i",
                str(video_path),
                "-to",
                str(end - start),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-acodec",
                "pcm_s16le",
                str(temp_wav),
            ]

            subprocess.run(cmd, capture_output=True, check=True)

            # 音声データを読み込み（float32で返す）
            audio, _ = sf.read(str(temp_wav))
            return audio.astype(np.float32)  # dtype mismatch エラーを防ぐため

        finally:
            if temp_wav.exists():
                try:
                    temp_wav.unlink()
                except Exception as e:
                    logger.warning(f"一時ファイル削除失敗: {temp_wav} - {e}")

    def _transcribe_segment_vad(
        self, audio: np.ndarray, model_size: str, progress_callback: Callable | None = None
    ) -> dict[str, Any]:
        """セグメントをVADで処理"""
        # モデルを読み込み
        model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=self.config.transcription.language,
        )

        # VADを有効にして文字起こし
        result = model.transcribe(
            audio, batch_size=self._get_optimal_batch_size(), language=self.config.transcription.language, chunk_size=30
        )

        # アライメント処理
        try:
            align_model, metadata = whisperx.load_align_model(
                language_code=self.config.transcription.language, device=self.device
            )

            aligned_result = whisperx.align(
                result["segments"], align_model, metadata, audio, self.device, return_char_alignments=True
            )

            return aligned_result
        except Exception as e:
            logger.warning(f"セグメントのアライメント処理に失敗: {e}")
            return result

    def _merge_results(
        self, results: list[tuple[int, dict[str, Any]]], video_path: str | Path, model_size: str
    ) -> TranscriptionResult:
        """結果を統合"""
        # インデックス順にソート
        results.sort(key=lambda x: x[0])

        # 全セグメントを結合
        all_segments = []
        for _, result in results:
            all_segments.extend(result["segments"])

        # TranscriptionSegmentに変換
        transcription_segments = [
            TranscriptionSegment(
                start=seg["start"], end=seg["end"], text=seg["text"], words=seg.get("words"), chars=seg.get("chars")
            )
            for seg in all_segments
        ]

        return TranscriptionResult(
            language=self.config.transcription.language,
            segments=transcription_segments,
            original_audio_path=video_path,
            model_size=f"{model_size}_smart",
            processing_time=0.0,  # 後で設定される
        )

    def _get_optimal_batch_size(self) -> int:
        """最適なバッチサイズを取得"""
        # デフォルトバッチサイズ定数
        DEFAULT_BATCH_SIZE_CPU = 4

        # 利用可能メモリを取得
        available_memory_gb = psutil.virtual_memory().available / (1024**3)

        if self.device == "cuda":
            # GPU使用時
            if available_memory_gb >= 16:
                return 32
            elif available_memory_gb >= 8:
                return 16
            else:
                return 8
        else:
            # CPU使用時
            return DEFAULT_BATCH_SIZE_CPU

    def _transcribe_api_optimized(
        self,
        video_path: str | Path,
        model_size: str | None = None,
        progress_callback: Callable | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False,
    ) -> TranscriptionResult:
        """APIモード用の最適化された文字起こし"""
        # 動画情報を取得
        video_info = VideoInfo.from_file(video_path)
        duration = video_info.duration

        logger.info(f"APIモード最適化：動画時間 {duration / 60:.1f}分")

        # 25分以下の場合は通常のAPI処理
        if duration <= self.MIN_SPLIT_DURATION:
            logger.info("25分以下なのでアライメント分割なしで処理")
            # 最適なチャンクサイズを設定（5分）
            # Note: chunk_seconds is now managed by AutoOptimizer in API transcriber
            result = self.api_transcriber.transcribe(
                video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment
            )
            return result

        # 25分以上の場合は20分ごとに分割してアライメント処理
        logger.info("25分以上なので20分ごとに分割してアライメント処理")
        return self._transcribe_api_with_split_alignment(
            video_path, model_size, duration, progress_callback, skip_alignment
        )

    def _transcribe_api_with_split_alignment(
        self,
        video_path: str | Path,
        model_size: str,
        duration: float,
        progress_callback: Callable | None = None,
        skip_alignment: bool = False,
    ) -> TranscriptionResult:
        """APIモードで20分ごとに分割してアライメント処理"""
        start_time = time.time()

        # まず5分チャンクでAPI処理（アライメントなし）
        original_use_alignment = getattr(self.api_transcriber, "skip_alignment", False)

        try:
            # 一時的にアライメントをスキップ
            self.api_transcriber.skip_alignment = True

            if progress_callback:
                progress_callback(0.1, "APIで文字起こし中（5分チャンク）...")

            # API処理（アライメントなしで高速）
            api_result = self.api_transcriber.transcribe(video_path, model_size, None, True, True, True)

            if progress_callback:
                progress_callback(0.5, "文字起こし完了、アライメント処理を準備中...")

            # 音声を読み込み
            try:
                import whisperx

                audio = whisperx.load_audio(video_path)
                audio = audio.astype(np.float32)
            except ImportError:
                logger.warning("WhisperXが利用できないため、アライメント処理をスキップします")
                return api_result

            # 20分ごとに分割してアライメント処理
            segments = self._perform_split_alignment(audio, api_result.segments, duration, progress_callback)

            # 結果を更新
            api_result.segments = segments
            api_result.processing_time = time.time() - start_time
            api_result.model_size = f"{model_size}_api_smart"

            return api_result

        finally:
            # 設定を元に戻す
            if hasattr(self.api_transcriber, "skip_alignment"):
                self.api_transcriber.skip_alignment = original_use_alignment

    def _perform_split_alignment(
        self,
        audio: np.ndarray,
        segments: list[TranscriptionSegment],
        duration: float,
        progress_callback: Callable | None = None,
    ) -> list[TranscriptionSegment]:
        """20分ごとに分割してアライメント処理"""
        try:
            import whisperx

            # 分割数を計算
            n_splits = math.ceil(duration / self.TARGET_DURATION)
            aligned_segments = []

            for i in range(n_splits):
                start_time = i * self.TARGET_DURATION
                end_time = min((i + 1) * self.TARGET_DURATION, duration)

                if progress_callback:
                    base_progress = 0.5 + (0.45 * i / n_splits)
                    progress_callback(base_progress, f"アライメント処理 {i + 1}/{n_splits}")

                # この時間範囲のセグメントを抽出
                chunk_segments = [seg for seg in segments if start_time <= seg.start < end_time]

                if not chunk_segments:
                    continue

                # 音声の該当部分を抽出
                sample_rate = 16000
                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)
                chunk_audio = audio[start_sample:end_sample]

                # アライメントモデルを読み込み
                align_model, metadata = whisperx.load_align_model(
                    language_code=self.config.transcription.language, device=self.device
                )

                # WhisperX形式に変換（時間を調整）
                whisperx_segments = []
                for seg in chunk_segments:
                    whisperx_segments.append(
                        {"start": seg.start - start_time, "end": seg.end - start_time, "text": seg.text}
                    )

                # アライメント実行
                aligned_result = whisperx.align(
                    whisperx_segments, align_model, metadata, chunk_audio, self.device, return_char_alignments=True
                )

                # 結果を元の時間に戻してTranscriptionSegmentに変換
                for seg in aligned_result["segments"]:
                    segment = TranscriptionSegment(
                        start=seg["start"] + start_time,
                        end=seg["end"] + start_time,
                        text=seg["text"],
                        words=seg.get("words"),
                        chars=seg.get("chars"),
                    )
                    # wordsの時間も調整
                    if segment.words:
                        for word in segment.words:
                            if "start" in word:
                                word["start"] += start_time
                            if "end" in word:
                                word["end"] += start_time
                    aligned_segments.append(segment)

            if progress_callback:
                progress_callback(0.95, "アライメント処理完了")

            return aligned_segments

        except Exception as e:
            logger.warning(f"分割アライメント処理に失敗: {e}")
            # 失敗した場合は元のセグメントを返す
            return segments
