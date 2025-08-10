"""
パフォーマンスプロファイルリポジトリの実装
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from domain.entities.performance_profile import PerformanceProfile, PerformanceMetrics
from domain.repositories.performance_profile_repository import IPerformanceProfileRepository
from utils.logging import get_logger

logger = get_logger(__name__)


class FilePerformanceProfileRepository(IPerformanceProfileRepository):
    """ファイルベースのパフォーマンスプロファイルリポジトリ"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path.home() / ".textffcut"
        self.config_dir = config_dir
        self.config_file = config_dir / "performance_profile.json"
        
        # ディレクトリ作成
        self.config_dir.mkdir(exist_ok=True)
    
    def save(self, profile: PerformanceProfile) -> None:
        """プロファイルを保存"""
        try:
            data = {
                'id': profile.id,
                # optimization_preferenceとbatch_sizeは削除
                'compute_type': profile.compute_type,
                'max_conversion_time': profile.max_conversion_time,
                'min_memory_threshold_gb': profile.min_memory_threshold_gb,
                'metrics_history': [m.to_dict() for m in profile.metrics_history]
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"パフォーマンスプロファイルを保存: {self.config_file}")
            
        except Exception as e:
            logger.error(f"プロファイル保存エラー: {e}")
            raise
    
    def load(self) -> Optional[PerformanceProfile]:
        """プロファイルを読み込み"""
        if not self.config_file.exists():
            logger.info("プロファイルファイルが存在しません")
            return None
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # メトリクス履歴の復元
            metrics_history = []
            for m_data in data.get('metrics_history', []):
                metrics = PerformanceMetrics(
                    timestamp=datetime.fromisoformat(m_data['timestamp']),
                    success=m_data['success'],
                    processing_time=m_data['processing_time'],
                    error_message=m_data.get('error_message'),
                    optimization_info=m_data.get('optimization_info')
                )
                metrics_history.append(metrics)
            
            profile = PerformanceProfile(
                id=data.get('id', f"profile_{datetime.now().timestamp()}"),
                # optimization_preferenceとbatch_sizeは削除
                compute_type=data.get('compute_type'),
                max_conversion_time=data.get('max_conversion_time', 300),
                min_memory_threshold_gb=data.get('min_memory_threshold_gb', 4.0),
                metrics_history=metrics_history
            )
            
            logger.info(f"パフォーマンスプロファイルを読み込み: {self.config_file}")
            return profile
            
        except Exception as e:
            logger.error(f"プロファイル読み込みエラー: {e}")
            return None
    
    def get_default(self) -> PerformanceProfile:
        """デフォルトプロファイルを取得"""
        return PerformanceProfile()