"""
ユースケースの基底クラス
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar


@dataclass
class UseCaseRequest:
    """ユースケースリクエストの基底クラス"""

    pass


@dataclass
class UseCaseResponse:
    """ユースケースレスポンスの基底クラス"""

    success: bool = True
    error_message: str | None = None
    data: Any = None


TRequest = TypeVar("TRequest", bound=UseCaseRequest)
TResponse = TypeVar("TResponse", bound=UseCaseResponse)


class UseCase(ABC, Generic[TRequest, TResponse]):
    """ユースケースの基底クラス"""

    @abstractmethod
    def execute(self, request: TRequest) -> TResponse:
        """ユースケースを実行"""
        pass
