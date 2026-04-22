"""
SRT字幕自動生成

Phase 1: 全テキストをDP探索で最小ブロックに分割（全単語境界）
Phase 2: 隣接ブロックをDPで結合して11文字以下の1行にまとめる
Phase 3: 隣接する1行を2行ブロックにまとめるかAIに判断させる
"""

from __future__ import annotations

import logging
import re
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
    speed: float = 1.0,
) -> Path | None:
    """元 transcription の word-level timestamp を元に SRT を生成する.

    以前は出力音声を Whisper で再文字起こしして比較する経路 (_generate_from_segments)
    が存在したが、Whisper segment 内で char_times を均等配分するため word 精度が失わ
    れ、かつ音声抽出の先頭 prefix を誤って含める (hallucination) 問題があったため廃止.
    """
    if not suggestion.time_ranges:
        return None

    tmap = build_timeline_map(suggestion.time_ranges)
    parts_with_words = _collect_parts_core(suggestion.time_ranges, tmap, transcription, speed=speed)
    if not parts_with_words:
        return None

    full_text, char_times, seg_bounds = _build_char_time_map(parts_with_words)
    if not full_text:
        return None

    return _generate_from_char_times(
        full_text,
        char_times,
        seg_bounds,
        output_path,
        max_chars_per_line,
        max_lines,
    )



