"""
音声最適化のゲートウェイインターフェース
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np

from domain.value_objects import FilePath


class IAudioOptimizerGateway(ABC):
    """音声最適化のゲートウェイインターフェース"""

    @abstractmethod
    def prepare_audio(self, video_path: FilePath) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        音声を準備し、最適化の詳細情報を返す（常に最適化を実行）

        Args:
            video_path: 動画ファイルパス

        Returns:
            (音声データ, 最適化情報)
        """
        pass

    @abstractmethod
    def prepare_audio_for_api(self, video_path: FilePath, target_bitrate: str = "32k") -> FilePath:
        """
        API送信用に音声を圧縮

        Args:
            video_path: 動画ファイルパス
            target_bitrate: 目標ビットレート

        Returns:
            圧縮された音声ファイルパス
        """
        pass

    @abstractmethod
    def get_optimization_summary(self) -> Dict[str, Any]:
        """最適化の統計サマリーを取得"""
        pass
