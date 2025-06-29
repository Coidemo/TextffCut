"""
波形データ処理モジュール
音声波形の抽出、リサンプリング、正規化を行う
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)

# librosaの動的インポート
try:
    import librosa

    LIBROSA_AVAILABLE = True
except ImportError:
    logger.warning("librosa is not installed. Waveform extraction will be disabled.")
    LIBROSA_AVAILABLE = False


@dataclass
class ClipWaveformData:
    """クリップ単位の波形データクラス"""

    id: str
    start_time: float
    end_time: float
    sample_rate: int
    samples: list[float]  # 正規化された振幅値 (-1.0 ~ 1.0)


class WaveformProcessor:
    """波形処理クラス"""

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.cache_dir = Path(".cache/waveforms")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _downsample_waveform(self, waveform: np.ndarray, target_samples: int) -> np.ndarray:
        """波形データをダウンサンプリング（ピーク保持）"""
        if len(waveform) == 0 or target_samples <= 0:
            return np.array([])
        if len(waveform) <= target_samples:
            return waveform

        block_size = len(waveform) // target_samples
        downsampled = np.zeros(target_samples)
        for i in range(target_samples):
            block = waveform[i * block_size : (i + 1) * block_size]
            if len(block) > 0:
                downsampled[i] = block[np.argmax(np.abs(block))]
        return downsampled

    def extract_waveforms_for_clips(
        self, video_path: str | Path, time_ranges: list[tuple[float, float]], samples_per_clip: int = 500
    ) -> list[ClipWaveformData] | None:
        """
        指定された複数の時間範囲（クリップ）の波形データを一括で抽出する。

        Args:
            video_path: 動画ファイルパス
            time_ranges: 抽出する時間範囲のリスト [(start1, end1), (start2, end2), ...]
            samples_per_clip: 各クリップの波形のサンプル数

        Returns:
            クリップごとの波形データリスト、またはエラー時にNone
        """
        if not LIBROSA_AVAILABLE:
            logger.warning("librosa is not available. Cannot extract waveforms.")
            return None

        try:
            logger.info(f"Loading full audio for {video_path} to extract {len(time_ranges)} clips.")
            # 動画全体の音声を一度だけ読み込む
            full_audio, sr = librosa.load(video_path, sr=None, mono=True)
            logger.info(f"Full audio loaded. Sample rate: {sr}, Duration: {len(full_audio) / sr:.2f}s")

            results = []
            for i, (start_time, end_time) in enumerate(time_ranges):
                clip_id = f"clip-{i}"

                # 全体音声からクリップ部分を切り出し
                start_sample = int(start_time * sr)
                end_sample = int(end_time * sr)
                clip_audio = full_audio[start_sample:end_sample]

                # ダウンサンプリング
                resampled_audio = self._downsample_waveform(clip_audio, samples_per_clip)

                # 正規化 (-1.0 ~ 1.0)
                if len(resampled_audio) > 0:
                    max_amp = np.max(np.abs(resampled_audio))
                    normalized_audio = resampled_audio / max_amp if max_amp > 0 else resampled_audio
                else:
                    normalized_audio = np.array([])

                clip_data = ClipWaveformData(
                    id=clip_id,
                    start_time=start_time,
                    end_time=end_time,
                    sample_rate=int(sr),
                    samples=normalized_audio.tolist(),
                )
                results.append(clip_data)

            logger.info(f"Successfully extracted waveforms for {len(results)} clips.")
            return results

        except Exception as e:
            logger.error(f"Failed to extract waveforms for clips from {video_path}: {e}", exc_info=True)
            return None
