"""
ユースケース層

アプリケーションのビジネスロジックを定義します。
ドメイン層のエンティティを使用し、外部システムとの
やり取りはゲートウェイインターフェースを通じて行います。
"""

from .base import UseCase, UseCaseError

__all__ = [
    "UseCase",
    "UseCaseError",
]
