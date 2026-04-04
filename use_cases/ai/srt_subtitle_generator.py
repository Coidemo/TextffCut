"""
SRT字幕自動生成

方式:
1. 全テキスト結合 + 文字→タイムライン時間マッピング
2. スライディングウィンドウ探索: 先頭40文字の全単語境界から最良22文字ブロックを確定
   → 確定末尾から次の40文字で同様に → 繰り返し
3. 各ブロックを11文字×2行以内でフォーマット
4. SRT出力

テキストの改変は行わない。フィラーはセグメント単位でのみスキップ。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS_PER_LINE = 11
DEFAULT_MAX_LINES = 2
SEARCH_WINDOW = 40  # 探索窓の文字数


@dataclass
class SRTEntry:
    index: int
    start_time: float
    end_time: float
    text: str


def generate_srt(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    output_path: Path,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> Path | None:
    if not suggestion.time_ranges:
        return None

    timeline_map = _build_timeline_map(suggestion.time_ranges)
    parts = _collect_parts(suggestion.time_ranges, timeline_map, transcription)
    if not parts:
        return None

    full_text, char_times, seg_boundaries = _build_char_time_map(parts)
    if not full_text:
        return None

    max_block = max_chars_per_line * max_lines

    # スライディングウィンドウ探索（セグメント境界を優先候補にする）
    entries = _sliding_window_split(
        full_text, char_times, max_block, max_chars_per_line, max_lines,
        seg_boundaries,
    )

    if not entries:
        return None

    _write_srt(entries, output_path)
    logger.info(f"SRT生成: {len(entries)}エントリ → {output_path.name}")
    return output_path


def _sliding_window_split(
    full_text: str,
    char_times: list[tuple[float, float]],
    max_block: int,
    max_chars_per_line: int,
    max_lines: int,
    seg_boundaries: set[int] | None = None,
) -> list[SRTEntry]:
    """スライディングウィンドウで全テキストを最適ブロックに分割する。

    pos=0から:
      1. pos〜pos+SEARCH_WINDOW の範囲で全単語境界を取得
      2. 各境界を「ここでブロックを切る」候補として品詞スコアで評価
      3. 最良の切断点を選んでブロック確定
      4. posを切断点に進めて繰り返し
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        has_janome = True
    except ImportError:
        has_janome = False

    entries = []
    pos = 0
    n = len(full_text)

    while pos < n:
        remaining = n - pos

        # 残りがmax_block以下ならそのまま最後のブロック
        if remaining <= max_block:
            entries.append(_make_entry(
                len(entries) + 1, pos, n,
                full_text, char_times, max_chars_per_line, max_lines,
            ))
            break

        # 探索窓
        window_end = min(pos + SEARCH_WINDOW, n)
        window_text = full_text[pos:window_end]

        if has_janome:
            # 窓内の全単語境界+品詞情報を取得
            bp = JapaneseLineBreakRules.get_word_boundaries_with_pos(window_text)
            boundaries = [b for b, _, _ in bp]
        else:
            boundaries = list(range(1, len(window_text)))
            bp = []

        # max_block以下の切断点候補を評価
        best_cut = None
        best_score = -999

        for b in boundaries:
            if b < 3:  # 短すぎるブロックは除外
                continue
            if b > max_block:
                break

            score = 0.0

            # セグメント境界ボーナス（話者の自然な間で切るのが最も良い）
            abs_pos = pos + b
            if seg_boundaries and abs_pos in seg_boundaries:
                score += 30

            # 品詞スコア（助詞の後で切るのが良い）
            if bp:
                score += JapaneseLineBreakRules.evaluate_break_position(bp, b) * 10

            # 適度な長さのボーナス（短い方が読みやすい）
            if max_chars_per_line <= b <= max_block:
                score += 5  # 1-2行の理想的な長さ
            elif 6 <= b < max_chars_per_line:
                score += 2  # 1行に収まる短めのブロック

            # 短すぎペナルティ
            if b <= 3:
                score -= 30
            elif b <= 5:
                score -= 10

            if score > best_score:
                best_score = score
                best_cut = b

        if best_cut is None:
            # フォールバック: max_blockで切る
            best_cut = min(max_block, remaining)

        # ブロック確定
        abs_cut = pos + best_cut
        entries.append(_make_entry(
            len(entries) + 1, pos, abs_cut,
            full_text, char_times, max_chars_per_line, max_lines,
        ))
        pos = abs_cut

    return entries


def _make_entry(index, start_pos, end_pos, full_text, char_times, max_chars_per_line, max_lines):
    text = full_text[start_pos:end_pos]
    if not text.strip():
        return None

    tl_start = char_times[start_pos][0] if start_pos < len(char_times) else 0
    tl_end = char_times[min(end_pos - 1, len(char_times) - 1)][1] if end_pos > 0 else 0

    formatted = _format_text(text, max_chars_per_line, max_lines)
    return SRTEntry(index=index, start_time=tl_start, end_time=tl_end, text=formatted)


# --- タイムライン ---

def _build_timeline_map(time_ranges):
    m = []
    tl = 0.0
    for s, e in time_ranges:
        m.append((s, e, tl))
        tl += e - s
    return m


def _to_tl(orig, tmap):
    for os_, oe, tl in tmap:
        if os_ - 0.1 <= orig <= oe + 0.1:
            return tl + (orig - os_)
    return None


def _collect_parts(time_ranges, tmap, transcription):
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS
    parts = []
    for seg in transcription.segments:
        for tr_s, tr_e in time_ranges:
            if seg.end > tr_s and seg.start < tr_e:
                if seg.text.strip() not in FILLER_ONLY_TEXTS:
                    tl_s = _to_tl(seg.start, tmap)
                    tl_e = _to_tl(seg.end, tmap)
                    if tl_s is not None and tl_e is not None:
                        parts.append((seg.text, tl_s, tl_e))
                break
    return parts


def _build_char_time_map(parts):
    full = ""
    ctimes = []
    seg_boundaries = set()  # セグメント境界の文字位置
    for text, tl_s, tl_e in parts:
        seg_boundaries.add(len(full))  # セグメント開始位置
        dur = tl_e - tl_s
        n = max(len(text), 1)
        for i in range(len(text)):
            ctimes.append((tl_s + dur * i / n, tl_s + dur * (i + 1) / n))
        full += text
    seg_boundaries.add(len(full))  # 最後
    seg_boundaries.discard(0)  # 0は除外
    return full, ctimes, seg_boundaries


# --- テキストフォーマット ---

def _format_text(text, max_chars_per_line, max_lines):
    if len(text) <= max_chars_per_line:
        return text
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        lines = []
        remaining = text
        for _ in range(max_lines):
            if not remaining:
                break
            if len(remaining) <= max_chars_per_line:
                lines.append(remaining)
                break
            line, remaining = JapaneseLineBreakRules.extract_line(remaining, max_chars_per_line)
            lines.append(line)
        return "\n".join(lines)
    except ImportError:
        return text[:max_chars_per_line] + "\n" + text[max_chars_per_line:max_chars_per_line * 2]


# --- SRT出力 ---

def _write_srt(entries, output_path):
    items = [e for e in entries if e]
    lines = []
    for e in items:
        lines.append(str(e.index))
        lines.append(f"{_fmt(e.start_time)} --> {_fmt(e.end_time)}")
        lines.append(e.text)
        lines.append("")
    output_path.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8"))


def _fmt(s):
    if s < 0: s = 0
    return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d},{int(s%1*1000):03d}"
