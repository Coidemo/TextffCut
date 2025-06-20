"""
サービス層の基底クラスと共通型定義

すべてのサービスクラスはこの基底クラスを継承し、
統一されたインターフェースを提供する。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from config import Config
from utils.logging import get_logger
from core.constants import ErrorMessages


@dataclass
class ServiceResult:
    """サービス層の統一レスポンス
    
    Attributes:
        success: 処理の成功/失敗
        data: 処理結果のデータ
        error: エラーメッセージ（失敗時）
        error_type: エラーの種類（分類用）
        metadata: 追加のメタデータ
        timestamp: 処理実行時刻
    """
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """データ検証"""
        if self.success and self.error:
            raise ValueError("成功時にエラーメッセージは設定できません")
        if not self.success and not self.error:
            raise ValueError("失敗時はエラーメッセージが必要です")


# 型パラメータ（ジェネリック用）
T = TypeVar('T')


@dataclass
class TypedServiceResult(Generic[T]):
    """型付きサービスレスポンス（型安全性向上）"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


class ServiceError(Exception):
    """サービス層の基本エラー"""
    def __init__(self, message: str, error_type: str = "ServiceError"):
        super().__init__(message)
        self.error_type = error_type


class ValidationError(ServiceError):
    """入力検証エラー"""
    def __init__(self, message: str):
        super().__init__(message, "ValidationError")


class ProcessingError(ServiceError):
    """処理実行エラー"""
    def __init__(self, message: str):
        super().__init__(message, "ProcessingError")


class BaseService(ABC):
    """サービス層の基底クラス
    
    すべてのサービスクラスはこのクラスを継承する。
    共通のロギング、エラーハンドリング、設定管理を提供。
    """
    
    def __init__(self, config: Config):
        """初期化
        
        Args:
            config: アプリケーション設定
        """
        self.config = config
        self.logger = get_logger(self.__class__.__name__)
        self._initialize()
    
    def _initialize(self):
        """サブクラス固有の初期化処理（オーバーライド可能）"""
        pass
    
    @abstractmethod
    def execute(self, **kwargs) -> ServiceResult:
        """サービスのメイン実行メソッド
        
        サブクラスで実装必須。
        
        Args:
            **kwargs: サービス固有のパラメータ
            
        Returns:
            ServiceResult: 処理結果
        """
        pass
    
    def validate_file_exists(self, file_path: str) -> Path:
        """ファイルの存在確認
        
        Args:
            file_path: 確認するファイルパス
            
        Returns:
            Path: 正規化されたPathオブジェクト
            
        Raises:
            ValidationError: ファイルが存在しない場合
        """
        path = Path(file_path)
        if not path.exists():
            raise ValidationError(f"ファイルが見つかりません: {file_path}")
        if not path.is_file():
            raise ValidationError(f"ファイルではありません: {file_path}")
        return path
    
    def validate_directory_exists(self, dir_path: str) -> Path:
        """ディレクトリの存在確認
        
        Args:
            dir_path: 確認するディレクトリパス
            
        Returns:
            Path: 正規化されたPathオブジェクト
            
        Raises:
            ValidationError: ディレクトリが存在しない場合
        """
        path = Path(dir_path)
        if not path.exists():
            raise ValidationError(f"ディレクトリが見つかりません: {dir_path}")
        if not path.is_dir():
            raise ValidationError(f"ディレクトリではありません: {dir_path}")
        return path
    
    def wrap_error(self, error: Exception) -> ServiceResult:
        """エラーをServiceResultにラップ
        
        Args:
            error: 発生したエラー
            
        Returns:
            ServiceResult: エラー情報を含む結果
        """
        if isinstance(error, ServiceError):
            return ServiceResult(
                success=False,
                error=str(error),
                error_type=error.error_type
            )
        else:
            # 予期しないエラー
            self.logger.error(f"予期しないエラー: {error}", exc_info=True)
            return ServiceResult(
                success=False,
                error=str(error),
                error_type="UnexpectedError"
            )
    
    def create_success_result(
        self, 
        data: Any = None, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult:
        """成功結果の作成ヘルパー
        
        Args:
            data: 結果データ
            metadata: メタデータ
            
        Returns:
            ServiceResult: 成功結果
        """
        return ServiceResult(
            success=True,
            data=data,
            metadata=metadata or {}
        )
    
    def create_error_result(
        self, 
        error: str, 
        error_type: str = "Error",
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult:
        """エラー結果の作成ヘルパー
        
        Args:
            error: エラーメッセージ
            error_type: エラータイプ
            metadata: メタデータ
            
        Returns:
            ServiceResult: エラー結果
        """
        return ServiceResult(
            success=False,
            error=error,
            error_type=error_type,
            metadata=metadata or {}
        )


class AsyncBaseService(BaseService):
    """非同期サービスの基底クラス（将来の拡張用）"""
    
    @abstractmethod
    async def execute_async(self, **kwargs) -> ServiceResult:
        """非同期実行メソッド"""
        pass
    
    def execute(self, **kwargs) -> ServiceResult:
        """同期実行のラッパー（互換性のため）"""
        import asyncio
        return asyncio.run(self.execute_async(**kwargs))