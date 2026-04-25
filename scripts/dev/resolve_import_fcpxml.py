"""Phase 3: FCPXML を import して timeline を作成し、00_MMDD_ClipNN にリネーム。

事前準備:
  - Resolve で目的のビンを Media Pool でクリックして開いておく
  - FCPXML ファイルのパスを引数で渡す
  - MMDD は動画ディレクトリ名から自動抽出 (videos/YYYYMMDD_xxx_TextffCut/)

使用例:
  python scripts/dev/resolve_import_fcpxml.py \\
    "videos/20260210_xxx_TextffCut/fcpxml/01_xxx.fcpxml"

  または MMDD を明示:
  python scripts/dev/resolve_import_fcpxml.py \\
    "path/to/clip.fcpxml" --mmdd 0210

このフェーズでは SRT は触らない (Phase 4 で扱う)。
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
        print("❌ Resolve に接続できません", file=sys.stderr)
        sys.exit(1)
    return resolve


def extract_mmdd_from_path(fcpxml_path: Path) -> str | None:
    """videos/YYYYMMDD_xxx_TextffCut/fcpxml/...  から MMDD を抽出。"""
    for parent in fcpxml_path.parents:
        m = re.match(r"^\d{4}(\d{2})(\d{2})_.*_TextffCut$", parent.name)
        if m:
            return m.group(1) + m.group(2)
    return None


def compute_next_seq(folder, mmdd: str) -> int:
    pattern = re.compile(rf"^00_{mmdd}_Clip(\d+)$")
    nums = []
    for c in folder.GetClipList() or []:
        m = pattern.match(c.GetName())
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: FCPXML import + リネーム")
    parser.add_argument("fcpxml", type=Path, help="FCPXML ファイルパス")
    parser.add_argument("--mmdd", help="月日 (例: 0210)。省略時は動画ディレクトリ名から抽出")
    args = parser.parse_args()

    fcpxml_path: Path = args.fcpxml.resolve()
    if not fcpxml_path.exists():
        print(f"❌ FCPXML が見つかりません: {fcpxml_path}", file=sys.stderr)
        sys.exit(1)

    mmdd = args.mmdd or extract_mmdd_from_path(fcpxml_path)
    if not mmdd or not re.match(r"^\d{4}$", mmdd):
        print(
            f"❌ MMDD を抽出できません。--mmdd で明示してください (path={fcpxml_path})",
            file=sys.stderr,
        )
        sys.exit(1)

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

    print(f"✓ 現在のビン: {current.GetName()}")

    next_seq = compute_next_seq(current, mmdd)
    new_name = f"00_{mmdd}_Clip{next_seq:02d}"
    print(f"→ 新規 timeline 名: {new_name}")
    print(f"  FCPXML: {fcpxml_path}")
    print()

    # FCPXML import
    print("FCPXML を import 中...")
    timeline = media_pool.ImportTimelineFromFile(str(fcpxml_path))
    if timeline is None:
        print("❌ FCPXML import に失敗しました", file=sys.stderr)
        sys.exit(1)

    imported_name = timeline.GetName()
    print(f"✓ Import 完了 (元の名前: {imported_name})")

    # リネーム
    if imported_name != new_name:
        ok = timeline.SetName(new_name)
        if ok:
            print(f"✓ リネーム成功: {imported_name} → {new_name}")
        else:
            print(f"⚠ リネーム失敗 (元名のまま: {imported_name})", file=sys.stderr)
    else:
        print(f"✓ 元名と新名が一致 (リネーム不要): {new_name}")

    print()
    print("Phase 3 完了。 Phase 4 (SRT import) に進めます。")


if __name__ == "__main__":
    main()
