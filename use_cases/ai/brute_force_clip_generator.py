"""
力任せ探索によるクリップ候補生成

セグメント単位の組み合わせで大量の候補を機械的に生成し、
スコアリングで絞り込んだ後、AIに最終評価させる。

セグメント単位でカットするため、words内カットによる音声の不自然さが発生しない。
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from domain.entities.clip_suggestion import TopicRange
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 80  # 生成する最大候補数
TOP_N_FOR_AI = 5  # AIに評価させる上位件数


@dataclass
class ClipCandidate:
    """1つの切り抜き候補"""

    segments: list[TranscriptionSegment]  # 使用するセグメント（順序保持）
    segment_indices: list[int]  # 元のtranscriptionでのインデックス
    text: str
    time_ranges: list[tuple[float, float]]
    total_duration: float
    mechanical_score: float = 0.0


def generate_candidates(
    topic: TopicRange,
    transcription: TranscriptionResult,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
) -> list[ClipCandidate]:
    """セグメント組み合わせで大量の候補を生成し、機械的スコアで上位を返す。"""

    segments = transcription.segments
    start_idx = topic.segment_start_index
    end_idx = topic.segment_end_index

    if start_idx < 0 or end_idx >= len(segments) or start_idx > end_idx:
        return []

    # 対象セグメントからフィラーを除外
    pool = []
    for i in range(start_idx, end_idx + 1):
        seg = segments[i]
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue
        pool.append((i, seg))

    if not pool:
        return []

    # 組み合わせ生成戦略:
    # 連続するセグメントの部分列を様々な開始/終了位置で切り出す
    candidates = []

    # 戦略1: スライディングウィンドウ（連続セグメント）
    for window_start in range(len(pool)):
        cumulative_dur = 0.0
        window_segs = []
        for j in range(window_start, len(pool)):
            idx, seg = pool[j]
            dur = seg.end - seg.start
            cumulative_dur += dur
            window_segs.append((idx, seg))

            if cumulative_dur >= min_duration:
                c = _build_candidate(window_segs)
                if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
                    candidates.append(c)

            if cumulative_dur > max_duration * 1.5:
                break

    # 戦略2: 中間スキップ（冒頭N + 末尾M、中間を飛ばす）
    if len(pool) > 10:
        for skip_start in range(3, len(pool) - 3):
            for skip_end in range(skip_start + 1, min(skip_start + 15, len(pool) - 2)):
                kept = pool[:skip_start] + pool[skip_end:]
                c = _build_candidate(kept)
                if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
                    candidates.append(c)
                    if len(candidates) >= MAX_CANDIDATES * 2:
                        break
            if len(candidates) >= MAX_CANDIDATES * 2:
                break

    # 戦略3: ランダムサンプリング（ランダムにセグメントをスキップ）
    for _ in range(min(50, MAX_CANDIDATES)):
        # 各セグメントを70-90%の確率で含める
        kept = [(i, seg) for i, seg in pool if random.random() < random.uniform(0.7, 0.95)]
        if not kept:
            continue
        c = _build_candidate(kept)
        if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
            candidates.append(c)

    if not candidates:
        # フォールバック: 全セグメント使用
        c = _build_candidate(pool)
        if c:
            candidates.append(c)

    # 重複除去
    seen = set()
    unique = []
    for c in candidates:
        key = tuple(c.segment_indices)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    candidates = unique

    # 機械的スコアリング
    for c in candidates:
        c.mechanical_score = _calculate_score(c, min_duration, max_duration)

    # スコア上位を返す
    candidates.sort(key=lambda c: c.mechanical_score, reverse=True)

    logger.info(
        f"組み合わせ生成: {len(candidates)}候補 "
        f"(best: {candidates[0].mechanical_score:.0f}pts, "
        f"{candidates[0].total_duration:.0f}s, "
        f"{len(candidates[0].segment_indices)}segs)"
    )

    return candidates[:TOP_N_FOR_AI]


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


def _calculate_score(
    candidate: ClipCandidate,
    min_duration: float,
    max_duration: float,
) -> float:
    """機械的な品質スコアを計算する（0-100）。"""
    score = 50.0

    # デュレーション適合度（±20点）
    center = (min_duration + max_duration) / 2
    if min_duration <= candidate.total_duration <= max_duration:
        deviation = abs(candidate.total_duration - center) / center
        score += 20 * (1.0 - deviation)
    else:
        if candidate.total_duration < min_duration:
            ratio = candidate.total_duration / min_duration
        else:
            ratio = max_duration / candidate.total_duration
        score -= 20 * (1.0 - ratio)

    # テキスト密度（5-7文字/秒が理想） ±10点
    if candidate.total_duration > 0:
        density = len(candidate.text) / candidate.total_duration
        if 5.0 <= density <= 7.0:
            score += 10
        elif 3.0 <= density <= 9.0:
            score += 5

    # クリップ数（少ないほど自然） ±10点
    num_ranges = len(candidate.time_ranges)
    if num_ranges == 1:
        score += 10
    elif num_ranges <= 3:
        score += 5
    elif num_ranges > 8:
        score -= 10

    # 末尾の自然さ（±10点）
    GOOD_ENDINGS = [
        "です",
        "ます",
        "ですね",
        "ますね",
        "ですよね",
        "よね",
        "ました",
        "思います",
        "んですよ",
        "んです",
        "ですか",
        "ですかね",
        "ませんか",
        "しれません",
    ]
    BAD_ENDINGS = ["ので", "けど", "から", "って", "のが", "みたいな", "けれども", "とか", "んですけど"]
    last_text = candidate.text.rstrip()
    if any(last_text.endswith(g) for g in GOOD_ENDINGS):
        score += 10
    elif any(last_text.endswith(b) for b in BAD_ENDINGS):
        score -= 15

    # フィラー残存ペナルティ（強めに減点）
    filler_count = sum(1 for seg in candidate.segments if seg.text.strip() in FILLER_ONLY_TEXTS)
    score -= filler_count * 5

    # テキスト内のフィラー語彙ペナルティ
    text = candidate.text
    for filler in ["あの", "まあ", "なんか", "えー", "えっと", "うーん"]:
        count = text.count(filler)
        score -= count * 2

    # 冒頭/末尾ノイズペナルティ
    NOISE_KEYWORDS = {"すいません", "すみません", "マイク", "聞きづらい", "聞こえ", "音声"}
    first_text = candidate.segments[0].text if candidate.segments else ""
    last_text = candidate.segments[-1].text if candidate.segments else ""
    for kw in NOISE_KEYWORDS:
        if kw in first_text:
            score -= 10
            break
    for kw in NOISE_KEYWORDS:
        if kw in last_text:
            score -= 5
            break

    return max(0, min(100, score))
