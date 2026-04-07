"""
バージョン情報関連のヘルパー関数

アプリケーションのバージョン情報を管理するユーティリティ関数を提供。
pyproject.tomlのversionフィールドを単一ソースとする。
"""

from __future__ import annotations

from pathlib import Path


def get_app_version(default_version: str = "2.0.0") -> str:
    """
    アプリケーションのバージョン情報を取得

    優先順位:
    1. importlib.metadata（パッケージインストール済みの場合）
    2. pyproject.tomlを直接パース（開発環境等）
    3. デフォルトバージョン

    Args:
        default_version: 取得できない場合のデフォルトバージョン

    Returns:
        str: バージョン文字列（例: "2.0.0"）
    """
    # 1. importlib.metadata から取得（pip install済みの場合）
    try:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as _pkg_version

        return _pkg_version("textffcut")
    except (ImportError, Exception):
        # PackageNotFoundError は Exception のサブクラス
        pass

    # 2. pyproject.toml を直接パース（開発環境）
    try:
        # Python 3.11+ は tomllib、それ以前は正規表現フォールバック
        try:
            import tomllib
        except ModuleNotFoundError:
            tomllib = None  # type: ignore[assignment]

        # プロジェクトルートのpyproject.tomlを探す
        candidates = [
            Path(__file__).parent.parent / "pyproject.toml",
        ]
        try:
            import __main__

            if hasattr(__main__, "__file__") and __main__.__file__:
                candidates.append(Path(__main__.__file__).parent / "pyproject.toml")
        except (ImportError, AttributeError):
            pass

        import re

        for toml_path in candidates:
            if toml_path.exists():
                content = toml_path.read_text(encoding="utf-8")
                if tomllib is not None:
                    data = tomllib.loads(content)
                    ver = data.get("project", {}).get("version")
                    if ver:
                        return ver
                else:
                    # 正規表現フォールバック（Python < 3.11）
                    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
                    if match:
                        return match.group(1)
    except (OSError, UnicodeDecodeError, KeyError):
        pass

    return default_version


def format_version_display(version: str, include_prefix: bool = True) -> str:
    """
    バージョン文字列を表示用にフォーマット

    Args:
        version: バージョン文字列
        include_prefix: "v"プレフィックスを含めるかどうか

    Returns:
        str: フォーマットされたバージョン文字列
    """
    if version.startswith("v"):
        if include_prefix:
            return version
        else:
            return version[1:]
    else:
        if include_prefix:
            return f"v{version}"
        else:
            return version


def parse_version(version_string: str) -> tuple[int, int, int]:
    """
    バージョン文字列をメジャー、マイナー、パッチ番号に分解

    Args:
        version_string: バージョン文字列（例: "v1.2.3", "1.2.3"）

    Returns:
        tuple[int, int, int]: (メジャー, マイナー, パッチ)のタプル

    Raises:
        ValueError: バージョン文字列が不正な形式の場合
    """
    version = version_string[1:] if version_string.startswith("v") else version_string

    try:
        parts = version.split(".")
        if len(parts) != 3:
            raise ValueError(f"バージョン文字列は'X.Y.Z'形式である必要があります: {version_string}")

        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2])

        return (major, minor, patch)
    except (ValueError, IndexError) as e:
        raise ValueError(f"不正なバージョン文字列: {version_string}") from e
