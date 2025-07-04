"""
ファイルゲートウェイの実装

ファイルシステム操作を抽象化し、テスタビリティと保守性を向上させます。
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from domain.value_objects import FilePath
from use_cases.interfaces import IFileGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class FileGatewayAdapter(IFileGateway):
    """
    ファイルシステム操作のゲートウェイ実装

    標準のPython APIを使用してファイル操作を行います。
    エラーハンドリングとロギングを統一的に提供します。
    """

    def __init__(self, base_path: Path | None = None):
        """
        Args:
            base_path: ベースパス（相対パスの基準）
        """
        self.base_path = Path(base_path) if base_path else Path.cwd()
        self._temp_dirs: list[Path] = []

    def exists(self, path: FilePath) -> bool:
        """ファイルまたはディレクトリの存在確認"""
        try:
            return Path(str(path)).exists()
        except Exception as e:
            logger.error(f"Failed to check existence of {path}: {e}")
            return False

    def is_file(self, path: FilePath) -> bool:
        """ファイルかどうかの確認"""
        try:
            return Path(str(path)).is_file()
        except Exception as e:
            logger.error(f"Failed to check if {path} is file: {e}")
            return False

    def is_directory(self, path: FilePath) -> bool:
        """ディレクトリかどうかの確認"""
        try:
            return Path(str(path)).is_dir()
        except Exception as e:
            logger.error(f"Failed to check if {path} is directory: {e}")
            return False

    def get_size(self, path: FilePath) -> int:
        """ファイルサイズの取得（バイト）"""
        try:
            return Path(str(path)).stat().st_size
        except Exception as e:
            logger.error(f"Failed to get size of {path}: {e}")
            raise OSError(f"Failed to get file size: {e}")

    def read_text(self, path: FilePath, encoding: str = "utf-8") -> str:
        """テキストファイルの読み込み"""
        try:
            with open(str(path), encoding=encoding) as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to read text from {path}: {e}")
            raise OSError(f"Failed to read file: {e}")

    def write_text(self, path: FilePath, content: str, encoding: str = "utf-8") -> None:
        """テキストファイルの書き込み"""
        try:
            # 親ディレクトリを作成
            Path(str(path)).parent.mkdir(parents=True, exist_ok=True)

            with open(str(path), "w", encoding=encoding) as f:
                f.write(content)

            logger.debug(f"Written {len(content)} chars to {path}")
        except Exception as e:
            logger.error(f"Failed to write text to {path}: {e}")
            raise OSError(f"Failed to write file: {e}")

    def read_json(self, path: FilePath, encoding: str = "utf-8") -> dict[str, Any]:
        """JSONファイルの読み込み"""
        try:
            with open(str(path), encoding=encoding) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {path}: {e}")
            raise ValueError(f"Invalid JSON format: {e}")
        except Exception as e:
            logger.error(f"Failed to read JSON from {path}: {e}")
            raise OSError(f"Failed to read JSON file: {e}")

    def write_json(self, path: FilePath, data: dict[str, Any], encoding: str = "utf-8", indent: int = 2) -> None:
        """JSONファイルの書き込み"""
        try:
            # 親ディレクトリを作成
            Path(str(path)).parent.mkdir(parents=True, exist_ok=True)

            with open(str(path), "w", encoding=encoding) as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)

            logger.debug(f"Written JSON to {path}")
        except Exception as e:
            logger.error(f"Failed to write JSON to {path}: {e}")
            raise OSError(f"Failed to write JSON file: {e}")

    def copy_file(self, source: FilePath, destination: FilePath) -> None:
        """ファイルのコピー"""
        try:
            # 親ディレクトリを作成
            Path(str(destination)).parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(str(source), str(destination))
            logger.debug(f"Copied {source} to {destination}")
        except Exception as e:
            logger.error(f"Failed to copy {source} to {destination}: {e}")
            raise OSError(f"Failed to copy file: {e}")

    def move_file(self, source: FilePath, destination: FilePath) -> None:
        """ファイルの移動"""
        try:
            # 親ディレクトリを作成
            Path(str(destination)).parent.mkdir(parents=True, exist_ok=True)

            shutil.move(str(source), str(destination))
            logger.debug(f"Moved {source} to {destination}")
        except Exception as e:
            logger.error(f"Failed to move {source} to {destination}: {e}")
            raise OSError(f"Failed to move file: {e}")

    def delete_file(self, path: FilePath) -> None:
        """ファイルの削除"""
        try:
            Path(str(path)).unlink()
            logger.debug(f"Deleted file {path}")
        except FileNotFoundError:
            logger.warning(f"File not found for deletion: {path}")
        except Exception as e:
            logger.error(f"Failed to delete file {path}: {e}")
            raise OSError(f"Failed to delete file: {e}")

    def create_directory(self, path: FilePath, parents: bool = True) -> None:
        """ディレクトリの作成"""
        try:
            Path(str(path)).mkdir(parents=parents, exist_ok=True)
            logger.debug(f"Created directory {path}")
        except Exception as e:
            logger.error(f"Failed to create directory {path}: {e}")
            raise OSError(f"Failed to create directory: {e}")

    def delete_directory(self, path: FilePath, recursive: bool = False) -> None:
        """ディレクトリの削除"""
        try:
            path_obj = Path(str(path))
            if recursive:
                shutil.rmtree(path_obj)
            else:
                path_obj.rmdir()
            logger.debug(f"Deleted directory {path}")
        except FileNotFoundError:
            logger.warning(f"Directory not found for deletion: {path}")
        except Exception as e:
            logger.error(f"Failed to delete directory {path}: {e}")
            raise OSError(f"Failed to delete directory: {e}")

    def list_files(self, path: FilePath, pattern: str | None = None, recursive: bool = False) -> list[FilePath]:
        """ディレクトリ内のファイル一覧を取得"""
        try:
            path_obj = Path(str(path))

            if not path_obj.is_dir():
                raise ValueError(f"Path is not a directory: {path}")

            if recursive and pattern:
                # 再帰的なパターンマッチ
                files = path_obj.rglob(pattern)
            elif pattern:
                # 非再帰的なパターンマッチ
                files = path_obj.glob(pattern)
            else:
                # すべてのファイル（非再帰）
                files = path_obj.iterdir()

            # ファイルのみをフィルタしてFilePathに変換
            return [FilePath(str(f)) for f in files if f.is_file()]
        except Exception as e:
            logger.error(f"Failed to list files in {path}: {e}")
            raise OSError(f"Failed to list files: {e}")

    def create_temp_directory(self, prefix: str = "textffcut_", suffix: str | None = None) -> FilePath:
        """一時ディレクトリの作成"""
        try:
            temp_dir = tempfile.mkdtemp(prefix=prefix, suffix=suffix)
            temp_path = Path(temp_dir)

            # クリーンアップ用に記録
            self._temp_dirs.append(temp_path)

            logger.debug(f"Created temp directory: {temp_path}")
            return FilePath(str(temp_path))
        except Exception as e:
            logger.error(f"Failed to create temp directory: {e}")
            raise OSError(f"Failed to create temp directory: {e}")

    def cleanup_temp_directories(self) -> None:
        """作成した一時ディレクトリをすべてクリーンアップ"""
        for temp_dir in self._temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory {temp_dir}: {e}")

        self._temp_dirs.clear()

    def __del__(self):
        """デストラクタで一時ディレクトリをクリーンアップ"""
        self.cleanup_temp_directories()

    def get_relative_path(self, path: FilePath, base: FilePath | None = None) -> FilePath:
        """相対パスの取得"""
        try:
            path_obj = Path(str(path))
            base_obj = Path(str(base)) if base else self.base_path

            relative = path_obj.relative_to(base_obj)
            return FilePath(str(relative))
        except ValueError as e:
            # パスが基準パスの外にある場合
            logger.warning(f"Path {path} is not relative to {base_obj}: {e}")
            return path
        except Exception as e:
            logger.error(f"Failed to get relative path: {e}")
            raise OSError(f"Failed to get relative path: {e}")

    def get_absolute_path(self, path: FilePath) -> FilePath:
        """絶対パスの取得"""
        try:
            abs_path = Path(str(path)).resolve()
            return FilePath(str(abs_path))
        except Exception as e:
            logger.error(f"Failed to get absolute path for {path}: {e}")
            raise OSError(f"Failed to get absolute path: {e}")
