"""
自動最適化機能の結合テスト

メインアプリケーションとの統合をテストします。
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

# プロジェクトのルートをPythonパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from config import Config
from core.auto_optimizer import AutoOptimizer
from core.memory_monitor import MemoryMonitor


class TestAutoOptimizationIntegration(unittest.TestCase):
    """自動最適化機能の結合テスト"""

    def setUp(self):
        """テスト前の準備"""
        self.config = Config()
        self.model_size = "large-v3"

    def test_basic_initialization(self):
        """基本的な初期化テスト"""
        # AutoOptimizerの初期化
        optimizer = AutoOptimizer(self.model_size)
        self.assertIsNotNone(optimizer)

        # MemoryMonitorの初期化
        monitor = MemoryMonitor()
        self.assertIsNotNone(monitor)

        # メモリ使用率の取得
        memory_usage = monitor.get_memory_usage()
        self.assertGreaterEqual(memory_usage, 0)
        self.assertLessEqual(memory_usage, 100)

    def test_optimal_params_generation(self):
        """最適パラメータ生成のテスト"""
        optimizer = AutoOptimizer(self.model_size)
        monitor = MemoryMonitor()

        # 現在のメモリ使用率を取得
        current_memory = monitor.get_memory_usage()

        # 最適パラメータを取得
        params = optimizer.get_optimal_params(current_memory)

        # パラメータの検証
        self.assertIn("chunk_seconds", params)
        self.assertIn("max_workers", params)
        self.assertIn("batch_size", params)
        self.assertIn("align_chunk_seconds", params)

        # 値の妥当性チェック
        self.assertGreater(params["chunk_seconds"], 0)
        self.assertGreater(params["max_workers"], 0)
        self.assertGreater(params["batch_size"], 0)

    def test_memory_based_adjustment(self):
        """メモリ使用率に基づく調整テスト"""
        optimizer = AutoOptimizer("large-v3")

        # 異なるメモリ使用率での調整をテスト
        test_cases = [
            (30.0, "low"),  # 低使用率
            (60.0, "medium"),  # 中使用率
            (80.0, "high"),  # 高使用率
            (92.0, "critical"),  # 危機的使用率
        ]

        for memory_usage, expected_level in test_cases:
            params = optimizer.get_optimal_params(memory_usage)

            # メモリが逼迫するほどチャンクサイズが小さくなることを確認
            if expected_level == "critical":
                self.assertLessEqual(params["chunk_seconds"], 300)  # 5分以下
                self.assertEqual(params["max_workers"], 1)
            elif expected_level == "high":
                self.assertLessEqual(params["chunk_seconds"], 600)  # 10分以下

    @patch("core.memory_monitor.psutil.virtual_memory")
    def test_worker_transcribe_integration(self, mock_vm):
        """worker_transcribe.pyとの統合テスト"""
        # メモリ情報のモック
        mock_vm.return_value = Mock(percent=50.0, total=16 * 1024**3, available=8 * 1024**3)

        # 設定データの準備
        config_data = {
            "video_path": "/path/to/video.mp4",
            "model_size": "medium",
            "use_cache": False,
            "save_cache": False,
            "task_type": "separated_mode",
            "config": {
                "transcription": {
                    "use_api": False,
                    "api_provider": "openai",
                    "model_size": "medium",
                    "language": "ja",
                    "compute_type": "int8",
                    "sample_rate": 16000,
                    "isolation_mode": "none",
                }
            },
        }

        # worker_transcribeの動作をシミュレート
        from core.auto_optimizer import AutoOptimizer
        from core.memory_monitor import MemoryMonitor

        optimizer = AutoOptimizer(config_data["model_size"])
        monitor = MemoryMonitor()

        # パラメータ取得
        current_memory = monitor.get_memory_usage()
        params = optimizer.get_optimal_params(current_memory)

        # パラメータが適切に設定されることを確認
        self.assertIsNotNone(params)
        self.assertEqual(current_memory, 50.0)

    def test_profile_saving_loading(self):
        """プロファイルの保存と読み込みテスト"""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 一時的にホームディレクトリを変更
            from pathlib import Path

            original_home = Path.home()

            # HOME環境変数とPath.homeの両方をパッチ
            with patch.object(Path, "home", return_value=Path(temp_dir)):
                optimizer = AutoOptimizer("small")

                # 診断フェーズを完了させる
                for i in range(optimizer.DIAGNOSTIC_CHUNKS_COUNT):
                    optimizer.get_optimal_params(50.0 + i)

                # 診断フェーズ完了後の初期パラメータを取得
                initial_params = optimizer.get_optimal_params(50.0)
                initial_chunk = initial_params["chunk_seconds"]

                # 成功した実行のプロファイルを保存
                params = {
                    "chunk_seconds": 1500,  # 25分（初期値とは異なる値）
                    "max_workers": 3,
                    "batch_size": 10,
                    "align_chunk_seconds": 1800,
                }
                metrics = {
                    "completed": True,
                    "avg_memory": 45.0,  # 低メモリ使用
                    "processing_time": 800.0,
                    "segments_count": 100,
                    "successful_runs": 1,
                }

                optimizer.save_successful_run(params, metrics)

                # 新しいインスタンスで読み込みテスト
                new_optimizer = AutoOptimizer("small")

                # 新しいインスタンスでも診断フェーズを完了させる
                for i in range(new_optimizer.DIAGNOSTIC_CHUNKS_COUNT):
                    new_optimizer.get_optimal_params(50.0 + i)

                # 同じメモリ使用率でパラメータを取得
                new_params = new_optimizer.get_optimal_params(50.0)

                # プロファイルが反映されて、保存された値が使用されることを確認
                # (プロファイルの読み込みによって初期値が変更されているはず)
                self.assertEqual(new_params["chunk_seconds"], 1500)

    def test_ui_components_integration(self):
        """UIコンポーネントとの統合テスト"""
        # StreamlitのモックをセットアップしてUIコンポーネントをテスト
        with (
            patch("streamlit.info"),
            patch("streamlit.expander"),
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.metric"),
        ):

            # カラムのモック
            mock_col1 = MagicMock()
            mock_col2 = MagicMock()
            mock_columns.return_value = [mock_col1, mock_col2]

            from ui.components import show_optimization_status

            # 関数が正常に動作することを確認
            show_optimization_status()

    def test_error_handling_integration(self):
        """エラーハンドリングの統合テスト"""
        # メモリ取得エラーのシミュレート
        with patch("psutil.virtual_memory", side_effect=Exception("Memory error")):
            monitor = MemoryMonitor()
            usage = monitor.get_memory_usage()

            # フォールバック値が返されることを確認
            self.assertEqual(usage, 50.0)

            # AutoOptimizerがエラーを適切に処理することを確認
            optimizer = AutoOptimizer("base")
            params = optimizer.get_optimal_params(usage)
            self.assertIsNotNone(params)

    def test_config_integration(self):
        """config.pyとの統合テスト"""
        # 設定が正しく読み込まれることを確認
        config = Config()

        # 自動最適化で削除された設定が存在しないことを確認
        self.assertFalse(hasattr(config.transcription, "chunk_seconds"))
        self.assertFalse(hasattr(config.transcription, "max_workers"))
        self.assertFalse(hasattr(config.transcription, "batch_size"))
        self.assertFalse(hasattr(config.transcription, "force_separated_mode"))

        # 必要な設定は残っていることを確認
        self.assertTrue(hasattr(config.transcription, "model_size"))
        self.assertTrue(hasattr(config.transcription, "language"))
        self.assertTrue(hasattr(config.transcription, "use_api"))

    def test_docker_environment_integration(self):
        """Docker環境での統合テスト"""
        with patch("os.path.exists") as mock_exists:
            # Docker環境をシミュレート
            mock_exists.return_value = True  # /.dockerenvが存在

            monitor = MemoryMonitor()
            self.assertTrue(monitor.is_docker)

            # Dockerでもメモリ情報が取得できることを確認
            usage = monitor.get_memory_usage()
            self.assertGreaterEqual(usage, 0)

    def test_performance_tracking(self):
        """パフォーマンス追跡の統合テスト"""
        optimizer = AutoOptimizer("medium")

        # 複数回の実行をシミュレート
        for i in range(3):
            params = optimizer.get_optimal_params(50.0 + i * 10)
            metrics = {
                "completed": True,
                "avg_memory": 60.0 + i * 5,
                "processing_time": 600.0 + i * 100,
                "segments_count": 100 + i * 20,
            }
            optimizer.save_successful_run(params, metrics)

        # 調整が行われることを確認
        final_params = optimizer.get_optimal_params(65.0)
        self.assertIsNotNone(final_params)


if __name__ == "__main__":
    unittest.main()
