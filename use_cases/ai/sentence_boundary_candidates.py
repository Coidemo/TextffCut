"""
Phase 2b: 文境界ベース力任せ候補生成

1文字単位のタイムスタンプを活かし、文の完結点を候補の開始/終了位置とする。
セグメント境界に縛られない精密な候補生成。
"""

from __future__ import annotations

import logging

from domain.entities.clip_suggestion import TopicRange
from domain.entities.transcription import TranscriptionResult
from use_cases.ai.brute_force_clip_generator import ClipCandidate

logger = logging.getLogger(__name__)


def generate_sentence_boundary_candidates(
    clean_segments: list,  # list[CleanSegment]
    topic: TopicRange,
    min_duration: float,
    max_duration: float,
    *,
    transcription: TranscriptionResult | None = None,
) -> list[ClipCandidate]:
    """文完結位置の組み合わせで候補を生成する。

    Args:
        clean_segments: Phase 0で作成したフィラー除去済みセグメントリスト（全セグメント）
        topic: 話題範囲
        min_duration: 最小秒数
        max_duration: 最大秒数

    Returns:
        ClipCandidateリスト（スコア未計算）
    """
    from core.japanese_line_break import JapaneseLineBreakRules

    # topic範囲内のCleanSegmentを抽出
    topic_segments = [
        cs for cs in clean_segments if topic.segment_start_index <= cs.original_index <= topic.segment_end_index
    ]
    if not topic_segments:
        return []

    # Step 1: 連結テキスト + char_timesマップ構築
    full_text = ""
    all_char_times: list[tuple[float, float]] = []
    # 各セグメントのchar_times開始インデックスを記録（seg_indexとの対応用）
    seg_char_ranges: list[tuple[int, int, int]] = []  # (seg_original_index, char_start_in_full, char_end_in_full)

    for cs in topic_segments:
        start_pos = len(full_text)
        full_text += cs.clean_text
        all_char_times.extend(cs.char_times)
        end_pos = len(full_text)
        seg_char_ranges.append((cs.original_index, start_pos, end_pos))

    if not full_text:
        return []

    # Step 2: 文完結位置の検出
    # 走査しながらis_sentence_complete()がTrueになる位置を全列挙
    sentence_ends: list[int] = []  # full_text内の文字位置（完結文字の位置）

    # 効率のため、文完結判定は適切な粒度で行う
    # 最低5文字ごとにチェック（短すぎる分割を避ける）
    for i in range(4, len(full_text)):
        # 末尾の文字列で完結判定
        # 直近の一定文字数だけチェック（全文を渡す必要はない）
        check_text = full_text[max(0, i - 20) : i + 1].rstrip()
        if check_text and JapaneseLineBreakRules.is_sentence_complete(check_text):
            sentence_ends.append(i)

    if not sentence_ends:
        logger.debug(f"Phase 2b: 文完結位置なし ({topic.title})")
        return []

    # 重複する近接位置をフィルタ（2文字以内は同一文完結点として扱う）
    filtered_ends: list[int] = []
    for pos in sentence_ends:
        if not filtered_ends or pos - filtered_ends[-1] > 2:
            filtered_ends.append(pos)
    sentence_ends = filtered_ends

    # Step 3: 候補生成（文完結位置の組み合わせ）
    candidates: list[ClipCandidate] = []

    # 開始位置の候補: セグメント境界のみ（文字途中開始を防止）
    start_positions = sorted(set(char_start for _, char_start, _ in seg_char_ranges))

    for start_pos in start_positions:
        for end_pos in sentence_ends:
            if end_pos <= start_pos:
                continue

            # 時刻を計算
            if start_pos >= len(all_char_times) or end_pos >= len(all_char_times):
                continue

            time_start = all_char_times[start_pos][0]
            time_end = all_char_times[end_pos][1]
            duration = time_end - time_start

            if duration < min_duration or duration > max_duration:
                continue

            # テキスト抽出
            text = full_text[start_pos : end_pos + 1]

            # time_rangesを構築（連続する文字のタイムスタンプをマージ）
            time_ranges = _merge_char_times_to_ranges(all_char_times[start_pos : end_pos + 1])
            if not time_ranges:
                continue

            # セグメントindicesを特定
            segment_indices = _find_segment_indices(start_pos, end_pos, seg_char_ranges)

            # segment_indicesに対応するTranscriptionSegmentを取得
            segments = (
                [transcription.segments[i] for i in segment_indices]
                if transcription
                else []
            )

            candidate = ClipCandidate(
                segments=segments,
                segment_indices=segment_indices,
                text=text,
                time_ranges=time_ranges,
                total_duration=sum(e - s for s, e in time_ranges),
            )
            candidates.append(candidate)

    logger.info(
        f"Phase 2b: {len(candidates)}候補生成 "
        f"(文完結位置={len(sentence_ends)}, 開始位置={len(start_positions)}) "
        f"({topic.title})"
    )

    return candidates


def _merge_char_times_to_ranges(
    char_times: list[tuple[float, float]],
    gap_threshold: float = 0.5,
) -> list[tuple[float, float]]:
    """文字単位のタイムスタンプを連続するtime_rangesにマージする。

    gap_threshold秒以上のギャップがある場合、別のrangeとして分離する。
    """
    if not char_times:
        return []

    ranges: list[tuple[float, float]] = []
    current_start = char_times[0][0]
    current_end = char_times[0][1]

    for i in range(1, len(char_times)):
        c_start, c_end = char_times[i]
        # ギャップが閾値以内ならマージ
        if c_start - current_end <= gap_threshold:
            current_end = max(current_end, c_end)
        else:
            ranges.append((current_start, current_end))
            current_start = c_start
            current_end = c_end

    ranges.append((current_start, current_end))
    return ranges


def _find_segment_indices(
    start_pos: int,
    end_pos: int,
    seg_char_ranges: list[tuple[int, int, int]],
) -> list[int]:
    """full_text内の文字位置範囲から、対応するセグメントindicesを返す。"""
    indices = []
    for seg_idx, char_start, char_end in seg_char_ranges:
        # この範囲と重なるセグメントを抽出
        if char_start <= end_pos and char_end > start_pos:
            indices.append(seg_idx)
    return sorted(set(indices))
