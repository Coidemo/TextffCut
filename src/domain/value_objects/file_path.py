"""
FilePath Value Object

ファイルパスを表現する不変オブジェクト
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FilePath:
    """ファイルパスを表現するValue Object"""

    value: Path

    def __init__(self, path: str | Path):
        """
        Args:
            path: ファイルパス（文字列またはPathオブジェクト）

        Raises:
            ValueError: 空のパスが指定された場合
        """
        if isinstance(path, str):
            if not path:
                raise ValueError("File path cannot be empty")
            path = Path(path)
        elif not isinstance(path, Path):
            raise TypeError(f"Expected str or Path, got {type(path)}")

        # dataclassのfrozen=Trueを回避するためobject.__setattr__を使用
        object.__setattr__(self, "value", path)

    def __str__(self) -> str:
        """文字列表現"""
        return str(self.value)

    def __repr__(self) -> str:
        """開発者向け表現"""
        return f"FilePath('{self.value}')"

    @property
    def name(self) -> str:
        """ファイル名を取得"""
        return self.value.name

    @property
    def stem(self) -> str:
        """拡張子を除いたファイル名を取得"""
        return self.value.stem

    @property
    def suffix(self) -> str:
        """拡張子を取得"""
        return self.value.suffix

    @property
    def parent(self) -> "FilePath":
        """親ディレクトリを取得"""
        return FilePath(self.value.parent)

    def exists(self) -> bool:
        """ファイルの存在確認"""
        return self.value.exists()

    def is_file(self) -> bool:
        """ファイルかどうかの確認"""
        return self.value.is_file()

    def is_dir(self) -> bool:
        """ディレクトリかどうかの確認"""
        return self.value.is_dir()

    def with_suffix(self, suffix: str) -> "FilePath":
        """拡張子を変更した新しいFilePathを返す"""
        return FilePath(self.value.with_suffix(suffix))

    def with_name(self, name: str) -> "FilePath":
        """ファイル名を変更した新しいFilePathを返す"""
        return FilePath(self.value.with_name(name))

    def joinpath(self, *args) -> "FilePath":
        """パスを結合した新しいFilePathを返す"""
        return FilePath(self.value.joinpath(*args))
