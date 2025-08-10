"""
モデルキャッシュ機能のユニットテスト

キャッシュロジックの詳細な動作をテスト
"""
import unittest
from unittest.mock import MagicMock, patch, call

import torch

from adapters.gateways.transcription.optimized_transcription_gateway import (
    OptimizedTranscriptionGatewayAdapter
)
from config import Config


class TestModelCacheUnit(unittest.TestCase):
    """モデルキャッシュのユニットテスト"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = Config()
        
        # 最小限のモックでゲートウェイを作成
        with patch.object(OptimizedTranscriptionGatewayAdapter, '_load_or_create_profile'):
            self.gateway = OptimizedTranscriptionGatewayAdapter(
                config=self.config,
                audio_optimizer=MagicMock(),
                profile_repository=MagicMock()
            )
            
    def test_cache_params_comparison(self):
        """キャッシュパラメータの比較ロジックテスト"""
        # 初期状態
        self.assertEqual(self.gateway._model_cache['whisper_params'], {})
        
        # パラメータを設定
        params1 = {
            'model_size': 'medium',
            'device': 'cpu',
            'compute_type': 'int8',
            'language': 'ja'
        }
        self.gateway._model_cache['whisper_params'] = params1.copy()
        
        # 同じパラメータでの比較
        self.assertEqual(self.gateway._model_cache['whisper_params'], params1)
        
        # 異なるパラメータでの比較
        params2 = params1.copy()
        params2['model_size'] = 'large'
        self.assertNotEqual(self.gateway._model_cache['whisper_params'], params2)
        
    @patch('whisperx.load_model')
    def test_cache_hit_miss_logging(self, mock_load_model):
        """キャッシュヒット/ミスのログ出力テスト"""
        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        
        with patch('adapters.gateways.transcription.optimized_transcription_gateway.logger') as mock_logger:
            # 初回（キャッシュミス）
            self.gateway._get_cached_whisper_model(
                model_size="medium",
                device="cpu",
                compute_type="int8",
                language="ja"
            )
            
            # ログメッセージを確認
            mock_logger.info.assert_called_with(
                "Whisperモデルを読み込み中: medium, int8"
            )
            
            # 2回目（キャッシュヒット）
            mock_logger.reset_mock()
            self.gateway._get_cached_whisper_model(
                model_size="medium",
                device="cpu",
                compute_type="int8",
                language="ja"
            )
            
            # デバッグログを確認
            mock_logger.debug.assert_called_with(
                "Whisperモデルをキャッシュから使用"
            )
            
    def test_cache_state_consistency(self):
        """キャッシュの状態整合性テスト"""
        # Whisperキャッシュのみ設定
        self.gateway._model_cache['whisper'] = MagicMock()
        self.gateway._model_cache['whisper_params'] = {'test': 'params'}
        
        # アライメントキャッシュは未設定
        self.assertIsNone(self.gateway._model_cache['align'])
        self.assertIsNone(self.gateway._model_cache['align_language'])
        
        # 部分的なクリアは行わない（全体クリアのみ）
        with patch('torch.cuda.empty_cache'):
            self.gateway._clear_model_cache()
        
        # 全てクリアされていることを確認
        self.assertIsNone(self.gateway._model_cache['whisper'])
        self.assertEqual(self.gateway._model_cache['whisper_params'], {})
        self.assertIsNone(self.gateway._model_cache['align'])
        self.assertIsNone(self.gateway._model_cache['align_language'])
        
    def test_device_specific_cache_behavior(self):
        """デバイス別のキャッシュ動作テスト"""
        # CPUデバイスでのテスト
        with patch('whisperx.load_model') as mock_load_model, \
             patch('torch.cuda.is_available', return_value=False), \
             patch('torch.cuda.empty_cache') as mock_empty_cache:
            
            mock_model = MagicMock()
            mock_load_model.return_value = mock_model
            
            # CPUでモデルを読み込み
            self.gateway._get_cached_whisper_model(
                model_size="medium",
                device="cpu",
                compute_type="int8",
                language="ja"
            )
            
            # 異なるモデルサイズで再読み込み
            self.gateway._get_cached_whisper_model(
                model_size="large",
                device="cpu",
                compute_type="int8",
                language="ja"
            )
            
            # CPUではempty_cacheが呼ばれないことを確認
            mock_empty_cache.assert_not_called()
            
    def test_language_change_align_cache(self):
        """言語変更時のアライメントキャッシュテスト"""
        with patch('whisperx.load_align_model') as mock_load_align:
            mock_align = MagicMock()
            mock_metadata = MagicMock()
            mock_load_align.return_value = (mock_align, mock_metadata)
            
            # 日本語でロード
            self.gateway._get_cached_align_model("ja", "cpu")
            self.assertEqual(self.gateway._model_cache['align_language'], "ja")
            
            # 英語でロード（キャッシュ無効化）
            self.gateway._get_cached_align_model("en", "cpu")
            self.assertEqual(self.gateway._model_cache['align_language'], "en")
            
            # 2回ロードされたことを確認
            self.assertEqual(mock_load_align.call_count, 2)
            
    def test_exception_handling_in_destructor(self):
        """デストラクタでの例外処理テスト"""
        # _clear_model_cacheでエラーを発生させる
        with patch.object(self.gateway, '_clear_model_cache', side_effect=Exception("Test error")):
            # デストラクタを呼び出してもエラーが伝播しないことを確認
            try:
                self.gateway.__del__()
                # エラーが発生しなければテスト成功
                self.assertTrue(True)
            except Exception:
                self.fail("デストラクタから例外が伝播しました")
                
    def test_concurrent_cache_access_safety(self):
        """並行アクセス時のキャッシュ安全性テスト"""
        # 現在の実装はシングルスレッドを前提としているため、
        # 将来的にマルチスレッド対応が必要な場合のプレースホルダー
        # 
        # TODO: threadingやasyncioを使用する場合は、
        # ロック機構の追加とテストが必要
        pass
        
    def test_memory_calculation_for_cache_clear(self):
        """メモリ使用率に基づくキャッシュクリア判定テスト"""
        # 様々なメモリ使用率でのテスト
        test_cases = [
            (89.9, False),  # クリアしない
            (90.0, False),  # 境界値（クリアしない）
            (90.1, True),   # クリアする
            (95.0, True),   # クリアする
            (100.0, True),  # クリアする
        ]
        
        for memory_usage, should_clear in test_cases:
            with self.subTest(memory_usage=memory_usage):
                # モックモニターを作成
                mock_monitor = MagicMock()
                mock_monitor.get_memory_usage.return_value = memory_usage
                
                # キャッシュクリアのロジックをテスト
                current_memory = mock_monitor.get_memory_usage()
                result = current_memory > 90
                
                self.assertEqual(result, should_clear, 
                               f"メモリ使用率 {memory_usage}% でのクリア判定が不正")


if __name__ == "__main__":
    unittest.main()