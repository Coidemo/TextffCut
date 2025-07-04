"""
依存性注入（DI）パッケージ

dependency-injectorを使用したDIコンテナの実装。
既存のコードベースと共存しながら段階的に移行するための基盤を提供します。
"""

from .config import DIConfig
from .containers import ApplicationContainer, create_container

__all__ = [
    "ApplicationContainer",
    "create_container",
    "DIConfig",
]
