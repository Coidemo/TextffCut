"""
最適化された文字起こしの統合テスト
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import numpy as np
import tempfile

from config import Config
from domain.value_objects import FilePath
from domain.entities import TranscriptionResult
from adapters.gateways.transcription.optimized_transcription_gateway import OptimizedTranscriptionGatewayAdapter
from infrastructure.gateways.audio_optimizer_gateway_adapter import AudioOptimizerGatewayAdapter
from infrastructure.repositories.performance_profile_repository import FilePerformanceProfileRepository


class TestOptimizedTranscriptionIntegration:
    """最適化された文字起こしの統合テスト"""
    
    @pytest.fixture
    def temp_dir(self):
        """一時ディレクトリ"""
        with tempfile.TemporaryDirectory() as td:
            yield Path(td)
    
    @pytest.fixture
    def config(self):
        """テスト用設定"""
        config = Config()
        config.transcription.use_api = False
        config.transcription.model_size = "base"
        config.transcription.compute_type = "int8"
        return config
    
    @pytest.fixture
    def audio_optimizer(self):
        """音声最適化ゲートウェイ"""
        return AudioOptimizerGatewayAdapter()
    
    @pytest.fixture
    def profile_repository(self, temp_dir):
        """パフォーマンスプロファイルリポジトリ"""
        return FilePerformanceProfileRepository(base_dir=temp_dir)
    
    @pytest.fixture
    def gateway(self, config, audio_optimizer, profile_repository):
        """最適化された文字起こしゲートウェイ"""
        return OptimizedTranscriptionGatewayAdapter(
            config=config,
            audio_optimizer=audio_optimizer,
            profile_repository=profile_repository
        )
    
    def test_transcribe_with_auto_optimization(self, gateway, temp_dir):
        """自動最適化での文字起こしテスト"""
        # テスト用動画ファイル
        video_path = temp_dir / "test_video.mp4"
        video_path.touch()
        
        # モック設定
        with patch('psutil.virtual_memory') as mock_memory:
            # 低メモリ環境をシミュレート
            mock_memory.return_value = Mock(available=3 * 1024**3)
            
            # 音声最適化のモック
            with patch.object(gateway.audio_optimizer, 'prepare_audio') as mock_prepare:
                mock_prepare.return_value = (
                    np.zeros((16000 * 60,), dtype=np.float32),  # 最適化された音声
                    {'optimized': True, 'reduction_percent': 66.7}
                )
                
                # 基底クラスのtranscribeメソッドをモック
                with patch.object(gateway.__class__.__bases__[0], 'transcribe') as mock_transcribe:
                    # モック結果
                    mock_result = TranscriptionResult(
                        video_id="test_video",
                        segments=[],
                        language="ja",
                        processing_time=10.0
                    )
                    mock_transcribe.return_value = mock_result
                    
                    # 実行
                    result = gateway.transcribe(
                        video_path=FilePath(str(video_path)),
                        model_size="base",
                        language="ja"
                    )
                    
                    # 検証
                    assert result == mock_result
                    mock_prepare.assert_called_once_with(video_path, "auto")
                    mock_transcribe.assert_called_once()
    
    def test_transcribe_with_memory_error_retry(self, gateway, temp_dir):
        """メモリエラー時のリトライテスト"""
        video_path = temp_dir / "test_video.mp4"
        video_path.touch()
        
        # プロファイルの初期設定
        gateway.profile.batch_size = 8
        gateway.profile.optimization_preference = "never"
        
        call_count = 0
        
        def mock_transcribe_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                # 初回はメモリエラー
                raise MemoryError("Out of memory")
            else:
                # 2回目は成功
                return TranscriptionResult(
                    video_id="test_video",
                    segments=[],
                    language="ja",
                    processing_time=15.0
                )
        
        with patch.object(gateway.__class__.__bases__[0], 'transcribe', side_effect=mock_transcribe_side_effect):
            with patch.object(gateway.audio_optimizer, 'prepare_audio') as mock_prepare:
                mock_prepare.return_value = (
                    np.zeros((16000 * 60,), dtype=np.float32),
                    {'optimized': True}
                )
                
                # 実行
                result = gateway.transcribe(
                    video_path=FilePath(str(video_path)),
                    model_size="base"
                )
                
                # 検証
                assert result is not None
                assert call_count == 2  # 2回試行
                assert gateway.profile.batch_size == 4  # バッチサイズが半減
                assert gateway.profile.optimization_preference == "memory_critical"  # メモリ優先モードに
    
    def test_profile_persistence(self, gateway, temp_dir):
        """プロファイルの永続化テスト"""
        # 初期プロファイルを変更
        gateway.profile.optimization_preference = "always"
        gateway.profile.batch_size = 4
        gateway.profile_repository.save(gateway.profile)
        
        # 新しいゲートウェイインスタンスを作成
        new_gateway = OptimizedTranscriptionGatewayAdapter(
            config=gateway.config,
            audio_optimizer=gateway.audio_optimizer,
            profile_repository=gateway.profile_repository
        )
        
        # 設定が保持されていることを確認
        assert new_gateway.profile.optimization_preference == "always"
        assert new_gateway.profile.batch_size == 4
    
    def test_performance_tracking(self, gateway, temp_dir):
        """パフォーマンストラッキングのテスト"""
        video_path = temp_dir / "test_video.mp4"
        video_path.touch()
        
        with patch.object(gateway.__class__.__bases__[0], 'transcribe') as mock_transcribe:
            mock_transcribe.return_value = TranscriptionResult(
                video_id="test_video",
                segments=[],
                language="ja",
                processing_time=5.0
            )
            
            with patch.object(gateway.audio_optimizer, 'prepare_audio') as mock_prepare:
                mock_prepare.return_value = (
                    np.zeros((16000 * 60,), dtype=np.float32),
                    {'optimized': True, 'reduction_percent': 50.0}
                )
                
                # 実行
                result = gateway.transcribe(
                    video_path=FilePath(str(video_path)),
                    model_size="base"
                )
                
                # メトリクスが記録されていることを確認
                assert len(gateway.profile.metrics_history) == 1
                metrics = gateway.profile.metrics_history[0]
                assert metrics.success is True
                assert metrics.optimization_info['optimized'] is True
                assert metrics.optimization_info['reduction_percent'] == 50.0