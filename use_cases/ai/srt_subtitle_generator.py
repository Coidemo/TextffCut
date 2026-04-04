"""
SRT字幕自動生成

方式:
Phase 1: 全テキストを11文字以下のブロックに分割（全単語境界探索）
Phase 2: 隣接ブロックを結合して2行にするか1行のままにするかのパターンを生成
Phase 3: スコアリングで最良パターンを選出
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS_PER_LINE = 11
DEFAULT_MAX_LINES = 2
SEARCH_WINDOW = 40


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

    # Phase 1: 11文字以下のブロックに分割
    blocks = _split_into_lines(full_text, max_chars_per_line, seg_bounds)

    # Phase 2: 隣接ブロック結合パターンを生成→スコアリング
    entries = _merge_and_score(blocks, char_times, full_text, max_chars_per_line, max_lines, seg_bounds)

    if not entries:
        return None

    _write_srt(entries, output_path)
    logger.info(f"SRT生成: {len(entries)}エントリ → {output_path.name}")
    return output_path


# --- Phase 1: 11文字以下に分割 ---

@dataclass
class TextBlock:
    text: str
    start_pos: int  # full_text内の開始位置
    end_pos: int    # full_text内の終了位置


def _split_into_lines(full_text: str, max_chars: int, seg_bounds: set[int]) -> list[TextBlock]:
    """全テキストをmax_chars以下のブロックに分割する。

    スライディングウィンドウで先頭から探索し、
    セグメント境界と助詞の後を優先して切断する。
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules
        has_janome = True
    except ImportError:
        has_janome = False

    blocks = []
    pos = 0
    n = len(full_text)

    while pos < n:
        remaining = n - pos
        if remaining <= max_chars:
            blocks.append(TextBlock(full_text[pos:n], pos, n))
            break

        # 探索窓
        window = full_text[pos:min(pos + SEARCH_WINDOW, n)]

        if has_janome:
            bp = JapaneseLineBreakRules.get_word_boundaries_with_pos(window)
        else:
            bp = []

        best_cut = None
        best_score = -999

        # 全単語境界を候補として評価
        candidates = [b for b, _, _ in bp] if bp else list(range(1, len(window)))

        for b in candidates:
            if b < 3 or b > max_chars:
                continue

            score = 0.0

            # セグメント境界ボーナス（最優先）
            if (pos + b) in seg_bounds:
                score += 50

            # 品詞スコア
            if bp:
                for boundary, surface, pos_tag in bp:
                    if boundary == b:
                        if pos_tag == "助詞":
                            score += 30
                        elif pos_tag in ("動詞", "形容詞"):
                            score += 15
                        elif pos_tag == "名詞":
                            score += 8
                        break

            # max_charsに近いほどボーナス（無駄に短くしない）
            score += b * 0.5

            # 2文字以下ペナルティ
            if b <= 2:
                score -= 30

            if score > best_score:
                best_score = score
                best_cut = b

        if best_cut is None:
            best_cut = min(max_chars, remaining)

        abs_cut = pos + best_cut
        blocks.append(TextBlock(full_text[pos:abs_cut], pos, abs_cut))
        pos = abs_cut

    return blocks


# --- Phase 2: 結合パターン生成→スコアリング ---

