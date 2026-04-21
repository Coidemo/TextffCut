"""Phase 3.6: 検出済みフィラーの音声区間を time_ranges から物理的に切除する。

Phase 0 (early_filler_detection) で検出した FillerSpan の時間範囲を使い、
最終クリップの time_ranges からそれらの区間を減算する。Phase 3.5 の吃音除去
とは独立しており、後段で適用されることを想定。

SRT 生成は出力音声を Whisper で再認識するため、音声から切除した時点で
字幕からも自動的に消える。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from use_cases.ai.early_filler_detection import FillerMap

logger = logging.getLogger(__name__)

# 短すぎるフィラーは切らない（音飛びや不自然なカットを防ぐ）
DEFAULT_MIN_FILLER_DURATION = 0.15


def _collect_fillers_in_ranges(
    filler_map: FillerMap,
    time_ranges: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """filler_map から time_ranges のいずれかに重なるフィラーだけを (start, end) で集める。"""
    spans: list[tuple[float, float]] = []
    for seg_spans in filler_map.values():
        for span in seg_spans:
            for r_start, r_end in time_ranges:
                if span.time_end > r_start and span.time_start < r_end:
                    spans.append((span.time_start, span.time_end))
                    break
    return spans


def subtract_filler_ranges(
    time_ranges: list[tuple[float, float]],
    filler_spans: Iterable[tuple[float, float]],
    min_filler_duration: float = DEFAULT_MIN_FILLER_DURATION,
) -> list[tuple[float, float]]:
    """time_ranges から filler_spans を減算する。

    Args:
        time_ranges: 減算元の時間範囲（開始時刻で昇順想定）
        filler_spans: 切除したいフィラー区間の (start, end) 列
        min_filler_duration: 切除対象とするフィラーの最小長（秒）

    Returns:
        減算後の time_ranges（重なった箇所は分割、完全に覆われたら削除）
    """
    effective = [(s, e) for s, e in filler_spans if e - s >= min_filler_duration]
    if not effective:
        return list(time_ranges)

    result: list[tuple[float, float]] = list(time_ranges)
    for f_start, f_end in effective:
        new_result: list[tuple[float, float]] = []
        for s, e in result:
            if f_end <= s or f_start >= e:
                new_result.append((s, e))
                continue
            if s < f_start:
                new_result.append((s, f_start))
            if f_end < e:
                new_result.append((f_end, e))
        result = new_result

    return result


def apply_filler_removal(
    time_ranges: list[tuple[float, float]],
    filler_map: FillerMap,
    min_filler_duration: float = DEFAULT_MIN_FILLER_DURATION,
) -> tuple[list[tuple[float, float]], int]:
    """filler_map を使って time_ranges を減算する高レベルAPI。

    Returns:
        (new_time_ranges, 削除したフィラー区間数)
    """
    if not filler_map:
        return list(time_ranges), 0
    spans = _collect_fillers_in_ranges(filler_map, time_ranges)
    effective = [s for s in spans if s[1] - s[0] >= min_filler_duration]
    new_ranges = subtract_filler_ranges(time_ranges, spans, min_filler_duration)
    return new_ranges, len(effective)


__all__ = [
    "DEFAULT_MIN_FILLER_DURATION",
    "apply_filler_removal",
    "subtract_filler_ranges",
]
