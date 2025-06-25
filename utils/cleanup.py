"""
クリーンアップユーティリティ
"""

import shutil
from pathlib import Path

from .logging import logger


class TempFileManager:
    """一時ファイル管理クラス"""

    def __init__(self):
        self.temp_files: list[Path] = []
        self.temp_dirs: list[Path] = []

    def register_file(self, file_path: Path):
        """一時ファイルを登録"""
        if file_path.exists():
            self.temp_files.append(file_path)
            logger.debug(f"一時ファイルを登録: {file_path}")

    def register_dir(self, dir_path: Path):
        """一時ディレクトリを登録"""
        if dir_path.exists():
            self.temp_dirs.append(dir_path)
            logger.debug(f"一時ディレクトリを登録: {dir_path}")

    def cleanup(self):
        """登録された一時ファイル・ディレクトリを削除"""
        # ファイルを削除
        for file_path in self.temp_files:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"一時ファイルを削除: {file_path}")
            except Exception as e:
                logger.warning(f"ファイル削除エラー: {file_path} - {e}")

        # ディレクトリを削除
        for dir_path in self.temp_dirs:
            try:
                if dir_path.exists():
                    shutil.rmtree(dir_path)
                    logger.info(f"一時ディレクトリを削除: {dir_path}")
            except Exception as e:
                logger.warning(f"ディレクトリ削除エラー: {dir_path} - {e}")

        # リストをクリア
        self.temp_files.clear()
        self.temp_dirs.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()


def cleanup_intermediate_files(output_dir: Path, keep_patterns: list[str] | None = None):
    """
    中間ファイルをクリーンアップ

    Args:
        output_dir: 出力ディレクトリ
        keep_patterns: 保持するファイルパターン（例: ["combined.mp4", "*.fcpxml"]）
    """
    if not output_dir.exists():
        return

    keep_patterns = keep_patterns or ["*_TextffCut_*.mp4", "*.fcpxml", "*.xml", "*.srt", "*.edl", "transcriptions/"]

    # 保持するファイルとディレクトリを特定
    keep_files = set()
    keep_dirs = set()
    for pattern in keep_patterns:
        if pattern.endswith("/"):
            # ディレクトリパターン
            keep_dirs.add(output_dir / pattern.rstrip("/"))
        else:
            # ファイルパターン
            keep_files.update(output_dir.glob(pattern))

    # 削除対象のパターン
    cleanup_patterns = [
        "segment_*.mp4",
        "segment_*_part_*.mp4",
        "temp_*.wav",
        "temp_audio_*.wav",
        "*_combined.wav",
        "audio_list.txt",
        "concat_list*.txt",
        "segments_list*.txt",
    ]

    deleted_count = 0
    for pattern in cleanup_patterns:
        for file_path in output_dir.glob(pattern):
            # 保護対象のディレクトリ内のファイルはスキップ
            skip = False
            for keep_dir in keep_dirs:
                try:
                    file_path.relative_to(keep_dir)
                    skip = True
                    break
                except ValueError:
                    pass

            if not skip and file_path not in keep_files:
                try:
                    file_path.unlink()
                    logger.debug(f"中間ファイルを削除: {file_path}")
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"ファイル削除エラー: {file_path} - {e}")

    if deleted_count > 0:
        logger.info(f"{deleted_count}個の中間ファイルを削除しました")


def cleanup_old_projects(base_output_dir: Path, keep_recent: int = 5):
    """
    古いプロジェクトフォルダをクリーンアップ

    Args:
        base_output_dir: ベース出力ディレクトリ
        keep_recent: 保持する最近のプロジェクト数
    """
    if not base_output_dir.exists():
        return

    # プロジェクトフォルダを取得（更新時刻でソート）
    project_dirs = []
    for item in base_output_dir.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            project_dirs.append((item, item.stat().st_mtime))

    # 更新時刻でソート（新しい順）
    project_dirs.sort(key=lambda x: x[1], reverse=True)

    # 古いプロジェクトを削除
    for i, (dir_path, _) in enumerate(project_dirs):
        if i >= keep_recent:
            try:
                shutil.rmtree(dir_path)
                logger.info(f"古いプロジェクトを削除: {dir_path}")
            except Exception as e:
                logger.warning(f"プロジェクト削除エラー: {dir_path} - {e}")


class ProcessingContext:
    """処理コンテキスト（自動クリーンアップ付き）"""

    def __init__(self, output_dir: Path, cleanup_on_error: bool = True):
        self.output_dir = output_dir
        self.cleanup_on_error = cleanup_on_error
        self.temp_manager = TempFileManager()
        self.success = False

    def __enter__(self):
        return self.temp_manager

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            # 正常終了
            self.success = True
            # 中間ファイルのみクリーンアップ
            cleanup_intermediate_files(self.output_dir)
        else:
            # エラー発生
            if self.cleanup_on_error:
                logger.warning(f"エラーのため出力ディレクトリを削除: {self.output_dir}")
                try:
                    if self.output_dir.exists():
                        shutil.rmtree(self.output_dir)
                except Exception as e:
                    logger.error(f"出力ディレクトリ削除エラー: {e}")

        # 一時ファイルは常にクリーンアップ
        self.temp_manager.cleanup()
