"""
最適化された文字起こしゲートウェイの実装

音声最適化とエラー回復機能を統合した文字起こしゲートウェイ
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

import psutil

try:
    import torch
except ImportError:
    torch = None  # MLXモードではtorch不要

from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from application.interfaces.audio_optimizer_gateway import IAudioOptimizerGateway
from config import Config
from domain.entities.performance_profile import PerformanceProfile, PerformanceMetrics
from domain.repositories.performance_profile_repository import IPerformanceProfileRepository
from domain.value_objects import FilePath
from domain.entities import TranscriptionResult
from use_cases.interfaces import ITranscriptionGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class OptimizedTranscriptionGatewayAdapter(TranscriptionGatewayAdapter):
    """
    最適化された文字起こしゲートウェイ
    
    音声最適化、エラー回復、パフォーマンスプロファイルを統合
    """
    
    def __init__(
        self,
        config: Config,
        audio_optimizer: IAudioOptimizerGateway,
        profile_repository: IPerformanceProfileRepository
    ):
        super().__init__(config)
        self.audio_optimizer = audio_optimizer
        self.profile_repository = profile_repository
        self.profile = self._load_or_create_profile()
        self.max_retries = 3
        
    
    def _load_or_create_profile(self) -> PerformanceProfile:
        """プロファイルを読み込みまたは作成"""
        profile = self.profile_repository.load()
        if profile is None:
            profile = self.profile_repository.get_default()
            self.profile_repository.save(profile)
        return profile
    
    def transcribe(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        language: str | None = None,
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """
        動画ファイルを文字起こし（適応的最適化付き）
        """
        # MLXモードの場合、VAD/legacyをバイパスしてTranscriberに委譲
        from utils.environment import MLX_AVAILABLE
        if MLX_AVAILABLE and getattr(self.config.transcription, 'use_mlx_whisper', False):
            logger.info("MLXモードで文字起こし（OptimizedGatewayからTranscriberに委譲）")
            return self._transcribe_mlx(
                video_path=video_path,
                model_size=model_size,
                use_cache=use_cache,
                progress_callback=progress_callback,
            )

        # MLXモードが必須（Apple Silicon専用）
        raise NotImplementedError(
            "MLXモードのみサポートしています（Apple Silicon必須）。"
            "config.transcription.use_mlx_whisper = True を設定してください。"
        )

    def _transcribe_mlx(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """MLXモードの文字起こし（既存の_legacy_transcriberに委譲）"""
        # 親クラスで初期化済みの_legacy_transcriberを再利用（#4, #6修正）
        transcriber = self._legacy_transcriber

        # #2修正: progress_callbackの型を安全にラップ
        # Gatewayのシグネチャは Callable[[float], None] だが、
        # CoreTranscriberは Callable[[float, str], None] を期待する
        def safe_callback(progress: float, status: str = "") -> None:
            if progress_callback:
                try:
                    progress_callback(progress, status)
                except TypeError:
                    # 1引数のcallbackが渡された場合のフォールバック
                    progress_callback(progress)

        core_result = transcriber.transcribe(
            video_path=str(video_path),
            model_size=model_size,
            progress_callback=safe_callback,
            use_cache=use_cache,
        )

        # core.transcription.TranscriptionResult → domain.entities.TranscriptionResult に変換
        import uuid
        from domain.entities.transcription import TranscriptionResult as DomainResult
        from domain.entities.transcription import TranscriptionSegment as DomainSegment

        # #1修正: duration は動画の長さ（最後のセグメントの終了時間）を使う
        duration = 0.0
        domain_segments = []
        for seg in core_result.segments:
            domain_segments.append(DomainSegment(
                id=str(uuid.uuid4()),
                start=seg.start,
                end=seg.end,
                text=seg.text,
                words=seg.words,
                chars=seg.chars,
            ))
            if seg.end > duration:
                duration = seg.end

        return DomainResult(
            id=str(uuid.uuid4()),
            video_id=str(video_path),
            language=core_result.language,
            segments=domain_segments,
            duration=duration,
            original_audio_path=str(video_path),
            model_size=core_result.model_size,
            processing_time=core_result.processing_time,
        )

    def get_performance_profile(self) -> PerformanceProfile:
        """現在のパフォーマンスプロファイルを取得"""
        return self.profile
    
    def update_performance_profile(self, profile: PerformanceProfile):
        """パフォーマンスプロファイルを更新"""
        self.profile = profile
        self.profile_repository.save(profile)

    def __del__(self):
        """デストラクタ"""
        pass
