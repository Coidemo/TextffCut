"""
エラーハンドリングのインターフェース

ドメイン層で定義されるエラーハンドリングの抽象インターフェース。
"""

from abc import ABC, abstractmethod
from typing import Any


class IErrorHandler(ABC):
    """
    エラーハンドラーのインターフェース

    エラーのハンドリングとユーザーへのメッセージ提供を担当します。
    """

    @abstractmethod
    def handle_error(self, error: Exception, context: str, raise_after: bool = True) -> dict[str, Any] | None:
        """
        エラーをハンドリング

        Args:
            error: 発生したエラー
            context: エラーが発生したコンテキスト
            raise_after: ハンドリング後に例外を再発生させるか

        Returns:
            エラー情報の辞書（user_message, detailsなど）
            raise_afterがTrueの場合はNone
        """
        pass
