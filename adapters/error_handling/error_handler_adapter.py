"""
ErrorHandlerのアダプター

レガシーのErrorHandlerをドメインインターフェースに適応させます。
"""

from typing import Any

from core.error_handling import ErrorHandler as LegacyErrorHandler
from domain.interfaces.error_handler import IErrorHandler


class ErrorHandlerAdapter(IErrorHandler):
    """
    ErrorHandlerのアダプター実装

    レガシーのErrorHandlerをラップして、ドメインインターフェースを提供します。
    """

    def __init__(self, logger=None):
        """
        初期化

        Args:
            logger: ロガーインスタンス
        """
        self._legacy_handler = LegacyErrorHandler(logger=logger)

    def handle_error(self, error: Exception, context: str, raise_after: bool = True) -> dict[str, Any] | None:
        """
        エラーをハンドリング

        Args:
            error: 発生したエラー
            context: エラーが発生したコンテキスト
            raise_after: ハンドリング後に例外を再発生させるか

        Returns:
            エラー情報の辞書（user_message, detailsなど）
        """
        return self._legacy_handler.handle_error(error=error, context=context, raise_after=raise_after)
