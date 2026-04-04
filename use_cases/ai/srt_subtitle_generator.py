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
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> Path | None:
    if not suggestion.time_ranges:
        return None

    tmap = _build_timeline_map(suggestion.time_ranges)
    parts = _collect_parts(suggestion.time_ranges, tmap, transcription)
    if not parts:
        return None

    full_text, char_times, seg_bounds = _build_char_time_map(parts)
    if not full_text:
        return None

    # Phase 1: 最小ブロックに分割
    micro_blocks = _phase1_split(full_text, seg_bounds)

    # Phase 2: 11文字以下の1行にまとめる
    lines = _phase2_merge_to_lines(micro_blocks, max_chars_per_line, seg_bounds)

    # Phase 3: 2行ブロックにまとめるかAIに判断させる
    entries = _phase3_ai_group(lines, char_times, max_chars_per_line)

    if not entries:
        return None

    _write_srt(entries, output_path)
    logger.info(f"SRT生成: {len(entries)}エントリ → {output_path.name}")
    return output_path


# =============================================
# Phase 1: 全テキストをDP探索で最小ブロックに分割
# =============================================

def _phase1_split(full_text: str, seg_bounds: set[int]) -> list[TextBlock]:
    n = len(full_text)
    if n == 0:
        return []

    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        bp = JapaneseLineBreakRules.get_word_boundaries_with_pos(full_text)
        boundaries = sorted(set([b for b, _, _ in bp if 0 < b < n]))
    except ImportError:
        boundaries = list(range(1, n))
        bp = []

    # 分割点スコア
    cut_scores = {}
    for b in boundaries:
        score = 0.0
        if b in seg_bounds:
            score += 50
        for pos, surface, pos_tag in bp:
            if pos == b:
                if pos_tag == "助詞":
                    score += 30
                elif pos_tag in ("動詞", "形容詞"):
                    score += 15
                elif pos_tag == "名詞":
                    score += 8
                break
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
        combined_len = 0
        for j in range(i, n):
            combined_len += len(blocks[j].text)
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
# Phase 3: 隣接1行を2行ブロックにまとめるかAIに判断
# =============================================

def _phase3_ai_group(
    lines: list[TextBlock],
    char_times: list[tuple[float, float]],
    max_chars_per_line: int,
) -> list[SRTEntry]:
    max_total = max_chars_per_line * 2
    n = len(lines)

    # AI判断
    groups = _ai_group_lines(lines, max_total)

    # グループからSRTEntryを生成
    entries = []
    for group in groups:
        if not group:
            continue
        group_lines = [lines[i] for i in group if i < n]
        if not group_lines:
            continue

        if len(group_lines) == 1:
            text = group_lines[0].text
        else:
            text = "\n".join(gl.text for gl in group_lines)

        start_pos = group_lines[0].start_pos
        end_pos = group_lines[-1].end_pos
        tl_start = _char_time(start_pos, char_times, True)
        tl_end = _char_time(end_pos - 1, char_times, False)

        entries.append(SRTEntry(
            index=len(entries) + 1,
            start_time=tl_start,
            end_time=tl_end,
            text=text,
        ))

    return entries


def _ai_group_lines(lines: list[TextBlock], max_total: int) -> list[list[int]]:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        return _fallback_group(lines, max_total)

    line_list = "\n".join(f"[{i}] ({len(l.text)}字) {l.text}" for i, l in enumerate(lines))

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "字幕レイアウト担当。JSON形式で回答。"},
                {"role": "user", "content": f"""以下はショート動画の字幕（1行ずつ）です。
これを字幕エントリにグループ化してください。

ルール:
- 1エントリは最大2行。2行にする場合は合計{max_total}文字以下
- **1つの文の中で意味が連続しているなら結合する**
  OK: 「なりたい状態から」+「逆算するのは」（1文の前半と後半）
  OK: 「やる前から商社の」+「営業がいいか」（1文の中の一部）
  OK: 「めちゃくちゃ良く」+「ないので」（1つのフレーズが分かれている）
  OK: 「ITスタート」+「アップのエンジニアが」（1つの単語が分かれている）
- **別の文・別の話題は絶対に結合しない**
  NG: 「僕の主張です」+「なりたい状態から」（別の文）
  NG: 「いいのか」+「ITスタート」（「のか」で文が終わり、次は別の話題）
  NG: 「いいな」+「はいいんですけど」（「いいな」で一区切り）
- **「のか」「です」「ですよ」「ですね」「ですけど」で終わる行は文の終わり。次の行とは結合しない**
- 1行のままでも構わない

行一覧:
{line_list}

JSON: {{"groups": [[0,1], [2], [3,4], [5,6], ...]}}"""},
            ],
            temperature=0.2,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        groups = result.get("groups", [])

        # バリデーション
        if _validate_groups(groups, len(lines), max_total, lines):
            logger.info(f"AI字幕グループ: {len(groups)}エントリ ({len(lines)}行から)")
            return groups

    except Exception as e:
        logger.warning(f"AI字幕グループ失敗: {e}")

    return _fallback_group(lines, max_total)


def _validate_groups(groups, n, max_total, lines):
    if not groups:
        return False
    used = set()
    for g in groups:
        if not isinstance(g, list):
            return False
        for idx in g:
            if not isinstance(idx, int) or idx < 0 or idx >= n:
                return False
            if idx in used:
                return False
            used.add(idx)
        if len(g) > 2:
            return False
        if len(g) == 2:
            total = sum(len(lines[i].text) for i in g)
            if total > max_total:
                return False
    return len(used) == n


def _fallback_group(lines, max_total):
    groups = []
    i = 0
    while i < len(lines):
        if i + 1 < len(lines) and len(lines[i].text) + len(lines[i + 1].text) <= max_total:
            groups.append([i, i + 1])
            i += 2
        else:
            groups.append([i])
            i += 1
    return groups


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
                    tl_s = _to_tl(seg.start, tmap)
                    tl_e = _to_tl(seg.end, tmap)
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
