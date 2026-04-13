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
    _calculate_score,
    generate_candidates,
    validate_ai_selection,
)

logger = logging.getLogger(__name__)

MIN_TOPIC_SCORE = 8  # Phase 1 で低スコア話題をスキップする閾値


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

        # Phase 1: AI話題検出
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

        # Phase 1.5: embedding cosine類似度でtopic境界を補正
        detection_result.topics = self._refine_topic_boundaries(detection_result.topics, transcription)

        # Phase 2 & 3: 各話題に対して候補生成→AI選定（並列実行）
        from concurrent.futures import ThreadPoolExecutor, as_completed

        topics = detection_result.topics
        suggestions: list[tuple[int, ClipSuggestion]] = []
        with ThreadPoolExecutor(max_workers=min(len(topics), 5)) as executor:
            futures = {
                executor.submit(
                    self._process_topic, topic, transcription, video_path, min_duration, max_duration
                ): idx
                for idx, topic in enumerate(topics)
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    suggestions.append((futures[future], result))

        # トピック順にソート
        suggestions.sort(key=lambda x: x[0])
        return [s for _, s in suggestions]

    def _refine_topic_boundaries(
        self,
        topics: list[TopicRange],
        transcription: TranscriptionResult,
    ) -> list[TopicRange]:
        """embedding cosine類似度の急変点でtopic境界を補正する。"""
        if not topics:
            return topics

        texts = [seg.text for seg in transcription.segments]
        if not texts:
            return topics

        embeddings = self.gateway.compute_embeddings(texts)
        if not embeddings or len(embeddings) != len(texts):
            logger.info("Embedding取得失敗 → 境界補正スキップ")
            return topics

        # 全セグメントのembeddingをキャッシュ（層2-3で再利用）
        self._segment_embeddings = {i: emb for i, emb in enumerate(embeddings)}

        for topic in topics:
            start_idx = topic.segment_start_index
            end_idx = topic.segment_end_index
            if end_idx - start_idx < 3:
                continue

            # topic範囲内の隣接セグメント間cosine類似度を計算
            original_end = end_idx
            for i in range(end_idx, start_idx, -1):
                sim = _cosine_similarity(embeddings[i - 1], embeddings[i])
                if sim < 0.3:
                    # 類似度が急落 → ここが話題の境界
                    topic.segment_end_index = i - 1
                    logger.info(
                        f"boundary refined: {topic.title} seg_end {original_end}→{topic.segment_end_index} "
                        f"(cosine={sim:.2f})"
                    )
                    break

        return topics

    def _classify_segments(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
    ) -> list[dict] | None:
        """セグメントを essential/supportive/redundant に分類する。失敗時は None。"""
        try:
            segments = []
            for i in range(topic.segment_start_index, topic.segment_end_index + 1):
                seg = transcription.segments[i]
                segments.append(
                    {
                        "index": i,
                        "text": seg.text,
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

        segments_data = []
        pool = []
        for i in range(topic.segment_start_index, topic.segment_end_index + 1):
            seg = transcription.segments[i]
            if seg.text.strip() in FILLER_ONLY_TEXTS:
                continue
            if detect_noise_tag(seg.text.strip()):
                continue
            segments_data.append(
                {
                    "index": i,
                    "text": seg.text,
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

        # embeddingキャッシュ取得
        emb_cache = getattr(self, "_segment_embeddings", None)

        validated = []
        for indices in variants:
            candidate = validate_ai_selection(indices, pool, min_duration, max_duration)
            if candidate:
                candidate.mechanical_score = (
                    _calculate_score(
                        candidate,
                        min_duration,
                        max_duration,
                        embeddings=emb_cache,
                    )
                    + 20
                )  # 通常スコア + AI選定ボーナス
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

        # Phase 2: AI直接セグメント選定を試行
        ai_candidates = self._ai_select_segments(topic, transcription, min_duration, max_duration)

        # embeddingキャッシュ取得
        emb_cache = getattr(self, "_segment_embeddings", None)

        if ai_candidates:
            # AI選定成功 → AI候補を先頭に、力任せ上位をフォールバックとして追加
            classifications = self._classify_segments(topic, transcription)
            brute_candidates = generate_candidates(
                topic,
                transcription,
                min_duration,
                max_duration,
                segment_classifications=classifications,
                embeddings=emb_cache,
            )
            candidates = ai_candidates + brute_candidates[:3]
        else:
            # フォールバック: 既存フロー
            logger.info(f"AI segment selection failed, fallback to brute-force: {topic.title}")
            classifications = self._classify_segments(topic, transcription)
            candidates = generate_candidates(
                topic,
                transcription,
                min_duration,
                max_duration,
                segment_classifications=classifications,
                embeddings=emb_cache,
            )

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

        # 候補が1つだけならそのまま採用
        if len(candidates) == 1:
            best = candidates[0]
        else:
            # Phase 3: 上位候補の出来上がり音声をAIに評価させる
            best = self._ai_select_best(topic.title, candidates, video_path)

        if not best:
            return None

        # topic境界の実時間を算出
        topic_start_time = transcription.segments[topic.segment_start_index].start
        topic_end_idx = min(topic.segment_end_index, len(transcription.segments) - 1)
        topic_end_time = transcription.segments[topic_end_idx].end

        return ClipSuggestion(
            id=best.segment_indices[0].__str__(),
            title=topic.title,
            text=best.text,
            time_ranges=best.time_ranges,
            total_duration=best.total_duration,
            score=topic.score,
            category=topic.category,
            reasoning=topic.reasoning,
            keywords=topic.keywords,
            variant_label=f"{len(best.segment_indices)}segs, score={best.mechanical_score:.0f}",
            topic_start_time=topic_start_time,
            topic_end_time=topic_end_time,
        )

    def _ai_select_best(
        self,
        title: str,
        candidates: list[ClipCandidate],
        video_path: Path,
    ) -> ClipCandidate | None:
        """上位候補の既存テキストを使ってAIに最良を選ばせる。"""
        # 音響分析で候補をリランキング
        try:
            from use_cases.ai.audio_naturalness import analyze_join_naturalness

            for cand in candidates:
                if len(cand.time_ranges) >= 2:
                    joins = analyze_join_naturalness(video_path, cand.time_ranges)
                    unnatural_count = sum(1 for j in joins if not j.is_natural)
                    cand.mechanical_score -= unnatural_count * 10
            candidates.sort(key=lambda c: c.mechanical_score, reverse=True)
        except Exception as e:
            logger.debug(f"音響分析スキップ: {e}")

        # 各候補の既存テキストを使用（Whisper再文字起こし廃止）
        transcriptions = [(i, cand.text[:300]) for i, cand in enumerate(candidates)]

        # AIに評価させる
        options = []
        for i, text in transcriptions:
            cand = candidates[i]
            options.append(
                f"候補{i+1}（{cand.total_duration:.0f}秒、{len(cand.time_ranges)}クリップ）:\n" f"{text[:300]}"
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

