"""
MemoryMonitorの単体テスト

Docker環境検出やエラーハンドリングを含むテスト
"""

import os

# プロジェクトのルートをPythonパスに追加
import sys
import time
import unittest
from unittest.mock import Mock, mock_open, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from core.memory_monitor import MemoryMonitor


class TestMemoryMonitor(unittest.TestCase):
    """MemoryMonitorの単体テスト"""

    def test_initialization(self):
        """正常な初期化"""
        monitor = MemoryMonitor(history_size=50)
        self.assertEqual(monitor.history.maxlen, 50)

    @patch("psutil.virtual_memory")
    def test_get_memory_usage_normal(self, mock_vm):
        """通常のメモリ使用率取得"""
        # psutilのモック
        mock_vm.return_value = Mock(percent=65.5, total=16 * 1024**3, available=5.5 * 1024**3)

        monitor = MemoryMonitor()
        usage = monitor.get_memory_usage()

        self.assertEqual(usage, 65.5)
        self.assertEqual(len(monitor.history), 1)

    @patch("psutil.virtual_memory")
    def test_get_memory_usage_error_handling(self, mock_vm):
        """メモリ取得時のエラーハンドリング"""
        # psutilでエラーを発生させる
        mock_vm.side_effect = Exception("Memory access error")

        monitor = MemoryMonitor()
        usage = monitor.get_memory_usage()

        # デフォルト値が返されることを確認
        self.assertEqual(usage, 50.0)

    @patch("core.memory_monitor.PSUTIL_AVAILABLE", False)
    def test_no_psutil_fallback(self):
        """psutil未インストール時のフォールバック"""
        monitor = MemoryMonitor()

        usage = monitor.get_memory_usage()
        self.assertEqual(usage, 50.0)

        stats = monitor.get_memory_stats()
        self.assertEqual(stats["percent"], 50.0)
        self.assertEqual(stats["total_gb"], 8.0)

    @patch("os.path.exists")
    def test_docker_detection_dockerenv(self, mock_exists):
        """/.dockerenvによるDocker検出"""
        mock_exists.return_value = True

        monitor = MemoryMonitor()
        self.assertTrue(monitor.is_docker)

    @patch("builtins.open", new_callable=mock_open, read_data="12:devices:/docker/abc123\n")
    @patch("os.path.exists")
    def test_docker_detection_cgroup(self, mock_exists, mock_file):
        """cgroupによるDocker検出"""
        mock_exists.return_value = False  # /.dockerenvは存在しない

        monitor = MemoryMonitor()
        self.assertTrue(monitor.is_docker)

    @patch("core.memory_monitor.MemoryMonitor._read_cgroup_value")
    @patch("core.memory_monitor.MemoryMonitor._detect_docker_environment")
    def test_docker_memory_usage(self, mock_detect, mock_read):
        """Docker環境でのメモリ使用率取得"""
        mock_detect.return_value = True

        # cgroupの値を設定
        def read_side_effect(path):
            if "limit" in path or "max" in path:
                return 8 * 1024**3  # 8GB制限
            elif "usage" in path or "current" in path:
                return 5 * 1024**3  # 5GB使用
            return None

        mock_read.side_effect = read_side_effect

        monitor = MemoryMonitor()
        usage = monitor.get_memory_usage()

        # 5/8 = 62.5%
        self.assertAlmostEqual(usage, 62.5, places=1)

    def test_memory_pressure_levels(self):
        """メモリ圧迫度の判定"""
        monitor = MemoryMonitor()

        test_cases = [
            (30.0, "low"),
            (65.0, "medium"),
            (80.0, "high"),
            (90.0, "critical"),
        ]

        for memory_percent, expected_pressure in test_cases:
            with patch.object(monitor, "get_memory_usage", return_value=memory_percent):
                pressure = monitor.get_memory_pressure()
                self.assertEqual(pressure, expected_pressure)

    def test_is_memory_critical(self):
        """危機的メモリ状態の判定"""
        monitor = MemoryMonitor()

        with patch.object(monitor, "get_memory_usage", return_value=92.0):
            self.assertTrue(monitor.is_memory_critical(90.0))
            self.assertFalse(monitor.is_memory_critical(95.0))

    @patch("psutil.virtual_memory")
    def test_get_memory_stats(self, mock_vm):
        """詳細なメモリ統計の取得"""
        mock_vm.return_value = Mock(
            percent=70.0, total=16 * 1024**3, available=4.8 * 1024**3, used=11.2 * 1024**3, free=4.8 * 1024**3
        )

        # スワップのモック
        with patch("psutil.swap_memory") as mock_swap:
            mock_swap.return_value = Mock(percent=25.0, total=8 * 1024**3)

            monitor = MemoryMonitor()
            stats = monitor.get_memory_stats()

            self.assertEqual(stats["percent"], 70.0)
            self.assertAlmostEqual(stats["total_gb"], 16.0, places=1)
            self.assertEqual(stats["swap_percent"], 25.0)

    @patch("psutil.virtual_memory")
    def test_average_usage_calculation(self, mock_vm):
        """平均使用率の計算"""
        monitor = MemoryMonitor()

        # 複数のサンプルを追加
        usage_values = [60.0, 65.0, 70.0, 75.0, 80.0]
        for i, usage in enumerate(usage_values):
            mock_vm.return_value = Mock(percent=usage, available=8 * 1024**3, total=16 * 1024**3)
            monitor.get_memory_usage()
            time.sleep(0.1)  # タイムスタンプを変える

        # 平均を計算
        avg = monitor.get_average_usage(seconds=10)

        # 期待値の範囲内か確認
        self.assertGreater(avg, 60.0)
        self.assertLess(avg, 80.0)

    def test_average_usage_no_history(self):
        """履歴がない場合の平均使用率"""
        monitor = MemoryMonitor()

        with patch.object(monitor, "get_memory_usage", return_value=55.0):
            avg = monitor.get_average_usage(60)
            self.assertEqual(avg, 55.0)

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_memory_available(self, mock_time, mock_sleep):
        """メモリ待機機能のテスト"""
        monitor = MemoryMonitor()

        # 時間の経過をシミュレート（while条件チェックと経過時間計算で複数回呼ばれる）
        mock_time.side_effect = [0, 0, 5, 5, 10, 10, 15]

        # メモリ使用率が徐々に下がる
        with patch.object(monitor, "get_memory_usage", side_effect=[85.0, 82.0, 78.0]):
            result = monitor.wait_for_memory_available(target_percent=80.0, timeout=60)
            self.assertTrue(result)

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_for_memory_timeout(self, mock_time, mock_sleep):
        """メモリ待機のタイムアウト"""
        monitor = MemoryMonitor()

        # 時間の経過をシミュレート（タイムアウト）
        mock_time.side_effect = [0, 10, 20, 30, 40, 50, 60, 70]

        # メモリが下がらない
        with patch.object(monitor, "get_memory_usage", return_value=85.0):
            result = monitor.wait_for_memory_available(target_percent=80.0, timeout=60)
            self.assertFalse(result)

    def test_status_summary(self):
        """ステータスサマリーの生成"""
        monitor = MemoryMonitor()

        with patch.object(
            monitor,
            "get_memory_stats",
            return_value={
                "percent": 72.5,
                "used_gb": 11.6,
                "total_gb": 16.0,
                "is_docker": False,
                "swap_percent": 10.0,
                "swap_total_gb": 8.0,
            },
        ):
            summary = monitor.get_status_summary()
            self.assertIn("72.5%", summary)
            self.assertIn("11.6/16.0GB", summary)
            self.assertIn("Pressure:", summary)  # pressure levelが含まれることを確認

    def test_cgroup_value_reading(self):
        """cgroupファイル読み取りのテスト"""
        monitor = MemoryMonitor()

        # 数値の場合
        with patch("builtins.open", mock_open(read_data="8589934592")):
            value = monitor._read_cgroup_value("/path/to/memory.limit")
            self.assertEqual(value, 8589934592)

        # 'max'の場合（cgroup v2）
        with patch("builtins.open", mock_open(read_data="max")):
            value = monitor._read_cgroup_value("/path/to/memory.max")
            self.assertEqual(value, 9223372036854775807)

        # ファイルが存在しない場合
        with patch("builtins.open", side_effect=FileNotFoundError):
            value = monitor._read_cgroup_value("/nonexistent")
            self.assertIsNone(value)


if __name__ == "__main__":
    unittest.main()
