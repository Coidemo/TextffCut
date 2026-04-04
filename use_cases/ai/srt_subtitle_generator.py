"""
SRT字幕自動生成

方式:
1. セグメントのテキスト+時間を収集（フィラーセグメントのみ除外）
2. マージ/分割の組み合わせで大量パターン生成
3. 機械スコアで上位5件に絞り込み
4. AIに最良パターンを選ばせる
5. SRT出力

テキストの改変は行わない（元テキストそのまま）。
フィラーは「セグメント全体がフィラー」の場合のみスキップ。
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
TOP_N_FOR_AI = 5


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

    # 力任せ: 大量パターン生成 → スコアリング → AI選定
    best = _brute_force_layout(parts, max_chars_per_line, max_lines)
    if not best:
        return None

    _write_srt(best, output_path)
    logger.info(f"SRT生成: {len(best)}エントリ → {output_path.name}")
    return output_path


# --- タイムライン変換 ---

def _build_timeline_map(time_ranges):
    mapping = []
    tl_pos = 0.0
    for orig_start, orig_end in time_ranges:
        mapping.append((orig_start, orig_end, tl_pos))
        tl_pos += orig_end - orig_start
    return mapping


def _to_timeline_time(original_time, timeline_map):
    for orig_start, orig_end, tl_offset in timeline_map:
        if orig_start - 0.1 <= original_time <= orig_end + 0.1:
            return tl_offset + (original_time - orig_start)
    return None


def _collect_parts(time_ranges, timeline_map, transcription):
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS
    parts = []
    for seg in transcription.segments:
        for tr_start, tr_end in time_ranges:
            if seg.end > tr_start and seg.start < tr_end:
                if seg.text.strip() in FILLER_ONLY_TEXTS:
                    break
                tl_start = _to_timeline_time(seg.start, timeline_map)
                tl_end = _to_timeline_time(seg.end, timeline_map)
                if tl_start is not None and tl_end is not None:
                    parts.append((seg.text, tl_start, tl_end))
                break
    return parts


# --- 力任せレイアウト ---

def _brute_force_layout(parts, max_chars_per_line, max_lines):
    max_chars = max_chars_per_line * max_lines
    patterns = []

    # 戦略1: 貪欲マージ（max_charsに収まるだけ結合）
    patterns.append(_greedy_merge(parts, max_chars, max_chars_per_line, max_lines))

    # 戦略2: 1セグメント=1ブロック（長いセグメントは複数ブロックに分割）
    patterns.append(_split_long_segments(parts, max_chars, max_chars_per_line, max_lines))

    # 戦略3: 1行分だけマージ（max_chars_per_lineに収まるだけ結合）
    patterns.append(_greedy_merge(parts, max_chars_per_line, max_chars_per_line, max_lines))

    # 戦略4: 固定サイズマージ（2,3個ずつ）+ 長いものは分割
    for size in [2, 3]:
        patterns.append(_fixed_merge_with_split(parts, size, max_chars, max_chars_per_line, max_lines))

    # 戦略5: オフセット版（1つずらして開始）
    for size in [2, 3]:
        if len(parts) > 1:
            first = _split_long_segments(parts[:1], max_chars, max_chars_per_line, max_lines)
            rest = _fixed_merge_with_split(parts[1:], size, max_chars, max_chars_per_line, max_lines)
            combined = first + rest
            _reindex(combined)
            patterns.append(combined)

    # 戦略6: 目標文字数バリエーション
    for target in [max_chars_per_line, int(max_chars * 0.7), max_chars]:
        patterns.append(_greedy_merge(parts, target, max_chars_per_line, max_lines))

    # 空とNone除去 + 重複除去
    valid = [p for p in patterns if p]
    seen = set()
    unique = []
    for p in valid:
        key = tuple((e.start_time, e.text) for e in p)
        if key not in seen:
            seen.add(key)
            unique.append(p)

    if not unique:
        return None

    # スコアリング
    scored = [(p, _score(p, max_chars_per_line, max_lines)) for p in unique]
    scored.sort(key=lambda x: -x[1])

    # 上位をAIに選ばせる
    top = scored[:TOP_N_FOR_AI]
    if len(top) > 1:
        best_idx = _ai_select(top)
        if best_idx is not None:
            return top[best_idx][0]

    return top[0][0]


def _greedy_merge(parts, max_chars, max_chars_per_line, max_lines):
    entries = []
    buf = ""
    buf_start = buf_end = None

    for text, tl_start, tl_end in parts:
        if not text:
            continue
        combined = buf + text
        if buf_start is not None and len(combined) <= max_chars:
            buf = combined
            buf_end = tl_end
        else:
            if buf:
                entries.extend(_text_to_entries(len(entries), buf, buf_start, buf_end, max_chars_per_line, max_lines))
            buf = text
            buf_start = tl_start
            buf_end = tl_end

    if buf:
        entries.extend(_text_to_entries(len(entries), buf, buf_start, buf_end, max_chars_per_line, max_lines))
    _reindex(entries)
    return entries


def _split_long_segments(parts, max_chars, max_chars_per_line, max_lines):
    entries = []
    for text, tl_start, tl_end in parts:
        if not text:
            continue
        entries.extend(_text_to_entries(len(entries), text, tl_start, tl_end, max_chars_per_line, max_lines))
    _reindex(entries)
    return entries


def _fixed_merge_with_split(parts, group_size, max_chars, max_chars_per_line, max_lines):
    entries = []
    for i in range(0, len(parts), group_size):
        group = parts[i:i + group_size]
        text = "".join(t for t, _, _ in group if t)
        if not text:
            continue
        tl_start = group[0][1]
        tl_end = group[-1][2]
        entries.extend(_text_to_entries(len(entries), text, tl_start, tl_end, max_chars_per_line, max_lines))
    _reindex(entries)
    return entries


def _text_to_entries(base_index, text, tl_start, tl_end, max_chars_per_line, max_lines):
    """テキストを1つ以上のSRTEntryに変換する。

    max_chars_per_line * max_linesに収まればそのまま1エントリ。
    収まらなければ自然な位置で分割して複数エントリにする。
    """
    max_chars = max_chars_per_line * max_lines
    if len(text) <= max_chars:
        formatted = _format_text(text, max_chars_per_line, max_lines)
        return [SRTEntry(index=0, start_time=tl_start, end_time=tl_end, text=formatted)]

    # 長いテキストを分割
    chunks = _split_text_naturally(text, max_chars)
    if not chunks:
        return []

    # 時間を按分
    total_chars = sum(len(c) for c in chunks)
    duration = tl_end - tl_start
    entries = []
    pos = tl_start
    for chunk in chunks:
        chunk_dur = duration * (len(chunk) / total_chars) if total_chars > 0 else 0
        formatted = _format_text(chunk, max_chars_per_line, max_lines)
        entries.append(SRTEntry(index=0, start_time=pos, end_time=pos + chunk_dur, text=formatted))
        pos += chunk_dur

    return entries


def _split_text_naturally(text, max_chars):
    """テキストを自然な位置で分割する。"""
    if len(text) <= max_chars:
        return [text]

    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= max_chars:
                chunks.append(remaining)
                break
            line, remaining = JapaneseLineBreakRules.extract_line(remaining, max_chars)
            chunks.append(line)
        return chunks
    except ImportError:
        chunks = []
        while text:
            chunks.append(text[:max_chars])
            text = text[max_chars:]
        return chunks


def _reindex(entries):
    for i, e in enumerate(entries):
        e.index = i + 1


# --- スコアリング ---

def _score(entries, max_chars_per_line, max_lines):
    if not entries:
        return 0
    score = 50.0

    for entry in entries:
        lines = entry.text.split("\n")
        for line in lines:
            if len(line) <= max_chars_per_line:
                score += 2
            else:
                score -= 5 * (len(line) - max_chars_per_line)

        if len(lines) <= max_lines:
            score += 1
        else:
            score -= 10

        # 短すぎるエントリのペナルティ（強め）
        text_len = len(entry.text.replace("\n", ""))
        if text_len <= 3:
            score -= 20
        elif text_len <= 5:
            score -= 10
        elif text_len <= 7:
            score -= 3

    # 隙間チェック
    for i in range(len(entries) - 1):
        gap = entries[i + 1].start_time - entries[i].end_time
        if gap < 0.05:
            score += 2
        elif gap < 0.3:
            score += 1
        else:
            score -= 3

    return max(0, min(100, score))


# --- AI選定 ---

def _ai_select(scored_patterns):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        return 0

    options = []
    for i, (entries, sc) in enumerate(scored_patterns):
        preview = " / ".join(e.text.replace("\n", "｜") for e in entries[:6])
        options.append(f"パターン{i+1}（{len(entries)}ブロック）: {preview}")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "ショート動画の字幕レイアウト選定担当。JSON形式で回答。"},
                {"role": "user", "content": f"""以下の字幕パターンから最も読みやすいものを選んでください。

選定基準:
- 意味の塊で区切られている
- 1行が短すぎず長すぎない
- 途中で意味が切れていない
- 接続詞だけの行がない

{chr(10).join(options)}

JSON: {{"selected": パターン番号(1始まり)}}"""},
            ],
            temperature=0.2,
            max_tokens=100,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        idx = result.get("selected", 1) - 1
        return max(0, min(idx, len(scored_patterns) - 1))
    except Exception as e:
        logger.debug(f"AI字幕選定失敗: {e}")
        return 0


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
        lines = []
        remaining = text
        for _ in range(max_lines):
            if not remaining:
                break
            lines.append(remaining[:max_chars_per_line])
            remaining = remaining[max_chars_per_line:]
        return "\n".join(lines)


# --- SRT出力 ---

def _write_srt(entries, output_path):
    lines = []
    for entry in entries:
        lines.append(str(entry.index))
        lines.append(f"{_fmt(entry.start_time)} --> {_fmt(entry.end_time)}")
        lines.append(entry.text)
        lines.append("")
    content = "\r\n".join(lines)
    output_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))


def _fmt(seconds):
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
