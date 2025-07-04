"""
ユースケース基底クラスのテスト
"""

import logging
from unittest.mock import patch

import pytest

from use_cases.base import UseCase, UseCaseError


# テスト用の具体的なユースケース実装
class ConcreteUseCase(UseCase[str, str]):
    """テスト用の具体実装"""

    def execute(self, request: str) -> str:
        if request == "error":
            raise ValueError("Test error")
        return f"Result: {request}"

    def validate_request(self, request: str) -> None:
        if request == "invalid":
            raise UseCaseError("Invalid request")


class TestUseCase:
    """UseCaseクラスのテスト"""

    def test_create_use_case(self):
        """ユースケースの作成"""
        use_case = ConcreteUseCase()
        assert use_case is not None
        assert isinstance(use_case.logger, logging.Logger)
        assert use_case.logger.name == "ConcreteUseCase"

    def test_execute_success(self):
        """正常な実行"""
        use_case = ConcreteUseCase()
        result = use_case("test")
        assert result == "Result: test"

    def test_execute_with_call(self):
        """__call__メソッドでの実行"""
        use_case = ConcreteUseCase()
        result = use_case("test")
        assert result == "Result: test"

    def test_validation_error(self):
        """バリデーションエラー"""
        use_case = ConcreteUseCase()

        with pytest.raises(UseCaseError) as exc_info:
            use_case("invalid")

        assert str(exc_info.value) == "Invalid request"

    def test_execution_error_wrapped(self):
        """実行時エラーがUseCaseErrorでラップされる"""
        use_case = ConcreteUseCase()

        with pytest.raises(UseCaseError) as exc_info:
            use_case("error")

        assert "Failed to execute ConcreteUseCase" in str(exc_info.value)
        assert isinstance(exc_info.value.cause, ValueError)
        assert str(exc_info.value.cause) == "Test error"

    def test_logging(self):
        """ロギングの動作確認"""
        use_case = ConcreteUseCase()

        with patch.object(use_case.logger, "debug") as mock_debug:
            use_case("test")

            assert mock_debug.call_count == 2
            mock_debug.assert_any_call("Executing ConcreteUseCase with request: test")
            mock_debug.assert_any_call("Successfully executed ConcreteUseCase")

    def test_logging_on_error(self):
        """エラー時のロギング"""
        use_case = ConcreteUseCase()

        with patch.object(use_case.logger, "error") as mock_error:
            with pytest.raises(UseCaseError):
                use_case("error")

            mock_error.assert_called_once()
            args = mock_error.call_args[0]
            assert "Error in ConcreteUseCase: Test error" in args[0]


class TestUseCaseError:
    """UseCaseErrorのテスト"""

    def test_create_error_without_cause(self):
        """原因なしでエラーを作成"""
        error = UseCaseError("Test message")
        assert str(error) == "Test message"
        assert error.cause is None

    def test_create_error_with_cause(self):
        """原因ありでエラーを作成"""
        cause = ValueError("Original error")
        error = UseCaseError("Wrapped message", cause=cause)

        assert str(error) == "Wrapped message"
        assert error.cause is cause
        assert str(error.cause) == "Original error"
