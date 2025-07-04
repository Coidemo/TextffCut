"""
基底Viewクラス

Presentation層のViewの基底クラスを提供します。
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from presentation.view_models.base import BaseViewModel

T = TypeVar("T", bound=BaseViewModel)


class BaseView(ABC, Generic[T]):
    """
    Viewの基底クラス

    MVPパターンのView部分を担当し、UIの表示と更新を行います。
    ViewModelの変更を監視し、必要に応じて再描画を行います。
    """

    def __init__(self, view_model: T):
        """
        初期化

        Args:
            view_model: このViewが監視するViewModel
        """
        self.view_model = view_model
        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    @abstractmethod
    def render(self) -> None:
        """UIをレンダリング"""
        pass

    def update(self, view_model: BaseViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # デフォルトでは何もしない
        # Streamlitの場合、自動的に再描画されるため
        pass

    def dispose(self) -> None:
        """リソースの解放"""
        # ViewModelの監視を解除
        self.view_model.unsubscribe(self)
