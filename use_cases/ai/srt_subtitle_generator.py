"""
SRT字幕自動生成

切り抜き候補のtime_rangesと文字起こし結果からSRTファイルを生成する。
- タイムラインtime（隙間詰め）へのタイムスタンプ変換
- フィラー省略
- 形態素解析ベースの自然な改行（JapaneseLineBreakRules）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult
from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, FILLER_WORDS

logger = logging.getLogger(__name__)

# SRT字幕のデフォルト設定
DEFAULT_MAX_CHARS_PER_LINE = 11
DEFAULT_MAX_LINES = 2
MIN_DISPLAY_DURATION = 0.5   # 最小表示時間（秒）
MAX_DISPLAY_DURATION = 7.0   # 最大表示時間（秒）


@dataclass
class SRTEntry:
    index: int
    start_time: float  # タイムライン時間（秒）
    end_time: float
    text: str


def generate_srt(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    output_path: Path,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> Path | None:
    """切り抜き候補のSRT字幕ファイルを生成する。

    Args:
        suggestion: 切り抜き候補（time_ranges確定済み）
        transcription: 文字起こし結果
        output_path: SRTファイル出力パス
        max_chars_per_line: 1行の最大文字数
        max_lines: 最大行数

    Returns:
        生成されたSRTファイルのパス。生成できなかった場合はNone。
    """
    if not suggestion.time_ranges:
        return None

    # 1. タイムライン時間のマッピングを構築
    timeline_map = _build_timeline_map(suggestion.time_ranges)

    # 2. time_ranges内のセグメントを抽出し、タイムライン時間に変換
    entries = _create_entries(
        suggestion.time_ranges, timeline_map, transcription,
        max_chars_per_line, max_lines,
    )

    if not entries:
        return None

    # 3. SRTファイル出力
    _write_srt(entries, output_path)

    logger.info(f"SRT生成: {len(entries)}エントリ → {output_path.name}")
    return output_path


def _build_timeline_map(
    time_ranges: list[tuple[float, float]],
) -> list[tuple[float, float, float]]:
    """元動画の時間 → タイムライン時間のマッピングを構築する。

    Returns:
        [(original_start, original_end, timeline_offset), ...]
        timeline_offset: このrangeがタイムライン上で始まる位置
    """
    mapping = []
    timeline_pos = 0.0
    for orig_start, orig_end in time_ranges:
        mapping.append((orig_start, orig_end, timeline_pos))
        timeline_pos += orig_end - orig_start
    return mapping


def _to_timeline_time(
    original_time: float,
    timeline_map: list[tuple[float, float, float]],
) -> float | None:
    """元動画の時間をタイムライン時間に変換する。"""
    for orig_start, orig_end, tl_offset in timeline_map:
        if orig_start - 0.1 <= original_time <= orig_end + 0.1:
            return tl_offset + (original_time - orig_start)
    return None


def _create_entries(
    time_ranges: list[tuple[float, float]],
    timeline_map: list[tuple[float, float, float]],
    transcription: TranscriptionResult,
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry]:
    """time_ranges内のセグメントからSRTエントリを生成する。

    セグメントを積極的にマージし、max_chars_totalに収まる意味の塊にする。
    2行目に短い接続詞だけ残る場合は省略する。
    """
    # time_ranges内のセグメントを収集
    raw_segments = []
    for seg in transcription.segments:
        for tr_start, tr_end in time_ranges:
            if seg.end > tr_start and seg.start < tr_end:
                raw_segments.append(seg)
                break

    if not raw_segments:
        return []

    # 全セグメントのテキストをフィラー除去してタイムライン時間付きで収集
    cleaned_parts: list[tuple[str, float, float]] = []  # (text, tl_start, tl_end)
    for seg in raw_segments:
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue
        cleaned = _remove_fillers(seg.text)
        if not cleaned:
            continue
        tl_start = _to_timeline_time(seg.start, timeline_map)
        tl_end = _to_timeline_time(seg.end, timeline_map)
        if tl_start is None or tl_end is None:
            continue
        cleaned_parts.append((cleaned, tl_start, tl_end))

    if not cleaned_parts:
        return []

    # 全テキストを結合 + 文字位置→時間マッピング
    full_text = ""
    char_times: list[float] = []  # 各文字の開始時間

    for text, tl_start, tl_end in cleaned_parts:
        char_dur = (tl_end - tl_start) / max(len(text), 1)
        for i in range(len(text)):
            char_times.append(tl_start + i * char_dur)
        full_text += text

    if not full_text:
        return []

    # AIに字幕分割を依頼
    blocks = _ai_split_subtitles(full_text, max_chars_per_line, max_lines)

    if not blocks:
        return []

    # 各ブロックのタイムスタンプを計算（全テキスト内での位置から逆算）
    entries = []
    search_pos = 0
    for block_text in blocks:
        # full_text内でのblock_textの位置を探す
        # （AIがフィラー省略等で元テキストと完全一致しない場合に備えてfuzzy検索）
        start_idx = _find_block_position(full_text, block_text, search_pos)
        if start_idx < 0:
            continue

        end_idx = start_idx + len(block_text) - 1
        if end_idx >= len(char_times):
            end_idx = len(char_times) - 1

        tl_start = char_times[start_idx]
        tl_end = char_times[end_idx] + (char_times[1] - char_times[0] if len(char_times) > 1 else 0.1)

        # 改行処理（AIが改行を入れていなければ自動改行）
        formatted = block_text
        if "\n" not in formatted and len(formatted) > max_chars_per_line:
            formatted = _format_text(formatted, max_chars_per_line, max_lines)

        entry = SRTEntry(
            index=len(entries) + 1,
            start_time=max(0, tl_start),
            end_time=tl_end,
            text=formatted,
        )
        entries.append(entry)
        search_pos = start_idx + 1

    return entries


def _ai_split_subtitles(
    full_text: str,
    max_chars_per_line: int,
    max_lines: int,
) -> list[str]:
    """AIにテキストを字幕ブロックに分割させる。"""
    import json
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        return _fallback_split(full_text, max_chars_per_line * max_lines)

    max_chars_total = max_chars_per_line * max_lines

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        prompt = f"""以下のテキストをショート動画の字幕用に分割してください。