def _merge_and_score(
    blocks: list[TextBlock],
    char_times: list[tuple[float, float]],
    full_text: str,
    max_chars_per_line: int,
    max_lines: int,
    seg_bounds: set[int] | None = None,
) -> list[SRTEntry]:
    """AIに隣接ブロックの結合判断を依頼し、SRTEntryを生成する。"""
    max_total = max_chars_per_line * max_lines
    n = len(blocks)
    if n == 0:
        return []

    # AIに結合パターンを判断させる
    merge_decisions = _ai_merge_blocks(blocks, max_total)

    # 結合判断に従ってSRTEntryを生成
    entries = []
    i = 0
    idx = 1
    while i < n:
        block = blocks[i]

        if i in merge_decisions and i + 1 < n:
            # 結合
            next_block = blocks[i + 1]
            text = f"{block.text}\n{next_block.text}"
            tl_start = _char_to_time(block.start_pos, char_times, True)
            tl_end = _char_to_time(next_block.end_pos - 1, char_times, False)
            entries.append(SRTEntry(idx, tl_start, tl_end, text))
            idx += 1
            i += 2
        else:
            # 単独
            tl_start = _char_to_time(block.start_pos, char_times, True)
            tl_end = _char_to_time(block.end_pos - 1, char_times, False)
            entries.append(SRTEntry(idx, tl_start, tl_end, block.text))
            idx += 1
            i += 1

    return entries


def _ai_merge_blocks(blocks: list[TextBlock], max_total: int) -> set[int]:
    """AIに「どの隣接ブロックを2行にまとめるか」を判断させる。

    Returns:
        結合するブロックのインデックスのset。
        {3}なら blocks[3]とblocks[4]を結合。
    """
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
    if not api_key:
        # フォールバック: 貪欲結合
        return _greedy_merge_decisions(blocks, max_total)

    # ブロック一覧を作成
    block_list = "\n".join(
        f"[{i}] {b.text}" for i, b in enumerate(blocks)
    )

    # 結合可能なペアを列挙
    mergeable = []
    for i in range(len(blocks) - 1):
        if len(blocks[i].text) + len(blocks[i + 1].text) <= max_total:
            mergeable.append(i)

    if not mergeable:
        return set()

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "字幕レイアウト担当。JSON形式で回答。"},
                {"role": "user", "content": f"""以下はショート動画の字幕ブロック（各行11文字以下）です。
隣接する2つのブロックを「1つの字幕（2行表示）」にまとめるべきペアを選んでください。

判断基準:
- 意味のまとまりが同じなら結合する（例: 「やる前から」+「商社の営業がいいか」→ 結合しない。別の意味）
- 1つの文の前半と後半なら結合する（例: 「なりたい状態から」+「逆算するのは」→ 結合する）
- 結合しても合計{max_total}文字以下であること
- 結合可能なペア: {mergeable}

ブロック:
{block_list}

JSON: {{"merge": [結合するブロックのindex番号]}}
例: {{"merge": [2, 5, 8]}} → [2]+[3]を結合、[5]+[6]を結合、[8]+[9]を結合
結合不要なら {{"merge": []}}"""},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        merge_indices = set(result.get("merge", []))

        # 重複回避（[3]と[4]を結合したら[4]と[5]は結合できない）
        cleaned = set()
        skip = set()
        for idx in sorted(merge_indices):
            if idx in skip or idx not in mergeable:
                continue
            cleaned.add(idx)
            skip.add(idx + 1)

        logger.info(f"AI字幕結合: {len(cleaned)}ペア結合 ({len(blocks)}→{len(blocks) - len(cleaned)}エントリ)")
        return cleaned

    except Exception as e:
        logger.warning(f"AI字幕結合失敗: {e}")
        return _greedy_merge_decisions(blocks, max_total)


def _greedy_merge_decisions(blocks: list[TextBlock], max_total: int) -> set[int]:
    """フォールバック: 貪欲に結合する。"""
    merge = set()
    i = 0
    while i < len(blocks) - 1:
        if len(blocks[i].text) + len(blocks[i + 1].text) <= max_total:
            merge.add(i)
            i += 2
        else:
            i += 1
    return merge


def _char_to_time(char_pos: int, char_times: list[tuple[float, float]], start: bool) -> float:
    if char_pos < 0:
        char_pos = 0
    if char_pos >= len(char_times):
        char_pos = len(char_times) - 1
    return char_times[char_pos][0] if start else char_times[char_pos][1]


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


# --- SRT出力 ---

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
