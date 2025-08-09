"""
音声最適化ゲートウェイアダプター
"""

from pathlib import Path
from typing import Dict, Any, Tuple

import numpy as np

from application.interfaces.audio_optimizer_gateway import IAudioOptimizerGateway
from core.audio_optimizer import IntelligentAudioOptimizer
from domain.value_objects import FilePath


class AudioOptimizerGatewayAdapter(IAudioOptimizerGateway):
    """音声最適化ゲートウェイの実装"""
    
    def __init__(self):
        self._optimizer = IntelligentAudioOptimizer()
    
    def prepare_audio(
        self, 
        video_path: FilePath
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """音声を準備し、最適化の詳細情報を返す（常に最適化を実行）"""
        # FilePath を Path に変換
        path = Path(str(video_path))
        
        # 最適化実行（常に実行）
        audio, stats = self._optimizer.prepare_audio(path)
        
        return audio, stats
    
    def prepare_audio_for_api(
        self, 
        video_path: FilePath, 
        target_bitrate: str = "32k"
    ) -> FilePath:
        """API送信用に音声を圧縮"""
        # FilePath を Path に変換
        path = Path(str(video_path))
        
        # 圧縮実行
        compressed_path = self._optimizer.prepare_audio_for_api(
            path,
            target_bitrate
        )
        
        # FilePath に変換して返す
        return FilePath(str(compressed_path))
    
    def get_optimization_summary(self) -> Dict[str, Any]:
        """最適化の統計サマリーを取得"""
        return self._optimizer.get_optimization_summary()