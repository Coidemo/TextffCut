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
    has_core: bool = False  # 骨子（核心の主張）を含むか
