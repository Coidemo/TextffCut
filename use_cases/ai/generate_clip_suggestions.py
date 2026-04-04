"""
AI切り抜き候補生成ユースケース（3段階パイプライン）

1. AI: 話題の時間範囲を検出
2. 機械: フィラー削除→トリミングパターン生成→品質スコア計算
3. AI: ベストパターンを選定
"""

from __future__ import annotations

import logging

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    ClipVariant,
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface
from use_cases.ai.mechanical_clip_editor import generate_clip_variants

logger = logging.getLogger(__name__)


class GenerateClipSuggestionsUseCase:
    """3段階パイプラインで切り抜き候補を生成する"""

    def __init__(self, gateway: ClipSuggestionGatewayInterface):
        self.gateway = gateway

    def execute(
        self,
        transcription: TranscriptionResult,
        num_candidates: int = 5,
        min_duration: int = 30,
        max_duration: int = 60,
        prompt_path: str | None = None,
    ) -> list[ClipSuggestion]:
        """
        Returns:
            最終的な切り抜き候補リスト
        """
        segments_dicts = [
            {"text": seg.text, "start": seg.start, "end": seg.end}
            for seg in transcription.segments
        ]

        # Phase 1: AI — 話題範囲を検出
        request = TopicDetectionRequest(
            transcription_segments=segments_dicts,
            num_candidates=num_candidates,
            min_duration=min_duration,
            max_duration=max_duration,
            prompt_path=prompt_path,
        )
        detection_result = self.gateway.detect_topics(request)
        self.last_detection_result = detection_result

        logger.info(
            f"Phase 1: {len(detection_result.topics)} topics detected "
            f"({detection_result.processing_time:.1f}s, "
            f"${detection_result.estimated_cost_usd:.4f})"
        )

        # Phase 2 & 3: 各話題に対して機械的編集→AI選定
        suggestions = []
        for topic in detection_result.topics:
            suggestion = self._process_topic(
                topic, transcription, min_duration, max_duration
            )
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _process_topic(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
        min_duration: float,
        max_duration: float,
    ) -> ClipSuggestion | None:
        """1つの話題に対して機械的編集→AI選定を行う"""

        # Phase 2: 機械的パターン生成
        variants = generate_clip_variants(
            topic, transcription, min_duration, max_duration
        )

        if not variants:
            logger.warning(f"話題「{topic.title}」: パターン生成なし")
            return None

        logger.info(
            f"話題「{topic.title}」: {len(variants)}パターン生成 "
            f"(best: {variants[0].label}, {variants[0].total_duration:.0f}s, "
            f"score: {variants[0].quality_score:.0f})"
        )

        # Phase 3: AI選定（パターンが複数ある場合のみ）
        if len(variants) > 1:
            variant_dicts = [
                {
                    "label": v.label,
                    "text": v.text,
                    "duration": v.total_duration,
                }
                for v in variants
            ]
            selected_idx = self.gateway.select_best_variant(
                topic.title, variant_dicts
            )
            if selected_idx is not None:
                best = variants[selected_idx]
            else:
                best = variants[0]
        else:
            best = variants[0]

        return ClipSuggestion(
            id=best.id,
            title=topic.title,
            text=best.text,
            time_ranges=best.time_ranges,
            total_duration=best.total_duration,
            score=topic.score,
            category=topic.category,
            reasoning=topic.reasoning,
            keywords=topic.keywords,
            variant_label=best.label,
        )
