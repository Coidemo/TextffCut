"""
SRT字幕自動生成

切り抜き候補のtime_rangesと文字起こし結果からSRTファイルを生成する。

方式:
1. AIにフィラー省略+テキスト整形を依頼（1回だけ）
2. 整形済みテキストをセグメント単位の組み合わせで大量パターン生成
3. 機械スコアで最良パターンを選出
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS_PER_LINE = 11
DEFAULT_MAX_LINES = 2


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

    # セグメントを収集してタイムライン時間に変換
    parts = _collect_parts(suggestion.time_ranges, timeline_map, transcription)
    if not parts:
        return None

    # AIにフィラー省略+テキスト整形を依頼
    cleaned_texts = _ai_clean_texts([p[0] for p in parts])

    # 整形済みテキストでpartsを更新
    cleaned_parts = []
    for i, (_, tl_start, tl_end) in enumerate(parts):
        if i < len(cleaned_texts) and cleaned_texts[i]:
            cleaned_parts.append((cleaned_texts[i], tl_start, tl_end))

    if not cleaned_parts:
        cleaned_parts = parts

    # 力任せ: マージパターンを大量生成→スコアリング
    best = _brute_force_subtitle_layout(
        cleaned_parts, max_chars_per_line, max_lines
    )

    if not best:
        return None

    _write_srt(best, output_path)
    logger.info(f"SRT生成: {len(best)}エントリ → {output_path.name}")
    return output_path


# --- タイムライン変換 ---

def _build_timeline_map(
    time_ranges: list[tuple[float, float]],
) -> list[tuple[float, float, float]]:
    mapping = []
    tl_pos = 0.0
    for orig_start, orig_end in time_ranges:
        mapping.append((orig_start, orig_end, tl_pos))
        tl_pos += orig_end - orig_start
    return mapping


def _to_timeline_time(
    original_time: float,
    timeline_map: list[tuple[float, float, float]],
) -> float | None:
    for orig_start, orig_end, tl_offset in timeline_map:
        if orig_start - 0.1 <= original_time <= orig_end + 0.1:
            return tl_offset + (original_time - orig_start)
    return None


def _collect_parts(
    time_ranges, timeline_map, transcription,
) -> list[tuple[str, float, float]]:
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


# --- AI テキスト整形 ---

def _ai_clean_texts(texts: list[str]) -> list[str]:
    """AIにフィラー省略とテキスト整形を依頼する。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        return texts

    joined = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts))

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "字幕テキスト整形担当。JSON形式で回答。"},
                {"role": "user", "content": f"""以下は動画の文字起こしセグメントです。
字幕用にテキストを整形してください。

ルール:
- フィラー（あの、まあ、えー、なんか等）を省略
- 意味が変わらない範囲で口語を簡潔に
- 句読点は使わない
- 各セグメントは独立して整形（結合しない）
- 空になるセグメントは空文字で

セグメント:
{joined}

JSON: {{"texts": ["整形後テキスト0", "整形後テキスト1", ...]}}"""},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        cleaned = result.get("texts", [])
        if len(cleaned) == len(texts):
            logger.info(f"AIテキスト整形: {len(cleaned)}セグメント")
            return cleaned
    except Exception as e:
        logger.warning(f"AIテキスト整形失敗: {e}")

    return texts


# --- 力任せ字幕レイアウト ---

@dataclass
class SubtitlePattern:
    entries: list[SRTEntry]
    score: float


def _brute_force_subtitle_layout(
    parts: list[tuple[str, float, float]],
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry] | None:
    """セグメントのマージパターンを大量生成してスコアリングする。"""
    max_chars_total = max_chars_per_line * max_lines

    # 基本パターン: 隣接セグメントを順番にマージ
    # 何個ずつマージするかのバリエーションを試す
    patterns = []

    # 戦略1: 貪欲マージ（max_chars_totalに収まるだけマージ）
    entries = _greedy_merge(parts, max_chars_total, max_chars_per_line, max_lines)
    if entries:
        patterns.append(entries)

    # 戦略2: 1セグメント=1ブロック（マージなし）
    entries = _no_merge(parts, max_chars_per_line, max_lines)
    if entries:
        patterns.append(entries)

    # 戦略3: 2セグメントずつマージ
    entries = _fixed_merge(parts, 2, max_chars_total, max_chars_per_line, max_lines)
    if entries:
        patterns.append(entries)

    # 戦略4: 3セグメントずつマージ
    entries = _fixed_merge(parts, 3, max_chars_total, max_chars_per_line, max_lines)
    if entries:
        patterns.append(entries)

    if not patterns:
        return None

    # スコアリング
    scored = [(p, _score_pattern(p, max_chars_per_line, max_lines)) for p in patterns]
    scored.sort(key=lambda x: -x[1])

    return scored[0][0]


