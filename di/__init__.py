"""
依存性注入（DI）パッケージ

dependency-injectorを使用したDIコンテナの実装。
既存のコードベースと共存しながら段階的に移行するための基盤を提供します。
"""

from .containers import ApplicationContainer, create_container
from .config import DIConfig

__all__ = [
    "ApplicationContainer",
    "create_container",
    "DIConfig",
]