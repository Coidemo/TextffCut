"""
基底Presenterクラス

Presentation層のPresenterの基底クラスを提供します。
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional, Any
import logging

from presentation.view_models.base import BaseViewModel, ViewModelObserver

logger = logging.getLogger(__name__)

# ViewModelの型変数
TViewModel = TypeVar('TViewModel', bound=BaseViewModel)


class BasePresenter(Generic[TViewModel], ABC):
    """
    Presenterの基底クラス
    
    MVPパターンのPresenter部分を担当し、ViewとModelの仲介を行います。
    ユーザーイベントの処理、ビジネスロジックの呼び出し、ViewModelの更新を行います。
    """
    
    def __init__(self, view_model: TViewModel):
        """
        初期化
        
        Args:
            view_model: 管理するViewModel
        """
        self.view_model = view_model
        self._is_initialized = False
        
        # ViewModelの変更を監視（ViewModelObserverインターフェースを実装）
        if hasattr(self, 'update'):
            self.view_model.subscribe(self)
    
    def update(self, view_model: BaseViewModel) -> None:
        """
        ViewModelの変更通知を受け取る
        
        Args:
            view_model: 変更されたViewModel
        """
        # デフォルトでは何もしない（サブクラスでオーバーライド可能）
        logger.debug(f"{self.__class__.__name__} received update from {view_model.__class__.__name__}")
    
    @abstractmethod
    def initialize(self) -> None:
        """
        初期化処理
        
        ViewModelの初期状態を設定し、必要なデータを読み込みます。
        """
        pass
    
    def cleanup(self) -> None:
        """
        クリーンアップ処理
        
        リソースの解放やオブザーバーの登録解除を行います。
        """
        self.view_model.unsubscribe(self)
        self._is_initialized = False
    
    def handle_error(self, error: Exception, context: str = "") -> None:
        """
        エラーハンドリングの共通処理
        
        Args:
            error: 発生したエラー
            context: エラーが発生したコンテキスト
        """
        error_message = str(error)
        if context:
            error_message = f"{context}: {error_message}"
        
        logger.error(f"{self.__class__.__name__} - {error_message}", exc_info=True)
        
        # ViewModelにエラー情報を設定する共通パターン
        if hasattr(self.view_model, 'set_error'):
            self.view_model.set_error(error_message, {"exception": str(type(error).__name__)})
        elif hasattr(self.view_model, 'error_message'):
            self.view_model.error_message = error_message
            self.view_model.notify()
    
    @property
    def is_initialized(self) -> bool:
        """初期化済みかどうか"""
        return self._is_initialized
    
    def ensure_initialized(self) -> None:
        """初期化を保証"""
        if not self._is_initialized:
            self.initialize()
            self._is_initialized = True
    
    def execute_with_loading(self, operation, loading_attr: str = "is_loading") -> Any:
        """
        ローディング状態を管理しながら操作を実行
        
        Args:
            operation: 実行する操作（callable）
            loading_attr: ローディング状態を管理する属性名
            
        Returns:
            操作の結果
        """
        # ローディング開始
        if hasattr(self.view_model, loading_attr):
            setattr(self.view_model, loading_attr, True)
            self.view_model.notify()
        
        try:
            # 操作を実行
            result = operation()
            return result
        finally:
            # ローディング終了
            if hasattr(self.view_model, loading_attr):
                setattr(self.view_model, loading_attr, False)
                self.view_model.notify()
    
    def validate_state(self) -> Optional[str]:
        """
        現在の状態を検証
        
        Returns:
            エラーメッセージ（妥当な場合はNone）
        """
        return self.view_model.validate()