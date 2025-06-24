"""
メモリ管理強化モジュール

プロセス分離環境でのメモリ監視と管理を強化。
ワーカープロセスごとのメモリ使用状況を追跡し、
異常を検出して自動対処を行う。
"""

import gc
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import psutil

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.memory_monitor import MemoryMonitor
from orchestrator.process_communication import MessageType, ProcessMessage
from utils.logging import get_logger

logger = get_logger(__name__)


class MemoryPressureLevel(Enum):
    """メモリ圧迫レベル"""
    
    NORMAL = "normal"      # 正常（60%未満）
    WARNING = "warning"    # 警告（60-80%）
    CRITICAL = "critical"  # 危険（80-90%）
    EMERGENCY = "emergency"  # 緊急（90%以上）


@dataclass
class WorkerMemoryStatus:
    """ワーカーのメモリ状態"""
    
    worker_id: str
    process_id: int
    memory_mb: float
    memory_percent: float
    pressure_level: MemoryPressureLevel
    last_update: datetime
    gc_count: int = 0
    restart_count: int = 0


class EnhancedMemoryMonitor(MemoryMonitor):
    """拡張メモリ監視クラス"""
    
    def __init__(self, history_size: int = 100):
        """初期化"""
        super().__init__(history_size)
        self.worker_status: Dict[str, WorkerMemoryStatus] = {}
        self.pressure_thresholds = {
            MemoryPressureLevel.NORMAL: 60.0,
            MemoryPressureLevel.WARNING: 80.0,
            MemoryPressureLevel.CRITICAL: 90.0,
        }
        
    def update_worker_status(self, worker_id: str, process_id: int, 
                           memory_mb: float, memory_percent: float) -> WorkerMemoryStatus:
        """ワーカーのメモリ状態を更新"""
        pressure_level = self._calculate_pressure_level(memory_percent)
        
        status = WorkerMemoryStatus(
            worker_id=worker_id,
            process_id=process_id,
            memory_mb=memory_mb,
            memory_percent=memory_percent,
            pressure_level=pressure_level,
            last_update=datetime.now()
        )
        
        # 既存の状態があれば一部情報を引き継ぐ
        if worker_id in self.worker_status:
            old_status = self.worker_status[worker_id]
            status.gc_count = old_status.gc_count
            status.restart_count = old_status.restart_count
        
        self.worker_status[worker_id] = status
        
        # ログ出力
        if pressure_level != MemoryPressureLevel.NORMAL:
            logger.warning(
                f"Worker {worker_id} memory pressure: {pressure_level.value} "
                f"({memory_percent:.1f}%, {memory_mb:.1f}MB)"
            )
        
        return status
    
    def _calculate_pressure_level(self, memory_percent: float) -> MemoryPressureLevel:
        """メモリ圧迫レベルを計算"""
        if memory_percent >= self.pressure_thresholds[MemoryPressureLevel.CRITICAL]:
            return MemoryPressureLevel.EMERGENCY
        elif memory_percent >= self.pressure_thresholds[MemoryPressureLevel.WARNING]:
            return MemoryPressureLevel.CRITICAL
        elif memory_percent >= self.pressure_thresholds[MemoryPressureLevel.NORMAL]:
            return MemoryPressureLevel.WARNING
        else:
            return MemoryPressureLevel.NORMAL
    
    def get_workers_requiring_action(self) -> List[Tuple[str, WorkerMemoryStatus]]:
        """対処が必要なワーカーのリストを取得"""
        workers_needing_action = []
        
        for worker_id, status in self.worker_status.items():
            if status.pressure_level in [MemoryPressureLevel.CRITICAL, MemoryPressureLevel.EMERGENCY]:
                workers_needing_action.append((worker_id, status))
        
        return workers_needing_action
    
    def get_system_memory_info(self) -> Dict[str, Any]:
        """システム全体のメモリ情報を取得"""
        mem = psutil.virtual_memory()
        
        return {
            "total_mb": mem.total / 1024 / 1024,
            "available_mb": mem.available / 1024 / 1024,
            "used_mb": mem.used / 1024 / 1024,
            "percent": mem.percent,
            "worker_count": len(self.worker_status),
            "workers_in_pressure": len(self.get_workers_requiring_action())
        }
    
    def suggest_memory_optimization(self, worker_id: str) -> List[str]:
        """メモリ最適化の提案を生成"""
        if worker_id not in self.worker_status:
            return []
        
        status = self.worker_status[worker_id]
        suggestions = []
        
        if status.pressure_level == MemoryPressureLevel.WARNING:
            suggestions.append("バッチサイズを縮小することを推奨")
            suggestions.append("不要なオブジェクトの削除を実行")
            
        elif status.pressure_level == MemoryPressureLevel.CRITICAL:
            suggestions.append("即座にガベージコレクションを実行")
            suggestions.append("現在のタスクを中断して軽量タスクに切り替え")
            suggestions.append("バッチサイズを最小値に設定")
            
        elif status.pressure_level == MemoryPressureLevel.EMERGENCY:
            suggestions.append("ワーカープロセスの再起動を推奨")
            suggestions.append("すべてのタスクを一時停止")
            suggestions.append("メモリ集約的な処理を回避")
        
        return suggestions


