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
_DE_PREFIX_FILLERS: frozenset[str] = frozenset(
    {"でなんか", "であの", "でまあ", "でその"}
)

# GiNZA判定に渡すコンテキストウィンドウ（片側文字数）
_CONTEXT_WINDOW = 50

# Phase 0でGiNZA判定不能(None)をフィラーとして積極除去する語
# 話し言葉ではほぼフィラーだが、GiNZAだけでは確定できないケース
# Phase 4では同じ語もLLM判定に委譲される（_is_grammatical_by_contextは共有）
_PHASE0_AGGRESSIVE: frozenset[str] = frozenset(
    {"なんか", "あの", "まあ", "まぁ"}
)


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


def predetect_fillers(transcription: TranscriptionResult) -> FillerMap:
    """全セグメントを連結した full_text 上でフィラーを検出する。

    LLM判定（層3）はコスト節約のため行わない。曖昧フィラーでGiNZA判定不能なものはスキップ。
    _PHASE0_SKIP に含まれる談話マーカーは Phase 0 では検出しない（Phase 4 に委譲）。
    """
    from use_cases.ai.filler_constants import AMBIGUOUS_FILLERS
    from use_cases.ai.filler_constants import FILLER_WORDS as PURE_FILLERS
    from use_cases.ai.word_level_filler_polish import _get_filler_time, _is_grammatical_by_context

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

        f_start, f_end = _get_filler_time(words, seg_offset, filler_len)

        if f_start is None or f_end is None:
            pos += filler_len
            continue

        # 引用パターン: 直後が「って」→ 引用発話（「うーんって思う」等）、除去しない
        after_filler_pos = pos + filler_len
        if (
            after_filler_pos + 2 <= len(full_text)
            and full_text[after_filler_pos : after_filler_pos + 2] == "って"
        ):
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
                if char_pos < len(words):
                    w = words[char_pos]
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
    seg: object,
) -> list[tuple[float, float]]:
    """テキストの各文字に対応するタイムスタンプを取得する。"""
    char_times: list[tuple[float, float]] = []
    for char_pos in range(len(text)):
        if char_pos < len(words):
            w = words[char_pos]
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
