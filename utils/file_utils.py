"""
ファイル操作関連のユーティリティ関数
"""
import shutil
from pathlib import Path
from typing import List, Optional


def ensure_directory(path: Path, clean: bool = False) -> Path:
    """
    ディレクトリの存在を確認し、必要に応じて作成
    
    Args:
        path: 確認/作成するディレクトリパス
        clean: Trueの場合、既存のディレクトリを削除してから作成
        
    Returns:
        作成/確認されたディレクトリパス
    """
    path = Path(path).resolve()
    
    if clean and path.exists():
        shutil.rmtree(path)
    
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_video_files(directory: Path, extensions: Optional[List[str]] = None) -> List[Path]:
    """
    指定ディレクトリから動画ファイルを取得
    
    Args:
        directory: 検索するディレクトリ
        extensions: 検索する拡張子のリスト（デフォルトは一般的な動画形式）
        
    Returns:
        動画ファイルのパスリスト
    """
    if extensions is None:
        extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv']
    
    directory = Path(directory)
    if not directory.exists():
        return []
    
    video_files = []
    for ext in extensions:
        video_files.extend(directory.glob(f"*{ext}"))
        video_files.extend(directory.glob(f"*{ext.upper()}"))
    
    return sorted(set(video_files))


def clean_temp_files(directory: Path, patterns: List[str]) -> int:
    """
    一時ファイルのクリーンアップ
    
    Args:
        directory: クリーンアップするディレクトリ
        patterns: 削除するファイルパターンのリスト
        
    Returns:
        削除されたファイル数
    """
    directory = Path(directory)
    if not directory.exists():
        return 0
    
    deleted_count = 0
    for pattern in patterns:
        for file_path in directory.glob(pattern):
            try:
                if file_path.is_file():
                    file_path.unlink()
                    deleted_count += 1
            except Exception:
                # エラーを無視して続行
                pass
    
    return deleted_count


def get_file_size_mb(file_path: Path) -> float:
    """ファイルサイズをMB単位で取得"""
    return Path(file_path).stat().st_size / (1024 * 1024)


def get_safe_filename(filename: str) -> str:
    """
    ファイル名として安全な文字列に変換
    
    Args:
        filename: 元のファイル名
        
    Returns:
        安全なファイル名
    """
    # 使用できない文字を置換
    unsafe_chars = '<>:"/\\|?*'
    for char in unsafe_chars:
        filename = filename.replace(char, '_')
    
    # 連続するアンダースコアを1つに
    while '__' in filename:
        filename = filename.replace('__', '_')
    
    # 前後の空白とピリオドを削除
    filename = filename.strip('. ')
    
    # 最大長を制限（拡張子を考慮して200文字）
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename or 'untitled'


def get_unique_path(base_path: Path) -> Path:
    """
    ファイルが既に存在する場合、連番を付けてユニークなパスを生成
    
    Args:
        base_path: 基本となるファイルパス
        
    Returns:
        ユニークなファイルパス
    """
    if not base_path.exists():
        return base_path
    
    # ファイル名と拡張子を分離
    stem = base_path.stem
    suffix = base_path.suffix
    parent = base_path.parent
    
    # 連番を付けて試す
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter:02d}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1
        
        # 無限ループ防止
        if counter > 999:
            raise ValueError(f"Too many files with the same name: {base_path}")