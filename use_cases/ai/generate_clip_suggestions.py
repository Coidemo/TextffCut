"""
AI切り抜き候補生成ユースケース

1. AI: 話題の時間範囲を検出
2. 力任せ探索: セグメント組み合わせで大量候補生成 → 機械スコアで上位5件
3. AI: 既存テキストで最良候補を選定
"""

from __future__ import annotations

import logging
from pathlib import Path

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface
from use_cases.ai.brute_force_clip_generator import (
    ClipCandidate,
    validate_ai_selection,
)

logger = logging.getLogger(__name__)

MIN_TOPIC_SCORE = 8  # Phase 1 で低スコア話題をスキップする閾値

# 末尾の自然さ判定パターン（文字列フォールバック用）
_GOOD_ENDINGS_HIGH = ("です", "ます", "ました", "思います", "しれません")
_GOOD_ENDINGS_MEDIUM = (
    "ですね", "ますね", "ですよね", "よね", "んですよ",
    "んです", "ですか", "ですかね", "ませんか",
)
_DEFINITELY_INCOMPLETE = (
    "ので", "から", "けど", "けれども", "んですけど",
    "っていうのは", "んですけれども", "なんですけど",
)
_LIKELY_INCOMPLETE = (
    "って", "のが", "みたいな", "とか", "たら", "のは",
    "て", "より", "ながら", "つつ", "ものの", "にも", "を",
)

# 接続助詞（末尾に来ると不自然）
_CONJUNCTIVE_PARTICLES = frozenset(
    ("から", "けど", "ので", "って", "のが", "たら", "は", "て", "より", "ながら", "つつ")
)
# 終助詞（末尾に来ると自然）
_FINAL_PARTICLES = frozenset(("よ", "ね", "わ", "な", "さ"))
# 冒頭に来ると不自然な助詞
_BAD_START_PARTICLE_TEXTS = frozenset(
    ("で", "て", "けど", "けれども", "ので", "から", "が", "を", "に", "と", "も", "は")
)


def _ending_naturalness_score(text: str) -> int:
    """候補テキストの末尾自然さスコアを返す（GiNZA + 文字列フォールバック）。"""
    t = text.rstrip()
    if not t:
        return 0

    # 文字列マッチ（高確度パターンを先にチェック）
    str_score = _ending_str_score(t)

    # GiNZA POS判定
    ginza_score = _ending_ginza_score(t)

    # 両方のスコアのうち、絶対値が大きい方（より確信度が高い方）を採用
    if abs(ginza_score) >= abs(str_score):
        return ginza_score
    return str_score


def _ending_str_score(text: str) -> int:
    """文字列パターンによる末尾判定。"""
    if any(text.endswith(g) for g in _GOOD_ENDINGS_HIGH):
        return 15
    if any(text.endswith(g) for g in _GOOD_ENDINGS_MEDIUM):
        return 8
    if any(text.endswith(b) for b in _DEFINITELY_INCOMPLETE):
        return -20
    if any(text.endswith(b) for b in _LIKELY_INCOMPLETE):
        return -12
    return 0


def _ending_ginza_score(text: str) -> int:
    """GiNZA品詞による末尾判定。"""
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        # 末尾50文字で十分（GiNZA解析コスト削減）
        doc = JapaneseLineBreakRules._analyze(text[-50:])
        if not doc or len(doc) == 0:
            return 0

        last_token = doc[-1]
        pos = JapaneseLineBreakRules._normalize_pos_tag(last_token.tag_)
        pos_major = pos.split("-")[0]
        token_text = last_token.text

        score = 0
        if pos_major == "助動詞":
            score = 12  # です/ます系
        elif pos_major in ("名詞", "動詞"):
            score = 5  # 体言止め・動詞終止
        elif pos_major == "助詞":
            if token_text in _CONJUNCTIVE_PARTICLES:
                score = -18
            elif token_text in _FINAL_PARTICLES:
                score = 10
            elif token_text == "か":
                score = 8
            else:
                score = -10  # その他の助詞（格助詞等）

        # 主節存在チェック: 末尾3トークン内に述語なし → 追加ペナルティ
        if score <= 0 and len(doc) >= 2:
            recent_poses = [
                JapaneseLineBreakRules._normalize_pos_tag(tk.tag_).split("-")[0]
                for tk in doc[-3:]
            ]
            has_predicate = any(p in ("助動詞", "動詞", "形容詞") for p in recent_poses)
            if not has_predicate and pos_major == "助詞" and token_text not in _FINAL_PARTICLES and token_text != "か":
                score -= 5

        return score
    except Exception:
        return 0


