"""Phase 1: DaVinci Resolve scripting API への接続確認プロトタイプ。

このスクリプトを実行して以下を確認する:
  - DaVinciResolveScript モジュールが import できるか
  - 起動中の Resolve に接続できるか
  - 現在開いている project 名が取れるか
  - Media Pool のビン構造が取得できるか

事前準備:
  1. DaVinci Resolve 20 を起動して任意のプロジェクトを開く
  2. Resolve > Preferences > System > General で
     "External scripting using" を "Local" に設定
  3. このスクリプトを実行: python scripts/dev/resolve_connection_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def setup_resolve_path() -> None:
    """DaVinciResolveScript モジュールを sys.path に追加する。

    macOS の標準インストールパスを使用。環境変数 RESOLVE_SCRIPT_API があれば
    それを優先。
    """
    api_root = os.environ.get(
        "RESOLVE_SCRIPT_API",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
    )
    modules_path = Path(api_root) / "Modules"
    if not modules_path.exists():
        print(f"❌ Resolve scripting modules が見つかりません: {modules_path}", file=sys.stderr)
        print("   Resolve がインストールされているか確認してください", file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(modules_path))


def connect() -> object:
    """Resolve に接続して Resolve オブジェクトを返す。"""
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"❌ DaVinciResolveScript の import 失敗: {e}", file=sys.stderr)
        sys.exit(1)

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        print("❌ Resolve に接続できませんでした", file=sys.stderr)
        print("   Resolve を起動して、Preferences > System > General で", file=sys.stderr)
        print("   'External scripting using' を 'Local' に設定してください", file=sys.stderr)
        sys.exit(1)
    return resolve


def print_bin_tree(folder: object, depth: int = 0) -> None:
    """ビン構造を再帰的に表示。"""
    indent = "  " * depth
    name = folder.GetName()  # type: ignore[attr-defined]
    clips = folder.GetClipList() or []  # type: ignore[attr-defined]
    subs = folder.GetSubFolderList() or []  # type: ignore[attr-defined]
    print(f"{indent}📁 {name}/  (clips: {len(clips)}, subfolders: {len(subs)})")
    for sub in subs:
        print_bin_tree(sub, depth + 1)


def main() -> None:
    setup_resolve_path()
    print("=" * 60)
    print("DaVinci Resolve 接続確認")
    print("=" * 60)

    resolve = connect()
    version = resolve.GetVersionString()  # type: ignore[attr-defined]
    print(f"✓ Resolve に接続成功 (version: {version})")

    pm = resolve.GetProjectManager()  # type: ignore[attr-defined]
    project = pm.GetCurrentProject()
    if project is None:
        print("❌ プロジェクトが開かれていません", file=sys.stderr)
        sys.exit(1)

    project_name = project.GetName()
    timeline_count = project.GetTimelineCount()
    print(f"✓ プロジェクト: {project_name!r} (timelines: {timeline_count})")

    media_pool = project.GetMediaPool()
    root = media_pool.GetRootFolder()
    print()
    print("Media Pool 構造:")
    print_bin_tree(root)

    print()
    print("=" * 60)
    print("Phase 1 完了。 Phase 2 (ビン検索) に進めます。")
    print("=" * 60)


if __name__ == "__main__":
    main()
