"""FCPXML内の絶対パスを現在のマシン用に書き換えるユーティリティ。

別マシンで生成された FCPXML フォルダを受け取り、DaVinci Resolve で読み込める
ように file:// URI を書き換える。ユースケース:

- 配布されたキャッシュフォルダ（`{動画名}_TextffCut/`）を別マシンで開く
- GUIで動画プルダウン表示時に、各候補キャッシュフォルダへ自動適用
- CLI `textffcut relink` コマンド

書き換え対象のパス種別:
  1. キャッシュ内部のアセット（title_images/, source_*.mp4 等）
     → 新しい cache_dir 配下の相対位置に置き換え
  2. preset/ 配下のアセット（frame.png, bgm.mp3, SE）
     → 新しい preset_root 配下に置き換え
  3. videos/ 直下の動画本体（{動画名}.mp4）
     → 新しい videos_root 配下に置き換え

未分類の URI は警告ログを出して触らない。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import quote, unquote

logger = logging.getLogger(__name__)

# core/export.py が生成するキャッシュディレクトリ名のサフィックス
CACHE_DIR_SUFFIX = "_TextffCut"
PRESET_DIR_NAME = "preset"

# FCPXML の src="file:///..." 属性
FILE_URI_ATTR_PATTERN = re.compile(r'src="(file://[^"]+)"')


class RelinkStatus(str, Enum):
    UP_TO_DATE = "up_to_date"
    RELINKED = "relinked"
    MISSING_FILES = "missing_files"
    ERROR = "error"


@dataclass
class RelinkResult:
    status: RelinkStatus
    cache_dir: Path
    fcpxml_count: int = 0
    rewritten_count: int = 0
    missing_files: list[str] = field(default_factory=list)
    unmapped_uris: list[str] = field(default_factory=list)
    error_message: str | None = None


def _uri_to_path(uri: str) -> Path:
    """`file:///...` を復号して Path に変換。"""
    if uri.startswith("file:///"):
        raw = uri[len("file://") :]
    elif uri.startswith("file://localhost"):
        raw = uri[len("file://localhost") :]
    else:
        raw = uri[len("file://") :]
    return Path(unquote(raw))


def _path_to_uri(path: Path) -> str:
    """Path を URL エンコードされた `file:///...` に変換（core/export.py と同じ形式）。"""
    path_str = str(path)
    encoded = "/".join(quote(part, safe="") for part in path_str.split("/"))
    return f"file://{encoded}"


def _resolve_default_preset_root(cache_dir: Path) -> Path:
    """cache_dir から preset_root を推測（`videos/` の親直下の `preset/`）。"""
    videos_root = cache_dir.parent
    return videos_root.parent / PRESET_DIR_NAME


def _remap_path(
    old_path: Path,
    old_cache_dir_name: str | None,
    current_cache_dir: Path,
    current_videos_root: Path,
    current_preset_root: Path,
) -> Path | None:
    """旧絶対パスを現在のマシン用の新パスにマップする。

    分類できなければ None を返す（呼び出し側は触らずに警告）。
    """
    parts = old_path.parts

    # キャッシュ内部（title_images/、source_*.mp4 等）
    if old_cache_dir_name and old_cache_dir_name in parts:
        idx = parts.index(old_cache_dir_name)
        rel = Path(*parts[idx + 1 :])
        return current_cache_dir / rel

    # preset/ 配下
    if PRESET_DIR_NAME in parts:
        idx = parts.index(PRESET_DIR_NAME)
        rel = Path(*parts[idx + 1 :])
        return current_preset_root / rel

    # videos/ 直下の動画本体（拡張子で判定。cache_dir.parent.name と同じ親配下にあれば videos/）
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}
    if old_path.suffix.lower() in video_exts:
        return current_videos_root / old_path.name

    return None


def _detect_old_cache_dir_name(fcpxml_text: str) -> str | None:
    """FCPXML 内の URI から旧キャッシュディレクトリ名（`{動画名}_TextffCut`）を推測する。"""
    for match in FILE_URI_ATTR_PATTERN.finditer(fcpxml_text):
        uri = match.group(1)
        path = _uri_to_path(uri)
        for part in path.parts:
            if part.endswith(CACHE_DIR_SUFFIX):
                return part
    return None


def _process_single_fcpxml(
    fcpxml_path: Path,
    current_cache_dir: Path,
    current_videos_root: Path,
    current_preset_root: Path,
    result: RelinkResult,
) -> bool:
    """1ファイルを処理。書き換えが発生したら True を返す。"""
    try:
        original_text = fcpxml_path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning(f"FCPXML読み込み失敗: {fcpxml_path} - {e}")
        return False

    old_cache_dir_name = _detect_old_cache_dir_name(original_text)

    def _replace(match: re.Match[str]) -> str:
        old_uri = match.group(1)
        old_path = _uri_to_path(old_uri)
        new_path = _remap_path(
            old_path,
            old_cache_dir_name,
            current_cache_dir,
            current_videos_root,
            current_preset_root,
        )
        if new_path is None:
            result.unmapped_uris.append(old_uri)
            return match.group(0)
        if not new_path.exists():
            result.missing_files.append(str(new_path))
        new_uri = _path_to_uri(new_path)
        return f'src="{new_uri}"'

    new_text = FILE_URI_ATTR_PATTERN.sub(_replace, original_text)
    if new_text == original_text:
        return False

    try:
        fcpxml_path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        logger.error(f"FCPXML書き込み失敗: {fcpxml_path} - {e}")
        return False
    return True


def relink_folder(
    cache_dir: Path,
    videos_root: Path | None = None,
    preset_root: Path | None = None,
) -> RelinkResult:
    """キャッシュフォルダ内の FCPXML を現在のマシン用にrelinkする。

    Args:
        cache_dir: `{動画名}_TextffCut` フォルダ
        videos_root: 動画本体の格納ディレクトリ（None なら cache_dir.parent）
        preset_root: preset 素材ディレクトリ（None なら cache_dir.parent.parent/preset）

    Returns:
        RelinkResult: 処理結果サマリ
    """
    cache_dir = cache_dir.resolve()
    result = RelinkResult(status=RelinkStatus.UP_TO_DATE, cache_dir=cache_dir)

    if not cache_dir.is_dir():
        result.status = RelinkStatus.ERROR
        result.error_message = f"ディレクトリが存在しません: {cache_dir}"
        return result

    if not cache_dir.name.endswith(CACHE_DIR_SUFFIX):
        result.status = RelinkStatus.ERROR
        result.error_message = (
            f"TextffCutキャッシュフォルダではありません（`{CACHE_DIR_SUFFIX}` で終わる必要あり）: {cache_dir.name}"
        )
        return result

    current_videos_root = (videos_root or cache_dir.parent).resolve()
    current_preset_root = (preset_root or _resolve_default_preset_root(cache_dir)).resolve()

    fcpxml_files = sorted(cache_dir.rglob("*.fcpxml"))
    result.fcpxml_count = len(fcpxml_files)

    for fcpxml_path in fcpxml_files:
        if _process_single_fcpxml(
            fcpxml_path,
            cache_dir,
            current_videos_root,
            current_preset_root,
            result,
        ):
            result.rewritten_count += 1

    if result.rewritten_count > 0:
        result.status = RelinkStatus.RELINKED
    if result.missing_files:
        # 書き換えしていなくても欠損検出なら MISSING_FILES を優先
        result.status = RelinkStatus.MISSING_FILES

    return result


def relink_all_in_videos_root(videos_root: Path) -> list[RelinkResult]:
    """videos_root 直下の全 `*_TextffCut` フォルダをrelinkする。"""
    videos_root = videos_root.resolve()
    results: list[RelinkResult] = []
    if not videos_root.is_dir():
        return results
    for child in sorted(videos_root.iterdir()):
        if child.is_dir() and child.name.endswith(CACHE_DIR_SUFFIX):
            results.append(relink_folder(child))
    return results
