"""
クリップ候補のデータ構造とAI選定結果のバリデーション
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from domain.entities.transcription import TranscriptionSegment

logger = logging.getLogger(__name__)


@dataclass
class ClipCandidate:
    """1つの切り抜き候補"""

    segments: list[TranscriptionSegment]  # 使用するセグメント（順序保持）
    segment_indices: list[int]  # 元のtranscriptionでのインデックス
    text: str
    time_ranges: list[tuple[float, float]]
    total_duration: float
    embedding_similarity: float = 0.0
    composite_score: float = 0.0


def validate_ai_selection(
    indices: list[int],
    pool: list[tuple[int, TranscriptionSegment]],
    min_duration: float,
    max_duration: float,
) -> ClipCandidate | None:
    """AIが返したindexリストをバリデーションし、ClipCandidateを構築する。"""
    pool_map = dict(pool)
    pool_indices = set(pool_map.keys())

    # 全indexが有効
    invalid = [idx for idx in indices if idx not in pool_indices]
    if invalid:
        logger.debug(f"validate_ai_selection: invalid indices {invalid}")
        return None

    # 昇順
    if indices != sorted(indices):
        logger.debug("validate_ai_selection: indices not sorted")
        return None

    # 重複なし
    if len(indices) != len(set(indices)):
        logger.debug("validate_ai_selection: duplicate indices")
        return None

    # 最低3セグメント
    if len(indices) < 3:
        logger.debug(f"validate_ai_selection: too few segments ({len(indices)})")
        return None

    # _build_candidate() で構築
    seg_list = [(idx, pool_map[idx]) for idx in indices]
    candidate = _build_candidate(seg_list)
    if not candidate:
        logger.debug("validate_ai_selection: _build_candidate returned None")
        return None

    # duration範囲（ユーザー指定の上限下限を尊重）
    if not (min_duration <= candidate.total_duration <= max_duration):
        logger.debug(
            f"validate_ai_selection: duration {candidate.total_duration:.1f}s "
            f"out of range [{min_duration:.1f}, {max_duration:.1f}]"
        )
        return None

    # 末尾の自然さチェック: 明らかに不完全な末尾は拒否
    _DEFINITELY_INCOMPLETE_ENDINGS = (
        "ので", "から", "けど", "けれども", "んですけど",
        "っていうのは", "んですけれども", "なんですけど",
    )
    last_text = candidate.segments[-1].text.rstrip() if candidate.segments else ""
    if last_text and any(last_text.endswith(e) for e in _DEFINITELY_INCOMPLETE_ENDINGS):
        logger.debug(
            f"validate_ai_selection: incomplete ending '{last_text[-10:]}'"
        )
        return None

    return candidate


def _build_candidate(
    seg_list: list[tuple[int, TranscriptionSegment]],
) -> ClipCandidate | None:
    """セグメントリストからClipCandidateを構築する。"""
    if not seg_list:
        return None

    # 連続するセグメントをtime_rangesにマージ（0.5秒以内のギャップ）
    time_ranges = []
    texts = []
    indices = []

    for idx, seg in seg_list:
        indices.append(idx)
        texts.append(seg.text)
        if time_ranges and seg.start - time_ranges[-1][1] <= 0.5:
            time_ranges[-1] = (time_ranges[-1][0], seg.end)
        else:
            time_ranges.append((seg.start, seg.end))

    total = sum(e - s for s, e in time_ranges)
    if total < 5:
        return None

    return ClipCandidate(
        segments=[seg for _, seg in seg_list],
        segment_indices=indices,
        text="".join(texts),
        time_ranges=time_ranges,
        total_duration=total,
    )
