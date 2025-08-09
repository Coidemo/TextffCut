"""
最適化された文字起こしゲートウェイの実装

音声最適化とエラー回復機能を統合した文字起こしゲートウェイ
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

import psutil
import torch

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
        start_time = datetime.now()
        
        for attempt in range(self.max_retries):
            try:
                # 現在の設定を取得
                current_config = self._get_current_config()
                
                logger.info(f"""
                文字起こし試行 {attempt + 1}/{self.max_retries}
                設定: batch_size={current_config['batch_size']}, 
                      compute_type={current_config['compute_type']}
                """)
                
                if progress_callback:
                    progress_callback(0.0)
                
                # 音声最適化（常に実行）
                audio_path = video_path
                if not self.config.transcription.use_api:
                    # ローカルモードの場合のみ音声最適化を実施
                    audio_data, optimization_info = self.audio_optimizer.prepare_audio(
                        video_path
                    )
                    
                    if optimization_info.get('optimized', False):
                        message = f"音声最適化: {optimization_info.get('reduction_percent', 0):.0f}%削減"
                    else:
                        message = f"音声最適化スキップ: {optimization_info.get('reason', '')}"
                    
                    logger.info(message)
                    if progress_callback:
                        progress_callback(0.1)
                
                # 既存のtranscribeメソッドを実行
                # バッチサイズとcompute_typeを一時的に設定
                original_batch_size = getattr(self._legacy_transcriber, 'DEFAULT_BATCH_SIZE', 8)
                original_compute_type = self.config.transcription.compute_type
                
                try:
                    # 設定を適用
                    self._legacy_transcriber.DEFAULT_BATCH_SIZE = current_config['batch_size']
                    self.config.transcription.compute_type = current_config['compute_type']
                    
                    # 基底クラスのtranscribeを実行
                    result = super().transcribe(
                        video_path=video_path,
                        model_size=model_size,
                        language=language,
                        use_cache=use_cache,
                        progress_callback=lambda p, s="": progress_callback(0.1 + p * 0.9) if progress_callback else None
                    )
                    
                finally:
                    # 設定を元に戻す
                    self._legacy_transcriber.DEFAULT_BATCH_SIZE = original_batch_size
                    self.config.transcription.compute_type = original_compute_type
                
                # 成功を記録
                processing_time = (datetime.now() - start_time).total_seconds()
                metrics = PerformanceMetrics(
                    timestamp=datetime.now(),
                    success=True,
                    processing_time=processing_time,
                    optimization_info=optimization_info if 'optimization_info' in locals() else None
                )
                self.profile.add_metrics(metrics)
                self.profile_repository.save(self.profile)
                
                logger.info(f"文字起こし成功: {processing_time:.1f}秒")
                
                return result
                
            except torch.cuda.OutOfMemoryError as e:
                # GPUメモリエラー
                self._handle_memory_error(e, "GPU", attempt)
                
            except MemoryError as e:
                # システムメモリエラー
                self._handle_memory_error(e, "System", attempt)
                
            except Exception as e:
                # その他のエラー
                self._handle_general_error(e, attempt)
        
        # すべての試行が失敗
        raise RuntimeError(
            f"文字起こしがすべての試行で失敗しました。"
            f"最後のエラー: {self.profile.metrics_history[-1].error_message if self.profile.metrics_history else 'Unknown'}"
        )
    
    def _get_current_config(self) -> dict:
        """現在の処理設定を取得"""
        available_memory = psutil.virtual_memory().available / (1024**3)
        
        config = {
            'batch_size': self.profile.get_effective_batch_size(),
            'compute_type': self.profile.get_effective_compute_type(),
            # optimization_preferenceは削除
        }
        
        # メモリ制約時の自動調整
        if available_memory < 4 and config['batch_size'] > 2:
            config['batch_size'] = 2
            logger.warning(f"メモリ不足のためバッチサイズを調整: {config['batch_size']}")
        
        return config
    
    def _handle_memory_error(self, error: Exception, memory_type: str, attempt: int):
        """メモリエラーのハンドリング"""
        error_message = f"{memory_type}メモリ不足: {str(error)}"
        logger.warning(error_message)
        
        # エラーを記録
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            success=False,
            processing_time=0,
            error_message=error_message
        )
        self.profile.add_metrics(metrics)
        
        # 設定を調整
        if self.profile.batch_size and self.profile.batch_size > 1:
            self.profile.batch_size = max(1, self.profile.batch_size // 2)
        else:
            self.profile.batch_size = 1
        
        self.profile.compute_type = 'int8'
        
        # optimization_preferenceは削除（常に最適化を実行）
        
        self.profile_repository.save(self.profile)
        
        # GPUメモリをクリア
        if memory_type == "GPU" and torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # 最後の試行でなければ待機
        if attempt < self.max_retries - 1:
            time.sleep(2)
        else:
            raise
    
    def _handle_general_error(self, error: Exception, attempt: int):
        """一般的なエラーのハンドリング"""
        error_message = f"エラー: {type(error).__name__} - {str(error)}"
        logger.error(error_message)
        
        # エラーを記録
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            success=False,
            processing_time=0,
            error_message=error_message
        )
        self.profile.add_metrics(metrics)
        self.profile_repository.save(self.profile)
        
        # 最後の試行でなければ再試行
        if attempt < self.max_retries - 1:
            time.sleep(1)
        else:
            raise
    
    def get_performance_profile(self) -> PerformanceProfile:
        """現在のパフォーマンスプロファイルを取得"""
        return self.profile
    
    def update_performance_profile(self, profile: PerformanceProfile):
        """パフォーマンスプロファイルを更新"""
        self.profile = profile
        self.profile_repository.save(profile)