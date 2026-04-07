"""
SRT字幕自動生成

Phase 1: 全テキストをDP探索で最小ブロックに分割（全単語境界）
Phase 2: 隣接ブロックをDPで結合して11文字以下の1行にまとめる
Phase 3: 隣接する1行を2行ブロックにまとめるかAIに判断させる
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


@dataclass
class TextBlock:
    text: str
    start_pos: int
    end_pos: int


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
    video_path: Path | None = None,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> Path | None:
    if not suggestion.time_ranges:
        return None

    # 切り抜き後の音声を結合して再文字起こし→正確なタイムスタンプを取得
    if video_path:
        segments = _transcribe_output_audio(suggestion.time_ranges, video_path)
        if segments:
            return _generate_from_segments(
                segments, output_path, max_chars_per_line, max_lines
            )

    # フォールバック: 元の文字起こしを使用
    tmap = _build_timeline_map(suggestion.time_ranges)
    parts = _collect_parts(suggestion.time_ranges, tmap, transcription)
    if not parts:
        return None

    full_text, char_times, seg_bounds = _build_char_time_map(parts)
    if not full_text:
        return None

    return _generate_from_char_times(
        full_text, char_times, seg_bounds, output_path,
        max_chars_per_line, max_lines,
    )


def _transcribe_output_audio(
    time_ranges: list[tuple[float, float]],
    video_path: Path,
) -> list[dict] | None:
    """切り抜き後の音声を結合し、Whisper APIで文字起こしする。

    Returns:
        [{"text": str, "start": float, "end": float}, ...] セグメントリスト
        タイムスタンプは結合後の音声の時間（0始まり）
    """
    import subprocess
    import tempfile

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 各rangeの音声を抽出
            parts = []
            for i, (start, end) in enumerate(time_ranges):
                p = f"{tmpdir}/p{i}.wav"
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
                     "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1", p],
                    capture_output=True, timeout=15,
                )
                parts.append(p)

            # 結合
            with open(f"{tmpdir}/list.txt", "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", f"{tmpdir}/list.txt", "-c", "copy", f"{tmpdir}/out.wav"],
                capture_output=True, timeout=15,
            )

            # Whisper APIでsegment-levelタイムスタンプ付き文字起こし
            with open(f"{tmpdir}/out.wav", "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="ja",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            segments = []
            for seg in resp.segments:
                segments.append({
                    "text": seg.text.strip() if hasattr(seg, "text") else seg.get("text", "").strip(),
                    "start": seg.start if hasattr(seg, "start") else seg.get("start", 0),
                    "end": seg.end if hasattr(seg, "end") else seg.get("end", 0),
                })

            logger.info(f"出力音声文字起こし: {len(segments)}セグメント")
            return segments

    except Exception as e:
        logger.warning(f"出力音声文字起こし失敗: {e}")
        return None


def _generate_from_segments(
    segments: list[dict],
    output_path: Path,
    max_chars_per_line: int,
    max_lines: int,
) -> Path | None:
    """Whisperセグメントから字幕を生成する。"""
    if not segments:
        return None

    # 全テキスト結合 + セグメントベースのchar_times
    full_text = ""
    char_times = []
    seg_bounds = set()

    for seg in segments:
        text = seg["text"]
        if not text:
            continue
        seg_bounds.add(len(full_text))
        start = seg["start"]
        end = seg["end"]
        dur = end - start
        n = max(len(text), 1)
        for i in range(len(text)):
            char_times.append((start + dur * i / n, start + dur * (i + 1) / n))
        full_text += text

    seg_bounds.add(len(full_text))
    seg_bounds.discard(0)

    if not full_text:
        return None

    return _generate_from_char_times(
        full_text, char_times, seg_bounds, output_path,
        max_chars_per_line, max_lines,
    )


def _generate_from_char_times(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
    output_path: Path,
    max_chars_per_line: int,
    max_lines: int,
) -> Path | None:
    """char_timesベースで字幕を生成する（共通処理）。"""
    micro_blocks = _phase1_split(full_text, seg_bounds)
    lines = _phase2_merge_to_lines(micro_blocks, max_chars_per_line, seg_bounds)
    entries = _phase3_dp_group(lines, char_times, max_chars_per_line)

    if not entries:
        return None

    # 隣接エントリ間の隙間を埋める
    for i in range(len(entries) - 1):
        if entries[i + 1].start_time > entries[i].end_time:
            entries[i].end_time = entries[i + 1].start_time

    for i, e in enumerate(entries, 1):
        e.index = i

    _write_srt(entries, output_path)
    logger.info(f"SRT生成: {len(entries)}エントリ → {output_path.name}")
    return output_path


# =============================================
# Phase 1: 全テキストをDP探索で最小ブロックに分割
# =============================================

def _tokenize(text: str) -> list[tuple[int, str, str]]:
    """janomeで形態素解析。

    Returns:
        [(boundary_pos, surface, pos_tag), ...]
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        return JapaneseLineBreakRules.get_word_boundaries_with_pos(text)
    except ImportError:
        pass

    # フォールバック: 1文字ずつ
    return [(i + 1, text[i], "") for i in range(len(text))]


