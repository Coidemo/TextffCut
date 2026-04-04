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
    """time_ranges内のセグメントからSRTエントリを生成する。"""
    # time_ranges内のセグメントを収集
    raw_segments = []
    for seg in transcription.segments:
        for tr_start, tr_end in time_ranges:
            if seg.end > tr_start and seg.start < tr_end:
                raw_segments.append(seg)
                break

    if not raw_segments:
        return []

    # セグメントをグループ化（隣接するものをまとめて字幕ブロックにする）
    entries = []
    max_chars_total = max_chars_per_line * max_lines

    current_text = ""
    current_start = None
    current_end = None

    for seg in raw_segments:
        # フィラーのみのセグメントはスキップ
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue

        # テキストからフィラーを除去
        cleaned = _remove_fillers(seg.text)
        if not cleaned:
            continue

        tl_start = _to_timeline_time(seg.start, timeline_map)
        tl_end = _to_timeline_time(seg.end, timeline_map)
        if tl_start is None or tl_end is None:
            continue

        # 現在のブロックに追加できるか
        if current_start is not None:
            combined = current_text + cleaned
            if len(combined) <= max_chars_total and tl_start - current_end < 0.5:
                # 同じブロックに追加
                current_text = combined
                current_end = tl_end
                continue
            else:
                # 現在のブロックを確定
                entry = _finalize_entry(
                    len(entries) + 1, current_start, current_end,
                    current_text, max_chars_per_line, max_lines,
                )
                if entry:
                    entries.append(entry)

        # 新しいブロック開始
        current_text = cleaned
        current_start = tl_start
        current_end = tl_end

    # 最後のブロックを確定
    if current_start is not None:
        entry = _finalize_entry(
            len(entries) + 1, current_start, current_end,
            current_text, max_chars_per_line, max_lines,
        )
        if entry:
            entries.append(entry)

    return entries


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
