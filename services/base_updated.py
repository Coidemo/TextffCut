"""
サービス層の基底クラスと共通型定義（エラーハンドリング統合版）

すべてのサービスクラスはこの基底クラスを継承し、
統一されたインターフェースを提供する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, TypeVar

from config import Config
from core.error_handling import (
    ErrorHandler,
    FileValidationError,
    TextffCutError,
)
from core.error_handling import (
    ProcessingError as CoreProcessingError,
)
from core.error_handling import (
    ValidationError as CoreValidationError,
)
from utils.logging import get_logger


@dataclass
class ServiceResult:
    """サービス層の統一レスポンス

    Attributes:
        success: 処理の成功/失敗
        data: 処理結果のデータ
        error: エラーメッセージ（失敗時）
        error_type: エラーの種類（分類用）
        error_code: エラーコード（新規追加）
        metadata: 追加のメタデータ
        timestamp: 処理実行時刻
    """

    success: bool
    data: Any | None = None
    error: str | None = None
    error_type: str | None = None
    error_code: str | None = None  # 新規追加
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """データ検証"""
        if self.success and self.error:
            raise ValueError("成功時にエラーメッセージは設定できません")
        if not self.success and not self.error:
            raise ValueError("失敗時はエラーメッセージが必要です")


# 型パラメータ（ジェネリック用）
T = TypeVar("T")


@dataclass
class TypedServiceResult(Generic[T]):
    """型付きサービスレスポンス（型安全性向上）"""

    success: bool
    data: T | None = None
    error: str | None = None
    error_type: str | None = None
    error_code: str | None = None  # 新規追加
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


# 後方互換性のためのエイリアス（非推奨）
ServiceError = TextffCutError
ValidationError = CoreValidationError
ProcessingError = CoreProcessingError


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
        self.error_handler = ErrorHandler(self.logger)  # 新規追加
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
            FileValidationError: ファイルが存在しない場合
        """
        path = Path(file_path)
        if not path.exists():
            raise FileValidationError(f"ファイルが見つかりません: {file_path}", details={"path": file_path})
        if not path.is_file():
            raise FileValidationError(
                f"ファイルではありません: {file_path}", details={"path": file_path, "is_directory": path.is_dir()}
            )
        return path

    def validate_directory_exists(self, dir_path: str) -> Path:
        """ディレクトリの存在確認

        Args:
            dir_path: 確認するディレクトリパス

        Returns:
            Path: 正規化されたPathオブジェクト

        Raises:
            FileValidationError: ディレクトリが存在しない場合
        """
        path = Path(dir_path)
        if not path.exists():
            raise FileValidationError(f"ディレクトリが見つかりません: {dir_path}", details={"path": dir_path})
        if not path.is_dir():
            raise FileValidationError(
                f"ディレクトリではありません: {dir_path}", details={"path": dir_path, "is_file": path.is_file()}
            )
        return path

    def create_success_result(self, data: Any = None, metadata: dict[str, Any] | None = None) -> ServiceResult:
        """成功結果を作成

        Args:
            data: 処理結果のデータ
            metadata: 追加のメタデータ

        Returns:
            ServiceResult: 成功結果
        """
        return ServiceResult(success=True, data=data, metadata=metadata or {})

    def create_error_result(
        self,
        error: str,
        error_type: str = "ProcessingError",
        error_code: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ServiceResult:
        """エラー結果を作成

        Args:
            error: エラーメッセージ
            error_type: エラーの種類
            error_code: エラーコード
            metadata: 追加のメタデータ

        Returns:
            ServiceResult: エラー結果
        """
        return ServiceResult(
            success=False, error=error, error_type=error_type, error_code=error_code, metadata=metadata or {}
        )

    def wrap_error(self, error: Exception) -> ServiceResult:
        """例外をServiceResultにラップ

        統一エラーハンドリングシステムと統合

        Args:
            error: ラップする例外

        Returns:
            ServiceResult: エラー結果
        """
        # エラーハンドラーで処理
        error_info = self.error_handler.handle_error(error, context=self.__class__.__name__, raise_after=False)

        # ユーザー向けメッセージを取得
        user_message = ErrorHandler.format_user_message(error)

        return ServiceResult(
            success=False,
            error=user_message,
            error_type=error_info.get("error_type", "UnknownError"),
            error_code=error_info.get("error_code"),
            metadata={"error_details": error_info, "recoverable": ErrorHandler.is_recoverable(error)},
        )

    def log_and_wrap_error(self, message: str, error: Exception, **kwargs) -> ServiceResult:
        """エラーをログに記録してServiceResultにラップ

        Args:
            message: ログメッセージ
            error: ラップする例外
            **kwargs: 追加のログ情報

        Returns:
            ServiceResult: エラー結果
        """
        self.logger.error(message, exc_info=True, extra=kwargs)
        return self.wrap_error(error)

    def handle_service_error(self, operation: str, error: Exception) -> ServiceResult:
        """サービス操作のエラーをハンドリング

        Args:
            operation: 実行中の操作名
            error: 発生したエラー

        Returns:
            ServiceResult: エラー結果
        """
        context_message = f"{self.__class__.__name__}.{operation}"

        # TextffCutErrorの場合は詳細情報を保持
        if isinstance(error, TextffCutError):
            return ServiceResult(
                success=False,
                error=error.user_message,
                error_type=type(error).__name__,
                error_code=error.error_code,
                metadata={"operation": operation, "details": error.details, "recoverable": error.recoverable},
            )

        # その他のエラーはwrap_errorを使用
        return self.wrap_error(error)
