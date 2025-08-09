"""
柔軟なパフォーマンスプロファイル管理
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FlexiblePerformanceProfile:
    """ユーザーの選択を尊重する設定管理"""
    
    # 最適化設定
    optimization_preference: str = "auto"  # "auto", "always", "never", "memory_critical"
    
    # 処理設定
    batch_size: Optional[int] = None
    compute_type: Optional[str] = None
    
    # 詳細設定
    max_conversion_time: int = 300  # 最大変換時間（秒）
    min_memory_threshold_gb: float = 4.0  # 最小メモリ閾値
    
    # 統計情報
    performance_history: List[Dict] = field(default_factory=list)
    
    def get_optimization_preference_display(self) -> str:
        """ユーザー向けの表示テキスト"""
        
        displays = {
            "auto": "自動判断（推奨）",
            "always": "常に最適化",
            "never": "最適化しない",
            "memory_critical": "メモリ優先"
        }
        
        return displays.get(self.optimization_preference, "自動判断")
    
    def record_performance(self, metrics: Dict[str, Any]):
        """パフォーマンス記録"""
        self.performance_history.append({
            'timestamp': datetime.now().isoformat(),
            'metrics': metrics
        })
        
        # 最新20件のみ保持
        self.performance_history = self.performance_history[-20:]
    
    def suggest_settings_based_on_history(self) -> Dict[str, Any]:
        """履歴に基づく推奨設定"""
        if len(self.performance_history) < 3:
            return {}
        
        # メモリエラーの頻度
        memory_errors = sum(
            1 for h in self.performance_history 
            if 'error' in h['metrics'] and 'memory' in h['metrics']['error'].lower()
        )
        
        # 平均処理時間
        processing_times = [
            h['metrics'].get('processing_time', 0) 
            for h in self.performance_history
            if h['metrics'].get('success', False)
        ]
        avg_time = sum(processing_times) / len(processing_times) if processing_times else 0
        
        suggestions = {}
        
        if memory_errors > len(self.performance_history) * 0.3:
            suggestions['optimization_preference'] = 'memory_critical'
            suggestions['reason'] = 'メモリエラーが頻発しています'
        elif avg_time > 600:  # 10分以上
            suggestions['batch_size'] = 8
            suggestions['reason'] = '処理時間を短縮するため'
        
        return suggestions
    
    def get_processing_config(self) -> Dict[str, Any]:
        """処理設定の取得"""
        
        base_config = {
            'use_manual_chunks': False,  # 常にFalse（WhisperXに委譲）
            'batch_size': self.batch_size or self._get_default_batch_size(),
            'compute_type': self.compute_type or 'int8',
        }
        
        # エラー履歴に基づく自動調整
        recent_errors = [
            h for h in self.performance_history[-5:]  # 最新5件
            if not h['metrics'].get('success', True)
        ]
        
        if recent_errors:
            last_error = recent_errors[-1]
            if "OutOfMemoryError" in last_error['metrics'].get('error', ''):
                base_config['batch_size'] = max(1, base_config['batch_size'] // 2)
                logger.info(f"メモリエラーのためバッチサイズを調整: {base_config['batch_size']}")
        
        return base_config
    
    def _get_default_batch_size(self) -> int:
        """最適化レベルに応じたデフォルトバッチサイズ"""
        
        if self.optimization_preference == "memory_critical":
            return 2
        elif self.optimization_preference == "never":
            return 8  # 最適化しない場合は大きめ
        else:  # "auto" or "always"
            return 4
    
    def save(self, config_path: Optional[Path] = None):
        """プロファイルを保存"""
        if config_path is None:
            config_dir = Path.home() / ".textffcut"
            config_dir.mkdir(exist_ok=True)
            config_path = config_dir / "performance_profile.json"
        
        data = asdict(self)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"パフォーマンスプロファイルを保存: {config_path}")
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "FlexiblePerformanceProfile":
        """保存されたプロファイルを読み込み"""
        if config_path is None:
            config_path = Path.home() / ".textffcut" / "performance_profile.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                logger.info(f"パフォーマンスプロファイルを読み込み: {config_path}")
                return cls(**data)
            except Exception as e:
                logger.warning(f"プロファイル読み込みエラー: {e}")
        
        logger.info("デフォルトのパフォーマンスプロファイルを使用")
        return cls()
    
    def should_optimize_audio(self, available_memory_gb: float) -> bool:
        """音声最適化の必要性を判断"""
        
        if self.optimization_preference == "always":
            return True
        elif self.optimization_preference == "never":
            return False
        elif self.optimization_preference == "memory_critical":
            return True
        else:  # "auto"
            # メモリが閾値以下なら最適化
            return available_memory_gb < self.min_memory_threshold_gb
    
    def get_safe_batch_size(self, device: str, available_memory_gb: float) -> int:
        """安全なバッチサイズを決定"""
        
        # ユーザー指定があれば優先
        if self.batch_size is not None:
            return self.batch_size
        
        # デバイスとメモリに基づく推奨値
        if device == 'cuda':
            # GPU使用時
            try:
                import torch
                gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
                if gpu_memory >= 8:
                    return 16
                elif gpu_memory >= 4:
                    return 8
                else:
                    return 4
            except:
                return 4
        else:
            # CPU使用時
            if available_memory_gb >= 16:
                return 8
            elif available_memory_gb >= 8:
                return 4
            else:
                return 2
    
    def update_from_suggestions(self, suggestions: Dict[str, Any]):
        """提案された設定で更新"""
        
        if 'optimization_preference' in suggestions:
            self.optimization_preference = suggestions['optimization_preference']
        
        if 'batch_size' in suggestions:
            self.batch_size = suggestions['batch_size']
        
        if 'compute_type' in suggestions:
            self.compute_type = suggestions['compute_type']
        
        logger.info(f"設定を更新: {suggestions}")
    
    def get_summary(self) -> Dict[str, Any]:
        """設定のサマリー"""
        
        success_count = sum(
            1 for h in self.performance_history
            if h['metrics'].get('success', False)
        )
        
        error_count = len(self.performance_history) - success_count
        
        return {
            'current_settings': {
                'optimization': self.get_optimization_preference_display(),
                'batch_size': self.batch_size or 'auto',
                'compute_type': self.compute_type or 'auto',
            },
            'statistics': {
                'total_runs': len(self.performance_history),
                'success_count': success_count,
                'error_count': error_count,
                'success_rate': success_count / len(self.performance_history) * 100 if self.performance_history else 0
            }
        }