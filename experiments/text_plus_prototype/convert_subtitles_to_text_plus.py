"""DaVinci Resolve の Subtitle トラックを Text+ クリップに変換するプロトタイプ。

TextffCut 統合前の挙動検証用スクリプト。Resolve scripting API のみで動作する。

事前準備:
  1. DaVinci Resolve を起動し、対象プロジェクトを開く
  2. Preferences > System > General > External scripting using: Local
  3. Media Pool の root に "TextffCut" ビンを作成
  4. "TextffCut" ビン内に "Caption_Default" という Fusion Title (Text+) を配置
  5. Subtitle 1 に SRT 字幕が乗ったタイムラインを current にする

使用例:
    python convert_subtitles_to_text_plus.py --dry-run     # 字幕を列挙するだけ
    python convert_subtitles_to_text_plus.py               # 既定で実行
    python convert_subtitles_to_text_plus.py --template Caption_Bold
    python convert_subtitles_to_text_plus.py --video-track 5  # 既存トラックに配置
    python convert_subtitles_to_text_plus.py --keep-subtitle  # subtitle 無効化しない
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.davinci_resolve import ResolveError, connect_resolve  # noqa: E402

logger = logging.getLogger("text_plus_prototype")

CLIP_COLOR = "Green"  # Snap Captions と同じ
# Resolve は SRT の改行を U+2028 (Line Separator) として保持する
LINE_SEPARATOR = chr(0x2028)


def find_bin(media_pool, name: str):
    root = media_pool.GetRootFolder()
    if root is None:
        return None
    for folder in root.GetSubFolderList() or []:
        if folder.GetName() == name:
            return folder
    return None


def find_template_clip(folder, name: str):
    for clip in folder.GetClipList() or []:
        if clip.GetName() == name:
            return clip
    return None


def add_video_track_on_top(timeline) -> int:
    """新規ビデオトラックを最上位に追加し、追加後の index を返す。"""
    before = timeline.GetTrackCount("video")
    if not timeline.AddTrack("video"):
        raise RuntimeError("video track の追加に失敗しました")
    after = timeline.GetTrackCount("video")
    if after != before + 1:
        raise RuntimeError(
            f"video track 追加が反映されていません: before={before} after={after}"
        )
    return after


def _normalize_tool_list(tool_list_obj):
    """GetToolList の戻り (dict / list / 単一) を list に正規化。"""
    if tool_list_obj is None:
        return []
    if isinstance(tool_list_obj, dict):
        return list(tool_list_obj.values())
    try:
        return list(tool_list_obj)
    except TypeError:
        return [tool_list_obj]


def convert(
    *,
    bin_name: str,
    template_name: str,
    subtitle_track: int,
    video_track: int | None,
    dry_run: bool,
    keep_subtitle: bool,
    fill_gaps: bool,
    max_fill_frames: int,
    extend_edges: bool,
    limit: int | None = None,
) -> int:
    resolve = connect_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        raise RuntimeError("Resolve でプロジェクトが開かれていません")

    timeline = project.GetCurrentTimeline()
    if timeline is None:
        raise RuntimeError("現在のタイムラインが取得できません")

    media_pool = project.GetMediaPool()

    folder = find_bin(media_pool, bin_name)
    if folder is None:
        raise RuntimeError(
            f"Media Pool に '{bin_name}' ビンが見つかりません。\n"
            f"DaVinci Resolve の Media Pool root に '{bin_name}' ビンを作成してください。"
        )

    template_clip = find_template_clip(folder, template_name)
    if template_clip is None:
        raise RuntimeError(
            f"'{bin_name}' ビン内に '{template_name}' テンプレートが見つかりません。\n"
            f"Snap Captions の Pack から好みのテンプレートを '{bin_name}' ビンへコピーし、\n"
            f"名前を '{template_name}' に変更してください。"
        )

    # 字幕トラックは指定 index (default 1) を固定で使う。
    # 複数 subtitle track があっても他は見ない。
    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_track > subtitle_count:
        raise RuntimeError(
            f"subtitle track {subtitle_track} がタイムラインにありません "
            f"(タイムラインの subtitle track 数: {subtitle_count})"
        )
    subtitles = timeline.GetItemListInTrack("subtitle", subtitle_track) or []
    if not subtitles:
        raise RuntimeError(f"subtitle track {subtitle_track} に字幕クリップがありません")

    framerate = float(timeline.GetSetting("timelineFrameRate") or 30.0)
    timeline_start = timeline.GetStartFrame()
    timeline_end = timeline.GetEndFrame()  # exclusive (= last frame + 1)
    logger.info(
        f"timeline frame_rate={framerate} range=[{timeline_start}, {timeline_end}) "
        f"subtitle_track={subtitle_track} 字幕件数={len(subtitles)}"
    )

    # 配置先のビデオトラックを決定
    if dry_run:
        target_video_track = video_track or "(自動追加予定)"
    elif video_track is None:
        target_video_track = add_video_track_on_top(timeline)
        logger.info(f"video track 新規追加: V{target_video_track}")
    else:
        target_video_track = video_track
        logger.info(f"video track (指定): V{target_video_track}")

    # duration_multiplier を計算 (Fusion comp の内部固有 duration により
    # AppendToTimeline で指定した endFrame と実際の配置長が一致しないため、
    # test clip を一度配置→測定→削除して補正係数を求める)
    duration_multiplier = 1.0
    if not dry_run:
        first_start = subtitles[0].GetStart()
        test_duration = 100
        test_info = {
            "mediaPoolItem": template_clip,
            "startFrame": 0,
            "endFrame": test_duration - 1,
            "trackIndex": target_video_track,
            "recordFrame": first_start,
        }
        test_appended = media_pool.AppendToTimeline([test_info])
        if (
            test_appended
            and test_appended[0] is not None
            and test_appended[0].GetName() is not None
        ):
            test_item = test_appended[0]
            test_real = test_item.GetDuration()
            if test_real and test_real > 0:
                duration_multiplier = test_duration / test_real
            timeline.DeleteClips([test_item], False)
            logger.info(
                f"duration_multiplier={duration_multiplier:.4f} "
                f"(test={test_duration}, real={test_real})"
            )
        else:
            logger.warning("duration test 配置失敗、multiplier=1.0 で続行")

    success = 0
    failed = 0
    fill_count = 0
    head_extended = 0
    tail_extended = 0
    for idx, sub in enumerate(subtitles, 1):
        if limit is not None and idx > limit:
            logger.info(f"--limit {limit} 到達のため終了")
            break

        # SRT の改行 (U+2028) を Text+ が認識する \n に変換
        text = (sub.GetName() or "").replace(LINE_SEPARATOR, "\n")
        start = sub.GetStart()
        end = sub.GetEnd()
        duration = end - start
        record_frame = start
        prefix = f"[{idx}/{len(subtitles)}]"

        if duration <= 0:
            logger.warning(f"{prefix} duration<=0 でスキップ: {text!r}")
            failed += 1
            continue

        # 最初の字幕: タイムラインの開始まで伸ばす
        if extend_edges and idx == 1:
            head_ext = start - timeline_start
            if head_ext > 0:
                record_frame = timeline_start
                duration += head_ext
                head_extended = head_ext

        # 最後の字幕: タイムラインの末尾まで伸ばす
        if extend_edges and idx == len(subtitles):
            tail_ext = timeline_end - end
            if tail_ext > 0:
                duration += tail_ext
                tail_extended = tail_ext

        # Fill Gaps: 次字幕までの gap が max_fill_frames 以下なら end を伸ばす
        end_frame = duration - 1
        gap_filled = 0
        if fill_gaps and idx < len(subtitles):
            next_sub = subtitles[idx]  # idx は 1-origin → idx 番目 = subtitles[idx]
            gap = next_sub.GetStart() - end
            if 0 < gap <= max_fill_frames:
                end_frame += gap
                gap_filled = gap
                fill_count += 1

        if dry_run:
            tags = []
            if gap_filled:
                tags.append(f"+gap{gap_filled}f")
            if idx == 1 and head_extended:
                tags.append(f"+head{head_extended}f")
            if idx == len(subtitles) and tail_extended:
                tags.append(f"+tail{tail_extended}f")
            extra = f" {' '.join(tags)}" if tags else ""
            logger.info(
                f"{prefix} DRY-RUN record={record_frame} duration={end_frame + 1}f"
                f"{extra} text={text!r}"
            )
            success += 1
            continue

        # duration_multiplier 補正 (Fusion comp の内部 duration によるスケール影響を打ち消す)
        # Snap Captions Lua line 1059-1063 と同じロジック
        base_duration = end_frame + 1
        corrected_end_frame = int(base_duration * duration_multiplier + 0.999) - 1

        clip_info = {
            "mediaPoolItem": template_clip,
            "startFrame": 0,
            "endFrame": corrected_end_frame,
            "trackIndex": target_video_track,
            "recordFrame": record_frame,
        }
        appended = media_pool.AppendToTimeline([clip_info])
        # AppendToTimeline は配置失敗しても [None] を返すことがあるため、
        # 要素の生存確認 (GetName が None でない) まで含めてチェック
        if (
            not appended
            or appended[0] is None
            or appended[0].GetName() is None
        ):
            logger.warning(
                f"{prefix} AppendToTimeline 失敗 "
                f"(track V{target_video_track} が占有されている可能性): {text!r}"
            )
            failed += 1
            continue

        new_item = appended[0]
        new_item.SetClipColor(CLIP_COLOR)

        if new_item.GetFusionCompCount() == 0:
            logger.error(
                f"{prefix} timeline item に Fusion comp が 0 個です。"
                f"テンプレート '{template_name}' が Fusion Title (Text+) ではない可能性"
            )
            failed += 1
            continue

        comp = new_item.GetFusionCompByIndex(1)
        if comp is None:
            logger.warning(f"{prefix} Fusion comp 取得失敗: {text!r}")
            failed += 1
            continue

        text_tools = _normalize_tool_list(comp.GetToolList(False, "TextPlus"))
        if not text_tools:
            logger.warning(f"{prefix} Text+ ツールが見つかりません: {text!r}")
            failed += 1
            continue

        # SetInput の戻り値は信用できないため呼びっぱなし (Snap Captions Lua も同じ)
        text_tools[0].SetInput("StyledText", text)
        tags = []
        if idx == 1 and head_extended:
            tags.append(f"+head{head_extended}f")
        if idx == len(subtitles) and tail_extended:
            tags.append(f"+tail{tail_extended}f")
        extra = f" [{' '.join(tags)}]" if tags else ""
        success += 1
        logger.info(f"{prefix} OK record={record_frame} text={text!r}{extra}")

    # 処理が成功した場合のみ subtitle track を無効化
    if not dry_run and success > 0 and not keep_subtitle:
        if timeline.SetTrackEnable("subtitle", subtitle_track, False):
            logger.info(f"subtitle track {subtitle_track} を無効化しました")
        else:
            logger.warning(f"subtitle track {subtitle_track} の無効化に失敗")

    extras = []
    if fill_gaps:
        extras.append(f"gap_filled={fill_count}")
    if extend_edges:
        extras.append(f"head_ext={head_extended}f tail_ext={tail_extended}f")
    extra_msg = (", " + ", ".join(extras)) if extras else ""
    logger.info(f"完了: success={success}, failed={failed}{extra_msg}")
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DaVinci Resolve の Subtitle トラックを Text+ クリップに変換するプロトタイプ"
    )
    parser.add_argument(
        "--bin",
        default="TextffCut",
        help="テンプレートを格納したビン名 (default: TextffCut)",
    )
    parser.add_argument(
        "--template",
        default="Caption_Default",
        help="テンプレートクリップ名 (default: Caption_Default)",
    )
    parser.add_argument(
        "--subtitle-track",
        type=int,
        default=1,
        help="字幕トラック index (default: 1)。複数あっても指定 index 以外は見ない",
    )
    parser.add_argument(
        "--video-track",
        type=int,
        default=None,
        help="Text+ 配置先ビデオトラック index。省略時は新規トラックを最上位に追加",
    )
    parser.add_argument(
        "--keep-subtitle",
        action="store_true",
        help="処理完了後に subtitle track を無効化しない",
    )
    parser.add_argument(
        "--fill-gaps",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="短い無音 gap を埋めて Text+ のチラつきを防ぐ (default: 有効)",
    )
    parser.add_argument(
        "--max-fill-frames",
        type=int,
        default=10,
        help="Fill Gaps で埋める最大フレーム数 (default: 10 ≒ 0.33s @ 30fps)",
    )
    parser.add_argument(
        "--extend-edges",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="最初の字幕をタイムライン先頭、最後の字幕を末尾まで伸ばす (default: 有効)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="変換せず字幕一覧の表示だけ行う",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="先頭 N 件だけ処理して停止 (デバッグ用)",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )

    try:
        return convert(
            bin_name=args.bin,
            template_name=args.template,
            subtitle_track=args.subtitle_track,
            video_track=args.video_track,
            dry_run=args.dry_run,
            keep_subtitle=args.keep_subtitle,
            fill_gaps=args.fill_gaps,
            max_fill_frames=args.max_fill_frames,
            extend_edges=args.extend_edges,
            limit=args.limit,
        )
    except (ResolveError, RuntimeError) as e:
        logger.error(f"ERROR: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
