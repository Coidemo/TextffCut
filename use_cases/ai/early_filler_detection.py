"""
Phase 0: 早期フィラー検出

候補生成前にフィラー位置を特定し、フィラー除去済みのCleanSegmentを作成する。
LLM判定（層3）はコスト節約のためPhase 0では行わない。

全セグメントを連結した full_text 上でマッチングし、GiNZA判定には
前後50文字のコンテキストウィンドウを渡すことでセグメント境界をまたいだ
文脈判定を可能にする。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from domain.entities.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

# Phase 0でスキップする語（談話マーカー等）
# filler_constants.py は変更せず、Phase 4のLLM判定は維持する
_PHASE0_SKIP: frozenset[str] = frozenset(
    {
        "どういうことかというと",  # 説明導入
        "じゃないですか",  # 修辞的同意要求
        "っていうのは",  # 主題提示
        "何て言うんですかね",  # 言い換え導入
        "簡単に言うと",  # 要約導入
        "ざっくり言うと",  # 要約導入
        "ぶっちゃけ",  # 率直表現（副詞）
        "とか",  # ほぼ常に並列助詞
    }
)

# "で"接頭辞の複合フィラー: 直前が「の」なら "ので" の一部なので複合マッチしない
_DE_PREFIX_FILLERS: frozenset[str] = frozenset({"でなんか", "であの", "でまあ", "でその"})

# GiNZA判定に渡すコンテキストウィンドウ（片側文字数）
_CONTEXT_WINDOW = 50

# Phase 0でGiNZA判定不能(None)をフィラーとして積極除去する語
# 話し言葉ではほぼフィラーだが、GiNZAだけでは確定できないケース
# Phase 4では同じ語もLLM判定に委譲される（_is_grammatical_by_contextは共有）
_PHASE0_AGGRESSIVE: frozenset[str] = frozenset({"なんか", "あの", "まあ", "まぁ"})


@dataclass
class FillerSpan:
    """フィラーの位置情報"""

    char_start: int  # セグメント内の文字開始位置
    char_end: int  # セグメント内の文字終了位置
    filler_text: str  # フィラーテキスト
    time_start: float  # 開始時刻
    time_end: float  # 終了時刻


# キー: セグメントindex、値: そのセグメント内のフィラー位置リスト
FillerMap = dict[int, list[FillerSpan]]


@dataclass
class CleanSegment:
    """フィラー除去済みセグメント"""

    original_index: int  # 元のセグメントindex
    clean_text: str  # フィラー除去後テキスト
    char_times: list[tuple[float, float]]  # 各文字の(start, end)時刻
    original_text: str  # 元テキスト（参照用）


def expand_words_to_chars(words: list) -> list:
    """wordsリスト（Word単位）を文字単位に展開する。

    Word.wordが複数文字の場合、各文字に同じWordオブジェクトを割り当てる。
    """
    expanded = []
    for w in words:
        w_text = w.word if hasattr(w, "word") else w.get("word", "")
        for _ in w_text:
            expanded.append(w)
    return expanded


def _get_filler_time(
    words: list,
    char_pos: int,
    filler_len: int,
) -> tuple[float | None, float | None]:
    """wordsリスト（1文字ずつ）からフィラーの開始・終了時刻を取得する。"""
    if char_pos >= len(words) or char_pos + filler_len > len(words):
        return None, None

    first_word = words[char_pos]
    last_word = words[char_pos + filler_len - 1]

    f_start = first_word.start if hasattr(first_word, "start") else first_word.get("start", None)
    f_end = last_word.end if hasattr(last_word, "end") else last_word.get("end", None)

    return f_start, f_end


def _analyze_text(text: str):
    """GiNZAでテキストを解析（キャッシュはJapaneseLineBreakRulesに委譲）。"""
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        return JapaneseLineBreakRules._analyze(text)
    except Exception:
        return None


def _is_grammatical_by_context(filler_text: str, seg_text: str, char_pos: int) -> bool | None:
    """GiNZA POS + 文脈ルールでフィラーか文法的用法かを判定。

    Returns:
        True  = 確実に文法的用法（カットしない）
        False = 確実にフィラー（カットする）
        None  = 判定不能（LLMに委譲）
    """
    doc = _analyze_text(seg_text)
    if doc is None:
        return None  # GiNZA利用不可 → LLM委譲

    # フィラーの直後テキストのPOSを取得
    after_pos = char_pos + len(filler_text)
    after_text = seg_text[after_pos : after_pos + 10].strip() if after_pos < len(seg_text) else ""
    before_text = seg_text[max(0, char_pos - 10) : char_pos].strip()

    # doc内でフィラー位置に対応するトークンを特定
    filler_token_idx = None
    running_pos = 0
    for i, token in enumerate(doc):
        token_end = running_pos + len(token.text)
        if running_pos <= char_pos < token_end:
            filler_token_idx = i
            break
        running_pos = token_end

    # フィラーの直後トークンのPOS
    after_token = None
    if filler_token_idx is not None:
        # フィラーが複数トークンにまたがる場合、最後のトークンの次を取る
        run = sum(len(doc[j].text) for j in range(filler_token_idx))
        for i in range(filler_token_idx, len(doc)):
            run += len(doc[i].text)
            if run >= after_pos:
                if i + 1 < len(doc):
                    after_token = doc[i + 1]
                break

    after_pos_tag = after_token.pos_ if after_token else ""

    if filler_text == "なんか":
        # 直前が「な」（形容動詞連体形） → 「異常ななんか」=「異常な何か」= 文法的用法
        if before_text and before_text.endswith("な"):
            return True
        # 直後が動詞・形容詞・副詞 → フィラー
        if after_pos_tag in ("VERB", "ADJ", "ADV"):
            return False
        # 文頭で直後が名詞以外 → フィラー
        if char_pos == 0:
            return False
        # 直後が名詞でも文脈依存（"なんかSNS"=フィラー vs "何か問題"=文法的）→ LLM委譲
        return None

    if filler_text == "あの":
        # 文頭 or 直後が動詞 → フィラー
        if char_pos == 0 or after_pos_tag == "VERB":
            return False
        # 直後が副詞 → フィラー（「あの全然」「あのそう」等）
        if after_pos_tag == "ADV":
            return False
        # 直後が名詞でも文脈依存（"あの人"=連体詞 vs "あのここ15年"=フィラー）→ LLM委譲
        return None

    if filler_text == "とか":
        # 前後に名詞が2つ以上 → 並列助詞「AとかBとか」
        nouns_before = sum(
            1
            for t in doc
            if t.pos_ == "NOUN" and sum(len(doc[j].text) for j in range(list(doc).index(t) + 1)) <= char_pos
        )
        nouns_after = sum(
            1 for t in doc if t.pos_ == "NOUN" and sum(len(doc[j].text) for j in range(list(doc).index(t))) >= after_pos
        )
        if nouns_before >= 1 and nouns_after >= 1:
            return True
        # 文末 or 直後が句点系 → フィラー
        if after_pos >= len(seg_text) or (after_text and after_text[0] in "。、"):
            return False
        return None

    if filler_text == "的な":
        # 直前が漢語名詞（漢字のみ） → 接尾辞「具体的な」
        before_chars = before_text
        if before_chars and re.search(r"[\u4e00-\u9fff]$", before_chars):
            return True
        # 直後が名詞 → 形容的用法「〜的な+名詞」（例: 「いいね的な拍手」）
        if after_pos_tag == "NOUN":
            return True
        # 文末 or 直前がひらがな → フィラー
        if after_pos >= len(seg_text) or (before_chars and re.search(r"[\u3040-\u309f]$", before_chars)):
            return False
        return None

    if filler_text in ("やっぱ", "やっぱり"):
        # 直後に述語（動詞・形容詞・助動詞）があれば文法的
        if after_pos_tag in ("VERB", "ADJ", "AUX"):
            return True
        # 文末 → 不明
        if after_pos >= len(seg_text):
            return None
        return None

    if filler_text in ("まあ", "まぁ"):
        # 文頭で直後が名詞以外 → フィラー
        if char_pos == 0 and after_pos_tag != "NOUN":
            return False
        # 直後に述語があっても文脈依存（"まあいいか"=副詞 vs "まあ例えば"=フィラー）→ LLM委譲
        return None

    if filler_text == "ぶっちゃけ":
        # 直後に述語あり → 副詞的用法
        if after_pos_tag in ("VERB", "ADJ", "ADV", "NOUN"):
            return True
        return None

    if filler_text == "みたいな感じで":
        # 直前に具体的な名詞 → 比喩「猫みたいな感じで」
        if before_text and any(t.pos_ == "NOUN" for t in doc if t.text in before_text[-5:]):
            return True
        # 文末付近 → フィラー
        if after_pos >= len(seg_text) - 2:
            return False
        return None

    if filler_text == "っていうのは":
        # 直後に述語 → 主題提示「幸せっていうのは〜」
        if after_pos_tag in ("VERB", "ADJ", "NOUN", "ADV"):
            return True
        return None

    if filler_text == "じゃないですか":
        # 直前に具体的内容あり + 直後が「だから」「でも」等 → 修辞的疑問（文法的）
        if after_text and any(after_text.startswith(w) for w in ("だから", "でも", "それで", "なので")):
            return True
        # 文末 → フィラー（同意要求）
        if after_pos >= len(seg_text) - 1:
            return False
        return None

    # 未知の曖昧フィラー → LLM委譲
    return None


def predetect_fillers(transcription: TranscriptionResult) -> FillerMap:
    """全セグメントを連結した full_text 上でフィラーを検出する。

    LLM判定（層3）はコスト節約のため行わない。曖昧フィラーでGiNZA判定不能なものはスキップ。
    _PHASE0_SKIP に含まれる談話マーカーは Phase 0 では検出しない（Phase 4 に委譲）。
    """
    from use_cases.ai.filler_constants import AMBIGUOUS_FILLERS
    from use_cases.ai.filler_constants import FILLER_WORDS as PURE_FILLERS

    # Phase 0スキップ語を除外したフィラーリスト（長い順）
    all_fillers = sorted(
        (set(PURE_FILLERS) | AMBIGUOUS_FILLERS) - _PHASE0_SKIP,
        key=len,
        reverse=True,
    )

    # Step 1: full_text構築 + 文字位置→(seg_idx, seg内offset)マッピング
    char_to_seg: list[tuple[int, int]] = []  # full_text[i] → (seg_idx, seg内offset)
    full_text_parts: list[str] = []

    for seg_idx, seg in enumerate(transcription.segments):
        text = seg.text
        for char_offset in range(len(text)):
            char_to_seg.append((seg_idx, char_offset))
        full_text_parts.append(text)

    full_text = "".join(full_text_parts)

    if not full_text:
        return {}

    # Step 2 & 3: full_text上でフィラーマッチング + GiNZA判定
    filler_map: FillerMap = {}
    pos = 0

    while pos < len(full_text):
        matched_filler = None
        for filler in all_fillers:
            if full_text[pos : pos + len(filler)] == filler:
                matched_filler = filler
                break

        if not matched_filler:
            pos += 1
            continue

        filler_len = len(matched_filler)

        # "で"接頭辞フィラーの境界チェック: 直前が「の」→ "ので"の一部、複合マッチしない
        if matched_filler in _DE_PREFIX_FILLERS and pos > 0 and full_text[pos - 1] == "の":
            pos += 1  # "で"をスキップ、次の文字から個別フィラーを再マッチ
            continue

        # フィラーがセグメント境界をまたぐ場合はスキップ
        end_char_idx = pos + filler_len - 1
        if end_char_idx >= len(char_to_seg):
            pos += filler_len
            continue
        seg_idx, seg_offset = char_to_seg[pos]
        seg_idx_end, _ = char_to_seg[end_char_idx]
        if seg_idx != seg_idx_end:
            pos += 1
            continue

        seg = transcription.segments[seg_idx]
        words = seg.words or []

        if not words:
            pos += filler_len
            continue

        expanded_words = expand_words_to_chars(words)
        f_start, f_end = _get_filler_time(expanded_words, seg_offset, filler_len)

        if f_start is None or f_end is None:
            pos += filler_len
            continue

        # 引用パターン: 直後が「って」→ 引用発話（「うーんって思う」等）、除去しない
        after_filler_pos = pos + filler_len
        if after_filler_pos + 2 <= len(full_text) and full_text[after_filler_pos : after_filler_pos + 2] == "って":
            pos += filler_len
            continue

        if matched_filler in AMBIGUOUS_FILLERS:
            # 前後_CONTEXT_WINDOW文字のコンテキストウィンドウでGiNZA判定
            ctx_start = max(0, pos - _CONTEXT_WINDOW)
            ctx_end = min(len(full_text), pos + filler_len + _CONTEXT_WINDOW)
            context_text = full_text[ctx_start:ctx_end]
            ctx_char_pos = pos - ctx_start

            verdict = _is_grammatical_by_context(matched_filler, context_text, ctx_char_pos)
            if verdict is True:
                # 文法的用法 → スキップ
                pos += filler_len
                continue
            if verdict is False or matched_filler in _PHASE0_AGGRESSIVE:
                # フィラー確定、または話し言葉でほぼフィラーの語(判定不能でも除去)
                if seg_idx not in filler_map:
                    filler_map[seg_idx] = []
                filler_map[seg_idx].append(
                    FillerSpan(
                        char_start=seg_offset,
                        char_end=seg_offset + filler_len,
                        filler_text=matched_filler,
                        time_start=f_start,
                        time_end=f_end,
                    )
                )
            # それ以外のverdict=None → Phase 4のLLMに委譲
        else:
            # 確定フィラー → 記録
            if seg_idx not in filler_map:
                filler_map[seg_idx] = []
            filler_map[seg_idx].append(
                FillerSpan(
                    char_start=seg_offset,
                    char_end=seg_offset + filler_len,
                    filler_text=matched_filler,
                    time_start=f_start,
                    time_end=f_end,
                )
            )

        pos += filler_len

    total_fillers = sum(len(v) for v in filler_map.values())
    if total_fillers > 0:
        logger.info(f"Phase 0: {total_fillers}箇所のフィラーを検出 ({len(filler_map)}セグメント)")

    return filler_map


def build_clean_segments(
    transcription: TranscriptionResult,
    filler_map: FillerMap,
) -> list[CleanSegment]:
    """フィラー除去済みのCleanSegmentリストを構築する。

    フィラーが文中にある場合、セグメントをフィラー前後で分割する。
    1つの元セグメントから複数のCleanSegmentが生成されることがある。
    各CleanSegmentのclean_textとchar_timesは1:1対応し、時間的に連続する。
    """
    clean_segments: list[CleanSegment] = []

    for seg_idx, seg in enumerate(transcription.segments):
        text = seg.text
        words = seg.words or []
        expanded_words = expand_words_to_chars(words)
        fillers = filler_map.get(seg_idx, [])

        if not fillers:
            # フィラーなし → そのまま1つのCleanSegment
            char_times = _extract_char_times(text, words, seg)
            clean_segments.append(
                CleanSegment(
                    original_index=seg_idx,
                    clean_text=text,
                    char_times=char_times,
                    original_text=text,
                )
            )
            continue

        # フィラーをchar_startでソートし、非フィラー範囲を計算
        sorted_fillers = sorted(fillers, key=lambda f: f.char_start)
        ranges: list[tuple[int, int]] = []
        current_pos = 0
        for f in sorted_fillers:
            if current_pos < f.char_start:
                ranges.append((current_pos, f.char_start))
            current_pos = f.char_end
        if current_pos < len(text):
            ranges.append((current_pos, len(text)))

        # 各非フィラー範囲からCleanSegmentを作成
        for range_start, range_end in ranges:
            sub_text = text[range_start:range_end]
            if not sub_text:
                continue

            char_times: list[tuple[float, float]] = []
            for char_pos in range(range_start, range_end):
                if char_pos < len(expanded_words):
                    w = expanded_words[char_pos]
                    w_start = w.start if hasattr(w, "start") else w.get("start", 0.0)
                    w_end = w.end if hasattr(w, "end") else w.get("end", 0.0)
                    char_times.append((w_start, w_end))
                else:
                    if char_times:
                        last_end = char_times[-1][1]
                        char_times.append((last_end, last_end))
                    else:
                        char_times.append((seg.start, seg.start))

            clean_segments.append(
                CleanSegment(
                    original_index=seg_idx,
                    clean_text=sub_text,
                    char_times=char_times,
                    original_text=text,
                )
            )

    return clean_segments


def _extract_char_times(
    text: str,
    words: list,
    seg: TranscriptionSegment,
) -> list[tuple[float, float]]:
    """テキストの各文字に対応するタイムスタンプを取得する。"""
    expanded = expand_words_to_chars(words)
    char_times: list[tuple[float, float]] = []
    for char_pos in range(len(text)):
        if char_pos < len(expanded):
            w = expanded[char_pos]
            w_start = w.start if hasattr(w, "start") else w.get("start", 0.0)
            w_end = w.end if hasattr(w, "end") else w.get("end", 0.0)
            char_times.append((w_start, w_end))
        else:
            if char_times:
                last_end = char_times[-1][1]
                char_times.append((last_end, last_end))
            else:
                char_times.append((seg.start, seg.start))
    return char_times
