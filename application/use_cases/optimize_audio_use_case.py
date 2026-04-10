"""
音声最適化のユースケース
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

import numpy as np

from application.interfaces.audio_optimizer_gateway import IAudioOptimizerGateway
from application.use_cases.base import UseCase, UseCaseRequest, UseCaseResponse
from domain.entities.performance_profile import PerformanceProfile, PerformanceMetrics
from domain.repositories.performance_profile_repository import IPerformanceProfileRepository
from domain.value_objects import FilePath
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class OptimizeAudioRequest(UseCaseRequest):
    """音声最適化リクエスト"""

    video_path: FilePath
    profile: PerformanceProfile


@dataclass
class OptimizeAudioResponse(UseCaseResponse):
    """音声最適化レスポンス"""

    audio_data: Optional[np.ndarray] = None
    optimization_info: Optional[Dict[str, Any]] = None


class OptimizeAudioUseCase(UseCase[OptimizeAudioRequest, OptimizeAudioResponse]):
    """音声最適化ユースケース"""

    def __init__(
        self, audio_optimizer_gateway: IAudioOptimizerGateway, profile_repository: IPerformanceProfileRepository
    ):
        self.audio_optimizer_gateway = audio_optimizer_gateway
        self.profile_repository = profile_repository

    def execute(self, request: OptimizeAudioRequest) -> OptimizeAudioResponse:
        """音声最適化を実行"""
        start_time = datetime.now()

        try:
            # 音声を最適化（常に実行）
            audio_data, optimization_info = self.audio_optimizer_gateway.prepare_audio(request.video_path)

            # 成功メトリクスを記録
            processing_time = (datetime.now() - start_time).total_seconds()
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                success=True,
                processing_time=processing_time,
                optimization_info=optimization_info,
            )
            request.profile.add_metrics(metrics)

            # プロファイルを保存
            self.profile_repository.save(request.profile)

            logger.info(f"音声最適化成功: {optimization_info}")

            return OptimizeAudioResponse(success=True, audio_data=audio_data, optimization_info=optimization_info)

        except Exception as e:
            # エラーメトリクスを記録
            processing_time = (datetime.now() - start_time).total_seconds()
            metrics = PerformanceMetrics(
                timestamp=datetime.now(), success=False, processing_time=processing_time, error_message=str(e)
            )
            request.profile.add_metrics(metrics)

            # プロファイルを保存
            self.profile_repository.save(request.profile)

            logger.error(f"音声最適化失敗: {e}")

            return OptimizeAudioResponse(success=False, error_message=f"音声最適化に失敗しました: {str(e)}")