def _start_naturalness_score(text: str) -> int:
    """候補テキストの冒頭自然さスコアを返す（GiNZA + 文字列フォールバック）。"""
    t = text.lstrip()
    if not t:
        return 0

    ginza_score = _start_ginza_score(t)
    if ginza_score != 0:
        return ginza_score
    return _start_str_score(t)


def _start_ginza_score(text: str) -> int:
    """GiNZA品詞による冒頭判定。"""
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        doc = JapaneseLineBreakRules._analyze(text[:50])
        if not doc or len(doc) == 0:
            return 0

        first_token = doc[0]
        pos = JapaneseLineBreakRules._normalize_pos_tag(first_token.tag_)
        pos_major = pos.split("-")[0]
        token_text = first_token.text

        if pos_major == "助詞":
            if token_text in _BAD_START_PARTICLE_TEXTS:
                return -15
            # 「っていう」等は接続助詞始まり
            if token_text in ("って", "っていう"):
                return -15
        elif pos_major == "助動詞":
            # 助動詞で始まる → 前文の述語からの続き
            return -10

        return 0
    except Exception:
        return 0


def _start_str_score(text: str) -> int:
    """文字列パターンによる冒頭判定（GiNZAフォールバック）。"""
    for p in _BAD_START_PARTICLE_TEXTS:
        if text.startswith(p) and len(text) > len(p):
            next_char = text[len(p)]
            safe_follows = {
                "で": "すはもきし", "て": "もはき",
                "は": "いっ", "と": "いこに",
            }
            if p in safe_follows and next_char in safe_follows[p]:
                continue
            return -15
    for c in ("っていう", "という", "ああい", "ういう"):
        if text.startswith(c):
            return -15
    return 0


def _boundary_naturalness_score(text: str) -> int:
    """候補テキストの冒頭+末尾の自然さ合算スコア。"""
    return _start_naturalness_score(text) + _ending_naturalness_score(text)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """2つのembeddingベクトルのcosine類似度を計算する。"""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _avg_pairwise_cosine(embeddings: list[list[float]]) -> float:
    """embeddingリストの平均ペアワイズcosine類似度を計算する。"""
    if len(embeddings) < 2:
        return 1.0
    total = 0.0
    count = 0
    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            total += _cosine_similarity(embeddings[i], embeddings[j])
            count += 1
    return total / count if count > 0 else 0.0


