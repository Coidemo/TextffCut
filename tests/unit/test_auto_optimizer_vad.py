"""
VADベース実装後のAutoOptimizerのユニットテスト
30秒制限を考慮したテスト
"""

import unittest
from unittest.mock import MagicMock, patch

from core.auto_optimizer import AutoOptimizer
from core.constants import ChunkSizeLimits, MemoryThresholds


class TestAutoOptimizerVAD(unittest.TestCase):
    """VADベース実装後のAutoOptimizerテスト"""

    def setUp(self):
        """テストのセットアップ"""
        self.optimizer = AutoOptimizer("medium")

    def test_chunk_size_limits_30_seconds(self):
        """チャンクサイズが30秒制限内であることを確認"""
        # 診断フェーズを完了させる
        for i in range(ChunkSizeLimits.DIAGNOSTIC_COUNT):
            params = self.optimizer.get_optimal_params(60.0 + i * 2)

        # 通常フェーズでチェック
        params = self.optimizer.get_optimal_params(90.0)  # 高メモリ
        self.assertLessEqual(params["chunk_seconds"], ChunkSizeLimits.MAXIMUM)  # 30秒以下
        self.assertGreaterEqual(params["chunk_seconds"], ChunkSizeLimits.ABSOLUTE_MINIMUM)  # 5秒以上

    def test_diagnostic_phase_30_seconds(self):
        """診断フェーズで30秒チャンクを使用することを確認"""
        # 診断フェーズ中
        params = self.optimizer.get_optimal_params(50.0)
        self.assertEqual(params["chunk_seconds"], ChunkSizeLimits.DIAGNOSTIC_CHUNK)  # 30秒
        self.assertEqual(params["batch_size"], 4)  # 診断中は最大4
        self.assertEqual(params["compute_type"], "int8")  # 診断中は常にint8

    def test_compute_type_dynamic_selection(self):
        """メモリ使用率に基づくcompute_typeの動的選択"""
        # 診断フェーズを完了させる
        for i in range(ChunkSizeLimits.DIAGNOSTIC_COUNT):
            self.optimizer.get_optimal_params(50.0 + i * 5)

        # 高メモリ使用率（80%以上）
        params = self.optimizer.get_optimal_params(85.0)
        self.assertEqual(params["compute_type"], "int8")

        # 中メモリ使用率（60-70%）
        params = self.optimizer.get_optimal_params(65.0)
        self.assertEqual(params["compute_type"], "float16")  # mediumモデル

        # 低メモリ使用率（60%未満）
        params = self.optimizer.get_optimal_params(50.0)
        self.assertEqual(params["compute_type"], "float16")  # mediumモデルはfloat16

    def test_compute_type_for_different_models(self):
        """モデルサイズによるcompute_type選択の違い"""
        # Baseモデル - 低メモリでfloat32可能
        optimizer_base = AutoOptimizer("base")
        for i in range(ChunkSizeLimits.DIAGNOSTIC_COUNT):
            optimizer_base.get_optimal_params(50.0)
        params = optimizer_base.get_optimal_params(40.0)
        self.assertEqual(params["compute_type"], "float32")

        # Large-v3モデル - 常にint8推奨
        optimizer_large = AutoOptimizer("large-v3")
        for i in range(ChunkSizeLimits.DIAGNOSTIC_COUNT):
            optimizer_large.get_optimal_params(50.0)
        params = optimizer_large.get_optimal_params(65.0)
        self.assertEqual(params["compute_type"], "int8")

    def test_vad_based_parameters(self):
        """VADベース処理のパラメータ調整"""
        # 診断フェーズを完了
        for i in range(ChunkSizeLimits.DIAGNOSTIC_COUNT):
            self.optimizer.get_optimal_params(50.0 + i * 3)

        # VADベースのため、ワーカー数は1に制限される
        params = self.optimizer.get_optimal_params(50.0)
        self.assertLessEqual(params["max_workers"], 2)  # VADベースでは並列度を抑える

    def test_emergency_mode_with_vad(self):
        """緊急モードでの30秒制限内の調整"""
        # 診断フェーズをスキップ
        self.optimizer.diagnostic_mode = False

        # 緊急モード（90%以上）
        params = self.optimizer.get_optimal_params(92.0)

        # 30秒制限を超えないこと
        self.assertLessEqual(params["chunk_seconds"], ChunkSizeLimits.MAXIMUM)
        # 緊急時の最小値以上
        self.assertGreaterEqual(params["chunk_seconds"], ChunkSizeLimits.EMERGENCY_MINIMUM)
        # compute_typeはint8
        self.assertEqual(params["compute_type"], "int8")
        # バッチサイズは最小
        self.assertEqual(params["batch_size"], 1)


if __name__ == "__main__":
    unittest.main()