def _phase1_split(full_text: str, seg_bounds: set[int]) -> list[TextBlock]:
    n = len(full_text)
    if n == 0:
        return []

    bp = _tokenize(full_text)
    boundaries = sorted(set([b for b, _, _ in bp if 0 < b < n]))

    if not boundaries:
        boundaries = list(range(1, n))

    # 長すぎるギャップ（11文字超）にフォールバック境界を追加
    MAX_BLOCK = 11
    all_b = sorted(set([0] + boundaries + [n]))
    for idx in range(len(all_b) - 1):
        gap = all_b[idx + 1] - all_b[idx]
        if gap > MAX_BLOCK:
            for fill in range(all_b[idx] + 1, all_b[idx + 1]):
                boundaries.append(fill)
    boundaries = sorted(set(boundaries))

    # 分割点スコア
    cut_scores = {}
    bp_dict = {pos: (surface, pos_tag) for pos, surface, pos_tag in bp}

    for b in boundaries:
        score = 0.0
        if b in seg_bounds:
            score += 50
        # 次の単語の品詞を取得
        next_tag = ""
        for pos2, _, tag2 in bp:
            if pos2 > b:
                next_tag = tag2
                break

        surface, pos_tag = bp_dict.get(b, ("", ""))
        if pos_tag == "助詞":
            score += 30
        elif pos_tag in ("動詞", "形容詞"):
            # 動詞/形容詞の後に動詞・助動詞が続く場合は切りにくい（活用形の途中）
            if next_tag in ("動詞", "助動詞"):
                score -= 15
            else:
                score += 15
        elif pos_tag == "助動詞":
            # 助動詞の後に助動詞が続く場合も切りにくい
            if next_tag == "助動詞":
                score -= 15
            else:
                score += 10
        elif pos_tag == "名詞":
            # 名詞+名詞の間で切るのはペナルティ（複合語）
            if next_tag == "名詞":
                score -= 10
            else:
                score += 8
        cut_scores[b] = score

    # DP（11文字以下で分割）
    MAX_BLOCK = 11
    dp = {0: (0.0, -1)}
    all_positions = sorted(set([0] + boundaries))

    for i in all_positions:
        if i not in dp or i >= n:
            continue
        for b in boundaries:
            if b <= i:
                continue
            if b - i > MAX_BLOCK:
                break
            if b - i < 2:
                continue
            new_score = dp[i][0] + cut_scores.get(b, 0)
            if b - i <= 2:
                new_score -= 20
            if b not in dp or new_score > dp[b][0]:
                dp[b] = (new_score, i)

        remaining = n - i
        if 2 <= remaining <= MAX_BLOCK:
            if n not in dp or dp[i][0] > dp.get(n, (-999, -1))[0]:
                dp[n] = (dp[i][0], i)

    if n not in dp:
        return [TextBlock(full_text, 0, n)]

    points = []
    pos = n
    while pos > 0:
        points.append(pos)
        pos = dp[pos][1]
    points.reverse()

    blocks = []
    prev = 0
    for sp in points:
        if sp > prev:
            blocks.append(TextBlock(full_text[prev:sp], prev, sp))
        prev = sp

    return blocks


