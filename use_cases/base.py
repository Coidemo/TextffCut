"""
ユースケース基底クラスと共通例外
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, Any
import logging


# 入力と出力の型変数
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


class UseCaseError(Exception):
    """ユースケース実行中のエラー"""
    def __init__(self, message: str, cause: Optional[Exception] = None):
        super().__init__(message)
        self.cause = cause


class UseCase(ABC, Generic[TInput, TOutput]):
    """
    ユースケースの基底クラス
    
    すべてのユースケースはこのクラスを継承し、
    executeメソッドを実装する必要があります。
    """
    
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    @abstractmethod
    def execute(self, request: TInput) -> TOutput:
        """
        ユースケースのメインロジックを実行
        
        Args:
            request: ユースケースへの入力
            
        Returns:
            ユースケースの実行結果
            
        Raises:
            UseCaseError: ビジネスロジックエラー
        """
        pass
    
    def validate_request(self, request: TInput) -> None:
        """
        リクエストのバリデーション（オーバーライド可能）
        
        Args:
            request: 検証するリクエスト
            
        Raises:
            UseCaseError: バリデーションエラー
        """
        pass
    
    def __call__(self, request: TInput) -> TOutput:
        """
        ユースケースを関数のように呼び出し可能にする
        
        バリデーション → 実行 → ロギングの流れを標準化
        """
        try:
            self.logger.debug(f"Executing {self.__class__.__name__} with request: {request}")
            
            # リクエストのバリデーション
            self.validate_request(request)
            
            # メインロジックの実行
            result = self.execute(request)
            
            self.logger.debug(f"Successfully executed {self.__class__.__name__}")
            return result
            
        except UseCaseError:
            # UseCaseErrorはそのまま再スロー
            raise
        except Exception as e:
            # その他のエラーはUseCaseErrorでラップ
            self.logger.error(f"Error in {self.__class__.__name__}: {str(e)}", exc_info=True)
            raise UseCaseError(
                f"Failed to execute {self.__class__.__name__}: {str(e)}",
                cause=e
            )