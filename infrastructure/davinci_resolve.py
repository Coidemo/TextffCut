"""DaVinci Resolve scripting API ラッパー。

CLI (`textffcut send`) と GUI から共通利用される。
Resolve は起動済み + Local scripting 有効化 + プロジェクト open 前提。
TextffCut は Apple Silicon Mac 専用のため、パスも macOS 前提で決め打ち。

主要関数:
  - send_clip_to_resolve(): FCPXML + SRT を 1 コマンドで取り込み + SE ミュート
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
class SendResult:
    """send_clip_to_resolve() の実行結果。"""

    timeline_name: str
    bin_name: str
    srt_imported: bool = False
    se_muted: list[int] = field(default_factory=list)
    se_kept: list[int] = field(default_factory=list)


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


def send_clip_to_resolve(
    fcpxml_path: Path,
    *,
    srt_path: Path | None = None,
    mmdd: str | None = None,
) -> SendResult:
    """FCPXML と SRT を Resolve の現在開いているビンに送信する。

    Args:
        fcpxml_path: FCPXML ファイルパス (絶対パス)
        srt_path: SRT ファイルパス。省略時は同名の .srt を探す
        mmdd: 連番計算用の月日 (例: "0210")。省略時は動画ディレクトリ名から抽出

    Returns:
        SendResult: 操作結果
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

    return SendResult(
        timeline_name=new_name,
        bin_name=bin_name,
        srt_imported=srt_imported,
        se_muted=se_muted,
        se_kept=se_kept,
    )
