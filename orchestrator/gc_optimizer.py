"""
ガベージコレクション最適化モジュール

メモリ使用パターンに基づいてガベージコレクションを
動的に調整し、メモリ効率を最適化する。
"""

import gc
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.logging import get_logger

logger = get_logger(__name__)


class GCStrategy(Enum):
    """ガベージコレクション戦略"""

    CONSERVATIVE = "conservative"  # 保守的（頻度低）
    BALANCED = "balanced"  # バランス型
    AGGRESSIVE = "aggressive"  # 積極的（頻度高）
    ADAPTIVE = "adaptive"  # 適応型


@dataclass
class GCMetrics:
    """GC実行メトリクス"""

    timestamp: datetime
    generation: int
    collected: int
    uncollectable: int
    duration: float
    memory_before: float
    memory_after: float
    efficiency: float  # (memory_before - memory_after) / duration


class GarbageCollectionOptimizer:
    """ガベージコレクション最適化クラス"""

    def __init__(self, initial_strategy: GCStrategy = GCStrategy.ADAPTIVE):
        """
        初期化

        Args:
            initial_strategy: 初期GC戦略
        """
        self.strategy = initial_strategy
        self.metrics_history: list[GCMetrics] = []
        self.max_history = 100

        # GC設定を保存
        self.original_thresholds = gc.get_threshold()

        # 戦略別の閾値設定
        self.strategy_thresholds = {
            GCStrategy.CONSERVATIVE: (1000, 20, 20),  # デフォルトより高い
            GCStrategy.BALANCED: (700, 10, 10),  # デフォルト値
            GCStrategy.AGGRESSIVE: (400, 5, 5),  # 頻繁にGC実行
            GCStrategy.ADAPTIVE: None,  # 動的に調整
        }

        # 適応型の設定
        self.adaptive_config = {
            "min_threshold": (200, 5, 5),
            "max_threshold": (2000, 30, 30),
            "adjustment_factor": 0.1,
            "efficiency_target": 0.5,  # MB/ms
        }

        # 統計情報
        self.stats = {
            "total_collections": 0,
            "total_collected": 0,
            "total_uncollectable": 0,
            "total_time": 0.0,
            "strategy_changes": 0,
        }

        # 初期戦略を適用
        self.apply_strategy(self.strategy)

        logger.info(f"GC Optimizer initialized with {self.strategy.value} strategy")

    def apply_strategy(self, strategy: GCStrategy):
        """GC戦略を適用"""
        if strategy == GCStrategy.ADAPTIVE:
            # 適応型は後で動的に設定
            logger.info("Using adaptive GC strategy")
        else:
            thresholds = self.strategy_thresholds.get(strategy)
            if thresholds:
                gc.set_threshold(*thresholds)
                logger.info(f"Applied {strategy.value} GC thresholds: {thresholds}")

        self.strategy = strategy
        self.stats["strategy_changes"] += 1

    def collect_with_metrics(self, generation: int = 2) -> GCMetrics:
        """メトリクスを記録しながらGCを実行"""
        import psutil

        process = psutil.Process()

        # 実行前のメモリ使用量
        memory_before = process.memory_info().rss / 1024 / 1024  # MB

        # GC実行と計測
        start_time = time.time()
        collected = gc.collect(generation)
        duration = (time.time() - start_time) * 1000  # ms

        # 実行後のメモリ使用量
        memory_after = process.memory_info().rss / 1024 / 1024  # MB

        # 収集不可能オブジェクト数
        uncollectable = len(gc.garbage)

        # 効率計算
        memory_freed = max(0, memory_before - memory_after)
        efficiency = memory_freed / duration if duration > 0 else 0

        # メトリクスを記録
        metrics = GCMetrics(
            timestamp=datetime.now(),
            generation=generation,
            collected=collected,
            uncollectable=uncollectable,
            duration=duration,
            memory_before=memory_before,
            memory_after=memory_after,
            efficiency=efficiency,
        )

        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.max_history:
            self.metrics_history.pop(0)

        # 統計更新
        self.stats["total_collections"] += 1
        self.stats["total_collected"] += collected
        self.stats["total_uncollectable"] += uncollectable
        self.stats["total_time"] += duration

        logger.debug(
            f"GC gen{generation}: collected={collected}, "
            f"freed={memory_freed:.1f}MB, duration={duration:.1f}ms, "
            f"efficiency={efficiency:.2f}MB/ms"
        )

        return metrics

    def optimize_based_on_memory_pressure(self, memory_percent: float) -> GCMetrics | None:
        """メモリ圧迫度に基づいて最適化"""
        if memory_percent < 50:
            # メモリに余裕がある場合
            if self.strategy != GCStrategy.CONSERVATIVE:
                self.apply_strategy(GCStrategy.CONSERVATIVE)
                logger.info("Switched to conservative GC due to low memory pressure")
            return None

        elif memory_percent < 70:
            # 中程度の使用率
            if self.strategy != GCStrategy.BALANCED:
                self.apply_strategy(GCStrategy.BALANCED)
                logger.info("Switched to balanced GC")

            # 世代1のGCを実行
            return self.collect_with_metrics(1)

        elif memory_percent < 85:
            # 高使用率
            if self.strategy != GCStrategy.AGGRESSIVE:
                self.apply_strategy(GCStrategy.AGGRESSIVE)
                logger.info("Switched to aggressive GC due to high memory pressure")

            # フルGCを実行
            return self.collect_with_metrics(2)

        else:
            # 危険レベル
            logger.warning(f"Critical memory pressure: {memory_percent:.1f}%")

            # 複数回のフルGC
            total_metrics = None
            for i in range(3):
                metrics = self.collect_with_metrics(2)
                if total_metrics is None:
                    total_metrics = metrics
                else:
                    total_metrics.collected += metrics.collected
                    total_metrics.duration += metrics.duration

                # 改善が見られない場合は中断
                if metrics.efficiency < 0.1:
                    break

                time.sleep(0.1)

            return total_metrics

    def adapt_thresholds(self):
        """適応型戦略での閾値調整"""
        if self.strategy != GCStrategy.ADAPTIVE:
            return

        if len(self.metrics_history) < 10:
            return  # 十分なデータがない

        # 最近のメトリクスを分析
        recent_metrics = self.metrics_history[-10:]
        avg_efficiency = sum(m.efficiency for m in recent_metrics) / len(recent_metrics)
        avg_collected = sum(m.collected for m in recent_metrics) / len(recent_metrics)

        current_thresholds = gc.get_threshold()
        new_thresholds = list(current_thresholds)

        # 効率が目標を下回る場合は頻度を上げる
        if avg_efficiency < self.adaptive_config["efficiency_target"]:
            # 閾値を下げる（頻度を上げる）
            for i in range(3):
                new_thresholds[i] = int(current_thresholds[i] * (1 - self.adaptive_config["adjustment_factor"]))
        elif avg_collected < 100:  # ほとんど収集されない場合
            # 閾値を上げる（頻度を下げる）
            for i in range(3):
                new_thresholds[i] = int(current_thresholds[i] * (1 + self.adaptive_config["adjustment_factor"]))

        # 最小/最大値でクリップ
        min_thresh = self.adaptive_config["min_threshold"]
        max_thresh = self.adaptive_config["max_threshold"]

        for i in range(3):
            new_thresholds[i] = max(min_thresh[i], min(max_thresh[i], new_thresholds[i]))

        # 変更が必要な場合のみ適用
        if new_thresholds != list(current_thresholds):
            gc.set_threshold(*new_thresholds)
            logger.info(f"Adapted GC thresholds: {current_thresholds} -> {new_thresholds}")

    def get_optimization_suggestions(self) -> list[str]:
        """最適化の提案を取得"""
        suggestions = []

        if not self.metrics_history:
            return ["GCメトリクスが不足しています"]

        # 最近のメトリクスを分析
        recent_metrics = self.metrics_history[-20:]

        # 収集不可能オブジェクトが多い場合
        avg_uncollectable = sum(m.uncollectable for m in recent_metrics) / len(recent_metrics)
        if avg_uncollectable > 100:
            suggestions.append(
                f"収集不可能オブジェクトが多い（平均{avg_uncollectable:.0f}個）: " "循環参照を確認してください"
            )

        # 効率が低い場合
        avg_efficiency = sum(m.efficiency for m in recent_metrics) / len(recent_metrics)
        if avg_efficiency < 0.1:
            suggestions.append(
                f"GC効率が低い（{avg_efficiency:.2f}MB/ms）: " "オブジェクトの生成パターンを見直してください"
            )

        # GC時間が長い場合
        avg_duration = sum(m.duration for m in recent_metrics) / len(recent_metrics)
        if avg_duration > 100:  # 100ms以上
            suggestions.append(f"GC実行時間が長い（平均{avg_duration:.0f}ms）: " "世代別GCの頻度調整を検討してください")

        return suggestions

    def get_stats(self) -> dict[str, Any]:
        """統計情報を取得"""
        avg_efficiency = 0.0
        avg_duration = 0.0

        if self.metrics_history:
            avg_efficiency = sum(m.efficiency for m in self.metrics_history) / len(self.metrics_history)
            avg_duration = sum(m.duration for m in self.metrics_history) / len(self.metrics_history)

        return {
            "current_strategy": self.strategy.value,
            "current_thresholds": gc.get_threshold(),
            "total_collections": self.stats["total_collections"],
            "total_collected": self.stats["total_collected"],
            "total_uncollectable": self.stats["total_uncollectable"],
            "total_time_ms": self.stats["total_time"],
            "average_efficiency": avg_efficiency,
            "average_duration_ms": avg_duration,
            "strategy_changes": self.stats["strategy_changes"],
            "suggestions": self.get_optimization_suggestions(),
        }

    def cleanup(self):
        """クリーンアップ（元の設定に戻す）"""
        gc.set_threshold(*self.original_thresholds)
        logger.info("Restored original GC thresholds")


