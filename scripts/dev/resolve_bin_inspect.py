"""Phase 2: 現在 Resolve で開いているビンを取得して、既存 timeline 名と次の連番を計算する。

事前準備:
  - Resolve で目的のビン (例: 2026/0210) を Media Pool でクリックして開いておく
  - 引数で MMDD (連番計算用の月日) を渡す

使用例:
  python scripts/dev/resolve_bin_inspect.py 0210

出力:
  - 現在開いているビン名
  - ビン内の既存 timeline 名
  - 00_0210_Clip{NN} パターンに一致する番号一覧
  - 次の連番
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def setup_resolve_path() -> None:
    api_root = os.environ.get(
        "RESOLVE_SCRIPT_API",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
    )
    modules_path = Path(api_root) / "Modules"
    if not modules_path.exists():
        print(f"❌ Resolve scripting modules が見つかりません: {modules_path}", file=sys.stderr)
        sys.exit(1)
    sys.path.insert(0, str(modules_path))


def connect():
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]
    except ImportError as e:
        print(f"❌ DaVinciResolveScript の import 失敗: {e}", file=sys.stderr)
        sys.exit(1)
    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        print("❌ Resolve に接続できません (起動 + Local scripting 有効化を確認)", file=sys.stderr)
        sys.exit(1)
    return resolve


def find_folder_path(root, target, path_so_far: list[str]) -> list[str] | None:
    """target フォルダオブジェクトに至るパス (ビン名のリスト) を返す。深さ優先探索。"""
    if root is target:
        return path_so_far + [root.GetName()]
    for sub in root.GetSubFolderList() or []:
        result = find_folder_path(sub, target, path_so_far + [root.GetName()])
        if result is not None:
            return result
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2: ビン取得 + 連番計算")
    parser.add_argument("mmdd", help="連番計算用の月日 (例: 0210)")
    args = parser.parse_args()

    if not re.match(r"^\d{4}$", args.mmdd):
        print(f"❌ MMDD は 4 桁数字で指定してください: {args.mmdd}", file=sys.stderr)
        sys.exit(1)
    mmdd = args.mmdd

    setup_resolve_path()
    resolve = connect()

    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        print("❌ プロジェクトが開かれていません", file=sys.stderr)
        sys.exit(1)

    media_pool = project.GetMediaPool()
    current = media_pool.GetCurrentFolder()
    if current is None:
        print("❌ Media Pool の current folder が取得できません", file=sys.stderr)
        sys.exit(1)

    # 現在のビンに至るパス表示
    root = media_pool.GetRootFolder()
    path = find_folder_path(root, current, [])
    if path:
        print(f"✓ 現在のビン: {' / '.join(path)}")
    else:
        print(f"✓ 現在のビン: {current.GetName()} (パス取得失敗)")

    # ビン内 clip / timeline の列挙
    clips = current.GetClipList() or []
    print(f"  既存 clip / timeline: {len(clips)} 件")
    for c in clips:
        name = c.GetName()
        type_ = c.GetClipProperty("Type") if hasattr(c, "GetClipProperty") else ""
        print(f"    - [{type_}] {name}")

    # 連番計算
    pattern = re.compile(rf"^00_{mmdd}_Clip(\d+)$")
    matched = []
    for c in clips:
        name = c.GetName()
        m = pattern.match(name)
        if m:
            matched.append((int(m.group(1)), name))

    print()
    if matched:
        matched.sort()
        max_num = max(num for num, _ in matched)
        print(f"  パターン一致 (00_{mmdd}_Clip*): {len(matched)} 件")
        for num, name in matched:
            print(f"    - {name} (#{num})")
        next_seq = max_num + 1
    else:
        print(f"  パターン一致 (00_{mmdd}_Clip*): 0 件")
        next_seq = 1

    print()
    print(f"→ 次の timeline 名: 00_{mmdd}_Clip{next_seq:02d}")
    print()
    print("Phase 2 完了。Phase 3 (FCPXML import) に進めます。")


if __name__ == "__main__":
    main()
