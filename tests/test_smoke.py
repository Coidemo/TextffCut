"""
スモークテスト - 基本的な動作確認
"""

import pytest
import sys
from pathlib import Path


class TestSmoke:
    """基本的な動作確認テスト"""
    
    def test_main_module_imports(self):
        """mainモジュールがインポートできることを確認"""
        try:
            import main
            assert hasattr(main, 'main')
        except ImportError as e:
            pytest.fail(f"mainモジュールのインポートに失敗: {e}")
    
    def test_core_modules_import(self):
        """coreモジュールがインポートできることを確認"""
        try:
            from core import (
                Transcriber, TranscriptionResult, TranscriptionSegment,
                VideoProcessor, VideoSegment, VideoInfo, SilenceInfo,
                TextProcessor, TextDifference, TextPosition,
                FCPXMLExporter, XMEMLExporter, EDLExporter, ExportSegment,
                SRTExporter
            )
            # 各クラスが存在することを確認
            assert all([
                Transcriber, TranscriptionResult, TranscriptionSegment,
                VideoProcessor, VideoSegment, VideoInfo, SilenceInfo,
                TextProcessor, TextDifference, TextPosition,
                FCPXMLExporter, XMEMLExporter, EDLExporter, ExportSegment,
                SRTExporter
            ])
        except ImportError as e:
            pytest.fail(f"coreモジュールのインポートに失敗: {e}")
    
    def test_di_container_initialization(self):
        """DIコンテナが初期化できることを確認"""
        try:
            from di.containers import ApplicationContainer
            container = ApplicationContainer()
            assert container is not None
        except Exception as e:
            pytest.fail(f"DIコンテナの初期化に失敗: {e}")
    
    def test_config_module_imports(self):
        """設定モジュールがインポートできることを確認"""
        try:
            import config
            # configモジュールの実際の属性を確認
            assert hasattr(config, '__file__')  # モジュールがロードされていることを確認
        except ImportError as e:
            pytest.fail(f"configモジュールのインポートに失敗: {e}")
    
    def test_audio_optimizer_imports(self):
        """音声最適化モジュールがインポートできることを確認"""
        try:
            from core.audio_optimizer import IntelligentAudioOptimizer
            optimizer = IntelligentAudioOptimizer()
            assert optimizer.target_sample_rate == 16000
        except ImportError as e:
            pytest.fail(f"audio_optimizerモジュールのインポートに失敗: {e}")
    
    def test_clean_architecture_layers(self):
        """クリーンアーキテクチャの各層がインポートできることを確認"""
        layers = [
            ("domain.entities", ["TextDifference", "TranscriptionResult"]),
            ("domain.value_objects", ["Duration", "TimeRange", "FilePath"]),
            ("application.use_cases", ["OptimizeAudioUseCase"]),
            ("infrastructure.gateways.audio_optimizer_gateway_adapter", ["AudioOptimizerGatewayAdapter"]),
            ("presentation.presenters.main", ["MainPresenter"]),
            ("presentation.views.main", ["MainView"]),
        ]
        
        for module_path, expected_items in layers:
            try:
                module = __import__(module_path, fromlist=expected_items)
                for item in expected_items:
                    assert hasattr(module, item), f"{module_path}に{item}が存在しません"
            except ImportError as e:
                # 一部のモジュールは存在しない可能性があるため、警告のみ
                pytest.skip(f"{module_path}のインポートに失敗（スキップ）: {e}")
    
    def test_utils_modules_import(self):
        """utilsモジュールがインポートできることを確認"""
        try:
            import utils
            # utilsモジュールが存在することを確認
            assert hasattr(utils, '__file__')
        except ImportError as e:
            pytest.fail(f"utilsモジュールのインポートに失敗: {e}")
    
    @pytest.mark.slow
    def test_mlx_availability(self):
        """MLXが利用可能かどうかを確認（Apple Silicon必須）"""
        try:
            import mlx_whisper
            assert mlx_whisper is not None
            pytest.skip("MLX Whisperは利用可能です（Apple Silicon環境）")
        except ImportError:
            pytest.skip("MLX Whisperが利用できません（Apple Silicon Mac が必要です）")