"""
AI切り抜き候補生成ユースケース

1. AI: 話題の時間範囲を検出 (Phase 1)
2. Phase 2c: 骨子+結びベース候補生成
3. AI: 既存テキストで最良候補を選定 (Phase 3)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface
from use_cases.ai.brute_force_clip_generator import ClipCandidate

logger = logging.getLogger(__name__)

MIN_TOPIC_SCORE = 8  # Phase 1 で低スコア話題をスキップする閾値

# 末尾の自然さ判定パターン（文字列フォールバック用）
_GOOD_ENDINGS_HIGH = ("です", "ます", "ました", "思います", "しれません")
_GOOD_ENDINGS_MEDIUM = (
    "ですね",
    "ますね",
    "ですよね",
    "よね",
    "んですよ",
    "んです",
    "ですか",
    "ですかね",
    "ませんか",
)
_DEFINITELY_INCOMPLETE = (
    "ので",
    "から",
    "けど",
    "けれども",
    "んですけど",
    "っていうのは",
    "んですけれども",
    "なんですけど",
)
_LIKELY_INCOMPLETE = (
    "って",
    "のが",
    "みたいな",
    "とか",
    "たら",
    "のは",
    "て",
    "より",
    "ながら",
    "つつ",
    "ものの",
    "にも",
    "を",
)

# 接続助詞（末尾に来ると不自然）
_CONJUNCTIVE_PARTICLES = frozenset(("から", "けど", "ので", "って", "のが", "たら", "て", "より", "ながら", "つつ"))
# 終助詞（末尾に来ると自然）
_FINAL_PARTICLES = frozenset(("よ", "ね", "わ", "な", "さ"))


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
            recent_poses = [JapaneseLineBreakRules._normalize_pos_tag(tk.tag_).split("-")[0] for tk in doc[-3:]]
            has_predicate = any(p in ("助動詞", "動詞", "形容詞") for p in recent_poses)
            if not has_predicate and pos_major == "助詞" and token_text not in _FINAL_PARTICLES and token_text != "か":
                score -= 5

        return score
    except Exception:
        return 0


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

        # Phase 1: AI話題検出
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
                result = self._process_topic(topic, transcription, min_duration, max_duration)
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
        if not topics:
            return topics

        # TPMリセット待機
        elapsed = time.time() - phase1_start
        wait_needed = max(0, 60 - elapsed)
        if wait_needed > 0 and topics:
            logger.info(f"Phase 1.5: TPMリセット待機 {wait_needed:.0f}s")
            time.sleep(wait_needed)

        max_seg_idx = len(transcription.segments) - 1
        for topic_i, topic in enumerate(topics):
            # 意図的にraw text使用: AIが境界判定するため、フィラー除去前の原文が必要
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

    def _process_topic(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
        min_duration: float,
        max_duration: float,
    ) -> ClipSuggestion | None:

        if topic.score < MIN_TOPIC_SCORE:
            logger.info(f"低スコアスキップ: {topic.title} (score={topic.score})")
            return None

        # Phase 2: 骨子+結びベース候補生成
        candidates: list[ClipCandidate] = []
        try:
            from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, detect_noise_tag

            clean_text_by_idx = self._build_clean_text_map()
            segments_for_cc = []
            cc_to_local: list[int] = []
            for local_idx, global_idx in enumerate(range(topic.segment_start_index, topic.segment_end_index + 1)):
                seg = transcription.segments[global_idx]
                clean_text = clean_text_by_idx.get(global_idx, seg.text)
                if not clean_text.strip() or clean_text.strip() in FILLER_ONLY_TEXTS:
                    continue
                if detect_noise_tag(clean_text.strip()):
                    continue
                segments_for_cc.append({"idx": len(segments_for_cc), "text": clean_text})
                cc_to_local.append(local_idx)

            if segments_for_cc:
                result = self.gateway.find_core_and_conclusion(
                    title=topic.title,
                    segments=segments_for_cc,
                )
                cores = result.get("core", [])
                conclusions = result.get("conclusion", [])
                if cores and conclusions:
                    from use_cases.ai.core_conclusion_candidates import (
                        generate_core_conclusion_candidates,
                    )

                    candidates = generate_core_conclusion_candidates(
                        topic,
                        transcription,
                        cores,
                        conclusions,
                        min_duration,
                        max_duration,
                        cc_to_local=cc_to_local,
                    )
                    logger.info(f"Phase 2: {len(candidates)}候補 ({topic.title})")
        except Exception as e:
            logger.warning(f"Phase 2候補生成スキップ: {e}")

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

        # 末尾不完全候補のハードフィルタ
        good = [c for c in candidates if _ending_naturalness_score(c.text) >= -10]
        if good:
            n_removed = len(candidates) - len(good)
            if n_removed:
                logger.info(f"末尾フィルタ: {len(candidates)}→{len(good)}候補 ({topic.title})")
            candidates = good

        if not candidates:
            logger.warning(f"全候補除外: {topic.title}")
            return None

        # 候補が1つだけならそのまま採用
        if len(candidates) == 1:
            best = candidates[0]
        else:
            # Phase 3: 上位候補の出来上がり音声をAIに評価させる
            best = self._ai_select_best(topic.title, candidates)

        if not best:
            return None

        # Phase 3.5: 吃音（言い淀み）除去
        try:
            from use_cases.ai.stammering_remover import remove_stammering

            cleaned_text, cleaned_ranges, cleaned_dur = remove_stammering(best.text, best.segments, best.time_ranges)
            if cleaned_ranges != best.time_ranges:
                logger.info(f"吃音除去: {best.total_duration:.1f}s→{cleaned_dur:.1f}s ({topic.title})")
                best.text = cleaned_text
                best.time_ranges = cleaned_ranges
                best.total_duration = cleaned_dur
        except Exception as e:
            logger.debug(f"吃音除去スキップ: {e}")

        # 結合部のmicro buffer追加（音声途切れ防止）
        buffered_ranges = self._apply_range_buffers(best.time_ranges)

        # topic境界の実時間を算出
        topic_start_time = transcription.segments[topic.segment_start_index].start
        topic_end_idx = min(topic.segment_end_index, len(transcription.segments) - 1)
        topic_end_time = transcription.segments[topic_end_idx].end

        return ClipSuggestion(
            id=str(best.segment_indices[0]),
            title=topic.title,
            text=best.text,
            time_ranges=buffered_ranges,
            total_duration=best.total_duration,
            score=topic.score,
            category=topic.category,
            reasoning=topic.reasoning,
            keywords=topic.keywords,
            variant_label=f"{len(best.segment_indices)}segs",
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
                next_start = result[i + 1][0]
                gap_after = next_start - e
                actual_tail = min(tail_buffer, gap_after * 0.4)
                e = e + max(actual_tail, 0)

            result[i] = (round(s, 3), round(e, 3))

        return result

    def _ai_select_best(
        self,
        title: str,
        candidates: list[ClipCandidate],
    ) -> ClipCandidate | None:
        """上位候補の既存テキストを使ってAIに最良を選ばせる。"""
        # 各候補の既存テキストを使用
        transcriptions = [(i, cand.text) for i, cand in enumerate(candidates)]

        # AIに評価させる
        options = []
        for i, text in transcriptions:
            cand = candidates[i]
            options.append(f"候補{i+1}（{cand.total_duration:.0f}秒、{len(cand.time_ranges)}クリップ）:\n" f"{text}")

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