class GenerateClipSuggestionsUseCase:

    def __init__(self, gateway: ClipSuggestionGatewayInterface):
        self.gateway = gateway

    def execute(
        self,
        transcription: TranscriptionResult,
        video_path: Path,
        num_candidates: int = 5,
        min_duration: int = 30,
        max_duration: int = 60,
        prompt_path: str | None = None,
    ) -> list[ClipSuggestion]:

        segments_dicts = [
            {
                "text": seg.text,
                "start": seg.start,
                "end": seg.end,
                "words": [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "probability": w.confidence if hasattr(w, "confidence") else None,
                    }
                    for w in (seg.words or [])
                    if hasattr(w, "word")
                ]
                or None,
            }
            for seg in transcription.segments
        ]

        # Phase 0: 早期フィラー検出（候補生成前にフィラー位置を特定）
        try:
            from use_cases.ai.early_filler_detection import build_clean_segments, predetect_fillers

            filler_map = predetect_fillers(transcription)
            self._clean_segments = build_clean_segments(transcription, filler_map)
            self._filler_map = filler_map

            # Phase 1にはフィラー除去済みテキストを渡す
            clean_by_idx: dict[int, list] = {}
            for cs in self._clean_segments:
                clean_by_idx.setdefault(cs.original_index, []).append(cs)
            for seg_idx, seg_dict in enumerate(segments_dicts):
                cs_list = clean_by_idx.get(seg_idx)
                if cs_list:
                    seg_dict["text"] = "".join(cs.clean_text for cs in cs_list)
                else:
                    # 全文フィラーのセグメント → 空文字
                    seg_dict["text"] = ""
        except Exception as e:
            logger.warning(f"Phase 0 フィラー検出スキップ: {e}")
            self._clean_segments = None
            self._filler_map = {}

        # Phase 1: AI話題検出
        import time

        phase1_start = time.time()
        request = TopicDetectionRequest(
            transcription_segments=segments_dicts,
            num_candidates=num_candidates,
            min_duration=min_duration,
            max_duration=max_duration,
            prompt_path=prompt_path,
        )
        detection_result = self.gateway.detect_topics(request, format_mode="individual")
        self.last_detection_result = detection_result

        logger.info(
            f"Phase 1: {len(detection_result.topics)} topics "
            f"({detection_result.processing_time:.1f}s, "
            f"${detection_result.estimated_cost_usd:.4f})"
        )

        # Phase 1.5: 話題境界の統合補正（旧1.5/1.6/1.8を統合）
        detection_result.topics = self._refine_topic_boundaries_unified(
            detection_result.topics, transcription, phase1_start
        )

        # Phase 1.7: 重複話題の除去
        detection_result.topics = self._deduplicate_topics(detection_result.topics)

        # Phase 2 & 3: 各話題に対して候補生成→AI選定（直列実行）
        # NOTE: gpt-4.1 の TPM 制限(30000)を超過しないよう並列→直列化
        topics = detection_result.topics
        if not topics:
            return []

        suggestions: list[tuple[int, ClipSuggestion]] = []
        for idx, topic in enumerate(topics):
            try:
                result = self._process_topic(topic, transcription, video_path, min_duration, max_duration)
            except Exception as e:
                logger.warning(f"トピック処理失敗 (idx={idx}): {e}")
                continue
            if result:
                suggestions.append((idx, result))

        return [s for _, s in suggestions]

    def _refine_topic_boundaries_unified(
        self,
        topics: list[TopicRange],
        transcription: TranscriptionResult,
        phase1_start: float,
    ) -> list[TopicRange]:
        """話題境界の統合補正（旧Phase 1.5/1.6/1.8を統合）。

        全セグメントをAIに送信し、trim/keep/extend を1回のAPI呼び出しで判定する。
        embeddingはスコアリング用にキャッシュするが、ハードカットは行わない。
        """
        import time

        if not topics:
            return topics

        # まずembedding計算（スコアリング用にキャッシュ）
        texts = [seg.text for seg in transcription.segments]
        embeddings = self.gateway.compute_embeddings(texts)
        if embeddings and len(embeddings) == len(texts):
            self._segment_embeddings = dict(enumerate(embeddings))

        # TPMリセット待機
        elapsed = time.time() - phase1_start
        wait_needed = max(0, 60 - elapsed)
        if wait_needed > 0 and topics:
            logger.info(f"Phase 1.5: TPMリセット待機 {wait_needed:.0f}s")
            time.sleep(wait_needed)

        max_seg_idx = len(transcription.segments) - 1
        for topic_i, topic in enumerate(topics):
            all_segs = [
                {
                    "index": i,
                    "text": transcription.segments[i].text,
                    "start": transcription.segments[i].start,
                    "end": transcription.segments[i].end,
                }
                for i in range(topic.segment_start_index, topic.segment_end_index + 1)
            ]
            ext_start = topic.segment_end_index + 1
            ext_end = min(topic.segment_end_index + 10, max_seg_idx)
            ext_segs = [
                {
                    "index": i,
                    "text": transcription.segments[i].text,
                    "start": transcription.segments[i].start,
                    "end": transcription.segments[i].end,
                }
                for i in range(ext_start, ext_end + 1)
            ]

            if topic_i > 0:
                time.sleep(1.0)  # レートリミット回避

            try:
                result = self.gateway.refine_topic_boundary(
                    title=topic.title,
                    all_segments=all_segs,
                    extension_candidates=ext_segs,
                )
            except Exception as e:
                logger.warning(f"Phase 1.5 境界補正失敗: {topic.title} — {e}")
                continue

            action = result.get("action", "keep")
            new_end = result.get("end_segment_index", topic.segment_end_index)
            is_complete = result.get("is_complete", True)

            # バリデーション
            new_end = max(topic.segment_start_index, min(new_end, max_seg_idx))

            if action == "trim" and new_end < topic.segment_end_index:
                logger.info(f"Phase 1.5 trim: '{topic.title}' seg_end {topic.segment_end_index}→{new_end}")
                topic.segment_end_index = new_end
            elif action == "extend" and new_end > topic.segment_end_index:
                logger.info(f"Phase 1.5 extend: '{topic.title}' seg_end {topic.segment_end_index}→{new_end}")
                topic.segment_end_index = new_end

            topic.is_complete = is_complete  # TopicRangeに属性を動的に追加
            logger.info(
                f"Phase 1.5: '{topic.title}' action={action}, is_complete={is_complete}"
                f" ({result.get('reason', '')})"
            )

        return topics

    @staticmethod
    def _deduplicate_topics(topics: list[TopicRange]) -> list[TopicRange]:
        """セグメント範囲が50%超重複する話題を除去する（低スコア側を削除）。"""
        if len(topics) <= 1:
            return topics

        to_remove: set[int] = set()
        for i in range(len(topics)):
            if i in to_remove:
                continue
            for j in range(i + 1, len(topics)):
                if j in to_remove:
                    continue
                si, ei = topics[i].segment_start_index, topics[i].segment_end_index
                sj, ej = topics[j].segment_start_index, topics[j].segment_end_index
                overlap_start = max(si, sj)
                overlap_end = min(ei, ej)
                if overlap_start > overlap_end:
                    continue
                overlap = overlap_end - overlap_start + 1
                shorter = min(ei - si + 1, ej - sj + 1)
                if overlap / shorter > 0.5:
                    # 低スコア側を除去
                    victim = j if topics[i].score >= topics[j].score else i
                    to_remove.add(victim)
                    logger.info(
                        f"重複話題除去: '{topics[victim].title}' "
                        f"('{topics[i].title}' と {overlap / shorter:.0%}重複)"
                    )

        result = [t for idx, t in enumerate(topics) if idx not in to_remove]
        if to_remove:
            logger.info(f"重複除去: {len(topics)}→{len(result)}話題")
        return result

    def _build_clean_text_map(self) -> dict[int, str]:
        """CleanSegmentsからセグメントindex→フィラー除去済みテキストのマップを構築する。"""
        clean_segments = getattr(self, "_clean_segments", None)
        if not clean_segments:
            return {}
        result: dict[int, str] = {}
        for cs in clean_segments:
            if cs.original_index in result:
                result[cs.original_index] += cs.clean_text
            else:
                result[cs.original_index] = cs.clean_text
        return result

    def _classify_segments(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
    ) -> list[dict] | None:
        """セグメントを essential/supportive/redundant に分類する。失敗時は None。"""
        clean_text_by_idx = self._build_clean_text_map()
        try:
            segments = []
            for i in range(topic.segment_start_index, topic.segment_end_index + 1):
                seg = transcription.segments[i]
                clean_text = clean_text_by_idx.get(i, seg.text)
                if not clean_text.strip():
                    continue
                segments.append(
                    {
                        "index": i,
                        "text": clean_text,
                        "start": seg.start,
                        "end": seg.end,
                    }
                )

            if not segments:
                return None

            classifications = self.gateway.classify_segment_essentiality(
                title=topic.title,
                segments=segments,
            )
            return classifications if classifications else None
        except Exception as e:
            logger.warning(f"セグメント分類失敗: {topic.title} — {e}")
            return None

    def _ai_select_segments(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
        min_duration: float,
        max_duration: float,
    ) -> list[ClipCandidate]:
        """AIにセグメントを直接選定させ、ClipCandidateリストを返す。失敗時は空リスト。"""
        from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, detect_noise_tag

        # CleanSegmentsからフィラー除去済みテキストを取得
        clean_text_by_idx = self._build_clean_text_map()

        segments_data = []
        pool = []
        for i in range(topic.segment_start_index, topic.segment_end_index + 1):
            seg = transcription.segments[i]
            clean_text = clean_text_by_idx.get(i, seg.text)
            if not clean_text.strip():
                continue
            if clean_text.strip() in FILLER_ONLY_TEXTS:
                continue
            if detect_noise_tag(clean_text.strip()):
                continue
            segments_data.append(
                {
                    "index": i,
                    "text": clean_text,
                    "start": seg.start,
                    "end": seg.end,
                }
            )
            pool.append((i, seg))

        if not segments_data:
            return []

        try:
            variants = self.gateway.select_clip_segments(
                title=topic.title,
                segments=segments_data,
                min_duration=min_duration,
                max_duration=max_duration,
                num_variants=2,
            )
        except Exception as e:
            logger.warning(f"AI segment selection API error: {e}")
            return []

        validated = []
        for indices in variants:
            candidate = validate_ai_selection(indices, pool, min_duration, max_duration)
            if candidate:
                validated.append(candidate)

        if validated:
            logger.info(f"AI segment selection: {len(validated)}/{len(variants)} variants validated")
        else:
            logger.info("AI segment selection: all variants failed validation")

        return validated

    def _process_topic(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
        video_path: Path,
        min_duration: float,
        max_duration: float,
    ) -> ClipSuggestion | None:

        if topic.score < MIN_TOPIC_SCORE:
            logger.info(f"低スコアスキップ: {topic.title} (score={topic.score})")
            return None

        # Phase 2a: AI直接セグメント選定を試行
        ai_candidates = self._ai_select_segments(topic, transcription, min_duration, max_duration)

        # Phase 2b: 文境界ベース候補生成（CleanSegmentがある場合）
        sentence_candidates: list[ClipCandidate] = []
        clean_segments = getattr(self, "_clean_segments", None)
        if clean_segments:
            try:
                from use_cases.ai.sentence_boundary_candidates import generate_sentence_boundary_candidates

                sentence_candidates = generate_sentence_boundary_candidates(
                    clean_segments, topic, min_duration, max_duration, transcription=transcription
                )
            except Exception as e:
                logger.debug(f"Phase 2b候補生成スキップ: {e}")

        # Phase 2a + 2b の統合（2cセグメント単位力任せは一旦スキップ）
        candidates = ai_candidates + sentence_candidates

        if not candidates:
            logger.warning(f"候補なし: {topic.title}")
            return None

        # 重複除去
        seen = set()
        unique = []
        for c in candidates:
            key = tuple(c.segment_indices)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        candidates = unique

        # フィラー除去済みテキストで元話題テキストを構築
        clean_text_by_idx = self._build_clean_text_map()
        original_text = "".join(
            clean_text_by_idx.get(i, transcription.segments[i].text)
            for i in range(topic.segment_start_index, topic.segment_end_index + 1)
        )

        # Phase 2.5a: Embedding類似度フィルタ
        candidates = self._filter_by_embedding_similarity(candidates, original_text)

        if not candidates:
            logger.warning(f"embeddingフィルタで全候補除外: {topic.title}")
            return None

        # 趣旨検証フィルタ
        # 未完結話題の場合、全候補invalidなら話題ごと破棄
        is_complete = getattr(topic, "is_complete", True)
        candidates = self._filter_by_thesis(topic.title, candidates, original_text=original_text)
        if not candidates:
            if not is_complete:
                logger.warning(f"未完結話題の全候補除外: {topic.title}")
            else:
                logger.warning(f"趣旨検証で全候補除外: {topic.title}")
            return None

        # 候補が1つだけならそのまま採用
        if len(candidates) == 1:
            best = candidates[0]
        else:
            # Phase 3: 上位候補の出来上がり音声をAIに評価させる
            best = self._ai_select_best(topic.title, candidates, video_path)

        if not best:
            return None

        # 結合部のmicro buffer追加（音声途切れ防止）
        buffered_ranges = self._apply_range_buffers(best.time_ranges)

        # topic境界の実時間を算出
        topic_start_time = transcription.segments[topic.segment_start_index].start
        topic_end_idx = min(topic.segment_end_index, len(transcription.segments) - 1)
        topic_end_time = transcription.segments[topic_end_idx].end

        return ClipSuggestion(
            id=best.segment_indices[0].__str__(),
            title=topic.title,
            text=best.text,
            time_ranges=buffered_ranges,
            total_duration=best.total_duration,
            score=topic.score,
            category=topic.category,
            reasoning=topic.reasoning,
            keywords=topic.keywords,
            variant_label=f"{len(best.segment_indices)}segs, score={best.mechanical_score:.0f}",
            topic_start_time=topic_start_time,
            topic_end_time=topic_end_time,
        )

    @staticmethod
    def _apply_range_buffers(
        time_ranges: list[tuple[float, float]],
        tail_buffer: float = 0.08,
        head_buffer: float = 0.05,
    ) -> list[tuple[float, float]]:
        """各rangeの末尾/先頭にmicro bufferを追加して結合部の音声途切れを防ぐ。

        - tail_buffer: range末尾を少し延長（最後の単語の残響を拾う）
        - head_buffer: range先頭を少し前倒し（最初の単語の立ち上がりを拾う）
        - 隣接rangeのギャップを超えないよう制限する
        """
        if len(time_ranges) <= 1:
            return time_ranges

        result = list(time_ranges)
        for i in range(len(result)):
            s, e = result[i]

            if i > 0:
                # 先頭バッファ: 前のrangeの末尾を超えない
                prev_end = result[i - 1][1]
                gap_before = s - prev_end
                actual_head = min(head_buffer, gap_before * 0.4)
                s = s - max(actual_head, 0)

            if i < len(result) - 1:
                # 末尾バッファ: 次のrangeの先頭を超えない
                next_start = time_ranges[i + 1][0]
                gap_after = next_start - e
                actual_tail = min(tail_buffer, gap_after * 0.4)
                e = e + max(actual_tail, 0)

            result[i] = (round(s, 3), round(e, 3))

        return result

    def _filter_by_embedding_similarity(
        self,
        candidates: list[ClipCandidate],
        original_text: str,
        min_similarity: float = 0.65,
    ) -> list[ClipCandidate]:
        """Embedding類似度で候補をフィルタ・ランキングする。

        元話題テキストと各候補テキストのcosine類似度を計算し:
        1. min_similarity未満の候補を除外
        2. similarity降順でランキング
        """
        if len(candidates) <= 1:
            return candidates

        # Embedding計算（バッチ処理）
        texts = [original_text] + [c.text[:500] for c in candidates]
        batch_size = 500
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                batch_embs = self.gateway.compute_embeddings(batch)
            except Exception as e:
                logger.warning(f"Embedding計算失敗（バッチ{i}）: {e}")
                return candidates  # 失敗時はフィルタなしで続行
            if not batch_embs:
                return candidates
            all_embeddings.extend(batch_embs)

        if len(all_embeddings) != len(texts):
            logger.warning(f"Embedding数不一致: {len(all_embeddings)} != {len(texts)}")
            return candidates

        topic_emb = all_embeddings[0]
        cand_embs = all_embeddings[1:]

        # cosine類似度計算 + フィルタ
        result: list[ClipCandidate] = []
        for c, emb in zip(candidates, cand_embs):
            sim = _cosine_similarity(topic_emb, emb)
            c.embedding_similarity = sim
            if sim >= min_similarity:
                result.append(c)

        if not result:
            # 全除外される場合は最も類似度の高いものを残す
            best_c = max(candidates, key=lambda c: c.embedding_similarity)
            logger.info(
                f"Embeddingフィルタ: 全候補が閾値{min_similarity}未満 "
                f"→ 最高sim={best_c.embedding_similarity:.3f}を残す"
            )
            return [best_c]

        # similarity降順でランキング
        result.sort(key=lambda c: c.embedding_similarity, reverse=True)

        # 多様性フィルタ: 内容パターン重複除去 + duration散らし
        # Step 1: 先頭80文字が同じ候補はグループの代表（最高sim）のみ残す
        pattern_pool: list[ClipCandidate] = []
        seen_prefixes: set[str] = set()
        for c in result:
            prefix = c.text[:80]
            if prefix not in seen_prefixes:
                seen_prefixes.add(prefix)
                pattern_pool.append(c)

        # Step 2: duration散らし + 末尾自然さで選出（greedy）
        # 最高simを1件目に選び、以降はduration差8秒以上の候補を優先
        # 同条件なら末尾が自然な候補を優先
        min_dur_gap = 8.0
        selected: list[ClipCandidate] = []
        remaining = list(pattern_pool)

        while remaining:
            if not selected:
                # 1件目: 最高sim（同simなら末尾自然な方）
                selected.append(remaining.pop(0))
            else:
                # duration差が十分な候補を集める
                dur_ok = [
                    (i, c) for i, c in enumerate(remaining)
                    if all(abs(c.total_duration - s.total_duration) >= min_dur_gap for s in selected)
                ]
                if dur_ok:
                    # duration差OKの中で冒頭+末尾自然さ最良 → sim最高の順で選ぶ
                    best_i, _ = max(
                        dur_ok,
                        key=lambda ic: (_boundary_naturalness_score(ic[1].text), ic[1].embedding_similarity),
                    )
                    selected.append(remaining.pop(best_i))
                else:
                    # duration差を満たす候補がない → 冒頭+末尾自然さ優先で次を取る
                    best_i = max(
                        range(len(remaining)),
                        key=lambda i: (_boundary_naturalness_score(remaining[i].text), remaining[i].embedding_similarity),
                    )
                    selected.append(remaining.pop(best_i))

        n_filtered = len(candidates) - len(result)
        n_deduped = len(result) - len(pattern_pool)
        if n_filtered > 0 or n_deduped > 0:
            logger.info(
                f"Embeddingフィルタ: {len(candidates)}→{len(result)}候補 "
                f"(sim={result[-1].embedding_similarity:.3f}~{result[0].embedding_similarity:.3f}, "
                f"除外{n_filtered}件, 重複統合{n_deduped}件→{len(pattern_pool)}パターン)"
            )

        return selected

    def _filter_by_thesis(
        self,
        title: str,
        candidates: list[ClipCandidate],
        original_text: str = "",
    ) -> list[ClipCandidate]:
        """趣旨検証: 各候補テキストが話題の趣旨を保っているか検証し、不適切な候補を除外する。"""
        if len(candidates) <= 1:
            return candidates

        # 上位5候補をAIに送信
        top = candidates[:5]
        api_input = [{"index": i, "text": c.text, "duration": c.total_duration} for i, c in enumerate(top)]

        try:
            valid_flags = self.gateway.validate_clip_candidates(
                title=title, candidates=api_input, original_text=original_text
            )
        except Exception as e:
            logger.warning(f"趣旨検証API失敗: {e}")
            return candidates

        if len(valid_flags) != len(top):
            return candidates

        filtered = [c for c, valid in zip(top, valid_flags, strict=True) if valid]
        # 上位5件以降の候補も保持
        rest = candidates[5:]

        if not filtered:
            # 全候補除外の場合、embedding similarity最高のものを1つ残す
            best = max(top, key=lambda c: c.embedding_similarity)
            logger.info(
                f"趣旨検証: 全候補invalid → sim最高を残す (sim={best.embedding_similarity:.3f})"
            )
            return [best] + rest

        result = filtered + rest
        if len(filtered) < len(top):
            logger.info(f"趣旨検証: {len(top)}→{len(filtered)}候補 ({title})")
        return result

    def _ai_select_best(
        self,
        title: str,
        candidates: list[ClipCandidate],
        video_path: Path,
    ) -> ClipCandidate | None:
        """上位候補の既存テキストを使ってAIに最良を選ばせる。"""
        # 各候補の既存テキストを使用
        transcriptions = [(i, cand.text) for i, cand in enumerate(candidates)]

        # AIに評価させる
        options = []
        for i, text in transcriptions:
            cand = candidates[i]
            options.append(
                f"候補{i+1}（{cand.total_duration:.0f}秒、{len(cand.time_ranges)}クリップ）:\n" f"{text}"
            )

        try:
            candidates_text = chr(10).join(options)
            selected_num = self.gateway.select_best_clip(
                title=title,
                candidates_text=candidates_text,
            )
            selected = max(0, min(selected_num - 1, len(candidates) - 1))
            logger.info(f"AI選定: 候補{selected+1} " f"({candidates[selected].total_duration:.0f}s)")
            return candidates[selected]

        except Exception as e:
            logger.warning(f"AI選定失敗: {e}")
            return candidates[0]
