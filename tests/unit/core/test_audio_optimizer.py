"""
音声最適化のユニットテスト
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

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
    
    @pytest.fixture
    def mock_audio_info(self):
        """音声ストリーム情報のモック"""
        return {
            'sample_rate': 48000,
            'channels': 2,
            'duration': 60.0,
            'codec': 'aac',
            'bitrate': '192k'
        }
    
    def test_prepare_audio_success(self, optimizer, mock_video_path, mock_audio_info):
        """prepare_audioの正常系テスト"""
        # モックの設定
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
                    'reduction_percent': 90,
                    'original_sample_rate': 48000,
                    'optimized_sample_rate': 16000
                }
                mock_optimize.return_value = (optimized_audio, optimization_stats)
                
                # 実行
                audio_data, info = optimizer.prepare_audio(mock_video_path)
                
                # 検証
                assert isinstance(audio_data, np.ndarray)
                assert audio_data.shape[0] == 16000 * 60
                assert info['optimized'] is True
                assert 'reduction_percent' in info
                assert info['reduction_percent'] == 90
                
                # メソッドが呼ばれたことを確認
                mock_analyze.assert_called_once_with(mock_video_path)
                mock_optimize.assert_called_once()
    
    def test_prepare_audio_fallback_on_error(self, optimizer, mock_video_path, mock_audio_info):
        """最適化失敗時のフォールバックテスト"""
        with patch.object(optimizer, '_analyze_audio_streams') as mock_analyze:
            mock_analyze.return_value = mock_audio_info
            
            with patch.object(optimizer, '_optimize_audio') as mock_optimize:
                # 最適化で例外を発生させる
                mock_optimize.side_effect = Exception("Optimization failed")
                
                # librosaフォールバックのモック
                fallback_audio = np.zeros((16000 * 60,), dtype=np.float32)
                with patch('core.audio_optimizer.librosa') as mock_librosa:
                    mock_librosa.load.return_value = (fallback_audio, 16000)

                    # 実行
                    audio_data, info = optimizer.prepare_audio(mock_video_path)

                    # 検証
                    assert audio_data.shape[0] == 16000 * 60
                    assert info['optimized'] is False
                    assert 'Optimization failed' in info['reason']
    
    def test_analyze_audio_streams(self, optimizer, mock_video_path):
        """音声ストリーム分析のテスト"""
        # ffprobeの出力をモック（実装に合わせて修正）
        mock_streams_output = '''
        {
            "streams": [{
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": "2",
                "bit_rate": "192000"
            }]
        }
        '''
        
        # _get_durationのモック
        with patch.object(optimizer, '_get_duration') as mock_get_duration:
            mock_get_duration.return_value = 60.0
            
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(
                    stdout=mock_streams_output,
                    stderr='',
                    returncode=0
                )
                
                # 実行
                info = optimizer._analyze_audio_streams(mock_video_path)
                
                # 検証
                assert info['sample_rate'] == 48000
                assert info['channels'] == 2
                assert info['duration'] == 60.0
                assert info['codec'] == 'aac'
                assert info['bit_rate'] == 192000
    
    def test_build_conversion_command(self, optimizer):
        """変換コマンド構築のテスト"""
        input_path = Path("/input/video.mp4")
        output_path = Path("/output/audio.wav")
        
        # 音声情報（実装に合わせた形式）
        audio_info = {
            'codec': 'aac',
            'sample_rate': 48000,
            'channels': 2,
            'bit_rate': 192000
        }
        
        # 標準戦略でテスト
        cmd = optimizer._build_conversion_command(
            input_path, output_path, audio_info, strategy='standard'
        )
        
        # 検証
        assert 'ffmpeg' in cmd
        assert '-i' in cmd
        assert str(input_path) in cmd
        assert str(output_path) in cmd
        assert '-ar' in cmd
        assert str(optimizer.target_sample_rate) in cmd  # 16000
        assert '-ac' in cmd
        assert '1' in cmd  # モノラル
        assert '-acodec' in cmd
        assert 'pcm_s16le' in cmd  # 標準戦略では16bit
        
        # アグレッシブ戦略でもテスト
        cmd_aggressive = optimizer._build_conversion_command(
            input_path, output_path, audio_info, strategy='aggressive'
        )
        
        assert 'pcm_u8' in cmd_aggressive  # アグレッシブ戦略では8bit
        assert '-af' in cmd_aggressive  # オーディオフィルタ
    
    def test_get_optimization_summary(self, optimizer):
        """最適化サマリー取得のテスト"""
        # 実装に合わせた統計データ
        optimizer.optimization_stats = [
            {
                'original_size_mb': 100,
                'optimized_size_mb': 10,
                'conversion_time_sec': 5.0
            },
            {
                'original_size_mb': 200,
                'optimized_size_mb': 30,
                'conversion_time_sec': 10.0
            }
        ]
        
        # 実行
        summary = optimizer.get_optimization_summary()
        
        # 検証
        assert summary['total_optimizations'] == 2
        assert summary['total_reduction_mb'] == 260  # (100-10) + (200-30)
        assert summary['average_reduction_percent'] == pytest.approx(86.67, rel=0.1)  # 1 - 40/300
        assert summary['total_conversion_time_sec'] == 15.0
        assert 'details' in summary
        assert summary['details'] == optimizer.optimization_stats
    
    @pytest.mark.parametrize("duration,file_size,expected_time", [
        (60.0, 10.0, pytest.approx(0.198, rel=1e-1)),     # 60秒, 10MB → 60*0.033*0.1
        (3600.0, 100.0, pytest.approx(118.8, rel=1e-1)),  # 1時間, 100MB → 3600*0.033*1.0
        (60.0, 200.0, pytest.approx(3.96, rel=1e-1)),     # 60秒, 200MB → 60*0.033*2.0
    ])
    def test_estimate_conversion_time(self, optimizer, duration, file_size, expected_time):
        """変換時間推定のテスト"""
        # 実行
        estimated = optimizer._estimate_conversion_time(duration, file_size)
        
        # 検証（概算なので範囲で確認）
        assert estimated == expected_time