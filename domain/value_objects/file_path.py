"""
ファイルパスの値オブジェクト

検証付きのファイルパスを表す不変オブジェクト。
"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FilePath:
    """ファイルパスを表す値オブジェクト"""

    path: str

    def __post_init__(self):
        """バリデーション"""
        if not self.path:
            raise ValueError("File path cannot be empty")

        # パスの正規化
        object.__setattr__(self, "path", os.path.normpath(self.path))

    @property
    def absolute(self) -> str:
        """絶対パス"""
        return os.path.abspath(self.path)

    @property
    def exists(self) -> bool:
        """ファイルが存在するか"""
        return os.path.exists(self.path)

    @property
    def is_file(self) -> bool:
        """ファイルかどうか"""
        return os.path.isfile(self.path)

    @property
    def is_directory(self) -> bool:
        """ディレクトリかどうか"""
        return os.path.isdir(self.path)

    @property
    def name(self) -> str:
        """ファイル名（拡張子含む）"""
        return os.path.basename(self.path)

    @property
    def stem(self) -> str:
        """ファイル名（拡張子除く）"""
        return Path(self.path).stem

    @property
    def extension(self) -> str:
        """拡張子（ドット含む）"""
        return Path(self.path).suffix

    @property
    def parent(self) -> "FilePath":
        """親ディレクトリ"""
        return FilePath(os.path.dirname(self.path))

    @property
    def size(self) -> int | None:
        """ファイルサイズ（バイト）"""
        if self.exists and self.is_file:
            return os.path.getsize(self.path)
        return None

    def with_suffix(self, suffix: str) -> "FilePath":
        """拡張子を変更した新しいパスを作成"""
        p = Path(self.path)
        return FilePath(str(p.with_suffix(suffix)))

    def with_name(self, name: str) -> "FilePath":
        """ファイル名を変更した新しいパスを作成"""
        p = Path(self.path)
        return FilePath(str(p.with_name(name)))

    def join(self, *parts: str) -> "FilePath":
        """パスを結合"""
        return FilePath(os.path.join(self.path, *parts))

    def relative_to(self, base: "FilePath") -> str:
        """基準パスからの相対パス"""
        return os.path.relpath(self.path, base.path)

    def validate_extension(self, allowed_extensions: list[str]) -> bool:
        """拡張子が許可されたものか確認"""
        ext = self.extension.lower()
        return any(
            ext == allowed.lower() if allowed.startswith(".") else ext == f".{allowed.lower()}"
            for allowed in allowed_extensions
        )

    def ensure_parent_exists(self) -> None:
        """親ディレクトリが存在しない場合は作成"""
        parent_dir = os.path.dirname(self.path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir)

    @classmethod
    def from_path(cls, path: Path) -> "FilePath":
        """PathlibのPathオブジェクトから作成"""
        return cls(str(path))

    def to_path(self) -> Path:
        """PathlibのPathオブジェクトに変換"""
        return Path(self.path)

    def __str__(self) -> str:
        """文字列表現"""
        return self.path

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"FilePath('{self.path}')"