ルール:
- 1ブロックは最大{max_chars_total}文字（{max_chars_per_line}文字×{max_lines}行）
- 意味のまとまりで区切る（文の途中で切らない）
- フィラー（「あの」「まあ」「えー」「なんか」等）は省略してよい
- 「ので」「けど」「から」等の接続詞だけで1ブロックにしない
- 省略しても意味が通じる口語表現は簡潔にしてよい
- 句読点は使わない
- 改行が必要な場合は\\nで入れる（{max_chars_per_line}文字を超える場合）
- 改行位置は助詞の後や文節の切れ目など自然な位置で

テキスト:
{full_text}

JSON: {{"blocks": ["ブロック1", "ブロック2", ...]}}"""

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "ショート動画の字幕分割担当。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=2000,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        blocks = result.get("blocks", [])
        if blocks:
            logger.info(f"AI字幕分割: {len(blocks)}ブロック")
            return blocks
    except Exception as e:
        logger.warning(f"AI字幕分割失敗: {e}")

    return _fallback_split(full_text, max_chars_total)


def _fallback_split(text: str, max_chars: int) -> list[str]:
    """AIが使えない場合のフォールバック分割。"""
    blocks = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            blocks.append(remaining)
            break
        blocks.append(remaining[:max_chars])
        remaining = remaining[max_chars:]
    return blocks


def _find_block_position(full_text: str, block_text: str, search_from: int) -> int:
    """full_text内でblock_textの開始位置を探す。

    AIがフィラー省略等でテキストを変更している場合、
    ブロックの最初の数文字で部分一致検索する。
    """
    # 改行を除去して検索
    clean_block = block_text.replace("\n", "")

    # 完全一致
    pos = full_text.find(clean_block, search_from)
    if pos >= 0:
        return pos

    # 先頭5文字で部分一致
    prefix = clean_block[:5]
    if prefix:
        pos = full_text.find(prefix, search_from)
        if pos >= 0:
            return pos

    # 先頭3文字で部分一致
    prefix = clean_block[:3]
    if prefix:
        pos = full_text.find(prefix, search_from)
        if pos >= 0:
            return pos

    return -1


# 2行目に残ると不格好な末尾パターン
TRAILING_CONNECTORS = [
    "ので", "けど", "から", "のは", "のが", "って",
    "けれども", "ですが", "ですけど", "んですけど",
]


LEADING_FRAGMENTS = [
    "のは", "のが", "って", "ですよ", "よね", "ですけど",
    "んですけど", "んですが", "はいいんですけど",
]


def _trim_leading_fragments(text: str) -> str:
    """先頭の接続詞残骸を除去する（前のブロックの続きが残った場合）。"""
    for frag in sorted(LEADING_FRAGMENTS, key=len, reverse=True):
        if text.startswith(frag) and len(text) > len(frag) + 3:
            return text[len(frag):]
    return text


def _trim_trailing_connectors(text: str) -> str:
    """末尾の接続詞を省略する（省略しても意味が通じる場合）。"""
    for conn in sorted(TRAILING_CONNECTORS, key=len, reverse=True):
        if text.endswith(conn) and len(text) > len(conn) + 3:
            return text[: -len(conn)]
    return text


def _remove_fillers(text: str) -> str:
    """テキストからフィラー語彙を除去する。"""
    result = text
    for filler in sorted(FILLER_WORDS, key=len, reverse=True):
        result = result.replace(filler, "")
    # 連続するスペースを1つに
    result = re.sub(r"\s+", "", result)
    return result.strip()


def _finalize_entry(
    index: int,
    start: float,
    end: float,
    text: str,
    max_chars_per_line: int,
    max_lines: int,
) -> SRTEntry | None:
    """テキストを改行処理してSRTEntryを作成する。"""
    if not text or end - start < 0.1:
        return None

    # 表示時間の調整
    duration = end - start
    if duration < MIN_DISPLAY_DURATION:
        end = start + MIN_DISPLAY_DURATION
    elif duration > MAX_DISPLAY_DURATION:
        end = start + MAX_DISPLAY_DURATION

    # 自然な改行処理
    formatted = _format_text(text, max_chars_per_line, max_lines)
    if not formatted:
        return None

    return SRTEntry(index=index, start_time=start, end_time=end, text=formatted)


def _format_text(
    text: str,
    max_chars_per_line: int,
    max_lines: int,
) -> str:
    """テキストを自然な位置で改行してフォーマットする。"""
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
                remaining = ""
                break
            line, remaining = JapaneseLineBreakRules.extract_line(
                remaining, max_chars_per_line
            )
            lines.append(line)

        # max_lines超過分は切り捨て
        return "\n".join(lines)

    except ImportError:
        # janomeがない場合のフォールバック: 単純な文字数分割
        lines = []
        remaining = text
        for _ in range(max_lines):
            if not remaining:
                break
            lines.append(remaining[:max_chars_per_line])
            remaining = remaining[max_chars_per_line:]
        return "\n".join(lines)


def _write_srt(entries: list[SRTEntry], output_path: Path) -> None:
    """SRTファイルを出力する（CRLF改行、UTF-8 BOM付き）。"""
    lines = []
    for entry in entries:
        lines.append(str(entry.index))
        lines.append(
            f"{_format_srt_time(entry.start_time)} --> "
            f"{_format_srt_time(entry.end_time)}"
        )
        lines.append(entry.text)
        lines.append("")  # 空行

    content = "\r\n".join(lines)
    # UTF-8 BOM付き（DaVinci Resolve対応）
    output_path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))


def _format_srt_time(seconds: float) -> str:
    """秒数をSRTのタイムスタンプ形式に変換する。"""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
