"""SRT 編集ログと SRT 書き込みユーティリティ.

GUI の字幕エディタから使われる。2 つの役割：
  1. ユーザー編集後の SRT ファイルを書き込み（元の SRT を上書き）
  2. 編集前後のデータを JSONL ログに追記（LoRA 訓練用）

ログファイル: {video}_TextffCut/subtitle_edits/edits.jsonl (append-only)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

EDIT_LOG_SUBDIR = "subtitle_edits"
EDIT_LOG_FILE = "edits.jsonl"


@dataclass(frozen=True)
class SRTEntry:
    """字幕 1 entry. start/end は秒."""

    index: int
    start_time: float
    end_time: float
    text: str  # "\n" で行分割

    @property
    def lines(self) -> list[str]:
        return self.text.split("\n")


def _fmt_srt_time(s: float) -> str:
    """秒 → HH:MM:SS,mmm."""
    if s < 0:
        s = 0.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = round((s % 1) * 1000)
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def write_srt(entries: list[SRTEntry], output_path: Path) -> None:
    """SRT ファイルに書き込み (BOMなし + LF 改行: macOS/DaVinci 推奨).

    既存 _write_srt (srt_subtitle_generator.py) と互換.
    """
    lines: list[str] = []
    for e in entries:
        lines.append(str(e.index))
        lines.append(f"{_fmt_srt_time(e.start_time)} --> {_fmt_srt_time(e.end_time)}")
        lines.append(e.text)
        lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")


_SRT_ENTRY_RE = re.compile(
    r"^(\d+)\s*\n(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)\s*\n(.*?)(?=\n\s*\n\d+\s*\n|\Z)",
    re.DOTALL | re.MULTILINE,
)


def _parse_srt_time(s: str) -> float:
    """HH:MM:SS,mmm → 秒."""
    h, m, rest = s.split(":")
    sec, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms) / 1000.0


def parse_srt(path: Path) -> list[SRTEntry]:
    """SRT ファイルをパースして SRTEntry list を返す."""
    text = path.read_text(encoding="utf-8").strip() + "\n\n"
    out: list[SRTEntry] = []
    for m in _SRT_ENTRY_RE.finditer(text):
        idx = int(m.group(1))
        start = _parse_srt_time(m.group(2))
        end = _parse_srt_time(m.group(3))
        body = m.group(4).rstrip()
        out.append(SRTEntry(index=idx, start_time=start, end_time=end, text=body))
    return out


def _flatten_text(entries: list[SRTEntry]) -> str:
    """全 entry の全文字（改行除去・空白除去）を連結."""
    return re.sub(r"\s", "", "".join(e.text for e in entries))


def compute_edit_diff(
    original: list[SRTEntry],
    edited: list[SRTEntry],
) -> dict[str, Any]:
    """before/after の構造的 diff を計算.

    LoRA 訓練時に「どんな編集があったか」を分析する材料.
    """
    orig_flat = _flatten_text(original)
    edited_flat = _flatten_text(edited)
    content_unchanged = orig_flat == edited_flat

    orig_count = len(original)
    edited_count = len(edited)

    # 各 entry の line 数
    orig_one_line = sum(1 for e in original if "\n" not in e.text)
    edited_one_line = sum(1 for e in edited if "\n" not in e.text)

    # 改行位置が変わった entry 数 (粒度粗いが目安)
    line_break_changes = 0
    shared = min(orig_count, edited_count)
    for a, b in zip(original[:shared], edited[:shared], strict=False):
        if a.text.replace("\n", "") == b.text.replace("\n", "") and a.text != b.text:
            line_break_changes += 1

    return {
        "content_unchanged": content_unchanged,
        "entries_before": orig_count,
        "entries_after": edited_count,
        "entries_delta": edited_count - orig_count,
        "one_line_before": orig_one_line,
        "one_line_after": edited_one_line,
        "line_break_changes": line_break_changes,
    }


def _entries_to_dict_list(entries: list[SRTEntry]) -> list[dict[str, Any]]:
    """SRTEntry list → serializable dict list."""
    return [
        {
            "index": e.index,
            "start": round(e.start_time, 3),
            "end": round(e.end_time, 3),
            "lines": e.lines,
        }
        for e in entries
    ]


def append_edit_log(
    base_dir: Path,
    clip_id: str,
    original: list[SRTEntry],
    edited: list[SRTEntry],
    *,
    algorithm_version: str = "",
    video_file: str = "",
    full_text: str = "",
    char_times: list[tuple[float, float]] | None = None,
    edit_duration_sec: float | None = None,
) -> Path:
    """編集ログを {base_dir}/subtitle_edits/edits.jsonl に append.

    Args:
        base_dir: {video}_TextffCut/ ディレクトリ
        clip_id: 例 "01_AIで情報収集格差が爆増中!"
        original: アルゴリズム生成の元 entries
        edited: ユーザー編集後の entries
        algorithm_version: どの字幕生成 version か (v2_fix_f 等)
        video_file: 元動画のファイル名
        full_text: 元文字列（timing 復元用に保持）
        char_times: 元 char_times（LoRA 訓練で timing mapping に使用）
        edit_duration_sec: 編集にかけた時間
    Returns:
        書き込んだログファイルパス
    """
    log_dir = base_dir / EDIT_LOG_SUBDIR
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / EDIT_LOG_FILE

    diff = compute_edit_diff(original, edited)
    entry: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "clip_id": clip_id,
        "algorithm_version": algorithm_version,
        "video_file": video_file,
        "full_text": full_text,
        "char_times": char_times,
        "generated_entries": _entries_to_dict_list(original),
        "edited_entries": _entries_to_dict_list(edited),
        "diff_summary": diff,
        "edit_duration_sec": edit_duration_sec,
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return log_path


# ---------------------------------------------------------------------------
# SRT meta サイドカー (char_times)
# ---------------------------------------------------------------------------


META_SUFFIX = ".meta.json"


def meta_path_for(srt_path: Path) -> Path:
    """SRT の meta サイドカーパス."""
    return srt_path.with_suffix(srt_path.suffix + META_SUFFIX)


def save_srt_meta(
    srt_path: Path,
    full_text: str,
    char_times: list[tuple[float, float]],
) -> Path:
    """SRT に対応する meta サイドカーを保存.

    full_text は SRT 全体の裸文字列 (改行なし)、char_times は各文字の (start, end).
    """
    if len(full_text) != len(char_times):
        raise ValueError(
            f"full_text ({len(full_text)} chars) と char_times ({len(char_times)}) の長さが一致しない"
        )
    path = meta_path_for(srt_path)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "full_text": full_text,
                "char_times": [[round(s, 4), round(e, 4)] for s, e in char_times],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return path


def load_srt_meta(srt_path: Path) -> tuple[str, list[tuple[float, float]]] | None:
    """SRT の meta を読み込み. 無ければ None."""
    path = meta_path_for(srt_path)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        full_text = str(data["full_text"])
        char_times = [(float(s), float(e)) for s, e in data["char_times"]]
        if len(full_text) != len(char_times):
            return None
        return full_text, char_times
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _map_edited_to_original_indices(
    edited_flat: str,
    original_flat: str,
) -> list[int] | None:
    """編集後 flat text の各文字が元 flat text のどの index にあるかを返す.

    ユーザーは文字を削除のみ可能（追加は許可しない）前提。
    mapping できなければ None.
    """
    indices: list[int] = []
    orig_pos = 0
    for ch in edited_flat:
        while orig_pos < len(original_flat) and original_flat[orig_pos] != ch:
            orig_pos += 1
        if orig_pos >= len(original_flat):
            return None
        indices.append(orig_pos)
        orig_pos += 1
    return indices


def reconstruct_entry_timing(
    edited_blocks: list[list[str]],
    full_text: str,
    char_times: list[tuple[float, float]],
) -> list[SRTEntry] | None:
    """編集後の entry を元 char_times にマッピングして正確な timing を復元.

    edited_blocks: [[line, ...], ...] (各 entry の行)
    full_text: 元の裸文字列 (SRT 全文、空白/改行除去済みでない)

    Returns:
        SRTEntry list (accurate timing) or None if reconstruction fails.
    """
    import re

    # 元の full_text を空白除去した flat text
    original_flat = re.sub(r"\s", "", full_text)
    if len(original_flat) != len(char_times):
        # full_text 自体が改行含むかもしれないので meta は flat で保存されてる前提
        # 不一致なら abort
        return None

    edited_flat = "".join(ln for block in edited_blocks for ln in block)
    edited_flat_clean = re.sub(r"\s", "", edited_flat)

    mapping = _map_edited_to_original_indices(edited_flat_clean, original_flat)
    if mapping is None:
        return None

    entries: list[SRTEntry] = []
    edit_cum = 0
    for i, block in enumerate(edited_blocks, 1):
        block_chars = sum(len(ln) for ln in block)
        if block_chars == 0:
            continue
        if edit_cum + block_chars > len(mapping):
            return None
        orig_start_idx = mapping[edit_cum]
        orig_end_idx = mapping[edit_cum + block_chars - 1]
        start = char_times[orig_start_idx][0]
        end = char_times[orig_end_idx][1]
        if end < start:
            end = start
        entries.append(
            SRTEntry(
                index=i,
                start_time=start,
                end_time=end,
                text="\n".join(block),
            )
        )
        edit_cum += block_chars
    return entries


def load_edit_log(base_dir: Path) -> list[dict[str, Any]]:
    """edit log を読み込み (存在しない場合は空 list)."""
    log_path = base_dir / EDIT_LOG_SUBDIR / EDIT_LOG_FILE
    if not log_path.exists():
        return []
    out: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
