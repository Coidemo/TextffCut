"""
基底ViewModelクラス

Presentation層のViewModelの基底クラスを提供します。
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class ViewModelObserver(Protocol):
    """ViewModelのオブザーバーインターフェース"""

    def update(self, view_model: "BaseViewModel") -> None:
        """ViewModelの変更通知を受け取る"""
        ...


@dataclass
class BaseViewModel(ABC):
    """
    ViewModelの基底クラス

    MVPパターンのModel部分を担当し、UIに表示するデータを保持します。
    オブザーバーパターンを実装し、データ変更時に通知を送ります。
    """

    # オブザーバーリスト（初期化時は空）
    _observers: list[ViewModelObserver] = field(default_factory=list, init=False, repr=False)

    # 変更追跡用
    _is_dirty: bool = field(default=False, init=False, repr=False)

    def subscribe(self, observer: ViewModelObserver) -> None:
        """
        オブザーバーを登録

        Args:
            observer: 変更通知を受け取るオブザーバー
        """
        if observer not in self._observers:
            self._observers.append(observer)
            logger.debug(f"Observer {observer} subscribed to {self.__class__.__name__}")

    def unsubscribe(self, observer: ViewModelObserver) -> None:
        """
        オブザーバーの登録解除

        Args:
            observer: 登録解除するオブザーバー
        """
        if observer in self._observers:
            self._observers.remove(observer)
            logger.debug(f"Observer {observer} unsubscribed from {self.__class__.__name__}")

    def notify(self) -> None:
        """すべてのオブザーバーに変更を通知"""
        self._is_dirty = True
        for observer in self._observers:
            try:
                observer.update(self)
            except Exception as e:
                logger.error(f"Error notifying observer {observer}: {e}")

    def mark_clean(self) -> None:
        """変更フラグをクリア"""
        self._is_dirty = False

    @property
    def is_dirty(self) -> bool:
        """変更されているかどうか"""
        return self._is_dirty

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """
        ViewModelを辞書形式に変換

        Returns:
            ViewModelのデータを含む辞書
        """
        pass

    @abstractmethod
    def validate(self) -> str | None:
        """
        ViewModelの妥当性を検証

        Returns:
            エラーメッセージ（妥当な場合はNone）
        """
        pass

    def update_from_dict(self, data: dict[str, Any]) -> None:
        """
        辞書からViewModelを更新

        Args:
            data: 更新データを含む辞書
        """
        for key, value in data.items():
            if hasattr(self, key) and not key.startswith("_"):
                setattr(self, key, value)
        self.notify()
