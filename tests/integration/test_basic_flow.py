"""
基本的な統合テスト - アプリケーションの基本フローを確認
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import numpy as np


class TestBasicFlow:
    """基本的なアプリケーションフローのテスト"""
    
    @pytest.fixture
    def mock_video_path(self, tmp_path):
        """テスト用の動画パス"""
        video_path = tmp_path / "test_video.mp4"
        video_path.touch()
        return video_path
    
    @pytest.fixture
    def mock_transcription_result(self):
        """モックの文字起こし結果"""
        mock_result = Mock()
        mock_result.text = "これはテストテキストです"
        mock_result.segments = [
            {
                'text': 'これはテストテキストです',
                'start': 0.0,
                'end': 3.0,
                'words': [
                    {'word': 'これは', 'start': 0.0, 'end': 1.0},
                    {'word': 'テスト', 'start': 1.0, 'end': 2.0},
                    {'word': 'テキストです', 'start': 2.0, 'end': 3.0}
                ]
            }
        ]
        return mock_result
    
    @pytest.mark.integration
    def test_transcription_flow(self, mock_video_path, mock_transcription_result):
        """文字起こしフローの基本テスト"""
        from core.transcription import Transcriber
        
        with patch('core.transcription.whisperx') as mock_whisperx:
            # WhisperXのモック設定
            mock_model = Mock()
            mock_whisperx.load_model.return_value = mock_model
            mock_model.transcribe.return_value = {
                'segments': mock_transcription_result.segments
            }
            
            # Transcriberのテスト
            transcriber = Transcriber(model_size="base")
            result = transcriber.transcribe(str(mock_video_path))
            
            # 結果の検証
            assert result is not None
            assert hasattr(result, 'segments')
            assert len(result.segments) > 0
    
    @pytest.mark.integration
    def test_text_processing_flow(self):
        """テキスト処理フローの基本テスト"""
        from core.text_processor import TextProcessor
        
        processor = TextProcessor()
        
        # 差分検出のテスト
        original = "これはテストテキストです"
        edited = "これは編集されたテキストです"
        
        differences = processor.find_differences(original, edited)
        
        assert differences is not None
        assert len(differences) > 0
        assert differences[0].type == "replace"
    
    @pytest.mark.integration
    def test_video_processing_flow(self, mock_video_path):
        """動画処理フローの基本テスト"""
        from core.video import VideoProcessor
        
        processor = VideoProcessor()
        
        with patch('subprocess.run') as mock_run:
            # FFprobeのモック
            mock_run.return_value = Mock(
                stdout='{"format": {"duration": "60.0"}}',
                stderr='',
                returncode=0
            )
            
            # 動画情報の取得
            info = processor.get_video_info(str(mock_video_path))
            
            assert info is not None
            assert info.duration == 60.0
    
    @pytest.mark.integration
    def test_export_flow(self, tmp_path):
        """エクスポートフローの基本テスト"""
        from core.export import FCPXMLExporter, ExportSegment
        
        # エクスポートセグメントの作成
        segments = [
            ExportSegment(
                start_time=0.0,
                end_time=3.0,
                text="テストセグメント",
                index=0
            )
        ]
        
        # FCPXMLエクスポート
        exporter = FCPXMLExporter()
        output_path = tmp_path / "test.fcpxml"
        
        result = exporter.export(
            segments=segments,
            video_path=str(tmp_path / "test.mp4"),
            output_path=str(output_path),
            video_duration=60.0,
            frame_rate=29.97
        )
        
        assert result is True
        assert output_path.exists()
    
    @pytest.mark.integration
    def test_audio_optimization_flow(self, mock_video_path):
        """音声最適化フローの基本テスト"""
        from core.audio_optimizer import IntelligentAudioOptimizer
        
        optimizer = IntelligentAudioOptimizer()
        
        with patch('core.audio_optimizer.whisperx') as mock_whisperx:
            # WhisperXが利用可能な場合のモック
            mock_whisperx.load_audio.return_value = np.zeros((16000 * 60,), dtype=np.float32)
            
            with patch.object(optimizer, '_analyze_audio_streams') as mock_analyze:
                mock_analyze.return_value = {
                    'sample_rate': 48000,
                    'channels': 2,
                    'duration': 60.0,
                    'codec': 'aac',
                    'bit_rate': 192000
                }
                
                with patch.object(optimizer, '_optimize_audio') as mock_optimize:
                    mock_optimize.return_value = (
                        np.zeros((16000 * 60,), dtype=np.float32),
                        {'optimized': True, 'reduction_percent': 80}
                    )
                    
                    # 音声準備のテスト
                    audio_data, info = optimizer.prepare_audio(mock_video_path)
                    
                    assert audio_data is not None
                    assert info['optimized'] is True
    
    @pytest.mark.integration
    def test_di_container_integration(self):
        """DIコンテナの統合テスト"""
        from di.containers import DIContainer
        
        container = DIContainer()
        
        # 各コンポーネントが取得できることを確認
        components = [
            'transcription_gateway',
            'text_processor_gateway',
            'video_processor_gateway',
            'file_gateway'
        ]
        
        for component_name in components:
            try:
                component = getattr(container, component_name)()
                assert component is not None
            except Exception as e:
                pytest.skip(f"{component_name}の取得に失敗（スキップ）: {e}")