# =============================================
# Phase 2: 隣接ブロックをDPで結合して11文字以下の1行に
# =============================================

def _phase2_merge_to_lines(
    blocks: list[TextBlock],
    max_chars: int,
    seg_bounds: set[int],
) -> list[TextBlock]:
    """隣接するmicro_blocksを結合して、各行がmax_chars以下になるようにする。

    DPで全体最適な結合を見つける。
    セグメント境界をまたぐ結合はペナルティ。
    """
    n = len(blocks)
    if n == 0:
        return []

    # dp[i] = (score, prev_group_start)
    # i = 次のグループの開始ブロックindex
    dp = {0: (0.0, -1)}

    for i in range(n):
        if i not in dp:
            continue
        current_score = dp[i][0]

        # i から j までのブロックを1行に結合
        combined_text = ""
        for j in range(i, n):
            combined_text += blocks[j].text
            combined_len = len(combined_text)
            if combined_len > max_chars:
                break

            # セグメント境界をまたぐ結合はペナルティ
            crosses = False
            if j > i:
                for k in range(i + 1, j + 1):
                    if blocks[k].start_pos in seg_bounds:
                        crosses = True
                        break

            score = current_score
            # 適度な長さにボーナス
            if combined_len >= 6:
                score += 5
            if combined_len >= 9:
                score += 3
            if crosses:
                score -= 10

            next_i = j + 1
            if next_i not in dp or score > dp[next_i][0]:
                dp[next_i] = (score, i)

    if n not in dp:
        return blocks

    # 逆順に復元
    group_starts = []
    pos = n
    while pos > 0:
        start = dp[pos][1]
        group_starts.append(start)
        pos = start
    group_starts.reverse()

    # グループからTextBlockを生成
    lines = []
    for idx, gs in enumerate(group_starts):
        ge = group_starts[idx + 1] if idx + 1 < len(group_starts) else n
        text = "".join(blocks[k].text for k in range(gs, ge))
        lines.append(TextBlock(text, blocks[gs].start_pos, blocks[ge - 1].end_pos))

    return lines


# =============================================
# Phase 3: 隣接1行を2行ブロックにまとめるかDPで判断
# =============================================

# 文の区切りパターン（これで終わる行は次の行と結合しない）
SENTENCE_ENDINGS = [
    "です", "ですよ", "ですね", "ですけど", "ですか", "ですかね",
    "ます", "ました", "ません",
    "のか", "のかとか",
    "いいな", "だな", "かな",
    "んですけど", "んですが",
    "ないので", "ないので",
    "ですよね", "ますよね",
    "しょう", "ください",
]


def _phase3_dp_group(
    lines: list[TextBlock],
    char_times: list[tuple[float, float]],
    max_chars_per_line: int,
) -> list[SRTEntry]:
    """DPで隣接行を2行にまとめるかどうかを最適化する。"""
    max_total = max_chars_per_line * 2
    n = len(lines)
    if n == 0:
        return []

    # dp[i] = (score, entries)
    dp = {0: (0.0, [])}

    for i in range(n):
        if i not in dp:
            continue
        prev_score, prev_entries = dp[i]

        # 選択肢A: 行iを単独エントリ
        entry_a = _make_srt_entry(
            len(prev_entries) + 1, [lines[i]], char_times
        )
        score_a = prev_score + _line_group_score(lines[i].text, None)
        next_a = i + 1
        if next_a not in dp or score_a > dp[next_a][0]:
            dp[next_a] = (score_a, prev_entries + [entry_a])

        # 選択肢B: 行iとi+1を結合
        if i + 1 < n:
            combined_len = len(lines[i].text) + len(lines[i + 1].text)
            if combined_len <= max_total:
                # 文末パターンで終わる場合は結合しない
                if _ends_with_sentence(lines[i].text):
                    pass  # 結合スキップ
                else:
                    entry_b = _make_srt_entry(
                        len(prev_entries) + 1,
                        [lines[i], lines[i + 1]],
                        char_times,
                    )
                    score_b = prev_score + _line_group_score(
                        lines[i].text, lines[i + 1].text
                    )
                    next_b = i + 2
                    if next_b not in dp or score_b > dp[next_b][0]:
                        dp[next_b] = (score_b, prev_entries + [entry_b])

    if n not in dp:
        return []

    _, best = dp[n]
    for idx, e in enumerate(best, 1):
        e.index = idx
    return best


