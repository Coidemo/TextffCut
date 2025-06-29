#!/usr/bin/env python3
"""
アライメント診断モジュールの単体テスト
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.alignment_diagnostics import AlignmentDiagnostics, DiagnosticResult
from core.constants import BatchSizeLimits


class TestDiagnosticResult(unittest.TestCase):
    """DiagnosticResultクラスのテスト"""

    def test_diagnostic_result_creation(self) -> None:
        """診断結果の作成テスト"""
        result = DiagnosticResult(
            optimal_batch_size=8,
            model_memory_usage_mb=300.0,
            base_memory_percent=50.0,
            estimated_memory_per_batch=56.0,
            available_memory_gb=8.0,
            segment_count=100,
            recommendations=["推奨事項1", "推奨事項2"],
            warnings=["警告1"],
        )

        self.assertEqual(result.optimal_batch_size, 8)
        self.assertEqual(result.model_memory_usage_mb, 300.0)
        self.assertEqual(result.base_memory_percent, 50.0)
        self.assertEqual(len(result.recommendations), 2)
        self.assertEqual(len(result.warnings), 1)

    def test_get_summary(self) -> None:
        """サマリー生成のテスト"""
        result = DiagnosticResult(
            optimal_batch_size=4,
            model_memory_usage_mb=500.0,
            base_memory_percent=60.0,
            estimated_memory_per_batch=40.0,
            available_memory_gb=4.0,
            segment_count=50,
            recommendations=["メモリを解放してください"],
            warnings=["メモリ不足"],
        )

        summary = result.get_summary()
        self.assertIn("診断結果サマリー", summary)
        self.assertIn("最適バッチサイズ: 4", summary)
        self.assertIn("メモリを解放してください", summary)
        self.assertIn("メモリ不足", summary)


class TestAlignmentDiagnostics(unittest.TestCase):
    """AlignmentDiagnosticsクラスのテスト"""

    def setUp(self) -> None:
        """テスト前の準備"""
        self.config = Config()
        self.diagnostics = AlignmentDiagnostics("medium", self.config)

    def test_initialization(self) -> None:
        """初期化のテスト"""
        # 正常なモデルサイズ
        diag = AlignmentDiagnostics("large-v3", self.config)
        self.assertEqual(diag.model_size, "large-v3")

        # 不明なモデルサイズ
        with patch("core.alignment_diagnostics.logger") as mock_logger:
            diag = AlignmentDiagnostics("unknown", self.config)
            self.assertEqual(diag.model_size, "base")
            mock_logger.warning.assert_called()

    @patch("psutil.virtual_memory")
    def test_estimate_optimal_batch_size(self, mock_vmem) -> None:
        """バッチサイズ推定のテスト"""
        # メモリ情報のモック
        mock_vmem.return_value = Mock(available=8 * 1024**3, total=16 * 1024**3, percent=50.0)  # 8GB  # 16GB

        # 通常のケース
        batch_size = self.diagnostics.estimate_optimal_batch_size(8.0, 100)
        self.assertGreater(batch_size, 0)
        self.assertLessEqual(batch_size, BatchSizeLimits.MAXIMUM)

        # 大量セグメント
        batch_size = self.diagnostics.estimate_optimal_batch_size(8.0, 1000)
        self.assertGreater(batch_size, 0)

        # メモリ不足
        mock_vmem.return_value = Mock(available=2 * 1024**3, total=16 * 1024**3, percent=87.5)  # 2GB
        batch_size = self.diagnostics.estimate_optimal_batch_size(2.0, 100)
        self.assertEqual(batch_size, BatchSizeLimits.MINIMUM)

    def test_estimate_model_memory_usage(self) -> None:
        """モデルメモリ使用量推定のテスト"""
        # mediumモデル
        memory = self.diagnostics._estimate_model_memory_usage()
        self.assertEqual(memory, 300.0)

        # large-v3モデル
        diag = AlignmentDiagnostics("large-v3", self.config)
        memory = diag._estimate_model_memory_usage()
        self.assertEqual(memory, 500.0)

    @patch("psutil.virtual_memory")
    @patch("core.alignment_diagnostics.AlignmentDiagnostics._measure_model_memory_usage")
    def test_run_diagnostics_without_test(self, mock_measure, mock_vmem) -> None:
        """診断実行のテスト（モデルロードなし）"""
        # メモリ情報のモック
        mock_vmem.return_value = Mock(available=8 * 1024**3, total=16 * 1024**3, percent=50.0)

        # メモリモニターのモック
        with patch.object(self.diagnostics.memory_monitor, "get_memory_usage", return_value=50.0):
            result = self.diagnostics.run_diagnostics(segment_count=100, language="ja", test_alignment=False)

        # 結果の検証
        self.assertIsInstance(result, DiagnosticResult)
        self.assertGreater(result.optimal_batch_size, 0)
        self.assertEqual(result.base_memory_percent, 50.0)
        self.assertEqual(result.segment_count, 100)

        # モデル測定が呼ばれないことを確認
        mock_measure.assert_not_called()

    @patch("psutil.virtual_memory")
    def test_calculate_optimal_batch_size(self, mock_vmem) -> None:
        """最適バッチサイズ計算の詳細テスト"""
        mock_vmem.return_value = Mock(total=16 * 1024**3)

        # 十分なメモリがある場合
        batch_size = self.diagnostics._calculate_optimal_batch_size(
            available_memory_gb=8.0, segment_count=100, model_memory_mb=300.0, base_memory_percent=40.0
        )
        self.assertGreater(batch_size, BatchSizeLimits.MINIMUM)

        # メモリが限られている場合
        batch_size = self.diagnostics._calculate_optimal_batch_size(
            available_memory_gb=2.0, segment_count=100, model_memory_mb=300.0, base_memory_percent=70.0
        )
        # BatchSizeLimits.EMERGENCYより大きい可能性があるため、より適切なチェック
        self.assertLessEqual(batch_size, BatchSizeLimits.DEFAULT)

        # メモリ不足の場合
        batch_size = self.diagnostics._calculate_optimal_batch_size(
            available_memory_gb=1.0, segment_count=100, model_memory_mb=500.0, base_memory_percent=80.0
        )
        self.assertEqual(batch_size, BatchSizeLimits.MINIMUM)

    def test_generate_recommendations(self) -> None:
        """推奨事項生成のテスト"""
        # メモリ不足のケース
        recs, warns = self.diagnostics._generate_recommendations(
            available_memory_gb=4.0, segment_count=1500, optimal_batch_size=2, base_memory_percent=85.0
        )

        self.assertGreater(len(warns), 0)
        self.assertGreater(len(recs), 0)

        # 正常なケース
        recs, warns = self.diagnostics._generate_recommendations(
            available_memory_gb=16.0, segment_count=100, optimal_batch_size=16, base_memory_percent=40.0
        )

        self.assertEqual(len(warns), 0)
        self.assertEqual(len(recs), 0)

    def test_large_v3_memory_constraints(self) -> None:
        """large-v3モデルの特別な制約テスト"""
        diag = AlignmentDiagnostics("large-v3", self.config)

        # メモリ不足の警告
        recs, warns = diag._generate_recommendations(
            available_memory_gb=8.0, segment_count=100, optimal_batch_size=4, base_memory_percent=50.0
        )

        # large-v3用の警告があることを確認
        self.assertTrue(any("large-v3" in warn for warn in warns))
        self.assertTrue(any("medium" in rec for rec in recs))


class TestIntegration(unittest.TestCase):
    """統合テスト"""

    @patch("psutil.virtual_memory")
    @patch("core.alignment_processor.AlignmentProcessor")
    def test_measure_model_memory_usage_integration(self, mock_processor_class, mock_vmem) -> None:
        """実際のモデル測定の統合テスト"""
        # メモリ情報のモック
        mock_vmem.return_value = Mock(total=16 * 1024**3, available=8 * 1024**3)

        # AlignmentProcessorのモック
        mock_processor = Mock()
        mock_processor_class.return_value = mock_processor

        config = Config()
        diagnostics = AlignmentDiagnostics("medium", config)

        # メモリ使用量のシミュレーション
        with patch.object(diagnostics.memory_monitor, "get_memory_usage", side_effect=[50.0, 52.0]):  # 2%増加
            memory_mb = diagnostics._measure_model_memory_usage("ja")

        # 結果の検証
        self.assertGreater(memory_mb, 0)
        mock_processor._load_align_model.assert_called_once_with("ja")


if __name__ == "__main__":
    unittest.main(verbosity=2)