def _greedy_merge(parts, max_chars_total, max_chars_per_line, max_lines):
    entries = []
    buf_text = ""
    buf_start = None
    buf_end = None

    for text, tl_start, tl_end in parts:
        if not text:
            continue
        combined = buf_text + text
        if buf_start is not None and len(combined) <= max_chars_total:
            buf_text = combined
            buf_end = tl_end
        else:
            if buf_text:
                entries.append(_make_entry(
                    len(entries) + 1, buf_start, buf_end,
                    buf_text, max_chars_per_line, max_lines,
                ))
            buf_text = text
            buf_start = tl_start
            buf_end = tl_end

    if buf_text:
        entries.append(_make_entry(
            len(entries) + 1, buf_start, buf_end,
            buf_text, max_chars_per_line, max_lines,
        ))
    return [e for e in entries if e]


def _no_merge(parts, max_chars_per_line, max_lines):
    entries = []
    for text, tl_start, tl_end in parts:
        if not text:
            continue
        e = _make_entry(len(entries) + 1, tl_start, tl_end, text, max_chars_per_line, max_lines)
        if e:
            entries.append(e)
    return entries


def _fixed_merge(parts, group_size, max_chars_total, max_chars_per_line, max_lines):
    entries = []
    for i in range(0, len(parts), group_size):
        group = parts[i:i + group_size]
        text = "".join(t for t, _, _ in group if t)
        if not text:
            continue
        tl_start = group[0][1]
        tl_end = group[-1][2]
        # max_chars_totalを超える場合は切り詰め
        if len(text) > max_chars_total:
            text = text[:max_chars_total]
        e = _make_entry(len(entries) + 1, tl_start, tl_end, text, max_chars_per_line, max_lines)
        if e:
            entries.append(e)
    return entries


def _make_entry(index, start, end, text, max_chars_per_line, max_lines):
    if not text or end - start < 0.05:
        return None

    # 改行処理
    formatted = _format_text(text, max_chars_per_line, max_lines)
    if not formatted:
        return None

    return SRTEntry(index=index, start_time=start, end_time=end, text=formatted)


def _score_pattern(entries: list[SRTEntry], max_chars_per_line: int, max_lines: int) -> float:
    """字幕パターンの品質スコア（0-100）。"""
    if not entries:
        return 0

    score = 50.0

    for entry in entries:
        lines = entry.text.split("\n")

        # 1行あたりの文字数チェック
        for line in lines:
            if len(line) <= max_chars_per_line:
                score += 2  # 制限内
            else:
                score -= 5 * (len(line) - max_chars_per_line)  # 超過ペナルティ

        # 行数チェック
        if len(lines) <= max_lines:
            score += 1
        else:
            score -= 10

    # 隙間チェック（隣接エントリ間のギャップ）
    for i in range(len(entries) - 1):
        gap = entries[i + 1].start_time - entries[i].end_time
        if gap < 0.05:
            score += 2  # 隙間なし
        elif gap < 0.3:
            score += 1
        else:
            score -= 3  # 隙間あり

    # 短すぎるエントリのペナルティ
    for entry in entries:
        text_len = len(entry.text.replace("\n", ""))
        if text_len < 3:
            score -= 5

    return max(0, min(100, score))


# --- テキストフォーマット ---

def _format_text(text: str, max_chars_per_line: int, max_lines: int) -> str:
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

def _write_srt(entries: list[SRTEntry], output_path: Path) -> None:
    lines = []
    for entry in entries:
        lines.append(str(entry.index))
        lines.append(f"{_fmt(entry.start_time)} --> {_fmt(entry.end_time)}")
        lines.append(entry.text)
        lines.append("")
    content = "\r\n".join(lines)
    output_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))


def _fmt(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
