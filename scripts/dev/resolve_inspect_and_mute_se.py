"""Phase 4.5: Timeline の audio track 構造を表示 + SE track をミュート。

TextffCut の FCPXML は lane 構造で:
  - 本編音声 (動画と同じ asset-clip)
  - lane 3: BGM
  - lane 4: SE (効果音)

Resolve に取り込まれると複数の audio track に分かれる。track 名や中身の clip 名から
SE track を判定してミュートする。

使用例:
  python scripts/dev/resolve_inspect_and_mute_se.py --timeline 00_0210_Clip01

  # ミュートせず一覧のみ表示
  python scripts/dev/resolve_inspect_and_mute_se.py --timeline 00_0210_Clip01 --dry-run
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


# SE 判定キーワード (preset/ 配下の SE ファイル名から)
SE_KEYWORDS = (
    "ジャン",
    "きらーん",
    "キュピーン",
    "グサッ",
    "シャキーン",
    "チリン",
    "ニュッ",
    "ビシッ",
    "ピアノ",
    "不安",
    "和太鼓",
    "拍子木",
    "涙",
    "間抜け",
    "シャ",
    "ドン",
    "コン",
    "ピコ",
    "ジャラン",
    "テロップ",
)


def is_se_clip_name(name: str) -> bool:
    if "bgm" in name.lower() or "BGM" in name:
        return False
    if "source_" in name.lower():
        return False
    return any(kw in name for kw in SE_KEYWORDS) or name.endswith(".mp3")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeline", required=True, help="対象 timeline 名")
    parser.add_argument("--dry-run", action="store_true", help="ミュートせず一覧のみ")
    args = parser.parse_args()

    setup_resolve_path()
    resolve = connect()
    project = resolve.GetProjectManager().GetCurrentProject()
    timeline = find_timeline_by_name(project, args.timeline)
    if timeline is None:
        print(f"❌ Timeline {args.timeline!r} が見つかりません", file=sys.stderr)
        sys.exit(1)
    print(f"✓ Timeline: {timeline.GetName()}")

    audio_count = timeline.GetTrackCount("audio")
    print(f"  audio track 数: {audio_count}")
    print()

    se_tracks: list[tuple[int, int]] = []  # [(track_index, clip_count)]
    for i in range(1, audio_count + 1):
        name = timeline.GetTrackName("audio", i)
        items = timeline.GetItemListInTrack("audio", i) or []
        enabled = timeline.GetIsTrackEnabled("audio", i)

        clip_names = [item.GetName() for item in items]
        unique_names = list(dict.fromkeys(clip_names))[:5]
        sample = ", ".join(unique_names) + ("..." if len(unique_names) >= 5 else "")

        se_count = sum(1 for n in clip_names if is_se_clip_name(n))
        is_se = items and se_count >= len(items) / 2 and not any("source_" in n for n in clip_names)

        marker = " ★SE★" if is_se else ""
        print(f"  A{i} [{name!r}] enabled={enabled}, clips={len(items)}{marker}")
        if sample:
            print(f"     例: {sample}")
        if is_se:
            se_tracks.append((i, len(items)))

    print()
    if not se_tracks:
        print("⚠ SE track と判定された track がありません")
        sys.exit(0)

    # SE トラックが複数あるとき: clip 数が最大のものを「素材用 (lane 4)」と判定
    # 残りは AI 自動配置 (lane 5) なので keep
    if len(se_tracks) >= 2:
        material_idx = max(se_tracks, key=lambda x: x[1])[0]
        ai_indices = [idx for idx, _ in se_tracks if idx != material_idx]
        print(f"→ 素材用 SE track (mute 対象): A{material_idx}")
        print(f"→ AI 自動配置 SE track (keep): A{', A'.join(str(i) for i in ai_indices)}")
        mute_targets = [material_idx]
        unmute_targets = ai_indices
    else:
        # SE track が 1 個のみ: 素材用のみと判断
        material_idx = se_tracks[0][0]
        print(f"→ SE track が 1 個のみ、素材用と判定: A{material_idx}")
        mute_targets = [material_idx]
        unmute_targets = []

    if args.dry_run:
        print("(dry-run のためミュート実行せず)")
        return

    print()
    print("実行中...")
    for i in mute_targets:
        ok = timeline.SetTrackEnable("audio", i, False)
        print(f"  A{i} ミュート: {'OK' if ok else 'FAIL'}")
    for i in unmute_targets:
        # AI 配置トラックは有効化 (前回テストで誤って mute したのを戻す)
        ok = timeline.SetTrackEnable("audio", i, True)
        print(f"  A{i} 有効化: {'OK' if ok else 'FAIL'}")

    print()
    print("Phase 4.5 完了。Resolve でトラックがミュートされたことを確認してください。")


if __name__ == "__main__":
    main()