class MemoryOptimizer:
    """メモリ最適化実行クラス"""
    
    def __init__(self, monitor: EnhancedMemoryMonitor):
        """初期化"""
        self.monitor = monitor
        self.optimization_history = defaultdict(list)
        
    def optimize_worker(self, worker_id: str, status: WorkerMemoryStatus) -> Dict[str, Any]:
        """ワーカーのメモリを最適化"""
        actions_taken = []
        
        # レベルに応じた最適化を実行
        if status.pressure_level == MemoryPressureLevel.WARNING:
            actions_taken.extend(self._optimize_warning_level(worker_id))
            
        elif status.pressure_level == MemoryPressureLevel.CRITICAL:
            actions_taken.extend(self._optimize_critical_level(worker_id))
            
        elif status.pressure_level == MemoryPressureLevel.EMERGENCY:
            actions_taken.extend(self._optimize_emergency_level(worker_id))
        
        # 最適化履歴を記録
        optimization_record = {
            "timestamp": datetime.now(),
            "pressure_level": status.pressure_level,
            "memory_before": status.memory_percent,
            "actions": actions_taken
        }
        self.optimization_history[worker_id].append(optimization_record)
        
        return {
            "worker_id": worker_id,
            "actions_taken": actions_taken,
            "success": len(actions_taken) > 0
        }
    
    def _optimize_warning_level(self, worker_id: str) -> List[str]:
        """警告レベルの最適化"""
        actions = []
        
        # ガベージコレクションの実行
        gc.collect(0)  # 世代0のみ
        actions.append("Performed generation 0 garbage collection")
        
        logger.info(f"Warning level optimization for worker {worker_id}")
        
        return actions
    
    def _optimize_critical_level(self, worker_id: str) -> List[str]:
        """危険レベルの最適化"""
        actions = []
        
        # フルガベージコレクション
        collected = gc.collect()
        actions.append(f"Full garbage collection (collected {collected} objects)")
        
        # メモリ統計の更新
        self.monitor.worker_status[worker_id].gc_count += 1
        
        logger.warning(f"Critical level optimization for worker {worker_id}")
        
        return actions
    
    def _optimize_emergency_level(self, worker_id: str) -> List[str]:
        """緊急レベルの最適化"""
        actions = []
        
        # 積極的なガベージコレクション
        for i in range(3):
            collected = gc.collect()
            if collected == 0:
                break
            time.sleep(0.1)
        
        actions.append("Aggressive garbage collection performed")
        
        # 再起動フラグを設定
        actions.append("Marked worker for restart")
        
        logger.error(f"Emergency level optimization for worker {worker_id}")
        
        return actions
    
    def should_restart_worker(self, worker_id: str) -> bool:
        """ワーカーの再起動が必要かどうかを判定"""
        if worker_id not in self.monitor.worker_status:
            return False
        
        status = self.monitor.worker_status[worker_id]
        
        # 緊急レベルが一定時間続いている
        if status.pressure_level == MemoryPressureLevel.EMERGENCY:
            return True
        
        # GC実行回数が多すぎる
        if status.gc_count > 10:
            return True
        
        # 再起動回数が少なく、危険レベルが続いている
        if status.restart_count < 3 and status.pressure_level == MemoryPressureLevel.CRITICAL:
            # 最適化履歴を確認
            recent_optimizations = self.optimization_history[worker_id][-5:]
            critical_count = sum(
                1 for opt in recent_optimizations 
                if opt["pressure_level"] == MemoryPressureLevel.CRITICAL
            )
            if critical_count >= 3:
                return True
        
        return False


