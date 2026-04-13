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
from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, detect_noise_tag

logger = logging.getLogger(__name__)

TOP_N_FOR_AI = 5  # AIに評価させる上位件数

# 各戦略の予算（合計80）
BUDGET_STRATEGY1 = 30  # スライディングウィンドウ
BUDGET_STRATEGY2 = 30  # 中間スキップ
BUDGET_STRATEGY3 = 20  # ランダムサンプリング


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
    segment_classifications: list[dict] | None = None,
    embeddings: dict[int, list[float]] | None = None,
) -> list[ClipCandidate]:
    """セグメント組み合わせで大量の候補を生成し、機械的スコアで上位を返す。"""

    segments = transcription.segments
    start_idx = topic.segment_start_index
    end_idx = topic.segment_end_index

    if start_idx < 0 or end_idx >= len(segments) or start_idx > end_idx:
        return []

    # 対象セグメントからフィラー・ノイズを除外
    pool = []
    for i in range(start_idx, end_idx + 1):
        seg = segments[i]
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue
        if detect_noise_tag(seg.text.strip()):
            continue
        pool.append((i, seg))

    if not pool:
        return []

    # 分類マップ構築（セグメントindex → role）
    role_map: dict[int, str] | None = None
    if segment_classifications:
        role_map = {c["index"]: c.get("role", "supportive") for c in segment_classifications}

    # 組み合わせ生成戦略:
    # 連続するセグメントの部分列を様々な開始/終了位置で切り出す
    candidates = []

    # 戦略0: Essential-guided 候補生成（分類がある場合のみ）
    if role_map:
        essential_pool = [(i, seg) for i, seg in pool if role_map.get(i) == "essential"]
        supportive_pool = [(i, seg) for i, seg in pool if role_map.get(i) == "supportive"]

        # essential-only 候補
        if essential_pool:
            c = _build_candidate(essential_pool)
            if c and c.total_duration >= min_duration * 0.5:
                candidates.append(c)

            # essential が短すぎる場合 → supportive を順に追加
            if c and c.total_duration < min_duration * 0.8 and supportive_pool:
                combined = list(essential_pool)
                for sp in supportive_pool:
                    combined.append(sp)
                    combined.sort(key=lambda x: x[0])
                    c2 = _build_candidate(combined)
                    if c2 and c2.total_duration >= min_duration * 0.8:
                        candidates.append(c2)
                        break

        # essential + supportive 候補（redundant のみ除外）
        non_redundant = [(i, seg) for i, seg in pool if role_map.get(i, "supportive") != "redundant"]
        if non_redundant:
            c = _build_candidate(non_redundant)
            if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
                candidates.append(c)

        s0_count = len(candidates)
        if s0_count:
            logger.info(f"Strategy 0 (essential-guided): {s0_count} candidates")

    # 戦略1: スライディングウィンドウ（連続セグメント）
    s1_count = 0
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
                    s1_count += 1
                    if s1_count >= BUDGET_STRATEGY1:
                        break

            if cumulative_dur > max_duration * 1.5:
                break
        if s1_count >= BUDGET_STRATEGY1:
            break

    # 戦略2: 中間スキップ（冒頭N + 末尾M、中間を飛ばす）
    s2_count = 0
    if len(pool) > 10:
        for skip_start in range(3, len(pool) - 3):
            for skip_end in range(skip_start + 1, min(skip_start + 15, len(pool) - 2)):
                kept = pool[:skip_start] + pool[skip_end:]
                c = _build_candidate(kept)
                if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
                    candidates.append(c)
                    s2_count += 1
                    if s2_count >= BUDGET_STRATEGY2:
                        break
            if s2_count >= BUDGET_STRATEGY2:
                break

    # 戦略3: ランダムサンプリング（ランダムにセグメントをスキップ）
    s3_count = 0
    for _ in range(50):
        # 各セグメントを70-90%の確率で含める
        kept = [(i, seg) for i, seg in pool if random.random() < random.uniform(0.7, 0.95)]
        if not kept:
            continue
        c = _build_candidate(kept)
        if c and min_duration * 0.8 <= c.total_duration <= max_duration * 1.2:
            candidates.append(c)
            s3_count += 1
            if s3_count >= BUDGET_STRATEGY3:
                break

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
        c.mechanical_score = _calculate_score(c, min_duration, max_duration, role_map=role_map, embeddings=embeddings)

    # スコア上位を返す
    candidates.sort(key=lambda c: c.mechanical_score, reverse=True)

    logger.info(
        f"組み合わせ生成: {len(candidates)}候補 "
        f"(best: {candidates[0].mechanical_score:.0f}pts, "
        f"{candidates[0].total_duration:.0f}s, "
        f"{len(candidates[0].segment_indices)}segs)"
    )

    return candidates[:TOP_N_FOR_AI]


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

    # duration範囲（下限20%、上限50%マージン — 超過分は後段のtrim_clipsで調整）
    if not (min_duration * 0.8 <= candidate.total_duration <= max_duration * 1.5):
        logger.debug(
            f"validate_ai_selection: duration {candidate.total_duration:.1f}s "
            f"out of range [{min_duration * 0.8:.1f}, {max_duration * 1.5:.1f}]"
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


def _calculate_score(
    candidate: ClipCandidate,
    min_duration: float,
    max_duration: float,
    role_map: dict[int, str] | None = None,
    embeddings: dict[int, list[float]] | None = None,
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

    # クリップ数 ±10点
    num_ranges = len(candidate.time_ranges)
    if role_map:
        # 骨子抽出ではクリップ数が増えるのが正常 → 緩和
        if num_ranges <= 3:
            score += 5
        elif num_ranges > 10:
            score -= 5
    else:
        # 既存ロジック（少ないほど自然）
        if num_ranges == 1:
            score += 10
        elif num_ranges <= 3:
            score += 5
        elif num_ranges > 8:
            score -= 10

    # 末尾の自然さ（3段階分類）
    GOOD_ENDINGS_HIGH = ["です", "ます", "ました", "思います", "しれません"]
    GOOD_ENDINGS_MEDIUM = [
        "ですね",
        "ますね",
        "ですよね",
        "よね",
        "んですよ",
        "んです",
        "ですか",
        "ですかね",
        "ませんか",
    ]
    DEFINITELY_INCOMPLETE = ["ので", "から", "けど", "けれども", "んですけど"]
    LIKELY_INCOMPLETE = ["って", "のが", "みたいな", "とか", "たら", "のは"]

    last_text = candidate.segments[-1].text.rstrip() if candidate.segments else ""
    if any(last_text.endswith(g) for g in GOOD_ENDINGS_HIGH):
        score += 15
    elif any(last_text.endswith(g) for g in GOOD_ENDINGS_MEDIUM):
        score += 8
    elif any(last_text.endswith(b) for b in DEFINITELY_INCOMPLETE):
        score -= 20
    elif any(last_text.endswith(b) for b in LIKELY_INCOMPLETE):
        score -= 12

    # GiNZA による末尾品詞判定（文字列マッチのフォールバック付き）
    if last_text:
        try:
            from core.japanese_line_break import JapaneseLineBreakRules

            rules = JapaneseLineBreakRules.get_instance()
            tokens = rules._analyze(last_text)
            if tokens:
                last_pos = tokens[-1].pos
                last_token_text = tokens[-1].text
                if last_pos == "助動詞":
                    score += 12  # です/ます
                elif last_pos in ("名詞", "動詞"):
                    score += 5  # 体言止め
                elif last_pos == "助詞":
                    if last_token_text in ("から", "けど", "ので", "って", "のが", "たら", "は"):
                        score -= 18  # 接続助詞・主題助詞
                    elif last_token_text in ("よ", "ね", "わ", "な", "さ"):
                        score += 10  # 終助詞
                    elif last_token_text == "か":
                        score += 8  # 疑問

                # 主節存在チェック: 末尾3トークン内に述語なし → 追加ペナルティ
                recent_poses = [t.pos for t in tokens[-3:]]
                if not any(p in ("助動詞", "動詞", "形容詞") for p in recent_poses):
                    if last_pos == "助詞" and last_token_text not in ("よ", "ね", "わ", "な", "さ", "か"):
                        score -= 5
        except Exception:
            pass

    # Essential/redundant 比率スコア（分類がある場合のみ）
    if role_map:
        total_segs = len(candidate.segment_indices)
        if total_segs > 0:
            essential_count = sum(1 for idx in candidate.segment_indices if role_map.get(idx) == "essential")
            redundant_count = sum(1 for idx in candidate.segment_indices if role_map.get(idx) == "redundant")
            essential_ratio = essential_count / total_segs
            redundant_ratio = redundant_count / total_segs
            if essential_ratio >= 0.6:
                score += 15
            elif essential_ratio >= 0.4:
                score += 10
            if redundant_ratio >= 0.3:
                score -= 15
            elif redundant_ratio >= 0.15:
                score -= 8

    # 話題一貫性スコア（±15点）
    if embeddings:
        seg_embs = [embeddings[idx] for idx in candidate.segment_indices if idx in embeddings]
        if len(seg_embs) >= 2:
            from use_cases.ai.generate_clip_suggestions import _avg_pairwise_cosine

            coherence = _avg_pairwise_cosine(seg_embs)
            if coherence >= 0.8:
                score += 15
            elif coherence >= 0.6:
                score += 5
            else:
                score -= 10

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
    last_seg_text = candidate.segments[-1].text if candidate.segments else ""
    for kw in NOISE_KEYWORDS:
        if kw in first_text:
            score -= 10
            break
    for kw in NOISE_KEYWORDS:
        if kw in last_seg_text:
            score -= 5
            break

    # 冒頭前置きペナルティ
    from use_cases.ai.filler_constants import _PREAMBLE_KEYWORDS

    if first_text and any(kw in first_text for kw in _PREAMBLE_KEYWORDS):
        score -= 12

    # 質問/回答比率チェック
    _QUESTION_MARKERS = ["？", "?", "ですか", "ですかね", "教えてください", "どう思いますか", "ありますか"]
    question_chars = 0
    total_chars = len(candidate.text)
    if total_chars > 0:
        for seg in candidate.segments:
            if any(m in seg.text for m in _QUESTION_MARKERS):
                question_chars += len(seg.text)
        ratio = question_chars / total_chars
        if ratio > 0.5:
            score -= 15
        elif ratio > 0.4:
            score -= 10
        elif ratio > 0.3:
            score -= 5

    # 低confidence セグメントペナルティ
    for seg in candidate.segments:
        if hasattr(seg, "words") and seg.words:
            confs = [w.confidence for w in seg.words if hasattr(w, "confidence") and w.confidence is not None]
            if confs and sum(confs) / len(confs) < 0.3:
                score -= 8

    return max(0, min(100, score))
