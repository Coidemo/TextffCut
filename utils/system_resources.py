"""
システムリソース管理モジュール
メモリやCPUの状態を監視し、最適な並列数を決定する
"""
import os
import psutil
from dataclasses import dataclass
from typing import Tuple
from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SystemSpec:
    """システムスペック情報"""
    total_memory_gb: float
    available_memory_gb: float
    cpu_count: int
    cpu_physical_count: int
    spec_level: str  # 'low', 'mid', 'high'
    recommended_api_workers: int
    recommended_align_workers: int
    recommended_chunk_seconds: int


class SystemResourceManager:
    """システムリソース管理クラス"""
    
    # スペックレベルの閾値（GB）
    LOW_SPEC_MEMORY = 4
    MID_SPEC_MEMORY = 8
    
    def __init__(self):
        self.process = psutil.Process()
    
    def get_system_spec(self) -> SystemSpec:
        """現在のシステムスペックを取得"""
        # メモリ情報
        memory = psutil.virtual_memory()
        total_memory_gb = memory.total / (1024**3)
        available_memory_gb = memory.available / (1024**3)
        
        # CPU情報
        cpu_count = os.cpu_count() or 4
        cpu_physical_count = psutil.cpu_count(logical=False) or cpu_count // 2
        
        # 強制低スペックモード（テスト用）
        if os.environ.get("TEXTFFCUT_FORCE_LOW_SPEC") == "true":
            spec_level = 'low'
            total_memory_gb = 3.0  # 3GBと偽装
            available_memory_gb = min(available_memory_gb, 2.0)  # 最大2GB
            logger.info("強制低スペックモードが有効です（テスト用）")
        else:
            # スペックレベルの判定
            if total_memory_gb < self.LOW_SPEC_MEMORY:
                spec_level = 'low'
            elif total_memory_gb < self.MID_SPEC_MEMORY:
                spec_level = 'mid'
            else:
                spec_level = 'high'
        
        # 推奨並列数の計算
        api_workers, align_workers, chunk_seconds = self._calculate_optimal_workers(
            available_memory_gb, cpu_count, spec_level
        )
        
        spec = SystemSpec(
            total_memory_gb=total_memory_gb,
            available_memory_gb=available_memory_gb,
            cpu_count=cpu_count,
            cpu_physical_count=cpu_physical_count,
            spec_level=spec_level,
            recommended_api_workers=api_workers,
            recommended_align_workers=align_workers,
            recommended_chunk_seconds=chunk_seconds
        )
        
        logger.info(f"システムスペック検出: {spec_level} (メモリ: {total_memory_gb:.1f}GB, CPU: {cpu_count}コア)")
        logger.info(f"推奨設定: API並列数={api_workers}, アライメント並列数={align_workers}, チャンクサイズ={chunk_seconds}秒")
        
        return spec
    
    def _calculate_optimal_workers(self, available_memory_gb: float, cpu_count: int, spec_level: str) -> Tuple[int, int, int]:
        """最適なワーカー数とチャンクサイズを計算"""
        # 低スペックPC（メモリ4GB未満）
        if spec_level == 'low':
            # メモリ制約が厳しいので並列数を抑える
            api_workers = min(3, cpu_count)
            align_workers = 1  # アライメントは1つのみ（メモリ節約）
            chunk_seconds = 20  # 小さいチャンクでメモリ節約
            
        # 中スペックPC（メモリ4-8GB）
        elif spec_level == 'mid':
            # バランス重視
            api_workers = min(5, cpu_count)
            align_workers = min(2, cpu_count // 2)
            chunk_seconds = 30
            
        # 高スペックPC（メモリ8GB以上）
        else:
            # パフォーマンス重視
            api_workers = min(15, cpu_count * 2)  # APIは非同期なので多めに（最大15に増加）
            align_workers = min(5, cpu_count // 2)  # アライメントも最大5に増加
            chunk_seconds = 60  # 大きいチャンクで効率化
        
        # 利用可能メモリに基づく調整（閾値を緩和）
        if available_memory_gb < 1:  # 2GB → 1GBに緩和
            # メモリが本当に逼迫している場合のみ制限
            api_workers = min(api_workers, 3)
            align_workers = 1
            logger.warning(f"利用可能メモリが非常に少ない({available_memory_gb:.1f}GB)ため、並列数を制限します")
        elif available_memory_gb < 2:
            # 軽い制限のみ
            api_workers = min(api_workers, 5)
            align_workers = min(align_workers, 2)
            logger.info(f"利用可能メモリ({available_memory_gb:.1f}GB)に基づいて並列数を調整")
        
        return api_workers, align_workers, chunk_seconds
    
    def get_memory_usage(self) -> float:
        """現在のプロセスのメモリ使用量を取得（GB）"""
        return self.process.memory_info().rss / (1024**3)
    
    def check_memory_pressure(self) -> bool:
        """メモリ圧迫状態かチェック"""
        memory = psutil.virtual_memory()
        # 利用可能メモリが1GB未満、または使用率が90%以上
        return memory.available < 1024**3 or memory.percent > 90
    
    def adjust_workers_for_memory(self, current_api_workers: int, current_align_workers: int) -> Tuple[int, int]:
        """メモリ圧迫時にワーカー数を調整"""
        if self.check_memory_pressure():
            logger.warning("メモリ圧迫を検出。ワーカー数を削減します")
            # API並列数を半分に
            new_api_workers = max(1, current_api_workers // 2)
            # アライメントは1つに制限
            new_align_workers = 1
            return new_api_workers, new_align_workers
        return current_api_workers, current_align_workers


# グローバルインスタンス
system_resource_manager = SystemResourceManager()


# 互換性のための関数
def get_memory_info() -> dict:
    """メモリ情報を取得（互換性のため）"""
    memory = psutil.virtual_memory()
    return {
        'total_gb': memory.total / (1024**3),
        'available_gb': memory.available / (1024**3),
        'used_gb': memory.used / (1024**3),
        'percent': memory.percent
    }