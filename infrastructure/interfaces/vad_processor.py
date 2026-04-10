"""
VAD (Voice Activity Detection) プロセッサーのインターフェース

音声区間検出のための抽象インターフェース
"""

from abc import ABC, abstractmethod
from typing import List, Tuple


class IVADProcessor(ABC):
    """VADプロセッサーのインターフェース"""

    @abstractmethod
    def detect_segments(
        self,
        audio_path: str,
        max_segment_duration: float = 30.0,
        min_segment_duration: float = 5.0,
        silence_threshold: float = -35.0,
        min_silence_duration: float = 0.3,
    ) -> List[Tuple[float, float]]:
        """
        音声ファイルから音声区間を検出し、適切なセグメントに分割

        Args:
            audio_path: 音声ファイルのパス
            max_segment_duration: 最大セグメント長（秒）
            min_segment_duration: 最小セグメント長（秒）
            silence_threshold: 無音閾値（dB）
            min_silence_duration: 最小無音長（秒）

        Returns:
            (開始時間, 終了時間)のタプルのリスト
        """
        pass

    @abstractmethod
    def get_audio_duration(self, audio_path: str) -> float:
        """
        音声ファイルの総時間を取得

        Args:
            audio_path: 音声ファイルのパス

        Returns:
            総時間（秒）
        """
        pass
