"""
ドメイン層のエラー定義

ビジネスロジックに関連するエラー
"""



class DomainError(Exception):
    """ドメインエラーの基底クラス"""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class ValidationError(DomainError):
    """検証エラー"""

    pass


class NotFoundError(DomainError):
    """リソースが見つからないエラー"""

    pass


class AlreadyExistsError(DomainError):
    """既に存在するエラー"""

    pass


class PermissionError(DomainError):
    """権限エラー"""

    pass


class NetworkError(DomainError):
    """ネットワークエラー"""

    pass


class TimeoutError(DomainError):
    """タイムアウトエラー"""

    pass


class ProcessingError(DomainError):
    """処理エラー"""

    pass


class UnsupportedFormatError(DomainError):
    """サポートされていない形式エラー"""

    pass


class InvalidStateError(DomainError):
    """不正な状態エラー"""

    pass


class ConfigurationError(DomainError):
    """設定エラー"""

    pass


class UnknownError(DomainError):
    """不明なエラー"""

    def __init__(self, message: str = "予期しないエラーが発生しました", code: str | None = None):
        super().__init__(message, code)
