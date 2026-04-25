"""DaVinci Resolve scripting API ラッパー。

CLI (`textffcut send`) と GUI から共通利用される。
Resolve は起動済み + Local scripting 有効化 + プロジェクト open 前提。
TextffCut は Apple Silicon Mac 専用のため、パスも macOS 前提で決め打ち。

主要関数:
  - send_clip_to_resolve(): FCPXML + SRT を 1 コマンドで取り込み + SE ミュート
  - convert_subtitles_to_text_plus(): Subtitle トラックを Fusion Text+ クリップに変換
"""

from __future__ import annotations

import logging
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# DaVinci Resolve scripting API モジュールのデフォルトパス (macOS)
# TextffCut は Apple Silicon Mac 専用のためこのパスで固定
_DEFAULT_API_ROOT = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"

# Resolve は SRT の改行を U+2028 (Line Separator) として保持するため、
# Text+ 用に \n へ変換する必要がある
_LINE_SEPARATOR = chr(0x2028)

# Text+ 変換のデフォルト値
TEXT_PLUS_DEFAULT_BIN = "TextffCut"
TEXT_PLUS_DEFAULT_TEMPLATE = "Caption_Default"
TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES = 10
TEXT_PLUS_CLIP_COLOR = "Green"


# SE 判定用のキーワード (preset/ 配下の SE ファイル名から)
# 保守性のため、preset/ ディレクトリに新しい SE を追加したらここにも追加する
SE_KEYWORDS: tuple[str, ...] = (
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


@dataclass
class TextPlusResult:
    """convert_subtitles_to_text_plus() の実行結果。"""

    video_track: int
    success: int
    failed: int
    gap_filled: int = 0
    head_extended: int = 0
    tail_extended: int = 0
    subtitle_disabled: bool = False


@dataclass
class SendResult:
    """send_clip_to_resolve() の実行結果。"""

    timeline_name: str
    bin_name: str
    srt_imported: bool = False
    se_muted: list[int] = field(default_factory=list)
    se_kept: list[int] = field(default_factory=list)
    text_plus: TextPlusResult | None = None


class ResolveError(Exception):
    """Resolve 接続/操作エラー。"""


def _setup_path() -> None:
    api_root = os.environ.get("RESOLVE_SCRIPT_API", _DEFAULT_API_ROOT)
    modules_path = Path(api_root) / "Modules"
    if not modules_path.exists():
        raise ResolveError(
            f"Resolve scripting modules が見つかりません: {modules_path}\n"
            "DaVinci Resolve がインストールされているか確認してください"
        )
    if str(modules_path) not in sys.path:
        sys.path.insert(0, str(modules_path))


def connect_resolve():
    """Resolve に接続して Resolve オブジェクトを返す。失敗時は ResolveError。"""
    _setup_path()
    try:
        import DaVinciResolveScript as dvr_script  # type: ignore[import-not-found]
    except ImportError as e:
        raise ResolveError(f"DaVinciResolveScript の import 失敗: {e}") from e

    resolve = dvr_script.scriptapp("Resolve")
    if resolve is None:
        raise ResolveError(
            "Resolve に接続できません。\n"
            "  1. DaVinci Resolve を起動\n"
            "  2. Preferences > System > General > External scripting using: Local"
        )
    return resolve


def _compute_next_seq(folder, mmdd: str) -> int:
    """ビン内の `00_{mmdd}_Clip{NN}` パターンから max+1 を返す。"""
    pattern = re.compile(rf"^00_{mmdd}_Clip(\d+)$")
    nums: list[int] = []
    for c in folder.GetClipList() or []:
        m = pattern.match(c.GetName())
        if m:
            nums.append(int(m.group(1)))
    return max(nums, default=0) + 1


def _extract_mmdd_from_path(fcpxml_path: Path) -> str | None:
    """`videos/YYYYMMDD_xxx_TextffCut/...` から MMDD を抽出。"""
    for parent in fcpxml_path.parents:
        m = re.match(r"^\d{4}(\d{2})(\d{2})_.*_TextffCut$", parent.name)
        if m:
            return m.group(1) + m.group(2)
    return None


def is_se_clip_name(name: str) -> bool:
    """SE_KEYWORDS のいずれかを含む名前を SE と判定する。

    BGM や本編動画 (source_*) は明示的に除外。
    .mp3 拡張子だけでは SE 扱いしない (ナレーション等の可能性があるため)。
    """
    lower = name.lower()
    if "bgm" in lower:
        return False
    if "source_" in lower:
        return False
    return any(kw in name for kw in SE_KEYWORDS)


def _detect_and_mute_material_se(timeline) -> tuple[list[int], list[int]]:
    """SE トラックを判定し、素材用 (clip 数最大) のみミュート。

    Returns:
        (muted_indices, kept_enabled_indices)
    """
    audio_count = timeline.GetTrackCount("audio")
    se_tracks: list[tuple[int, int]] = []
    for i in range(1, audio_count + 1):
        items = timeline.GetItemListInTrack("audio", i) or []
        if not items:
            continue
        clip_names = [item.GetName() for item in items]
        if any("source_" in n for n in clip_names):
            continue
        se_count = sum(1 for n in clip_names if is_se_clip_name(n))
        if se_count >= len(items) / 2:
            se_tracks.append((i, len(items)))

    if not se_tracks:
        return [], []

    if len(se_tracks) >= 2:
        # clip 数最大が素材用 (lane 4)、それ以外が AI 配置 (lane 5)
        material_idx = max(se_tracks, key=lambda x: x[1])[0]
        ai_indices = [idx for idx, _ in se_tracks if idx != material_idx]
    else:
        material_idx = se_tracks[0][0]
        ai_indices = []

    muted: list[int] = []
    kept: list[int] = []
    if timeline.SetTrackEnable("audio", material_idx, False):
        muted.append(material_idx)
    for i in ai_indices:
        # AI 配置トラックは確実に有効化する (前回テストで誤って mute された場合の復元)
        if timeline.SetTrackEnable("audio", i, True):
            kept.append(i)

    return muted, kept


def _find_text_plus_bin(media_pool, name: str):
    root = media_pool.GetRootFolder()
    if root is None:
        return None
    for folder in root.GetSubFolderList() or []:
        if folder.GetName() == name:
            return folder
    return None


def _find_text_plus_template(folder, name: str):
    for clip in folder.GetClipList() or []:
        if clip.GetName() == name:
            return clip
    return None


def _add_video_track_on_top(timeline) -> int:
    """新規ビデオトラックを最上位に追加し、追加後の index を返す。"""
    before = timeline.GetTrackCount("video")
    if not timeline.AddTrack("video"):
        raise ResolveError("video track の追加に失敗しました")
    after = timeline.GetTrackCount("video")
    if after != before + 1:
        raise ResolveError(
            f"video track 追加が反映されていません: before={before} after={after}"
        )
    return after


def _normalize_tool_list(tool_list_obj) -> list:
    """GetToolList の戻り (dict / list / 単一) を list に正規化。"""
    if tool_list_obj is None:
        return []
    if isinstance(tool_list_obj, dict):
        return list(tool_list_obj.values())
    try:
        return list(tool_list_obj)
    except TypeError:
        return [tool_list_obj]


def _compute_duration_multiplier(
    media_pool, timeline, template_clip, video_track: int, record_frame: int
) -> float:
    """テスト clip を一度配置→測定→削除して、Fusion comp の内部固有 duration による
    スケール影響を打ち消す補正係数を返す。失敗時は 1.0。"""
    test_duration = 100
    test_info = {
        "mediaPoolItem": template_clip,
        "startFrame": 0,
        "endFrame": test_duration - 1,
        "trackIndex": video_track,
        "recordFrame": record_frame,
    }
    test_appended = media_pool.AppendToTimeline([test_info])
    if (
        not test_appended
        or test_appended[0] is None
        or test_appended[0].GetName() is None
    ):
        logger.warning("Text+ duration test 配置失敗、multiplier=1.0 で続行")
        return 1.0
    test_item = test_appended[0]
    test_real = test_item.GetDuration()
    timeline.DeleteClips([test_item], False)
    if not test_real or test_real <= 0:
        logger.warning(
            f"Text+ duration test の GetDuration() が無効値 (test_real={test_real})、"
            "multiplier=1.0 で続行します。Text+ クリップ間に隙間が生じる可能性があります"
        )
        return 1.0
    return test_duration / test_real


def convert_subtitles_to_text_plus(
    project,
    timeline,
    *,
    bin_name: str = TEXT_PLUS_DEFAULT_BIN,
    template_name: str = TEXT_PLUS_DEFAULT_TEMPLATE,
    subtitle_track: int = 1,
    fill_gaps: bool = True,
    max_fill_frames: int = TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES,
    extend_edges: bool = True,
    disable_subtitle_after: bool = True,
) -> TextPlusResult:
    """Subtitle トラックの字幕を Fusion Text+ クリップに変換する。

    Args:
        project: Resolve プロジェクト (既に取得済みのもの)
        timeline: 対象タイムライン (current でなくても OK)
        bin_name: テンプレートを格納したビン名
        template_name: テンプレートクリップ名 (Fusion Title)
        subtitle_track: 字幕トラック index (default 1)。複数あっても他は見ない
        fill_gaps: 次字幕までの gap を埋める
        max_fill_frames: Fill Gaps で埋める最大フレーム数
        extend_edges: 最初/最後の字幕をタイムライン端まで伸ばす
        disable_subtitle_after: 処理成功時に subtitle track を無効化する

    Raises:
        ResolveError: ビン/テンプレート/字幕トラックが存在しない等
    """
    media_pool = project.GetMediaPool()

    folder = _find_text_plus_bin(media_pool, bin_name)
    if folder is None:
        raise ResolveError(
            f"Media Pool に '{bin_name}' ビンが見つかりません。\n"
            f"DaVinci Resolve の Media Pool root に '{bin_name}' ビンを作成し、"
            f"その中に '{template_name}' という名前の Fusion Title (Text+) を入れてください。"
        )

    template_clip = _find_text_plus_template(folder, template_name)
    if template_clip is None:
        raise ResolveError(
            f"'{bin_name}' ビン内に '{template_name}' テンプレートが見つかりません。\n"
            f"好きな Fusion Title (Text+) テンプレートを '{bin_name}' ビンへコピーし、"
            f"名前を '{template_name}' に変更してください。"
        )

    subtitle_count = timeline.GetTrackCount("subtitle")
    if subtitle_track > subtitle_count:
        raise ResolveError(
            f"subtitle track {subtitle_track} がタイムラインにありません "
            f"(タイムラインの subtitle track 数: {subtitle_count})"
        )
    subtitles = timeline.GetItemListInTrack("subtitle", subtitle_track) or []
    if not subtitles:
        raise ResolveError(
            f"subtitle track {subtitle_track} に字幕クリップがありません"
        )

    timeline_start = timeline.GetStartFrame()
    timeline_end = timeline.GetEndFrame()  # exclusive

    target_video_track = _add_video_track_on_top(timeline)
    logger.info(f"Text+ 用に video track V{target_video_track} を追加")

    duration_multiplier = _compute_duration_multiplier(
        media_pool, timeline, template_clip, target_video_track, subtitles[0].GetStart()
    )
    logger.info(f"Text+ duration_multiplier={duration_multiplier:.4f}")

    success = 0
    failed = 0
    fill_count = 0
    head_extended = 0
    tail_extended = 0

    for idx, sub in enumerate(subtitles, 1):
        text = (sub.GetName() or "").replace(_LINE_SEPARATOR, "\n")
        start = sub.GetStart()
        end = sub.GetEnd()
        duration = end - start
        record_frame = start

        if duration <= 0:
            logger.warning(f"[{idx}/{len(subtitles)}] duration<=0 でスキップ: {text!r}")
            failed += 1
            continue

        # 最初の字幕: タイムライン先頭まで伸ばす
        if extend_edges and idx == 1:
            head_ext = start - timeline_start
            if head_ext > 0:
                record_frame = timeline_start
                duration += head_ext
                head_extended = head_ext

        # 最後の字幕: タイムライン末尾まで伸ばす
        if extend_edges and idx == len(subtitles):
            tail_ext = timeline_end - end
            if tail_ext > 0:
                duration += tail_ext
                tail_extended = tail_ext

        # Fill Gaps: 次字幕までの gap が max_fill_frames 以下なら end を伸ばす
        end_frame = duration - 1
        if fill_gaps and idx < len(subtitles):
            next_sub = subtitles[idx]
            gap = next_sub.GetStart() - end
            if 0 < gap <= max_fill_frames:
                end_frame += gap
                fill_count += 1

        # duration_multiplier 補正 (Fusion comp の内部 duration による短縮を打ち消す)
        # `+ 0.999` は ceiling 風の丸め (Snap Captions Lua line 1063 と同じ慣用)。
        # math.ceil(...) でも等価だが、Lua 由来の意図を保持するためそのまま採用。
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
        if (
            not appended
            or appended[0] is None
            or appended[0].GetName() is None
        ):
            logger.warning(
                f"[{idx}/{len(subtitles)}] AppendToTimeline 失敗 "
                f"(track V{target_video_track} が占有されている可能性): {text!r}"
            )
            failed += 1
            continue

        new_item = appended[0]
        new_item.SetClipColor(TEXT_PLUS_CLIP_COLOR)

        if new_item.GetFusionCompCount() == 0:
            logger.error(
                f"timeline item に Fusion comp が 0 個です。"
                f"テンプレート '{template_name}' が Fusion Title (Text+) ではない可能性"
            )
            failed += 1
            continue

        comp = new_item.GetFusionCompByIndex(1)
        if comp is None:
            logger.warning(f"[{idx}/{len(subtitles)}] Fusion comp 取得失敗: {text!r}")
            failed += 1
            continue

        text_tools = _normalize_tool_list(comp.GetToolList(False, "TextPlus"))
        if not text_tools:
            logger.warning(f"[{idx}/{len(subtitles)}] Text+ ツールが見つかりません: {text!r}")
            failed += 1
            continue

        # SetInput の戻り値は信用できないため呼びっぱなし
        text_tools[0].SetInput("StyledText", text)
        success += 1

    subtitle_disabled = False
    if disable_subtitle_after and success > 0:
        if timeline.SetTrackEnable("subtitle", subtitle_track, False):
            subtitle_disabled = True
        else:
            logger.warning(f"subtitle track {subtitle_track} の無効化に失敗")

    return TextPlusResult(
        video_track=target_video_track,
        success=success,
        failed=failed,
        gap_filled=fill_count,
        head_extended=head_extended,
        tail_extended=tail_extended,
        subtitle_disabled=subtitle_disabled,
    )


def send_clip_to_resolve(
    fcpxml_path: Path,
    *,
    srt_path: Path | None = None,
    mmdd: str | None = None,
    text_plus: bool = False,
    text_plus_bin: str = TEXT_PLUS_DEFAULT_BIN,
    text_plus_template: str = TEXT_PLUS_DEFAULT_TEMPLATE,
) -> SendResult:
    """FCPXML と SRT を Resolve の現在開いているビンに送信する。

    Args:
        fcpxml_path: FCPXML ファイルパス (絶対パス)
        srt_path: SRT ファイルパス。省略時は同名の .srt を探す
        mmdd: 連番計算用の月日 (例: "0210")。省略時は動画ディレクトリ名から抽出
        text_plus: SRT 取り込み後に Text+ 自動変換を実行 (default: False)。
            ライブラリ層では明示オプトイン、UI 層 (CLI/GUI) でデフォ ON にして
            呼び出すレイヤ分離。CLI: `textffcut send` (デフォ ON、`--no-text-plus` で OFF)、
            GUI: 字幕エディタの「Text+ 自動変換」チェックボックス (デフォ ON)。
        text_plus_bin: Text+ テンプレートを格納したビン名
        text_plus_template: Text+ テンプレートクリップ名 (Fusion Title)

    Returns:
        SendResult: 操作結果。Text+ 変換が実行された場合は ``text_plus`` 属性に
            TextPlusResult が入る。テンプレ未配置等でスキップした場合は None。
    """
    fcpxml_path = fcpxml_path.resolve()
    if not fcpxml_path.exists():
        raise ResolveError(f"FCPXML が見つかりません: {fcpxml_path}")

    if srt_path is None:
        srt_path = fcpxml_path.with_suffix(".srt")
    srt_path = srt_path.resolve() if srt_path.exists() else None

    if mmdd is None:
        mmdd = _extract_mmdd_from_path(fcpxml_path)
    if not mmdd or not re.match(r"^\d{4}$", mmdd):
        raise ResolveError(
            f"MMDD を抽出できません。動画ディレクトリ名が `YYYYMMDD_xxx_TextffCut` 形式か確認してください "
            f"(path={fcpxml_path})"
        )

    resolve = connect_resolve()
    project = resolve.GetProjectManager().GetCurrentProject()
    if project is None:
        raise ResolveError("Resolve でプロジェクトが開かれていません")

    media_pool = project.GetMediaPool()
    current = media_pool.GetCurrentFolder()
    if current is None:
        raise ResolveError("Media Pool の current folder が取得できません")
    bin_name = current.GetName()

    # 連番計算
    next_seq = _compute_next_seq(current, mmdd)
    new_name = f"00_{mmdd}_Clip{next_seq:02d}"
    logger.info(f"target bin={bin_name!r}, new timeline name={new_name}")

    # FCPXML import
    timeline = media_pool.ImportTimelineFromFile(str(fcpxml_path))
    if timeline is None:
        raise ResolveError(
            f"FCPXML import に失敗しました。Resolve がフリーズしていれば project を開き直してください "
            f"(path={fcpxml_path})"
        )

    # リネーム
    if timeline.GetName() != new_name:
        if not timeline.SetName(new_name):
            logger.warning(f"timeline rename 失敗: {timeline.GetName()!r} → {new_name!r}")

    # SRT import
    # Resolve 20 には SRT 専用 import API がないため、ImportMedia → AppendToTimeline で代替。
    # ImportMedia が SRT を subtitle clip として認識するのは heuristic (公式ドキュメント化されていない) 。
    # 将来バージョンで挙動が変われば要再検証。
    srt_imported = False
    if srt_path is not None:
        project.SetCurrentTimeline(timeline)
        items = media_pool.ImportMedia([str(srt_path)])
        if items:
            if timeline.GetTrackCount("subtitle") == 0:
                timeline.AddTrack("subtitle")
            appended = media_pool.AppendToTimeline([items[0]])
            srt_imported = bool(appended)
            if not srt_imported:
                logger.warning(f"SRT を timeline に append できませんでした: {srt_path}")
        else:
            logger.warning(f"SRT を Media Pool に import できませんでした: {srt_path}")
    else:
        logger.info("SRT ファイルがないので SRT import スキップ")

    # SE ミュート
    se_muted, se_kept = _detect_and_mute_material_se(timeline)

    # Text+ 変換 (任意)
    text_plus_result: TextPlusResult | None = None
    if text_plus and srt_imported:
        try:
            text_plus_result = convert_subtitles_to_text_plus(
                project,
                timeline,
                bin_name=text_plus_bin,
                template_name=text_plus_template,
            )
        except ResolveError as e:
            logger.warning(f"Text+ 変換スキップ: {e}")
    elif text_plus and not srt_imported:
        logger.warning("Text+ 変換スキップ: SRT が import されていません")

    return SendResult(
        timeline_name=new_name,
        bin_name=bin_name,
        srt_imported=srt_imported,
        se_muted=se_muted,
        se_kept=se_kept,
        text_plus=text_plus_result,
    )
