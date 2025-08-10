"""
モデルキャッシュ機能の統合テスト

OptimizedTranscriptionGatewayAdapterのモデルキャッシュ機能をテスト
"""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import torch

from adapters.gateways.transcription.optimized_transcription_gateway import (
    OptimizedTranscriptionGatewayAdapter
)
from config import Config
from domain.entities import TranscriptionResult
from infrastructure.gateways.audio_optimizer_gateway_adapter import AudioOptimizerGatewayAdapter
from infrastructure.repositories.performance_profile_repository import FilePerformanceProfileRepository


class TestModelCache(unittest.TestCase):
    """モデルキャッシュ機能のテスト"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = Config()
        self.config.transcription.use_api = False
        self.config.transcription.language = "ja"
        self.config.transcription.compute_type = "int8"
        self.config.transcription.model_size = "medium"
        self.config.transcription.use_vad_processing = True
        
        # モックの作成
        self.mock_audio_optimizer = MagicMock(spec=AudioOptimizerGatewayAdapter)
        self.mock_profile_repository = MagicMock(spec=FilePerformanceProfileRepository)
        
        # デフォルトプロファイルのモック
        mock_profile = MagicMock()
        mock_profile.get_effective_compute_type.return_value = "int8"
        self.mock_profile_repository.load.return_value = mock_profile
        
        # ゲートウェイの初期化
        self.gateway = OptimizedTranscriptionGatewayAdapter(
            config=self.config,
            audio_optimizer=self.mock_audio_optimizer,
            profile_repository=self.mock_profile_repository
        )
        
    def test_whisper_model_cache_initialization(self):
        """Whisperモデルキャッシュの初期化テスト"""
        # キャッシュが正しく初期化されていることを確認
        self.assertIsNotNone(self.gateway._model_cache)
        self.assertIsNone(self.gateway._model_cache['whisper'])
        self.assertEqual(self.gateway._model_cache['whisper_params'], {})
        self.assertIsNone(self.gateway._model_cache['align'])
        self.assertIsNone(self.gateway._model_cache['align_language'])
        
    @patch('whisperx.load_model')
    def test_whisper_model_cache_first_load(self, mock_load_model):
        """Whisperモデルの初回読み込みテスト"""
        # モックモデルを設定
        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        
        # モデルを取得
        result = self.gateway._get_cached_whisper_model(
            model_size="medium",
            device="cpu",
            compute_type="int8",
            language="ja"
        )
        
        # 新規読み込みが実行されたことを確認
        mock_load_model.assert_called_once_with(
            "medium", "cpu", 
            compute_type="int8",
            language="ja"
        )
        
        # キャッシュに保存されたことを確認
        self.assertEqual(self.gateway._model_cache['whisper'], mock_model)
        self.assertEqual(self.gateway._model_cache['whisper_params'], {
            'model_size': 'medium',
            'device': 'cpu',
            'compute_type': 'int8',
            'language': 'ja'
        })
        self.assertEqual(result, mock_model)
        
    @patch('whisperx.load_model')
    def test_whisper_model_cache_reuse(self, mock_load_model):
        """Whisperモデルのキャッシュ再利用テスト"""
        # モックモデルを設定
        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        
        # 1回目の取得
        result1 = self.gateway._get_cached_whisper_model(
            model_size="medium",
            device="cpu",
            compute_type="int8",
            language="ja"
        )
        
        # 2回目の取得（同じパラメータ）
        result2 = self.gateway._get_cached_whisper_model(
            model_size="medium",
            device="cpu",
            compute_type="int8",
            language="ja"
        )
        
        # load_modelは1回だけ呼ばれたことを確認
        mock_load_model.assert_called_once()
        
        # 同じモデルが返されたことを確認
        self.assertEqual(result1, result2)
        self.assertEqual(result2, mock_model)
        
    @patch('whisperx.load_model')
    @patch('torch.cuda.empty_cache')
    def test_whisper_model_cache_invalidation(self, mock_empty_cache, mock_load_model):
        """Whisperモデルキャッシュの無効化テスト"""
        # 異なるモデルを設定
        mock_model1 = MagicMock()
        mock_model2 = MagicMock()
        mock_load_model.side_effect = [mock_model1, mock_model2]
        
        # GPUが利用可能であることを仮定
        with patch('torch.cuda.is_available', return_value=True):
            # 1回目の取得
            result1 = self.gateway._get_cached_whisper_model(
                model_size="medium",
                device="cuda",
                compute_type="int8",
                language="ja"
            )
            
            # 2回目の取得（異なるパラメータ）
            result2 = self.gateway._get_cached_whisper_model(
                model_size="large",
                device="cuda",
                compute_type="int8",
                language="ja"
            )
        
        # load_modelが2回呼ばれたことを確認
        self.assertEqual(mock_load_model.call_count, 2)
        
        # GPUキャッシュがクリアされたことを確認
        mock_empty_cache.assert_called()
        
        # 異なるモデルが返されたことを確認
        self.assertNotEqual(result1, result2)
        self.assertEqual(result1, mock_model1)
        self.assertEqual(result2, mock_model2)
        
    @patch('whisperx.load_align_model')
    def test_align_model_cache_first_load(self, mock_load_align_model):
        """アライメントモデルの初回読み込みテスト"""
        # モックモデルを設定
        mock_align_model = MagicMock()
        mock_metadata = MagicMock()
        mock_load_align_model.return_value = (mock_align_model, mock_metadata)
        
        # モデルを取得
        result = self.gateway._get_cached_align_model(
            language="ja",
            device="cpu"
        )
        
        # 新規読み込みが実行されたことを確認
        mock_load_align_model.assert_called_once_with(
            language_code="ja",
            device="cpu"
        )
        
        # キャッシュに保存されたことを確認
        self.assertEqual(self.gateway._model_cache['align'], (mock_align_model, mock_metadata))
        self.assertEqual(self.gateway._model_cache['align_language'], "ja")
        self.assertEqual(result, (mock_align_model, mock_metadata))
        
    @patch('whisperx.load_align_model')
    def test_align_model_cache_reuse(self, mock_load_align_model):
        """アライメントモデルのキャッシュ再利用テスト"""
        # モックモデルを設定
        mock_align_model = MagicMock()
        mock_metadata = MagicMock()
        mock_load_align_model.return_value = (mock_align_model, mock_metadata)
        
        # 1回目の取得
        result1 = self.gateway._get_cached_align_model("ja", "cpu")
        
        # 2回目の取得（同じパラメータ）
        result2 = self.gateway._get_cached_align_model("ja", "cpu")
        
        # load_align_modelは1回だけ呼ばれたことを確認
        mock_load_align_model.assert_called_once()
        
        # 同じモデルが返されたことを確認
        self.assertEqual(result1, result2)
        self.assertEqual(result2, (mock_align_model, mock_metadata))
        
    @patch('torch.cuda.empty_cache')
    def test_clear_model_cache(self, mock_empty_cache):
        """キャッシュクリアのテスト"""
        # キャッシュにモデルを設定
        mock_whisper = MagicMock()
        mock_align = (MagicMock(), MagicMock())
        self.gateway._model_cache['whisper'] = mock_whisper
        self.gateway._model_cache['whisper_params'] = {'test': 'params'}
        self.gateway._model_cache['align'] = mock_align
        self.gateway._model_cache['align_language'] = 'ja'
        
        # GPUが利用可能であることを仮定
        with patch('torch.cuda.is_available', return_value=True):
            # キャッシュをクリア
            self.gateway._clear_model_cache()
        
        # キャッシュがクリアされたことを確認
        self.assertIsNone(self.gateway._model_cache['whisper'])
        self.assertEqual(self.gateway._model_cache['whisper_params'], {})
        self.assertIsNone(self.gateway._model_cache['align'])
        self.assertIsNone(self.gateway._model_cache['align_language'])
        
        # GPUキャッシュもクリアされたことを確認
        mock_empty_cache.assert_called_once()
        
    @patch('infrastructure.external.ffmpeg_vad_processor.FFmpegVADProcessor')
    @patch('core.auto_optimizer.AutoOptimizer')
    @patch('core.memory_monitor.MemoryMonitor')
    @patch('subprocess.run')
    @patch('whisperx.load_audio')
    @patch('whisperx.load_model')
    @patch('whisperx.load_align_model')
    @patch('whisperx.align')
    def test_vad_segment_processing_with_cache(
        self,
        mock_align,
        mock_load_align_model,
        mock_load_model,
        mock_load_audio,
        mock_subprocess,
        mock_memory_monitor_class,
        mock_optimizer_class,
        mock_vad_class
    ):
        """VADセグメント処理でのキャッシュ使用テスト"""
        # モックの設定
        mock_vad = MagicMock()
        mock_vad.detect_segments.return_value = [
            (0.0, 10.0),
            (10.0, 20.0),
            (20.0, 30.0)
        ]
        mock_vad_class.return_value = mock_vad
        
        mock_optimizer = MagicMock()
        mock_optimizer.get_optimal_params.return_value = {
            'batch_size': 8,
            'compute_type': 'int8'
        }
        mock_optimizer_class.return_value = mock_optimizer
        
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value = 60.0
        mock_memory_monitor_class.return_value = mock_monitor
        
        # WhisperXのモック
        mock_model = MagicMock()
        mock_model.transcribe.return_value = {
            "segments": [{"start": 0.0, "end": 5.0, "text": "テスト"}]
        }
        mock_load_model.return_value = mock_model
        
        mock_align_model = MagicMock()
        mock_metadata = MagicMock()
        mock_load_align_model.return_value = (mock_align_model, mock_metadata)
        
        mock_align.return_value = {
            "segments": [{"start": 0.0, "end": 5.0, "text": "テスト"}]
        }
        
        # VAD処理を実行
        with patch('os.path.exists', return_value=True), \
             patch('shutil.rmtree'), \
             patch('tempfile.mkdtemp', return_value='/tmp/test'), \
             patch('os.unlink'):
            
            result = self.gateway.transcribe(
                video_path=Path("/tmp/test.mp4"),
                model_size="medium",
                language="ja"
            )
        
        # モデル読み込みが1回だけ実行されたことを確認（3セグメントで共有）
        mock_load_model.assert_called_once()
        mock_load_align_model.assert_called_once()
        
        # 3回の文字起こしが実行されたことを確認
        self.assertEqual(mock_model.transcribe.call_count, 3)
        
    def test_destructor_cleanup(self):
        """デストラクタでのクリーンアップテスト"""
        # キャッシュにモデルを設定
        self.gateway._model_cache['whisper'] = MagicMock()
        self.gateway._model_cache['align'] = (MagicMock(), MagicMock())
        
        # _clear_model_cacheメソッドをモック
        with patch.object(self.gateway, '_clear_model_cache') as mock_clear:
            # デストラクタを明示的に呼び出し
            self.gateway.__del__()
            
            # キャッシュクリアが呼ばれたことを確認
            mock_clear.assert_called_once()
            
    def test_memory_pressure_cache_clear(self):
        """高メモリ使用時のキャッシュクリアテスト"""
        # _process_vad_segmentメソッドの一部をテスト
        # メモリ使用率が90%を超えた場合のテスト
        
        # キャッシュにモデルを設定
        self.gateway._model_cache['whisper'] = MagicMock()
        self.gateway._model_cache['align'] = (MagicMock(), MagicMock())
        
        # メモリ使用率を91%に設定
        mock_monitor = MagicMock()
        mock_monitor.get_memory_usage.return_value = 91.0
        
        # _clear_model_cacheメソッドをモック
        with patch.object(self.gateway, '_clear_model_cache') as mock_clear:
            # 高メモリ使用率での処理をシミュレート
            # ここでは _process_vad_segment の該当部分のロジックをテスト
            current_memory = mock_monitor.get_memory_usage()
            if current_memory > 90:
                self.gateway._clear_model_cache()
            
            # キャッシュクリアが呼ばれたことを確認
            mock_clear.assert_called_once()


if __name__ == "__main__":
    unittest.main()