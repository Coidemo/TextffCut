"""
OptimizedTranscriptionGatewayAdapterのVAD統合テスト

インフラ層でのVAD処理統合をテスト
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from adapters.gateways.transcription.optimized_transcription_gateway import (
    OptimizedTranscriptionGatewayAdapter
)
from config import Config
from domain.entities import TranscriptionResult
from domain.entities.transcription import TranscriptionSegment, Word, Char
from domain.value_objects import FilePath, Duration, TimeRange
from infrastructure.gateways.audio_optimizer_gateway_adapter import AudioOptimizerGatewayAdapter
from infrastructure.repositories.performance_profile_repository import FilePerformanceProfileRepository


class TestOptimizedGatewayVADIntegration(unittest.TestCase):
    """OptimizedTranscriptionGatewayAdapterのVAD統合テスト"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = Config()
        self.config.transcription.use_api = False
        self.config.transcription.language = "ja"
        self.config.transcription.compute_type = "int8"
        self.config.transcription.model_size = "medium"
        # VAD処理を有効化
        self.config.transcription.use_vad_processing = True
        
        # モックの作成
        self.mock_audio_optimizer = MagicMock(spec=AudioOptimizerGatewayAdapter)
        # prepare_audioの戻り値を設定
        self.mock_audio_optimizer.prepare_audio.return_value = (
            "mock_audio_data",  # audio_data
            {"optimized": True, "reduction_percent": 30.0}  # optimization_info
        )
        self.mock_profile_repository = MagicMock(spec=FilePerformanceProfileRepository)
        
        # デフォルトプロファイルのモック
        mock_profile = MagicMock()
        mock_profile.get_effective_batch_size.return_value = 8
        mock_profile.get_effective_compute_type.return_value = "int8"
        mock_profile.batch_size = 8
        mock_profile.compute_type = "int8"
        mock_profile.add_metrics = MagicMock()
        mock_profile.metrics_history = []
        self.mock_profile_repository.load.return_value = mock_profile
        self.mock_profile_repository.save = MagicMock()
        
        # ゲートウェイの初期化
        self.gateway = OptimizedTranscriptionGatewayAdapter(
            config=self.config,
            audio_optimizer=self.mock_audio_optimizer,
            profile_repository=self.mock_profile_repository
        )
        
        # _legacy_transcriberのモック
        self.gateway._legacy_transcriber = MagicMock()
        self.gateway._legacy_transcriber.DEFAULT_BATCH_SIZE = 8
        
        # profileも設定
        self.gateway.profile = mock_profile
        
        # 親クラスのtranscribeメソッドをモック
        import adapters.gateways.transcription.transcription_gateway
        self.original_transcribe = adapters.gateways.transcription.transcription_gateway.TranscriptionGatewayAdapter.transcribe
        adapters.gateways.transcription.transcription_gateway.TranscriptionGatewayAdapter.transcribe = MagicMock(
            return_value=self._create_mock_result()
        )
        
    def tearDown(self):
        """テストのクリーンアップ"""
        # モックを元に戻す
        if hasattr(self, 'original_transcribe'):
            import adapters.gateways.transcription.transcription_gateway
            adapters.gateways.transcription.transcription_gateway.TranscriptionGatewayAdapter.transcribe = self.original_transcribe
        
    def test_vad_processing_enabled(self):
        """VAD処理が有効な場合の動作テスト"""
        video_path = FilePath("/tmp/test_video.mp4")
        
        with patch.object(self.gateway, '_transcribe_with_vad') as mock_vad, \
             patch.object(self.gateway, '_transcribe_legacy') as mock_legacy:
            
            # VAD処理が呼ばれることを確認
            mock_vad.return_value = self._create_mock_result()
            
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja"
            )
            
            # VAD処理が呼ばれたことを確認
            mock_vad.assert_called_once()
            mock_legacy.assert_not_called()
            
    def test_vad_processing_disabled(self):
        """VAD処理が無効な場合の動作テスト"""
        # VAD処理を無効化
        self.config.transcription.use_vad_processing = False
        video_path = FilePath("/tmp/test_video.mp4")
        
        with patch.object(self.gateway, '_transcribe_with_vad') as mock_vad, \
             patch.object(self.gateway, '_transcribe_legacy') as mock_legacy:
            
            # レガシー処理が呼ばれることを確認
            mock_legacy.return_value = self._create_mock_result()
            
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja"
            )
            
            # レガシー処理が呼ばれたことを確認
            mock_legacy.assert_called_once()
            mock_vad.assert_not_called()
            
    def test_vad_processing_with_api_mode(self):
        """APIモードではVAD処理が使用されないことのテスト"""
        # APIモードを有効化
        self.config.transcription.use_api = True
        self.config.transcription.use_vad_processing = True
        video_path = FilePath("/tmp/test_video.mp4")
        
        with patch.object(self.gateway, '_transcribe_with_vad') as mock_vad, \
             patch.object(self.gateway, '_transcribe_legacy') as mock_legacy:
            
            # レガシー処理が呼ばれることを確認
            mock_legacy.return_value = self._create_mock_result()
            
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja"
            )
            
            # APIモードではレガシー処理が使用される
            mock_legacy.assert_called_once()
            mock_vad.assert_not_called()
            
    @patch('infrastructure.external.ffmpeg_vad_processor.FFmpegVADProcessor')
    @patch('core.auto_optimizer.AutoOptimizer')
    @patch('core.memory_monitor.MemoryMonitor')
    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('whisperx.load_audio')
    @patch('whisperx.load_model')
    @patch('whisperx.load_align_model')
    def test_vad_transcribe_flow(
        self,
        mock_load_align_model,
        mock_load_model,
        mock_load_audio,
        mock_exists,
        mock_subprocess,
        mock_memory_monitor_class,
        mock_optimizer_class,
        mock_vad_class
    ):
        """VADベースの文字起こしフロー全体のテスト"""
        video_path = FilePath("/tmp/test_video.mp4")
        
        # モックの設定
        # os.path.existsの戻り値を設定（パスによって異なる値を返す）
        def mock_exists_side_effect(path):
            # segment_X.wavファイルは存在しない
            if "segment_" in path and path.endswith(".wav"):
                return False
            # その他のパス（一時ディレクトリなど）は存在する
            return True
        
        mock_exists.side_effect = mock_exists_side_effect
        
        # subprocess.runのモック
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        # VADプロセッサーのモック
        mock_vad = MagicMock()
        mock_vad.detect_segments.return_value = [
            (0.0, 10.0),
            (10.0, 20.0)
        ]
        mock_vad_class.return_value = mock_vad
        
        # オプティマイザーのモック
        mock_optimizer = MagicMock()
        mock_optimizer.get_optimal_params.return_value = {
            'batch_size': 8,
            'compute_type': 'int8'
        }
        mock_optimizer_class.return_value = mock_optimizer
        
        # メモリモニターのモック
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value = 60.0
        mock_memory_monitor_class.return_value = mock_monitor
        
        # WhisperXのモック
        mock_audio = MagicMock()
        mock_load_audio.return_value = mock_audio
        
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "start": 0.0,
                    "end": 5.0,
                    "text": "テストテキスト1"
                }
            ]
        }
        mock_load_model.return_value = mock_model
        
        # アライメントモデルのモック
        mock_align_model = MagicMock()
        mock_metadata = MagicMock()
        mock_load_align_model.return_value = (mock_align_model, mock_metadata)
        
        # whisperx.alignのモック
        with patch('whisperx.align') as mock_align:
            mock_align.return_value = {
                "segments": [
                    {
                        "start": 0.0,
                        "end": 5.0,
                        "text": "テストテキスト1",
                        "words": [
                            {"word": "テスト", "start": 0.0, "end": 2.0, "probability": 0.9},
                            {"word": "テキスト", "start": 2.0, "end": 4.0, "probability": 0.95},
                            {"word": "1", "start": 4.0, "end": 5.0, "probability": 0.99}
                        ],
                        "chars": [
                            {"char": "テ", "start": 0.0, "end": 0.5, "probability": 0.9},
                            {"char": "ス", "start": 0.5, "end": 1.0, "probability": 0.9},
                            {"char": "ト", "start": 1.0, "end": 2.0, "probability": 0.9}
                        ]
                    }
                ]
            }
            
            # 進捗コールバックのモック
            progress_messages = []
            def mock_progress(msg):
                progress_messages.append(msg)
            
            # VAD処理を実行
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja",
                progress_callback=mock_progress
            )
            
        # 結果の検証
        self.assertIsInstance(result, TranscriptionResult)
        self.assertEqual(len(result.segments), 2)  # 2つのVADセグメント
        
        # VADプロセッサーが呼ばれたことを確認
        mock_vad.detect_segments.assert_called_once()
        
        # 進捗メッセージの確認
        self.assertTrue(any("音声を抽出中" in msg for msg in progress_messages))
        self.assertTrue(any("音声区間を検出中" in msg for msg in progress_messages))
        self.assertTrue(any("セグメント" in msg for msg in progress_messages))
        
    def test_vad_error_fallback(self):
        """VAD処理エラー時のフォールバックテスト"""
        video_path = FilePath("/tmp/test_video.mp4")
        
        with patch('infrastructure.external.ffmpeg_vad_processor.FFmpegVADProcessor') as mock_vad_class, \
             patch.object(self.gateway, '_transcribe_legacy') as mock_legacy:
            
            # VADプロセッサーでエラーを発生させる
            mock_vad = MagicMock()
            mock_vad.detect_segments.side_effect = Exception("VAD error")
            mock_vad_class.return_value = mock_vad
            
            # レガシー処理の戻り値を設定
            mock_legacy.return_value = self._create_mock_result()
            
            # VAD処理を実行（エラーが発生してフォールバック）
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja"
            )
            
            # レガシー処理にフォールバックされたことを確認
            mock_legacy.assert_called_once()
            
    def test_progress_callback_format(self):
        """進捗コールバックのフォーマットテスト"""
        video_path = FilePath("/tmp/test_video.mp4")
        progress_messages = []
        
        def capture_progress(msg):
            progress_messages.append(msg)
            
        with patch.object(self.gateway, '_transcribe_legacy') as mock_legacy:
            mock_legacy.return_value = self._create_mock_result()
            
            # VAD無効でレガシー処理を実行
            self.config.transcription.use_vad_processing = False
            
            result = self.gateway.transcribe(
                video_path=video_path,
                model_size="medium",
                language="ja",
                progress_callback=capture_progress
            )
            
            # コールバックが文字列形式で呼ばれたことを確認
            mock_legacy.assert_called_once()
            call_args = mock_legacy.call_args
            self.assertIn('progress_callback', call_args.kwargs)
            
    def _create_mock_result(self):
        """モック用のTranscriptionResultを作成"""
        segments = [
            TranscriptionSegment(
                id="test-segment-1",
                text="テストセグメント",
                start=0.0,
                end=10.0,
                words=[
                    Word(
                        word="テスト",
                        start=0.0,
                        end=5.0,
                        confidence=0.95
                    )
                ],
                chars=[]
            )
        ]
        
        return TranscriptionResult(
            id="test-result-1",
            video_id="test-video-1",
            segments=segments,
            language="ja",
            duration=10.0,
            original_audio_path="/tmp/test.wav",
            model_size="medium",
            processing_time=5.0
        )


if __name__ == "__main__":
    unittest.main()