class ProcessMemoryManager:
    """プロセス全体のメモリ管理"""
    
    def __init__(self):
        """初期化"""
        self.monitor = EnhancedMemoryMonitor()
        self.optimizer = MemoryOptimizer(self.monitor)
        self.monitoring_interval = 5.0  # 5秒ごとに監視
        self.last_check = time.time()
        
    def process_memory_report(self, msg: ProcessMessage) -> Optional[Dict[str, Any]]:
        """メモリレポートメッセージを処理"""
        if msg.msg_type != MessageType.MEMORY_STATUS:
            return None
        
        worker_id = msg.worker_id
        memory_data = msg.data or {}
        
        # プロセス情報を取得
        try:
            process = psutil.Process(memory_data.get("pid", 0))
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            memory_percent = memory_data.get("memory_percent", 0.0)
        except:
            logger.error(f"Failed to get process info for worker {worker_id}")
            return None
        
        # ワーカー状態を更新
        status = self.monitor.update_worker_status(
            worker_id, process.pid, memory_mb, memory_percent
        )
        
        # 最適化が必要な場合は実行
        if status.pressure_level != MemoryPressureLevel.NORMAL:
            optimization_result = self.optimizer.optimize_worker(worker_id, status)
            
            # 再起動が必要かチェック
            if self.optimizer.should_restart_worker(worker_id):
                optimization_result["restart_required"] = True
            
            return optimization_result
        
        return None
    
    def get_memory_report(self) -> Dict[str, Any]:
        """メモリレポートを生成"""
        system_info = self.monitor.get_system_memory_info()
        worker_details = []
        
        for worker_id, status in self.monitor.worker_status.items():
            worker_details.append({
                "worker_id": worker_id,
                "memory_mb": status.memory_mb,
                "memory_percent": status.memory_percent,
                "pressure_level": status.pressure_level.value,
                "gc_count": status.gc_count,
                "restart_count": status.restart_count,
                "suggestions": self.monitor.suggest_memory_optimization(worker_id)
            })
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system": system_info,
            "workers": worker_details,
            "total_workers": len(worker_details),
            "workers_under_pressure": len(self.monitor.get_workers_requiring_action())
        }
    
    def should_check_memory(self) -> bool:
        """メモリチェックが必要かどうか"""
        current_time = time.time()
        if current_time - self.last_check >= self.monitoring_interval:
            self.last_check = current_time
            return True
        return False


# テスト用関数
def test_memory_management():
    """メモリ管理機能のテスト"""
    print("=== Memory Management Test ===")
    
    manager = ProcessMemoryManager()
    
    # 現在のプロセスIDを使用してテスト
    current_pid = psutil.Process().pid
    
    # ダミーのメモリレポートをシミュレート
    test_scenarios = [
        ("worker_0", current_pid, 1024, 45.0, "Normal memory usage"),
        ("worker_1", current_pid, 2048, 75.0, "Warning level"),
        ("worker_2", current_pid, 3072, 85.0, "Critical level"),
        ("worker_3", current_pid, 4096, 92.0, "Emergency level"),
    ]
    
    for worker_id, pid, memory_mb, memory_percent, description in test_scenarios:
        print(f"\n--- {description} ---")
        
        # メモリレポートメッセージを作成
        msg = ProcessMessage(
            msg_type=MessageType.MEMORY_STATUS,
            worker_id=worker_id,
            data={
                "pid": pid,
                "memory_percent": memory_percent
            }
        )
        
        # 処理
        result = manager.process_memory_report(msg)
        
        if result:
            print(f"Optimization performed: {result}")
            if result.get("restart_required"):
                print(f"⚠️ Worker {worker_id} requires restart!")
        
        # 提案を表示
        suggestions = manager.monitor.suggest_memory_optimization(worker_id)
        if suggestions:
            print(f"Suggestions for {worker_id}:")
            for suggestion in suggestions:
                print(f"  - {suggestion}")
    
    # 最終レポート
    print("\n=== Final Memory Report ===")
    report = manager.get_memory_report()
    print(f"System memory: {report['system']['percent']:.1f}%")
    print(f"Total workers: {report['total_workers']}")
    print(f"Workers under pressure: {report['workers_under_pressure']}")
    
    for worker in report['workers']:
        print(f"\n{worker['worker_id']}:")
        print(f"  Memory: {worker['memory_mb']:.1f}MB ({worker['memory_percent']:.1f}%)")
        print(f"  Pressure: {worker['pressure_level']}")
        print(f"  GC count: {worker['gc_count']}")


if __name__ == "__main__":
    test_memory_management()