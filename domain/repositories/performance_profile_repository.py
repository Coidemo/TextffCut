"""
パフォーマンスプロファイルのリポジトリインターフェース
"""

from abc import ABC, abstractmethod
from typing import Optional

from domain.entities.performance_profile import PerformanceProfile


class IPerformanceProfileRepository(ABC):
    """パフォーマンスプロファイルのリポジトリインターフェース"""

    @abstractmethod
    def save(self, profile: PerformanceProfile) -> None:
        """プロファイルを保存"""
        pass

    @abstractmethod
    def load(self) -> Optional[PerformanceProfile]:
        """プロファイルを読み込み"""
        pass

    @abstractmethod
    def get_default(self) -> PerformanceProfile:
        """デフォルトプロファイルを取得"""
        pass