def _ends_with_sentence(text: str) -> bool:
    """行が文の区切りで終わるかチェック。"""
    for ending in SENTENCE_ENDINGS:
        if text.endswith(ending):
            return True
    return False


def _line_group_score(line1: str, line2: str | None) -> float:
    """1エントリのスコア。"""
    score = 0.0

    if line2 is None:
        # 単独行
        if len(line1) >= 8:
            score += 3

        # 短い単独行はペナルティ（結合して2行にした方が読みやすい）
        if len(line1) <= 7:
            score -= 5

        # 助詞で終わる単独行は強ペナルティ
        if _ends_with_particle(line1):
            score -= 10

        return score

    # 2行結合
    score += 5  # 結合ボーナス

    # 1行目が助詞で終わる場合は結合を推奨（主語の途中）
    if _ends_with_particle(line1):
        score += 10

    # 2行目が「は」「が」等で終わる場合は強く結合（文頭〜主語が1ブロックに収まる）
    if line2.endswith(("のは", "には", "では", "とは", "は", "が")):
        score += 15

    # バランス
    balance = 1.0 - abs(len(line1) - len(line2)) / max(len(line1) + len(line2), 1)
    score += balance * 3

    # 表示文字数
    total = len(line1) + len(line2)
    if total >= 15:
        score += 2

    return score


def _ends_with_particle(text: str) -> bool:
    """行が助詞（は、が、を、に、で、から、の等）で終わるか。"""
    particles = ["のは", "には", "では", "とは", "から", "まで",
                 "は", "が", "を", "に", "で", "と", "も", "の"]
    for p in particles:
        if text.endswith(p):
            return True
    return False


def _make_srt_entry(index, line_blocks, char_times):
    if len(line_blocks) == 1:
        text = line_blocks[0].text
    else:
        text = "\n".join(lb.text for lb in line_blocks)

    start_pos = line_blocks[0].start_pos
    end_pos = line_blocks[-1].end_pos
    tl_start = _char_time(start_pos, char_times, True)
    tl_end = _char_time(end_pos - 1, char_times, False)

    return SRTEntry(index=index, start_time=tl_start, end_time=tl_end, text=text)


# =============================================
# ユーティリティ
# =============================================

def _char_time(pos, char_times, start):
    if pos < 0:
        pos = 0
    if pos >= len(char_times):
        pos = len(char_times) - 1
    return char_times[pos][0] if start else char_times[pos][1]


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
                    # セグメントがtime_rangeの端からはみ出す場合はクリップ
                    clipped_start = max(seg.start, tr_s)
                    clipped_end = min(seg.end, tr_e)
                    tl_s = _to_tl(clipped_start, tmap)
                    tl_e = _to_tl(clipped_end, tmap)
                    if tl_s is not None and tl_e is not None:
                        parts.append((seg.text, tl_s, tl_e))
                break
    return parts


def _build_char_time_map(parts):
    full = ""
    ctimes = []
    seg_bounds = set()
    for text, tl_s, tl_e in parts:
        seg_bounds.add(len(full))
        dur = tl_e - tl_s
        n = max(len(text), 1)
        for i in range(len(text)):
            ctimes.append((tl_s + dur * i / n, tl_s + dur * (i + 1) / n))
        full += text
    seg_bounds.add(len(full))
    seg_bounds.discard(0)
    return full, ctimes, seg_bounds


def _write_srt(entries, output_path):
    lines = []
    for e in entries:
        lines.append(str(e.index))
        lines.append(f"{_fmt(e.start_time)} --> {_fmt(e.end_time)}")
        lines.append(e.text)
        lines.append("")
    output_path.write_bytes(b"\xef\xbb\xbf" + "\r\n".join(lines).encode("utf-8"))


def _fmt(s):
    if s < 0: s = 0
    return f"{int(s//3600):02d}:{int(s%3600//60):02d}:{int(s%60):02d},{int(s%1*1000):03d}"
