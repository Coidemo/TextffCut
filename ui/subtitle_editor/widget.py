"""字幕エディタの補助ロジック (parse・validate・timing 再計算).

エディタは **タイミング調整のみ** (改行・entry 区切りの編集).
文字変更は禁止 — pipeline で使った 1 文字単位タイムスタンプ (char_times) と
マッピングできなくなるため。文字編集が必要な場合は pipeline 再生成で対処する.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass

from use_cases.ai.srt_edit_log import SRTEntry

MAX_CHARS = 13


@dataclass
class ValidationResult:
    ok: bool
    error_msg: str = ""


def parse_edited_text(text: str) -> list[list[str]]:
    """textarea 内容を [[line, ...], ...] にパース (NFC 正規化)."""
    normalized = unicodedata.normalize("NFC", text)
    blocks = re.split(r"\n\s*\n", normalized)
    result = []
    for b in blocks:
        lines = [ln.strip() for ln in b.strip().split("\n") if ln.strip()]
        if lines:
            result.append(lines)
    return result


def flatten_text(text: str) -> str:
    """全空白・改行を除いた裸の文字列 (NFC 正規化で Unicode 表現揺れを吸収)."""
    normalized = unicodedata.normalize("NFC", text)
    return re.sub(r"\s", "", normalized)


def entries_to_text(entries: list[SRTEntry]) -> str:
    """SRTEntry list → editor 用テキスト (空行で entry 区切り)."""
    return "\n\n".join(e.text for e in entries)


def validate_edit(
    original_text: str,
    edited_text: str,
) -> ValidationResult:
    """裸文字列が同一ならば OK (構造変更のみ許可).

    文字追加・削除・変更は禁止 — char_times とのマッピングが壊れるため。
    """
    if flatten_text(original_text) != flatten_text(edited_text):
        return ValidationResult(
            ok=False,
            error_msg="文字内容が変わっています。このエディタは **改行と空行の編集のみ** 可能です。"
                      "文字の追加・削除が必要な場合は pipeline を再実行してください。",
        )
    return ValidationResult(ok=True)


def assign_timing_from_structure(
    parsed_blocks: list[list[str]],
    original: list[SRTEntry],
) -> list[SRTEntry]:
    """TIMING モード用: 改行パターンが変わった新 blocks に timing を再配分.

    文字位置比で timing を線形マップ.
    """
    if not parsed_blocks or not original:
        return []
    orig_start = original[0].start_time
    orig_end = original[-1].end_time
    total_dur = orig_end - orig_start

    entries_chars = ["".join(lines) for lines in parsed_blocks]
    total_chars = sum(len(c) for c in entries_chars) or 1

    out: list[SRTEntry] = []
    cum = 0
    for i, (lines, chars) in enumerate(zip(parsed_blocks, entries_chars, strict=False), 1):
        s_ratio = cum / total_chars
        cum += len(chars)
        e_ratio = cum / total_chars
        out.append(
            SRTEntry(
                index=i,
                start_time=orig_start + total_dur * s_ratio,
                end_time=orig_start + total_dur * e_ratio,
                text="\n".join(lines),
            )
        )
    return out


def render_preview_html(entries: list[SRTEntry], max_chars: int = MAX_CHARS) -> str:
    """timeline 表示 HTML (読み取り専用)."""
    if not entries:
        return "<div style='color:#888;padding:8px;'>(空)</div>"

    orig_start = entries[0].start_time
    orig_end = entries[-1].end_time
    total_dur = max(orig_end - orig_start, 0.1)

    blocks_html = []
    for i, e in enumerate(entries, 1):
        is_over = any(len(ln) > max_chars for ln in e.lines)
        left = ((e.start_time - orig_start) / total_dur) * 100
        width = ((e.end_time - e.start_time) / total_dur) * 100
        bg = "#a06a28" if is_over else "#2a4d6e"
        color = "#fff" if is_over else "#aaf"
        title = f"#{i} [{e.end_time - e.start_time:.2f}s] " + " / ".join(e.lines)
        title_escaped = json.dumps(title, ensure_ascii=False)[1:-1]
        blocks_html.append(
            f'<div style="position:absolute;top:0;bottom:0;'
            f'left:{left:.2f}%;width:{width:.2f}%;'
            f'background:{bg};color:{color};border-right:1px solid #000;'
            f'font-size:10px;display:flex;align-items:center;justify-content:center;'
            f'overflow:hidden;" title="{title_escaped}">{i}</div>'
        )
    return f"""
    <div style="background:#1a1a1a;padding:6px;border-radius:4px;">
      <div style="position:relative;height:32px;background:#0d0d0d;border-radius:3px;overflow:hidden;">
        {"".join(blocks_html)}
      </div>
    </div>
    """
