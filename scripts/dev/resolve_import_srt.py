"""Phase 4: 既存の Timeline に SRT を字幕トラックとして追加。

Resolve には直接の "ImportSubtitlesFromFile" API はないので:
  1. MediaPool.ImportMedia で SRT を Media Pool に追加 (Resolve は SRT を字幕クリップとして認識)
  2. Timeline を current に設定
  3. MediaPool.AppendToTimeline で字幕トラックに配置

事前準備:
  - Resolve で対象 timeline を開いておく
  - SRT ファイルパスを引数で渡す

使用例:
  python scripts/dev/resolve_import_srt.py \\
    "videos/.../fcpxml/02_xxx.srt" \\
    --timeline 00_0210_Clip01
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def setup_resolve_path() -> None:
    api_root = os.environ.get(
        "RESOLVE_SCRIPT_API",
        "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
    )
    sys.path.insert(0, str(Path(api_root) / "Modules"))


def connect():
    import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        print("❌ Resolve に接続できません", file=sys.stderr)
        sys.exit(1)
    return resolve


def find_timeline_by_name(project, name: str):
    count = project.GetTimelineCount()
    for i in range(1, count + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and tl.GetName() == name:
            return tl
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4: SRT を timeline に字幕として追加")
    parser.add_argument("srt", type=Path, help="SRT ファイルパス")
    parser.add_argument("--timeline", required=True, help="対象 timeline 名 (例: 00_0210_Clip01)")
    args = parser.parse_args()

    srt_path: Path = args.srt.resolve()
    if not srt_path.exists():
        print(f"❌ SRT が見つかりません: {srt_path}", file=sys.stderr)
        sys.exit(1)

    setup_resolve_path()
    resolve = connect()
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        print("❌ プロジェクト未起動", file=sys.stderr)
        sys.exit(1)

    timeline = find_timeline_by_name(project, args.timeline)
    if timeline is None:
        print(f"❌ Timeline {args.timeline!r} が見つかりません", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Timeline 検出: {timeline.GetName()}")

    # current timeline に設定
    project.SetCurrentTimeline(timeline)

    # SRT を Media Pool に追加
    media_pool = project.GetMediaPool()
    print(f"SRT を Media Pool に追加中: {srt_path}")
    items = media_pool.ImportMedia([str(srt_path)])
    if not items:
        print("❌ ImportMedia 失敗", file=sys.stderr)
        sys.exit(1)
    srt_item = items[0]
    print(f"✓ Media Pool 追加: {srt_item.GetName()}")

    # subtitle track 数を確認 / なければ追加
    subtitle_count = timeline.GetTrackCount("subtitle")
    print(f"  既存 subtitle track 数: {subtitle_count}")
    if subtitle_count == 0:
        ok = timeline.AddTrack("subtitle")
        print(f"  subtitle track を新規追加: {'OK' if ok else 'FAIL'}")

    # AppendToTimeline で subtitle track に配置
    print("Timeline に append 中...")
    appended = media_pool.AppendToTimeline([srt_item])
    if not appended:
        print("⚠ AppendToTimeline が空のリストを返した", file=sys.stderr)
        print("  Resolve の subtitle track 仕様で配置できないかもしれません")
        print("  手動配置 (Media Pool → drag to subtitle track) を試してください")
        sys.exit(1)
    print(f"✓ {len(appended)} item 配置完了")

    print()
    print("Phase 4 完了。 Resolve でタイムラインを開いて字幕を確認してください。")


if __name__ == "__main__":
    main()
