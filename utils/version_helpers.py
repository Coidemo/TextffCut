"""
バージョン情報関連のヘルパー関数

アプリケーションのバージョン情報を管理するユーティリティ関数を提供。
"""

from pathlib import Path


def get_app_version(version_file_path: Path | None = None, default_version: str = "v1.0.0") -> str:
    """
    アプリケーションのバージョン情報を取得
    
    VERSION.txtファイルからバージョン情報を読み込む。
    ファイルが存在しない場合やエラーが発生した場合は、
    デフォルトバージョンを返す。
    
    Args:
        version_file_path: バージョンファイルのパス（省略時はメインファイルと同じディレクトリ）
        default_version: ファイルが読めない場合のデフォルトバージョン
        
    Returns:
        str: バージョン文字列（例: "v1.0.0"）
        
    Examples:
        >>> version = get_app_version()
        >>> print(version)
        "v1.0.0"
        
        >>> custom_path = Path("/path/to/VERSION.txt")
        >>> version = get_app_version(custom_path, "v2.0.0")
        >>> print(version)
        "v2.0.0"  # ファイルが存在しない場合
    """
    try:
        if version_file_path is None:
            # デフォルトパス: メインファイルと同じディレクトリのVERSION.txt
            import __main__
            if hasattr(__main__, '__file__'):
                version_file_path = Path(__main__.__file__).parent / "VERSION.txt"
            else:
                # __main__.__file__が存在しない場合（インタープリタ等）
                return default_version
        
        if version_file_path.exists():
            version = version_file_path.read_text().strip()
            # 空文字の場合はデフォルトを返す
            return version if version else default_version
        else:
            return default_version
            
    except (OSError, IOError, AttributeError):
        # ファイル読み込みエラーやその他のエラー
        return default_version


def format_version_display(version: str, include_prefix: bool = True) -> str:
    """
    バージョン文字列を表示用にフォーマット
    
    Args:
        version: バージョン文字列
        include_prefix: "v"プレフィックスを含めるかどうか
        
    Returns:
        str: フォーマットされたバージョン文字列
        
    Examples:
        >>> format_version_display("1.0.0")
        "v1.0.0"
        
        >>> format_version_display("v1.0.0", include_prefix=False)
        "1.0.0"
    """
    # すでに"v"で始まっている場合の処理
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
        
    Examples:
        >>> parse_version("v1.2.3")
        (1, 2, 3)
        
        >>> parse_version("2.0.0")
        (2, 0, 0)
    """
    # "v"プレフィックスを除去
    version = version_string.lstrip("v")
    
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