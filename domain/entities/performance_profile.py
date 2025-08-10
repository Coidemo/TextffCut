"""
パフォーマンスプロファイルのドメインエンティティ
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PerformanceMetrics:
    """パフォーマンスメトリクス"""
    timestamp: datetime
    success: bool
    processing_time: float
    error_message: Optional[str] = None
    optimization_info: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'timestamp': self.timestamp.isoformat(),
            'success': self.success,
            'processing_time': self.processing_time,
            'error_message': self.error_message,
            'optimization_info': self.optimization_info
        }


@dataclass
class PerformanceProfile:
    """パフォーマンスプロファイルのドメインエンティティ"""
    
    # ID
    id: str = field(default_factory=lambda: f"profile_{datetime.now().timestamp()}")
    
    # 最適化設定は削除（常に最適化を実行）
    
    # 処理設定（自動最適化のみ）
    compute_type: Optional[str] = None
    
    # 詳細設定
    max_conversion_time: int = 300  # 最大変換時間（秒）
    min_memory_threshold_gb: float = 4.0  # 最小メモリ閾値
    
    # 統計情報（最新20件のみ保持）
    metrics_history: List[PerformanceMetrics] = field(default_factory=list)
    
    def add_metrics(self, metrics: PerformanceMetrics) -> None:
        """メトリクスを追加（最新20件のみ保持）"""
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > 20:
            self.metrics_history = self.metrics_history[-20:]
    
    def get_recent_errors_count(self, limit: int = 5) -> int:
        """最近のエラー数を取得"""
        recent = self.metrics_history[-limit:] if len(self.metrics_history) >= limit else self.metrics_history
        return sum(1 for m in recent if not m.success)
    
    def get_average_processing_time(self) -> float:
        """平均処理時間を取得"""
        success_times = [m.processing_time for m in self.metrics_history if m.success]
        return sum(success_times) / len(success_times) if success_times else 0.0
    
    def has_recent_memory_errors(self) -> bool:
        """最近メモリエラーが発生しているか判定"""
        # 最近5件のうち2件以上がメモリエラーならTrue
        recent_errors = [
            m for m in self.metrics_history[-5:]
            if not m.success and m.error_message and 'memory' in m.error_message.lower()
        ]
        return len(recent_errors) >= 2
    
    def get_effective_compute_type(self) -> str:
        """実効的な計算精度を取得"""
        return self.compute_type or 'int8'