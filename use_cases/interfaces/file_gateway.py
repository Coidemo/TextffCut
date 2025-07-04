"""
ファイル操作ゲートウェイインターフェース
"""

from typing import Protocol

from domain.value_objects import FilePath


class IFileGateway(Protocol):
    """ファイル操作機能へのゲートウェイ"""

    def exists(self, path: FilePath) -> bool:
        """ファイルまたはディレクトリが存在するか確認"""
        ...

    def is_file(self, path: FilePath) -> bool:
        """パスがファイルかどうか確認"""
        ...

    def is_directory(self, path: FilePath) -> bool:
        """パスがディレクトリかどうか確認"""
        ...

    def create_directory(self, path: FilePath) -> None:
        """ディレクトリを作成（親ディレクトリも含む）"""
        ...

    def delete_file(self, path: FilePath) -> None:
        """ファイルを削除"""
        ...

    def delete_directory(self, path: FilePath, recursive: bool = False) -> None:
        """ディレクトリを削除"""
        ...

    def copy_file(self, source: FilePath, destination: FilePath) -> None:
        """ファイルをコピー"""
        ...

    def move_file(self, source: FilePath, destination: FilePath) -> None:
        """ファイルを移動"""
        ...

    def list_files(self, directory: FilePath, pattern: str | None = None, recursive: bool = False) -> list[FilePath]:
        """
        ディレクトリ内のファイルをリスト

        Args:
            directory: 対象ディレクトリ
            pattern: ファイル名パターン（glob形式）
            recursive: サブディレクトリも含むか

        Returns:
            ファイルパスのリスト
        """
        ...

    def read_text(self, path: FilePath, encoding: str = "utf-8") -> str:
        """テキストファイルを読み込み"""
        ...

    def write_text(self, path: FilePath, content: str, encoding: str = "utf-8", create_parents: bool = True) -> None:
        """
        テキストファイルを書き込み

        Args:
            path: 出力パス
            content: 書き込む内容
            encoding: エンコーディング
            create_parents: 親ディレクトリを自動作成するか
        """
        ...

    def get_size(self, path: FilePath) -> int:
        """ファイルサイズを取得（バイト）"""
        ...

    def get_modification_time(self, path: FilePath) -> float:
        """ファイルの最終更新時刻を取得（UNIXタイムスタンプ）"""
        ...

    def create_temp_directory(self, prefix: str = "textffcut_") -> FilePath:
        """一時ディレクトリを作成"""
        ...

    def create_temp_file(
        self, suffix: str = "", prefix: str = "textffcut_", directory: FilePath | None = None
    ) -> FilePath:
        """一時ファイルを作成"""
        ...