def generate_srt_entries_from_segments(
    segments: list[dict],
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[SRTEntry]:
    """Whisperセグメントから字幕エントリーのリストを返す（ファイル書き出しなし）。

    Args:
        segments: [{"text": str, "start": float, "end": float}, ...] セグメントリスト
        max_chars_per_line: 1行あたり最大文字数
        max_lines: 最大行数

    Returns:
        SRTEntryのリスト
    """
    if not segments:
        return []

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
        return []

    return _entries_from_char_times(full_text, char_times, seg_bounds, max_chars_per_line, max_lines)


# 字幕内で除去する安全なフィラー（長い順）
SUBTITLE_FILLER_WORDS = sorted(
    [
        "やっぱり",
        "やっぱ",
        "えーっと",
        "えっとね",
        "えーと",
        "えっと",
        "あのー",
        "なんかその",
        "なんかこう",
        "なんか",
        "あのね",
        "えー",
        "要は",  # Phase 3.6 音声切除が 0.15s 閾値で落ちた時のセーフティネット
    ],
    key=len,
    reverse=True,
)

# 文脈依存フィラー: 直後が特定パターンなら文法的用法として保持
# 例: 「あの人」「あの時」は連体詞、「あの世界」「あの仕事」はフィラー
AMBIGUOUS_SUBTITLE_FILLERS: tuple[str, ...] = ("あの", "まあ", "まぁ")

# "要は" の境界チェック用 (CJK Unified Ideographs 主要範囲)
_KANJI_RE = re.compile(r"[一-鿿]")

# 「あの」の直後が以下で始まれば連体詞（保持）
_ANO_DEMONSTRATIVE_FOLLOWERS: tuple[str, ...] = (
    "人", "時", "方", "事", "こと", "件", "日", "間", "頃", "あと", "前", "後",
    "とき", "ひと", "ほう", "ころ", "あいだ", "もの", "やつ", "とこ", "ところ",
    "会社", "店", "所", "場所", "話", "中", "なか", "辺", "あたり", "感じ", "時間",
    "お方", "場面", "時代", "当時", "家", "街", "町",
)

# 「まあ」の直後が以下で始まれば副詞（保持）
_MAA_ADVERB_FOLLOWERS: tuple[str, ...] = (
    "いい", "良い", "よい", "OK", "ok", "大丈夫", "何とか", "なんとか",
    "しか", "しょうがな", "仕方", "しかたな", "まあ", "どう", "そこそこ",
)


def _is_ambiguous_filler_to_keep(filler: str, text_after: str) -> bool:
    """ambiguous filler の直後を見て「残すべき文法用法」かを判定。

    text_after は filler の直後に続くテキスト（先頭10文字程度を想定）。
    """
    if filler == "あの":
        return any(text_after.startswith(k) for k in _ANO_DEMONSTRATIVE_FOLLOWERS)
    if filler in ("まあ", "まぁ"):
        return any(text_after.startswith(k) for k in _MAA_ADVERB_FOLLOWERS)
    return False


def _remove_inline_fillers(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
) -> tuple[str, list[tuple[float, float]], set[int]]:
    """テキスト内のフィラーを除去し、char_timesとseg_boundsを調整する。

    Returns:
        (除去後テキスト, 調整後char_times, 調整後seg_bounds)
    """
    if not full_text:
        return full_text, char_times, seg_bounds

    # 除去する区間を収集 [(start_pos, end_pos), ...]
    remove_ranges: list[tuple[int, int]] = []

    # 1. GiNZA形態素解析でフィラーPOSを検出
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        doc = JapaneseLineBreakRules._analyze(full_text)
        if doc is not None:
            for token in doc:
                tag = JapaneseLineBreakRules._normalize_pos_tag(token.tag_)
                if tag == "フィラー":
                    remove_ranges.append((token.idx, token.idx + len(token.text)))
    except ImportError:
        pass

    # 2. SUBTITLE_FILLER_WORDSによる追加検出
    for filler in SUBTITLE_FILLER_WORDS:
        start = 0
        while True:
            idx = full_text.find(filler, start)
            if idx == -1:
                break
            filler_end = idx + len(filler)
            # "要は" の境界ガード: 直前が漢字なら "必要は" "重要は" 等の複合語末尾なので除去しない
            if filler == "要は" and idx > 0 and _KANJI_RE.match(full_text[idx - 1]):
                start = filler_end
                continue
            # 既にカバーされていなければ追加
            already_covered = any(rs <= idx and filler_end <= re for rs, re in remove_ranges)
            if not already_covered:
                remove_ranges.append((idx, filler_end))
            start = filler_end

    # 3. AMBIGUOUS_SUBTITLE_FILLERSによる文脈判定除去
    # 「あの人」「まあいい」等の文法用法は保持、それ以外は除去
    for filler in AMBIGUOUS_SUBTITLE_FILLERS:
        start = 0
        while True:
            idx = full_text.find(filler, start)
            if idx == -1:
                break
            filler_end = idx + len(filler)
            text_after = full_text[filler_end : filler_end + 10]
            if _is_ambiguous_filler_to_keep(filler, text_after):
                start = filler_end
                continue
            already_covered = any(rs <= idx and filler_end <= re for rs, re in remove_ranges)
            if not already_covered:
                remove_ranges.append((idx, filler_end))
            start = filler_end

    if not remove_ranges:
        return full_text, char_times, seg_bounds

    # 重複・重なりを統合してソート
    remove_ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in remove_ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # 除去範囲に含まれる位置を集合化
    remove_set = set()
    for s, e in merged:
        for i in range(s, e):
            remove_set.add(i)

    # 新しいテキスト・char_timesを構築
    new_text_chars = []
    new_char_times = []
    # 位置マッピング: old_pos → new_pos
    pos_map = {}
    new_pos = 0
    for old_pos in range(len(full_text)):
        if old_pos not in remove_set:
            new_text_chars.append(full_text[old_pos])
            new_char_times.append(char_times[old_pos])
            pos_map[old_pos] = new_pos
            new_pos += 1

    # seg_boundsを調整
    new_seg_bounds = set()
    for bound in seg_bounds:
        # boundは「ここから新セグメント」の位置
        # bound以上で最初の残存位置を探す
        mapped = None
        for check_pos in range(bound, len(full_text)):
            if check_pos in pos_map:
                mapped = pos_map[check_pos]
                break
        if mapped is not None and mapped > 0:
            new_seg_bounds.add(mapped)
    # 末尾を追加
    new_len = len(new_text_chars)
    if new_len > 0:
        new_seg_bounds.add(new_len)
    new_seg_bounds.discard(0)

    new_text = "".join(new_text_chars)
    return new_text, new_char_times, new_seg_bounds


def _trim_incomplete_ending(entries: list[SRTEntry]) -> list[SRTEntry]:
    """SRT末尾が不完全文で終わる場合、最後の完結点まで切り詰める。

    パターン1: 最終エントリ内に完結点がある → テキストをその点で切り詰め
    パターン2: 最終エントリ全体が不完全 → 前のエントリに遡って完結点を探す（最大3エントリ）
    """
    if not entries:
        return entries

    from core.japanese_line_break import JapaneseLineBreakRules

    # 最終エントリのテキスト（改行除去して結合）
    last = entries[-1]
    flat = last.text.replace("\n", "")
    if JapaneseLineBreakRules.is_sentence_complete(flat):
        return entries

    # パターン1: 最終エントリ内を逆走して完結点を探す
    # 行単位でチェック（SRTは1-2行構成）
    lines = last.text.split("\n")
    if len(lines) >= 2:
        first_line = lines[0].rstrip()
        if first_line and JapaneseLineBreakRules.is_sentence_complete(first_line):
            # 1行目で完結 → 2行目以降をカット
            last.text = first_line
            logger.info(f"SRT末尾トリム: 最終エントリを1行目で切り詰め '{first_line[-15:]}'")
            return entries

    # パターン2: 最終エントリを丸ごと除去して前のエントリをチェック
    for drop_count in range(1, min(4, len(entries))):
        candidate_entries = entries[: len(entries) - drop_count]
        if not candidate_entries:
            break
        check = candidate_entries[-1]
        check_flat = check.text.replace("\n", "")
        if JapaneseLineBreakRules.is_sentence_complete(check_flat):
            logger.info(f"SRT末尾トリム: 末尾{drop_count}エントリ除去 → '{check_flat[-15:]}'")
            return candidate_entries

    # 完結点が見つからない場合はそのまま返す
    return entries


def _entries_from_char_times(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry]:
    """char_timesベースでSRTEntryリストを生成する（共通処理）。"""
    # フィラー除去
    full_text, char_times, seg_bounds = _remove_inline_fillers(full_text, char_times, seg_bounds)
    if not full_text:
        return []

    micro_blocks = _phase1_split(full_text, seg_bounds, max_chars_per_line)
    lines = _phase2_merge_to_lines(micro_blocks, max_chars_per_line, seg_bounds)
    entries = _phase3_dp_group(lines, char_times, max_chars_per_line, max_lines)

    if not entries:
        return []

    # 隣接エントリ間の隙間を埋める
    for i in range(len(entries) - 1):
        if entries[i + 1].start_time > entries[i].end_time:
            entries[i].end_time = entries[i + 1].start_time

    # 短すぎるエントリを前後と統合
    entries = _merge_short_entries(entries, max_chars_per_line, max_lines)

    # 末尾トリミング: 最後のエントリが不完全文で終わる場合、完結点まで切り詰める
    entries = _trim_incomplete_ending(entries)

    for i, e in enumerate(entries, 1):
        e.index = i

    return entries


def _generate_from_char_times(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
    output_path: Path,
    max_chars_per_line: int,
    max_lines: int,
) -> Path | None:
    """char_timesベースで字幕を生成する（共通処理）。"""
    # フィラー除去: meta 保存も SRT 生成も同じ post-filter 値を使うため、
    # ここで明示的に filter してから両方に渡す
    filtered_text, filtered_ctimes, filtered_bounds = _remove_inline_fillers(
        full_text, char_times, seg_bounds
    )

    entries = _entries_from_char_times(
        filtered_text, filtered_ctimes, filtered_bounds, max_chars_per_line, max_lines
    )

    if not entries:
        return None

    _write_srt(entries, output_path)

    # 字幕エディタ用の meta サイドカー (post-filter の full_text + char_times)
    # SRT と内容が一致し、backfill 経路とも semantics が揃う
    try:
        from use_cases.ai.srt_edit_log import save_srt_meta

        save_srt_meta(output_path, filtered_text, filtered_ctimes)
    except Exception as e:
        logger.debug("SRT meta 保存失敗 (non-fatal): %s", e)

    logger.info("SRT生成: %dエントリ → %s", len(entries), output_path.name)
    return output_path


# =============================================
# Phase 1: 全テキストをDP探索で最小ブロックに分割
# =============================================


def _tokenize(text: str) -> list[tuple[int, str, str]]:
    """GiNZAで形態素解析。

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


def _parse_pos(tag: str) -> tuple[str, str]:
    """品詞タグを (大分類, サブカテゴリ) に分解する。

    例: "助詞-格助詞" → ("助詞", "格助詞")
        "名詞" → ("名詞", "")
    """
    if "-" in tag:
        parts = tag.split("-", 1)
        return parts[0], parts[1]
    return tag, ""


def _phase1_split(full_text: str, seg_bounds: set[int], max_chars: int = DEFAULT_MAX_CHARS_PER_LINE) -> list[TextBlock]:
    n = len(full_text)
    if n == 0:
        return []

    # 統合API: 形態素境界と文節境界を1回の解析で取得
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        bp, bunsetu_bounds = JapaneseLineBreakRules.get_word_boundaries_and_bunsetu(full_text)
    except ImportError:
        bp = _tokenize(full_text)
        bunsetu_bounds = set()

    boundaries = sorted(set([b for b, _, _ in bp if 0 < b < n]))

    if not boundaries:
        boundaries = list(range(1, n))

    # 長すぎるギャップ（11文字超）にフォールバック境界を追加
    MAX_BLOCK = max_chars
    all_b = sorted(set([0] + boundaries + [n]))
    for idx in range(len(all_b) - 1):
        gap = all_b[idx + 1] - all_b[idx]
        if gap > MAX_BLOCK:
            for fill in range(all_b[idx] + 1, all_b[idx + 1]):
                boundaries.append(fill)
    boundaries = sorted(set(boundaries))

    # 分割点スコア（文節ベース）
    cut_scores = {}
    bp_dict = {pos: (surface, pos_tag) for pos, surface, pos_tag in bp}

    for b in boundaries:
        score = 0.0
        if b in seg_bounds:
            score += 50

        surface, pos_tag = bp_dict.get(b, ("", ""))
        pos_major, pos_sub = _parse_pos(pos_tag)

        if b in bunsetu_bounds:
            # 文節境界 = 自然な分割点
            score += 20
            # 品詞ボーナス
            if pos_major == "助詞" and pos_sub == "接続助詞" and surface not in ("て", "で"):
                score += 20  # から/けど/ので → 計40
            elif pos_major == "助詞" and pos_sub == "終助詞":
                score += 20  # な/ね/よ → 計40
            elif pos_major == "助詞" and pos_sub == "係助詞":
                score += 10  # は/も → 計30
            elif pos_major == "フィラー":
                score += 15
        else:
            # 文節内部 = 分割を強く抑制
            score -= 30
            # フィラーの後は文節内でも許容
            if pos_major == "フィラー":
                score += 45  # net: +15

        cut_scores[b] = score

    # DP（11文字以下で分割）
    MAX_BLOCK = max_chars
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
    "です",
    "ですよ",
    "ですね",
    "ですけど",
    "ですか",
    "ですかね",
    "ですよね",
    "ますよね",
    "ます",
    "ました",
    "ません",
    "ましたね",
    "のか",
    "のかとか",
    "いいな",
    "だな",
    "かな",
    "んですけど",
    "んですが",
    "ないので",
    "しょう",
    "ください",
    "だよ",
    "だよね",
    "よね",
    "んですけれども",
    "ですけれども",
    "んですけども",
    "ですけども",
    "けれども",
    "けども",
    "だけど",
    "からね",
    "しかない",
    "らしい",
]


def _phase3_dp_group(
    lines: list[TextBlock],
    char_times: list[tuple[float, float]],
    max_chars_per_line: int,
    max_lines: int = 2,
) -> list[SRTEntry]:
    """DPで隣接行を2行にまとめるかどうかを最適化する。"""
    if max_lines < 2:
        # 1行モード: 結合しない
        entries = []
        for i, line in enumerate(lines):
            entries.append(_make_srt_entry(i + 1, [line], char_times))
        return entries
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
        entry_a = _make_srt_entry(len(prev_entries) + 1, [lines[i]], char_times)
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
                    score_b = prev_score + _line_group_score(lines[i].text, lines[i + 1].text)
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
    particles = ["のは", "には", "では", "とは", "から", "まで", "は", "が", "を", "に", "で", "と", "も", "の"]
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


MIN_ENTRY_DURATION = 0.7  # 最小表示時間（秒）


def _merge_short_entries(
    entries: list[SRTEntry],
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry]:
    """短すぎるエントリを前後と統合する。"""
    if len(entries) <= 1:
        return entries

    max_total_chars = max_chars_per_line * max_lines

    def _text_lines(e: SRTEntry) -> list[str]:
        return e.text.split("\n")

    def _can_merge(a: SRTEntry, b: SRTEntry) -> bool:
        """2つのエントリを統合可能か（文字数制限チェック）"""
        a_lines = _text_lines(a)
        b_lines = _text_lines(b)
        combined_lines = a_lines + b_lines
        if len(combined_lines) > max_lines:
            # 行数超過 → 最終行同士を結合して収まるか
            merged_last = a_lines[-1] + b_lines[0]
            if len(merged_last) > max_chars_per_line:
                return False
            combined_lines = a_lines[:-1] + [merged_last] + b_lines[1:]
            if len(combined_lines) > max_lines:
                return False
        return all(len(line) <= max_chars_per_line for line in combined_lines)

    def _do_merge(a: SRTEntry, b: SRTEntry) -> SRTEntry:
        """2つのエントリを統合する"""
        a_lines = _text_lines(a)
        b_lines = _text_lines(b)
        combined_lines = a_lines + b_lines
        if len(combined_lines) > max_lines:
            merged_last = a_lines[-1] + b_lines[0]
            combined_lines = a_lines[:-1] + [merged_last] + b_lines[1:]
        return SRTEntry(
            index=0,
            start_time=a.start_time,
            end_time=b.end_time,
            text="\n".join(combined_lines),
        )

    changed = True
    max_iterations = 50
    iteration = 0
    while changed:
        iteration += 1
        if iteration > max_iterations:
            logger.warning("短エントリ統合ループが収束しません（%d回）。打ち切ります。", max_iterations)
            break
        changed = False
        new_entries = []
        i = 0
        while i < len(entries):
            e = entries[i]
            dur = e.end_time - e.start_time

            if dur < MIN_ENTRY_DURATION - 1e-3 and len(entries) > 1:
                # 前のエントリと統合を試みる
                if new_entries and _can_merge(new_entries[-1], e):
                    new_entries[-1] = _do_merge(new_entries[-1], e)
                    changed = True
                    i += 1
                    continue
                # 次のエントリと統合を試みる
                if i + 1 < len(entries) and _can_merge(e, entries[i + 1]):
                    merged = _do_merge(e, entries[i + 1])
                    new_entries.append(merged)
                    changed = True
                    i += 2
                    continue
                # 統合不可 → 表示時間を延長（前後から借りる）
                desired_end = e.start_time + MIN_ENTRY_DURATION
                if i + 1 < len(entries) and desired_end <= entries[i + 1].end_time:
                    # 次エントリの開始を後ろにずらす
                    entries[i + 1] = SRTEntry(
                        index=0,
                        start_time=desired_end,
                        end_time=entries[i + 1].end_time,
                        text=entries[i + 1].text,
                    )
                    e = SRTEntry(index=0, start_time=e.start_time, end_time=desired_end, text=e.text)
                    changed = True
                elif new_entries:
                    # 前エントリの終了を前にずらして自分を延長
                    desired_start = e.end_time - MIN_ENTRY_DURATION
                    if desired_start >= new_entries[-1].start_time:
                        new_entries[-1] = SRTEntry(
                            index=0,
                            start_time=new_entries[-1].start_time,
                            end_time=desired_start,
                            text=new_entries[-1].text,
                        )
                        e = SRTEntry(index=0, start_time=desired_start, end_time=e.end_time, text=e.text)
                        changed = True

            new_entries.append(e)
            i += 1
        entries = new_entries

    return entries


# =============================================
# ユーティリティ
# =============================================


def _char_time(pos, char_times, start):
    if not char_times:
        return 0.0
    if pos < 0:
        pos = 0
    if pos >= len(char_times):
        pos = len(char_times) - 1
    return char_times[pos][0] if start else char_times[pos][1]


def build_timeline_map(time_ranges):
    m = []
    tl = 0.0
    for s, e in time_ranges:
        m.append((s, e, tl))
        tl += e - s
    return m


def _to_tl(orig, tmap):
    for os_, oe, tl in tmap:
        if os_ - 0.1 <= orig <= oe + 0.1:
            return tl + max(0.0, orig - os_)
    return None


# 無音削除で消えたギャップに word が落ちた場合、この秒数以内なら最近傍 range に吸収する。
# silence-removal の典型的なギャップ（0.1〜0.3s）を拾うため 0.3s に設定。
_ORPHAN_WORD_TOLERANCE = 0.3


def _collect_parts_core(
    time_ranges: list[tuple[float, float]],
    tmap: list[tuple[float, float, float]],
    transcription: TranscriptionResult,
    speed: float = 1.0,
) -> list[tuple[str, float, float, list[tuple[str, float, float]]]]:
    """word 単位で range に割当てて parts を構築する（内部実装）。

    Returns:
        list of (text, tl_s, tl_e, word_tl_list)
          word_tl_list = [(word_text, w_tl_s, w_tl_e), ...]

    挙動：
    - segment 境界を跨いでも同一 range の連続 word は 1 part にまとめる（Fix1）
    - どの range とも重ならない word は tolerance 内の最近傍 range に吸収（Fix2）
    - part 内は word 単位の tl を保持（Fix3 の素材、_build_char_time_map が使う）

    time_ranges は speed 除算済み、seg.start/end と seg.words の時間は元時間。

    Raises:
        ValueError: seg に word-level タイムスタンプが無い場合（旧キャッシュ対応）
    """
    if speed <= 0:
        raise ValueError(f"speed must be > 0, got {speed}")
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS

    def _orig_to_tl(orig_time: float) -> float | None:
        return _to_tl(orig_time / speed, tmap)

    # 各 range を元時間で事前計算
    orig_ranges = [(tr_s * speed, tr_e * speed) for tr_s, tr_e in time_ranges]

    def _best_range_idx(word) -> int | None:  # noqa: ANN001
        """word と最も重なりが大きい range のインデックスを返す。

        重なり 0 の orphan word でも、tolerance 内の最近傍 range に吸収する（Fix2）。
        どの range からも離れすぎた word のみ None を返す。
        """
        best_idx = None
        best_overlap = 0.0
        for idx, (orig_s, orig_e) in enumerate(orig_ranges):
            overlap = max(0.0, min(word.end, orig_e) - max(word.start, orig_s))
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = idx
        if best_idx is not None:
            return best_idx

        # Fix2: orphan word — tolerance 内なら最近傍 range に吸収
        best_dist = _ORPHAN_WORD_TOLERANCE
        for idx, (orig_s, orig_e) in enumerate(orig_ranges):
            if word.end < orig_s:
                dist = orig_s - word.end
            elif word.start > orig_e:
                dist = word.start - orig_e
            else:
                dist = 0.0
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx

    # Fix1: 全 segment を flat な word 列に展開し、segment 境界で flush しない
    all_words: list = []
    for seg in transcription.segments:
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue
        if not getattr(seg, "words", None):
            raise ValueError(
                f"segment at {seg.start:.2f}s has no word-level timestamps. "
                "Transcription cache is outdated; re-transcribe the video."
            )
        all_words.extend(seg.words)

    parts: list = []
    current_range_idx: int | None = None
    current_words: list = []

    def _flush(range_idx: int | None, words_buf: list) -> None:
        if range_idx is None or not words_buf:
            return
        orig_s, orig_e = orig_ranges[range_idx]

        word_tl_list: list[tuple[str, float, float]] = []
        prev_tl_e = 0.0
        for w in words_buf:
            clipped_s = max(w.start, orig_s)
            clipped_e = min(w.end, orig_e)
            if clipped_e <= clipped_s:
                # range 外の orphan を吸収したケース — word 全体を range 端に寄せる
                if w.end < orig_s:
                    clipped_s = clipped_e = orig_s
                elif w.start > orig_e:
                    clipped_s = clipped_e = orig_e
            w_tl_s = _orig_to_tl(clipped_s)
            w_tl_e = _orig_to_tl(clipped_e)
            if w_tl_s is None or w_tl_e is None:
                continue
            # 単調増加を強制（膨張 timestamp が前 word と逆転するのを防ぐ）
            if word_tl_list and w_tl_s < prev_tl_e:
                w_tl_s = prev_tl_e
            if w_tl_e < w_tl_s:
                w_tl_e = w_tl_s
            word_tl_list.append((w.word, w_tl_s, w_tl_e))
            prev_tl_e = w_tl_e

        if not word_tl_list:
            return
        text = "".join(wt[0] for wt in word_tl_list)
        if not text.strip():
            return
        tl_s = word_tl_list[0][1]
        tl_e = word_tl_list[-1][2]
        if tl_e <= tl_s:
            return
        parts.append((text, tl_s, tl_e, word_tl_list))

    for w in all_words:
        r_idx = _best_range_idx(w)
        if r_idx is None:
            # tolerance 外の orphan — 現在の part を破壊しないようスキップだけ
            continue
        if r_idx != current_range_idx:
            _flush(current_range_idx, current_words)
            current_range_idx = r_idx
            current_words = []
        current_words.append(w)
    _flush(current_range_idx, current_words)

    return parts


def collect_parts(time_ranges, tmap, transcription, speed=1.0):
    """word-levelタイムスタンプを使ってtime_rangesに含まれる発話を抽出する。

    Returns:
        list of (text, tl_s, tl_e) tuples. 外部 API 互換。
    """
    return [(text, tl_s, tl_e) for text, tl_s, tl_e, _ in _collect_parts_core(time_ranges, tmap, transcription, speed)]


def _build_char_time_map(parts_with_words):
    """word 境界ベースで char_times を構築する（Fix3）。

    Args:
        parts_with_words: _collect_parts_core() の戻り値
            list of (text, tl_s, tl_e, word_tl_list)
    """
    full = ""
    ctimes = []
    seg_bounds = set()
    for _text, _tl_s, _tl_e, word_tl_list in parts_with_words:
        seg_bounds.add(len(full))
        for word_text, w_tl_s, w_tl_e in word_tl_list:
            n = max(len(word_text), 1)
            dur = max(w_tl_e - w_tl_s, 0.0)
            for i in range(len(word_text)):
                ctimes.append((w_tl_s + dur * i / n, w_tl_s + dur * (i + 1) / n))
            full += word_text
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
    # BOMなし + LF改行（macOS + DaVinci Resolve推奨）
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(s):
    if s < 0:
        s = 0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = round((s % 1) * 1000)
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
