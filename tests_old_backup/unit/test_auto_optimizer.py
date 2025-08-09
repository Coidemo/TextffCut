"""
AutoOptimizerの単体テスト

エラーケースや境界値条件を含む包括的なテスト
"""

import os

# プロジェクトのルートをPythonパスに追加
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.auto_optimizer import AutoOptimizer


class TestAutoOptimizer(unittest.TestCase):
    """AutoOptimizerの単体テスト"""

    def setUp(self):
        """テスト前の準備"""
        # 一時ディレクトリを使用してプロファイルの干渉を防ぐ
        self.temp_dir = tempfile.mkdtemp()
        self.profile_path_patch = patch.object(Path, "home", return_value=Path(self.temp_dir))
        self.profile_path_patch.start()

    def tearDown(self):
        """テスト後のクリーンアップ"""
        self.profile_path_patch.stop()
        # 一時ディレクトリの削除
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization_with_valid_model(self):
        """正常なモデルサイズでの初期化"""
        optimizer = AutoOptimizer("medium", 75.0)
        self.assertEqual(optimizer.model_size, "medium")
        self.assertEqual(optimizer.target_memory_percent, 75.0)

    def test_initialization_with_invalid_model(self):
        """無効なモデルサイズでの初期化（フォールバック）"""
        optimizer = AutoOptimizer("invalid_model", 75.0)
        self.assertEqual(optimizer.model_size, "base")  # baseにフォールバック

    def test_target_memory_bounds(self):
        """目標メモリ使用率の境界値テスト"""
        # 下限テスト
        optimizer = AutoOptimizer("base", 30.0)
        self.assertEqual(optimizer.target_memory_percent, 50.0)  # 50%に制限

        # 上限テスト
        optimizer = AutoOptimizer("base", 95.0)
        self.assertEqual(optimizer.target_memory_percent, 90.0)  # 90%に制限

    def test_get_optimal_params_normal_case(self):
        """通常ケースでのパラメータ最適化"""
        optimizer = AutoOptimizer("medium", 75.0)

        # メモリに余裕がある場合
        params = optimizer.get_optimal_params(60.0)
        self.assertIn("chunk_seconds", params)
        self.assertIn("max_workers", params)
        self.assertGreater(params["chunk_seconds"], 0)

    def test_get_optimal_params_memory_pressure(self):
        """メモリ逼迫時のパラメータ調整"""
        optimizer = AutoOptimizer("medium", 75.0)

        # 初期パラメータを取得
        initial_params = optimizer.current_params.copy()

        # 高メモリ使用率でパラメータ取得
        params = optimizer.get_optimal_params(88.0)

        # チャンクサイズが減少していることを確認
        self.assertLess(params["chunk_seconds"], initial_params["chunk_seconds"])

    def test_get_optimal_params_emergency(self):
        """緊急時（メモリ90%超）のパラメータ調整"""
        optimizer = AutoOptimizer("large", 75.0)

        # 緊急レベルのメモリ使用率
        params = optimizer.get_optimal_params(92.0)

        # 最小値に近い値になっていることを確認
        self.assertLessEqual(params["chunk_seconds"], 600)  # 10分以下
        self.assertEqual(params["max_workers"], 1)  # 最小ワーカー

    def test_get_optimal_params_invalid_input(self):
        """無効な入力でのエラーハンドリング"""
        optimizer = AutoOptimizer("base", 75.0)

        # 文字列入力
        params = optimizer.get_optimal_params("invalid")
        self.assertIsInstance(params, dict)

        # None入力
        params = optimizer.get_optimal_params(None)
        self.assertIsInstance(params, dict)

        # 負の値
        params = optimizer.get_optimal_params(-50.0)
        self.assertIsInstance(params, dict)

        # 100%超
        params = optimizer.get_optimal_params(150.0)
        self.assertIsInstance(params, dict)

    def test_chunk_size_limits(self):
        """チャンクサイズの制限テスト"""
        optimizer = AutoOptimizer("base", 75.0)

        # 診断フェーズを完了させる
        for i in range(optimizer.DIAGNOSTIC_CHUNKS_COUNT):
            params = optimizer.get_optimal_params(60.0 + i * 2)  # メモリを徐々に増加
            if optimizer.diagnostic_mode:
                # 診断フェーズ中は30秒のチャンク
                self.assertEqual(params["chunk_seconds"], optimizer.DIAGNOSTIC_CHUNK_SECONDS)

        # 診断フェーズ完了後、複数回の調整でも制限内に収まることを確認
        for memory in [95.0, 98.0, 99.0]:
            params = optimizer.get_optimal_params(memory)
            self.assertGreaterEqual(params["chunk_seconds"], 180)  # 3分以上
            self.assertLessEqual(params["chunk_seconds"], 1800)  # 30分以下

    def test_profile_saving_and_loading(self):
        """プロファイルの保存と読み込み"""
        # 最初のオプティマイザでプロファイル保存
        optimizer1 = AutoOptimizer("small", 75.0)
        test_params = {"chunk_seconds": 1000, "align_chunk_seconds": 1500, "max_workers": 2, "batch_size": 8}
        test_metrics = {"completed": True, "avg_memory": 70.0, "successful_runs": 5}
        optimizer1.save_successful_run(test_params, test_metrics)

        # 新しいオプティマイザで読み込み
        optimizer2 = AutoOptimizer("small", 75.0)

        # 保存したパラメータが読み込まれていることを確認
        self.assertEqual(optimizer2.current_params["chunk_seconds"], 1000)

    def test_profile_corruption_handling(self):
        """破損したプロファイルファイルの処理"""
        # 破損したプロファイルを作成
        profile_dir = Path(self.temp_dir) / ".textffcut"
        profile_dir.mkdir(exist_ok=True)
        profile_path = profile_dir / "optimizer_profile_base.json"

        with open(profile_path, "w") as f:
            f.write("invalid json content {]}")

        # エラーなく初期化できることを確認
        optimizer = AutoOptimizer("base", 75.0)
        self.assertIsNotNone(optimizer.current_params)

    def test_metrics_validation(self):
        """メトリクス検証のテスト"""
        optimizer = AutoOptimizer("medium", 75.0)

        # 無効なメトリクス（未完了）
        invalid_metrics = {"completed": False, "avg_memory": 70.0}
        optimizer.save_successful_run({}, invalid_metrics)

        # プロファイルが保存されていないことを確認
        profile_path = Path(self.temp_dir) / ".textffcut" / "optimizer_profile_medium.json"
        self.assertFalse(profile_path.exists())

    def test_adjustment_history(self):
        """調整履歴の管理"""
        optimizer = AutoOptimizer("base", 75.0)

        # 複数回調整
        for i in range(25):
            optimizer.get_optimal_params(60.0 + i)

        # 履歴が20件に制限されていることを確認
        self.assertLessEqual(len(optimizer.adjustment_history), 20)

    def test_memory_velocity_calculation(self):
        """メモリ変化速度の計算"""
        optimizer = AutoOptimizer("medium", 75.0)

        # 初回（速度0）
        optimizer.get_optimal_params(70.0)

        # 急上昇
        params1 = optimizer.get_optimal_params(85.0)  # +15%

        # 緩やかな上昇
        params2 = optimizer.get_optimal_params(87.0)  # +2%

        # 速度による調整の違いを確認
        self.assertIsNotNone(params1)
        self.assertIsNotNone(params2)

    def test_concurrent_profile_access(self):
        """複数プロセスからの同時アクセス（ファイルロックなし）"""
        # 2つのオプティマイザが同時にプロファイルを書き込む
        optimizer1 = AutoOptimizer("base", 75.0)
        optimizer2 = AutoOptimizer("base", 75.0)

        metrics = {"completed": True, "avg_memory": 70.0}

        # 両方から保存（エラーが出ないことを確認）
        optimizer1.save_successful_run(optimizer1.current_params, metrics)
        optimizer2.save_successful_run(optimizer2.current_params, metrics)

    def test_get_status(self):
        """ステータス取得のテスト"""
        optimizer = AutoOptimizer("large", 80.0)

        # 診断フェーズ中のステータス確認
        optimizer.get_optimal_params(75.0)
        status = optimizer.get_status()
        self.assertEqual(status["model_size"], "large")
        self.assertEqual(status["target_memory"], 80.0)
        self.assertIn("current_params", status)
        self.assertTrue(status["diagnostic_mode"])
        self.assertEqual(status["diagnostic_progress"], "1/3")

        # 診断フェーズを完了させる
        for i in range(optimizer.DIAGNOSTIC_CHUNKS_COUNT - 1):
            optimizer.get_optimal_params(75.0 + i)

        # 診断フェーズ完了後のステータス確認
        optimizer.get_optimal_params(80.0)
        status = optimizer.get_status()
        self.assertFalse(status["diagnostic_mode"])
        self.assertIsNotNone(status["last_adjustment"])

    def test_all_model_sizes(self):
        """全モデルサイズでの初期化テスト"""
        model_sizes = ["base", "small", "medium", "large", "large-v3"]

        for model_size in model_sizes:
            optimizer = AutoOptimizer(model_size, 75.0)
            self.assertEqual(optimizer.model_size, model_size)
            self.assertIsNotNone(optimizer.current_params)
            self.assertGreater(optimizer.current_params["chunk_seconds"], 0)

    def test_diagnostic_phase(self):
        """診断フェーズのテスト"""
        optimizer = AutoOptimizer("medium", 75.0)

        # 診断フェーズ開始時の状態確認
        self.assertTrue(optimizer.diagnostic_mode)
        self.assertEqual(optimizer.diagnostic_chunks_processed, 0)

        # 診断フェーズ中のパラメータ確認
        for i in range(optimizer.DIAGNOSTIC_CHUNKS_COUNT):
            params = optimizer.get_optimal_params(50.0 + i * 5)

            if i < optimizer.DIAGNOSTIC_CHUNKS_COUNT - 1:
                # 診断中は30秒チャンク
                self.assertEqual(params["chunk_seconds"], 30)
                self.assertEqual(params["max_workers"], 1)
                self.assertLessEqual(params["batch_size"], 4)
            else:
                # 最後のチャンクで診断完了
                self.assertFalse(optimizer.diagnostic_mode)
                self.assertGreater(params["chunk_seconds"], 30)

    def test_diagnostic_phase_memory_prediction(self):
        """診断フェーズのメモリ予測テスト"""
        optimizer = AutoOptimizer("base", 75.0)

        # メモリが徐々に増加するケース
        memory_values = [40.0, 42.0, 44.0]  # 2%ずつ増加

        for _, memory in enumerate(memory_values):
            optimizer.get_optimal_params(memory)

        # 診断完了後、適切なパラメータが予測されているか
        self.assertFalse(optimizer.diagnostic_mode)
        self.assertGreater(optimizer.diagnostic_data["memory_growth_rate"], 0)

        # 予測されたチャンクサイズが妥当か
        final_params = optimizer.current_params
        self.assertGreater(final_params["chunk_seconds"], 180)
        self.assertLess(final_params["chunk_seconds"], 1800)

    def test_reset_diagnostic_mode(self):
        """診断モードのリセットテスト"""
        optimizer = AutoOptimizer("small", 75.0)

        # 診断フェーズを進める
        optimizer.get_optimal_params(50.0)
        optimizer.get_optimal_params(52.0)

        self.assertEqual(optimizer.diagnostic_chunks_processed, 2)

        # リセット
        optimizer.reset_diagnostic_mode()

        # リセット後の状態確認
        self.assertTrue(optimizer.diagnostic_mode)
        self.assertEqual(optimizer.diagnostic_chunks_processed, 0)
        self.assertEqual(len(optimizer.diagnostic_data["memory_samples"]), 0)


if __name__ == "__main__":
    unittest.main()