def optimize_for_transcription() -> GarbageCollectionOptimizer:
    """文字起こし処理用に最適化されたGCオプティマイザーを作成"""
    optimizer = GarbageCollectionOptimizer(GCStrategy.ADAPTIVE)

    # 文字起こし特有の設定
    optimizer.adaptive_config.update(
        {"efficiency_target": 1.0, "adjustment_factor": 0.15}  # より高い効率目標  # より積極的な調整
    )

    return optimizer


# テスト用関数
def test_gc_optimizer():
    """GC最適化のテスト"""
    print("=== GC Optimizer Test ===")

    # オプティマイザーを作成
    optimizer = optimize_for_transcription()

    # メモリ圧迫シミュレーション
    test_scenarios = [
        (30.0, "Low memory pressure"),
        (60.0, "Medium memory pressure"),
        (75.0, "High memory pressure"),
        (90.0, "Critical memory pressure"),
    ]

    for memory_percent, description in test_scenarios:
        print(f"\n--- {description} ({memory_percent}%) ---")

        # 最適化実行
        metrics = optimizer.optimize_based_on_memory_pressure(memory_percent)

        if metrics:
            print(
                f"GC executed: collected={metrics.collected}, "
                f"freed={metrics.memory_before - metrics.memory_after:.1f}MB, "
                f"duration={metrics.duration:.1f}ms"
            )

        # 適応型戦略の場合は閾値を調整
        if optimizer.strategy == GCStrategy.ADAPTIVE:
            optimizer.adapt_thresholds()

    # 統計表示
    print("\n--- Final Statistics ---")
    stats = optimizer.get_stats()

    print(f"Strategy: {stats['current_strategy']}")
    print(f"Current thresholds: {stats['current_thresholds']}")
    print(f"Total collections: {stats['total_collections']}")
    print(f"Total collected: {stats['total_collected']}")
    print(f"Average efficiency: {stats['average_efficiency']:.2f} MB/ms")
    print(f"Average duration: {stats['average_duration_ms']:.1f} ms")

    if stats["suggestions"]:
        print("\nOptimization suggestions:")
        for suggestion in stats["suggestions"]:
            print(f"  - {suggestion}")

    # クリーンアップ
    optimizer.cleanup()
    print("\n✓ Test completed!")


if __name__ == "__main__":
    test_gc_optimizer()
