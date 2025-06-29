"""
メモリ監視モジュール

システムメモリの使用状況を監視し、
Docker環境でも正確な情報を取得する。
"""

import os
import time
from collections import deque
from datetime import datetime
from typing import Any

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from utils.logging import get_logger

logger = get_logger(__name__)


class MemoryMonitor:
    """メモリ使用状況の監視"""

    def __init__(self, history_size: int = 100) -> None:
        """
        初期化

        Args:
            history_size: 保持する履歴のサイズ
        """
        self.history: deque[dict[str, Any]] = deque(maxlen=history_size)
        self.is_docker = self._detect_docker_environment()

        if not PSUTIL_AVAILABLE:
            logger.warning("psutil not available, using fallback values")

        logger.info(f"MemoryMonitor initialized (Docker: {self.is_docker})")

    def _detect_docker_environment(self) -> bool:
        """Docker環境かどうかを検出"""
        # 方法1: /.dockerenvファイルの存在確認
        if os.path.exists("/.dockerenv"):
            return True

        # 方法2: /proc/1/cgroupの確認
        try:
            with open("/proc/1/cgroup") as f:
                if "docker" in f.read():
                    return True
        except OSError:
            pass

        return False

    def get_memory_usage(self) -> float:
        """
        現在のメモリ使用率を取得（0-100%）

        Returns:
            メモリ使用率（エラー時は50.0を返す）
        """
        try:
            if not PSUTIL_AVAILABLE:
                logger.warning("psutil not available, returning default value")
                return 50.0

            if self.is_docker:
                return self._get_docker_memory_usage()
            else:
                return self._get_system_memory_usage()

        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return 50.0  # 安全なデフォルト値

    def _get_system_memory_usage(self) -> float:
        """通常のシステムメモリ使用率を取得"""
        try:
            mem = psutil.virtual_memory()
            usage_percent = mem.percent

            # 履歴に記録
            self._record_usage(usage_percent, mem.available, mem.total)

            return usage_percent

        except Exception as e:
            logger.error(f"Error getting system memory: {e}")
            return 50.0

    def _get_docker_memory_usage(self) -> float:
        """Docker環境でのメモリ使用率を取得"""
        try:
            # Docker環境では/sys/fs/cgroup/memory/を確認
            memory_limit = self._read_cgroup_value("/sys/fs/cgroup/memory/memory.limit_in_bytes")
            memory_usage = self._read_cgroup_value("/sys/fs/cgroup/memory/memory.usage_in_bytes")

            # cgroup v2の場合
            if memory_limit is None or memory_usage is None:
                memory_limit = self._read_cgroup_value("/sys/fs/cgroup/memory.max")
                memory_usage = self._read_cgroup_value("/sys/fs/cgroup/memory.current")

            # 読み取れない場合はpsutilにフォールバック
            if memory_limit is None or memory_usage is None:
                logger.debug("Cannot read cgroup values, falling back to psutil")
                return self._get_system_memory_usage()

            # 無制限の場合
            if memory_limit > 9223372036854775807:  # 2^63 - 1
                return self._get_system_memory_usage()

            usage_percent = (memory_usage / memory_limit) * 100

            # 履歴に記録
            available = memory_limit - memory_usage
            self._record_usage(usage_percent, available, memory_limit)

            return min(usage_percent, 100.0)

        except Exception as e:
            logger.error(f"Error getting Docker memory: {e}")
            return self._get_system_memory_usage()

    def _read_cgroup_value(self, path: str) -> int | None:
        """cgroupファイルから値を読み取る"""
        try:
            with open(path) as f:
                value = f.read().strip()
                if value.isdigit():
                    return int(value)
                elif value == "max":  # cgroup v2
                    return 9223372036854775807
        except OSError:
            pass
        return None

    def _record_usage(self, percent: float, available: int, total: int) -> None:
        """使用状況を履歴に記録"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "percent": percent,
            "available_mb": available / (1024 * 1024),
            "total_mb": total / (1024 * 1024),
        }
        self.history.append(record)

    def get_memory_stats(self) -> dict:
        """
        詳細なメモリ統計を取得

        Returns:
            メモリ統計辞書（エラー時は安全なデフォルト値）
        """
        try:
            if not PSUTIL_AVAILABLE:
                return self._get_default_stats()

            mem = psutil.virtual_memory()

            stats = {
                "percent": mem.percent,
                "total_gb": mem.total / (1024**3),
                "available_gb": mem.available / (1024**3),
                "used_gb": mem.used / (1024**3),
                "free_gb": mem.free / (1024**3),
                "is_docker": self.is_docker,
            }

            # スワップ情報（利用可能な場合）
            try:
                swap = psutil.swap_memory()
                stats["swap_percent"] = swap.percent
                stats["swap_total_gb"] = swap.total / (1024**3)
            except (AttributeError, OSError):
                stats["swap_percent"] = 0.0
                stats["swap_total_gb"] = 0.0

            return stats

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return self._get_default_stats()

    def _get_default_stats(self) -> dict:
        """デフォルトの統計値"""
        return {
            "percent": 50.0,
            "total_gb": 8.0,
            "available_gb": 4.0,
            "used_gb": 4.0,
            "free_gb": 4.0,
            "is_docker": self.is_docker,
            "swap_percent": 0.0,
            "swap_total_gb": 0.0,
        }

    def get_average_usage(self, seconds: int = 60) -> float:
        """
        指定秒数の平均メモリ使用率を取得

        Args:
            seconds: 平均を計算する秒数

        Returns:
            平均メモリ使用率
        """
        if not self.history:
            return self.get_memory_usage()

        cutoff_time = datetime.now().timestamp() - seconds
        recent_records = [r for r in self.history if datetime.fromisoformat(r["timestamp"]).timestamp() > cutoff_time]

        if not recent_records:
            return self.history[-1]["percent"] if self.history else 50.0

        avg_percent = sum(r["percent"] for r in recent_records) / len(recent_records)
        return avg_percent

    def is_memory_critical(self, threshold: float = 90.0) -> bool:
        """
        メモリが危機的な状態かチェック

        Args:
            threshold: 危機的とみなす閾値（%）

        Returns:
            危機的な場合True
        """
        current = self.get_memory_usage()
        return current >= threshold

    def get_memory_pressure(self) -> str:
        """
        メモリ圧迫度を取得

        Returns:
            'low', 'medium', 'high', 'critical' のいずれか
        """
        usage = self.get_memory_usage()

        if usage < 60:
            return "low"
        elif usage < 75:
            return "medium"
        elif usage < 85:
            return "high"
        else:
            return "critical"

    def wait_for_memory_available(self, target_percent: float = 80.0, timeout: int = 60) -> bool:
        """
        メモリが利用可能になるまで待機

        Args:
            target_percent: 目標メモリ使用率
            timeout: タイムアウト秒数

        Returns:
            目標値に達した場合True、タイムアウトした場合False
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            current = self.get_memory_usage()
            if current <= target_percent:
                return True

            logger.info(f"Waiting for memory to drop below {target_percent}% (current: {current:.1f}%)")
            time.sleep(5)  # 5秒待機

        return False

    def get_status_summary(self) -> str:
        """状態サマリーを取得（ログ用）"""
        stats = self.get_memory_stats()
        return (
            f"Memory: {stats['percent']:.1f}% "
            f"({stats['used_gb']:.1f}/{stats['total_gb']:.1f}GB) "
            f"Pressure: {self.get_memory_pressure()}"
        )
