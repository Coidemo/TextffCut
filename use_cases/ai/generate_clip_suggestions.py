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

        # Phase 2a: AI直接セグメント選定を試行
        ai_candidates = self._ai_select_segments(topic, transcription, min_duration, max_duration)

        # embeddingキャッシュ取得
        emb_cache = getattr(self, "_segment_embeddings", None)

        # Phase 2b: 文境界ベース候補生成（CleanSegmentがある場合）
        sentence_candidates: list[ClipCandidate] = []
        clean_segments = getattr(self, "_clean_segments", None)
        if clean_segments:
            try:
                from use_cases.ai.sentence_boundary_candidates import generate_sentence_boundary_candidates

                sentence_candidates = generate_sentence_boundary_candidates(
                    clean_segments, topic, min_duration, max_duration, transcription=transcription
                )
                # スコア計算
                for c in sentence_candidates:
                    c.mechanical_score = _calculate_score(c, min_duration, max_duration, embeddings=emb_cache)
            except Exception as e:
                logger.debug(f"Phase 2b候補生成スキップ: {e}")

        # Phase 2c: セグメント単位力任せ候補生成
        classifications = self._classify_segments(topic, transcription)
        brute_candidates = generate_candidates(
            topic,
            transcription,
            min_duration,
            max_duration,
            segment_classifications=classifications,
            embeddings=emb_cache,
        )

        # 3戦略の統合
        if ai_candidates:
            candidates = ai_candidates + sentence_candidates + brute_candidates[:3]
        else:
            logger.info(f"AI segment selection failed, fallback to brute-force: {topic.title}")
            candidates = sentence_candidates + brute_candidates

        if not candidates:
            logger.warning(f"候補なし: {topic.title}")
            return None

        # 重複除去 + スコア順ソート
        seen = set()
        unique = []
        for c in candidates:
            key = tuple(c.segment_indices)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        candidates = sorted(unique, key=lambda c: c.mechanical_score, reverse=True)

        # 趣旨検証フィルタ（フィラー除去済みテキスト）
        clean_text_by_idx = self._build_clean_text_map()
        original_text = "".join(
            clean_text_by_idx.get(i, transcription.segments[i].text)
            for i in range(topic.segment_start_index, topic.segment_end_index + 1)
        )
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

        # 候補先頭の文途中チェック: 前セグメントが未完結なら開始位置を調整
        best = self._fix_candidate_start(best, transcription, min_duration)

        # 候補末尾の完結チェック: 候補の最終セグメントが未完結なら拡張
        best = self._fix_candidate_ending(best, topic, transcription, max_duration)

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

    @staticmethod
    def _fix_candidate_start(
        best: ClipCandidate,
        transcription: TranscriptionResult,
        min_duration: float,
    ) -> ClipCandidate:
        """候補の先頭が文途中から始まっている場合、開始位置を調整する。

        候補テキストの先頭トークンをGiNZA解析し：
        - 助詞・助動詞で始まる → 常にトリム（前文の残り）
        - 動詞+接続助詞 → 前セグメントが未完結の場合のみトリム
        - 名詞・副詞等 → 問題なし
        """
        from core.japanese_line_break import JapaneseLineBreakRules

        if not best.segment_indices or not best.segments:
            return best

        # 候補先頭をGiNZA解析
        boundaries = JapaneseLineBreakRules.get_word_boundaries_with_pos(
            best.text[:40]
        )
        if not boundaries:
            return best

        first_end_pos, first_word, first_tag = boundaries[0]
        first_base = first_tag.split("-")[0]

        # 文頭として自然な品詞 → トリム不要
        _GOOD_START = {"名詞", "副詞", "形容詞", "感動詞", "連体詞", "接続詞", "代名詞"}
        # 接続節の末尾位置（この位置以降から新しい文頭を探す）
        skip_to = 0

        # 形式名詞（とき/ため/こと/もの/ほう/わけ等）は依存節マーカーであり
        # 文頭として不自然 → トリム対象
        _FORMAL_NOUNS = {"とき", "ため", "こと", "もの", "ほう", "わけ", "はず"}
        if first_base in _GOOD_START and first_word not in _FORMAL_NOUNS:
            return best
        if first_base == "動詞" and len(first_word) >= 2:
            # 動詞始まりは2段階判定:
            # (1) 前セグメントが文完結なら信頼 → return
            # (2) 未完結かつ直後に接続助詞 → トリム
            first_idx = best.segment_indices[0]
            if first_idx > 0:
                prev_text = transcription.segments[first_idx - 1].text.rstrip()
                if JapaneseLineBreakRules.is_sentence_complete(prev_text):
                    return best

            is_continuation = False
            for ep, w, tag in boundaries[1:5]:
                if tag == "助詞-接続助詞":
                    is_continuation = True
                    skip_to = ep
                    break
                # 動詞+「と」も接続パターン（「いうと」「すると」等）
                if tag.startswith("助詞") and w == "と":
                    is_continuation = True
                    skip_to = ep
                    break
                if tag.split("-")[0] in _GOOD_START:
                    break
            if not is_continuation:
                return best

        # 助詞・助動詞・1文字動詞・接続節 → 前文の残りと判断（常にトリム）

        # 助詞・助動詞・1文字動詞・接続節 → 前文の残りと判断
        # skip_to以降で最初の自然な文頭トークンの位置を探す
        trim_pos = 0
        for end_pos, word, tag in boundaries:
            word_start = end_pos - len(word)
            if word_start < skip_to:
                continue
            base = tag.split("-")[0]
            if base in _GOOD_START or (base == "動詞" and len(word) >= 2):
                trim_pos = word_start
                break

        if trim_pos == 0 or trim_pos > len(best.text) * 0.3:
            return best  # トリム位置が見つからない or 多すぎる

        # テキストのトリム + time_ranges調整
        trimmed_prefix = best.text[:trim_pos]
        first_seg = best.segments[0]
        seg_chars = len(first_seg.text)
        if seg_chars > 0 and best.time_ranges:
            seg_duration = first_seg.end - first_seg.start
            time_per_char = seg_duration / seg_chars
            trim_time = trim_pos * time_per_char
            old_start, old_end = best.time_ranges[0]
            new_start = min(old_start + trim_time, old_end - 0.1)
            best.time_ranges[0] = (new_start, old_end)

        best.text = best.text[trim_pos:]
        best.total_duration = sum(e - s for s, e in best.time_ranges)
        logger.info(
            f"候補先頭トリム: '{trimmed_prefix}' 除去 → "
            f"'{best.text[:20]}...' ({best.total_duration:.1f}s)"
        )
        return best

    @staticmethod
    def _fix_candidate_ending(
        best: ClipCandidate,
        topic: TopicRange,
        transcription: TranscriptionResult,
        max_duration: float,
    ) -> ClipCandidate:
        """候補の最終セグメントが文未完結なら、topic範囲内の次セグメントを追加して完結させる。

        また、最終time_rangeにバッファを追加し、無音削除→Whisper再文字起こし時に
        文末が確実に含まれるようにする。
        """
        from core.japanese_line_break import JapaneseLineBreakRules

        last_idx = best.segment_indices[-1]
        last_text = best.segments[-1].text.rstrip()

        # topic境界内で最大8セグメント拡張 + 境界超えも最大5セグメント許容
        # （Phase 1.8が失敗した場合でも末尾完結を保証するため）
        hard_limit = min(topic.segment_end_index + 5, len(transcription.segments) - 1)
        for _ in range(8):
            if JapaneseLineBreakRules.is_sentence_complete(last_text):
                break
            next_idx = last_idx + 1
            if next_idx > hard_limit:
                break

            next_seg = transcription.segments[next_idx]
            added_dur = next_seg.end - next_seg.start
            if best.total_duration + added_dur > max_duration * 1.2:
                break

            # セグメント追加
            best.segments.append(next_seg)
            best.segment_indices.append(next_idx)
            best.text += next_seg.text

            # time_ranges更新（0.5秒以内のギャップならマージ）
            if best.time_ranges and next_seg.start - best.time_ranges[-1][1] <= 0.5:
                best.time_ranges[-1] = (best.time_ranges[-1][0], next_seg.end)
            else:
                best.time_ranges.append((next_seg.start, next_seg.end))
            best.total_duration = sum(e - s for s, e in best.time_ranges)

            last_idx = next_idx
            last_text = next_seg.text.rstrip()
            logger.info(f"候補末尾拡張: seg[{next_idx}] 追加 → {best.total_duration:.0f}s")

        return best

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
        api_input = [{"index": i, "text": c.text[:300], "duration": c.total_duration} for i, c in enumerate(top)]

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
            # 全候補除外の場合、機械スコア最高のものを1つ残す
            best_mechanical = max(top, key=lambda c: c.mechanical_score)
            logger.info(
                f"趣旨検証: 全候補invalid → 機械スコア最高を残す (score={best_mechanical.mechanical_score:.0f})"
            )
            return [best_mechanical] + rest

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
