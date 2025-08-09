"""
音声最適化のユニットテスト
"""

import numpy as np
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.audio_optimizer import IntelligentAudioOptimizer


class TestIntelligentAudioOptimizer:
    """IntelligentAudioOptimizerのテスト"""
    
    @pytest.fixture
    def optimizer(self):
        """テスト用のオプティマイザーインスタンス"""
        return IntelligentAudioOptimizer()
    
    @pytest.fixture
    def mock_video_path(self, tmp_path):
        """テスト用の動画パス"""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        return video_path
    
    def test_prepare_audio_auto_mode_with_sufficient_memory(self, optimizer, mock_video_path):
        """十分なメモリがある場合のautoモードテスト"""
        # モック設定
        with patch('psutil.virtual_memory') as mock_memory:
            # 16GBの利用可能メモリ
            mock_memory.return_value = Mock(available=16 * 1024**3)
            
            with patch.object(optimizer, '_extract_audio_stream') as mock_extract:
                mock_extract.return_value = np.zeros((48000 * 60,), dtype=np.float32)  # 1分の音声
                
                # 実行
                audio_data, info = optimizer.prepare_audio(mock_video_path, "auto")
                
                # 検証
                assert info['optimized'] is False
                assert info['reason'] == '十分なメモリあり'
                assert audio_data.shape[0] == 48000 * 60
    
    def test_prepare_audio_auto_mode_with_low_memory(self, optimizer, mock_video_path):
        """メモリ不足時のautoモードテスト"""
        with patch('psutil.virtual_memory') as mock_memory:
            # 2GBの利用可能メモリ
            mock_memory.return_value = Mock(available=2 * 1024**3)
            
            with patch.object(optimizer, '_extract_audio_stream') as mock_extract:
                # 48kHz、ステレオの音声データ
                mock_extract.return_value = np.zeros((48000 * 60, 2), dtype=np.float32)
                
                with patch.object(optimizer, '_optimize_audio') as mock_optimize:
                    # 最適化後のデータ（16kHz、モノラル）
                    mock_optimize.return_value = np.zeros((16000 * 60,), dtype=np.float32)
                    
                    # 実行
                    audio_data, info = optimizer.prepare_audio(mock_video_path, "auto")
                    
                    # 検証
                    assert info['optimized'] is True
                    assert 'reduction_percent' in info
                    assert audio_data.shape[0] == 16000 * 60
    
    def test_prepare_audio_always_mode(self, optimizer, mock_video_path):
        """alwaysモードテスト（新実装では常に最適化される）"""
        # 音声ストリーム情報のモック
        mock_audio_info = {
            'sample_rate': 48000,
            'channels': 2,
            'duration': 60.0,
            'codec': 'aac'
        }
        
        with patch.object(optimizer, '_analyze_audio_streams') as mock_analyze:
            mock_analyze.return_value = mock_audio_info
            
            with patch.object(optimizer, '_optimize_audio') as mock_optimize:
                # 最適化後のデータとstatsを返す
                optimized_audio = np.zeros((16000 * 60,), dtype=np.float32)
                optimization_stats = {
                    'optimized': True,
                    'reason': '精度を保ちながらメモリ効率を最大化',
                    'original_size_mb': 100,
                    'optimized_size_mb': 10,
                    'reduction_percent': 90
                }
                mock_optimize.return_value = (optimized_audio, optimization_stats)
                
                # 実行（新実装ではmodeパラメータがない）
                audio_data, info = optimizer.prepare_audio(mock_video_path)
                
                # 検証
                assert info['optimized'] is True
                assert 'reduction_percent' in info
                assert audio_data.shape[0] == 16000 * 60
    
    def test_prepare_audio_never_mode(self, optimizer, mock_video_path):
        """neverモードテスト"""
        with patch.object(optimizer, '_extract_audio_stream') as mock_extract:
            mock_extract.return_value = np.zeros((48000 * 60,), dtype=np.float32)
            
            # 実行
            audio_data, info = optimizer.prepare_audio(mock_video_path, "never")
            
            # 検証
            assert info['optimized'] is False
            assert info['reason'] == 'ユーザー指定'
    
    def test_optimize_audio(self, optimizer):
        """音声最適化のテスト"""
        # 48kHzステレオ音声（1秒）
        original_audio = np.random.randn(48000, 2).astype(np.float32)
        
        with patch('librosa.resample') as mock_resample:
            # リサンプル後のデータ
            mock_resample.return_value = np.random.randn(16000).astype(np.float32)
            
            # 実行
            optimized = optimizer._optimize_audio(original_audio, 48000)
            
            # 検証
            mock_resample.assert_called_once()
            assert optimized.shape == (16000,)
            assert optimized.dtype == np.float32
    
    def test_extract_audio_stream_error_handling(self, optimizer, mock_video_path):
        """音声抽出エラーハンドリングのテスト"""
        with patch('subprocess.run') as mock_run:
            # ffprobeエラー
            mock_run.return_value = Mock(returncode=1, stderr="Error")
            
            # 例外が発生することを確認
            with pytest.raises(Exception) as exc_info:
                optimizer._extract_audio_stream(mock_video_path)
            
            assert "音声ストリーム情報の取得に失敗" in str(exc_info.value)