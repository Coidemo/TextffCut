"""
波形データ処理モジュール
音声波形の抽出、リサンプリング、正規化を行う
"""

import hashlib
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
class WaveformData:
    """波形データクラス"""

    segment_id: str
    sample_rate: int
    samples: list[float]  # 正規化された振幅値 (-1.0 ~ 1.0)
    duration: float
    start_time: float
    end_time: float


class WaveformProcessor:
    """波形処理クラス"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.target_samples = 1600  # 最大サンプル数（表示用）
        self.cache_dir = Path(".cache/waveforms")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_cache_key(self, video_path: str, segment_id: str) -> str:
        """キャッシュキーの生成"""
        video_hash = hashlib.md5(video_path.encode()).hexdigest()
        return f"waveform_{video_hash}_{segment_id}"

    def extract_waveform(self, video_path: str, start_time: float, end_time: float, segment_id: str) -> WaveformData:
        """
        動画から波形データを抽出

        Args:
            video_path: 動画ファイルパス
            start_time: 開始時間（秒）
            end_time: 終了時間（秒）
            segment_id: セグメントID

        Returns:
            波形データ
        """
        if not LIBROSA_AVAILABLE:
            logger.warning("librosa is not available. Returning empty waveform data.")
            return WaveformData(
                segment_id=segment_id,
                sample_rate=44100,
                samples=[],
                duration=end_time - start_time,
                start_time=start_time,
                end_time=end_time,
            )

        try:
            logger.info(f"Extracting waveform for segment {segment_id}: {start_time:.2f}s - {end_time:.2f}s")

            # 音声データの読み込み（指定範囲のみ）
            duration = end_time - start_time
            y, sr = librosa.load(
                video_path, sr=None, offset=start_time, duration=duration, mono=True  # 元のサンプリングレートを維持
            )

            # リサンプリング（表示用に間引き）
            samples_per_pixel = len(y) / self.target_samples
            if samples_per_pixel > 1:
                # ダウンサンプリング
                resampled = self._downsample_waveform(y, self.target_samples)
            else:
                resampled = y

            # 正規化（-1.0 ~ 1.0）
            if len(resampled) > 0:
                max_amplitude = np.max(np.abs(resampled))
                if max_amplitude > 0:
                    normalized = resampled / max_amplitude
                else:
                    normalized = resampled
            else:
                normalized = np.array([])

            # リストに変換
            samples_list = normalized.tolist()

            waveform_data = WaveformData(
                segment_id=segment_id,
                sample_rate=sr,
                samples=samples_list,
                duration=duration,
                start_time=start_time,
                end_time=end_time,
            )

            logger.info(f"Waveform extracted: {len(samples_list)} samples")
            return waveform_data

        except Exception as e:
            logger.error(f"Failed to extract waveform: {e}")
            # エラー時は空の波形データを返す
            return WaveformData(
                segment_id=segment_id,
                sample_rate=44100,
                samples=[],
                duration=end_time - start_time,
                start_time=start_time,
                end_time=end_time,
            )

    def _downsample_waveform(self, waveform: np.ndarray, target_samples: int) -> np.ndarray:
        """
        波形データをダウンサンプリング

        Args:
            waveform: 元の波形データ
            target_samples: 目標サンプル数

        Returns:
            ダウンサンプリングされた波形
        """
        # ブロックサイズを計算
        block_size = len(waveform) // target_samples

        # 各ブロックの最大振幅を取得（ピークを保持）
        downsampled = []
        for i in range(target_samples):
            start_idx = i * block_size
            end_idx = min((i + 1) * block_size, len(waveform))

            if start_idx < len(waveform):
                block = waveform[start_idx:end_idx]
                if len(block) > 0:
                    # ブロック内の最大絶対値を使用（ピーク保持）
                    max_idx = np.argmax(np.abs(block))
                    downsampled.append(block[max_idx])

        return np.array(downsampled)

    def get_silence_threshold(self) -> float:
        """無音判定の閾値を取得（dB）"""
        return -35.0  # デフォルト値

    def detect_silence_regions(self, waveform_data: WaveformData) -> list[tuple[int, int]]:
        """
        波形データから無音領域を検出

        Args:
            waveform_data: 波形データ

        Returns:
            無音領域のインデックスリスト [(start_idx, end_idx), ...]
        """
        if not waveform_data.samples:
            return []

        samples = np.array(waveform_data.samples)

        # 振幅をdBに変換（小さい値はクリップ）
        epsilon = 1e-10
        amplitude_db = 20 * np.log10(np.abs(samples) + epsilon)

        # 無音判定
        threshold_db = self.get_silence_threshold()
        is_silence = amplitude_db < threshold_db

        # 無音領域を検出
        silence_regions = []
        in_silence = False
        start_idx = 0

        for i, silent in enumerate(is_silence):
            if silent and not in_silence:
                # 無音開始
                in_silence = True
                start_idx = i
            elif not silent and in_silence:
                # 無音終了
                in_silence = False
                silence_regions.append((start_idx, i))

        # 最後まで無音の場合
        if in_silence:
            silence_regions.append((start_idx, len(samples)))

        return silence_regions
