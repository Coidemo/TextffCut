"""
AI切り抜き候補生成のユニットテスト

domain/entities のエンティティと brute_force_clip_generator のデータ構造を検証する。
外部API依存なし。
"""

import uuid

import pytest

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    ClipVariant,
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from use_cases.ai.brute_force_clip_generator import (
    ClipCandidate,
    _build_candidate,
)


# --- Helpers ---


def _make_segment(text: str, start: float, end: float) -> TranscriptionSegment:
    return TranscriptionSegment(
        id=str(uuid.uuid4()),
        text=text,
        start=start,
        end=end,
        words=[],
    )


def _make_segments(
    texts: list[str],
    duration_each: float = 5.0,
) -> list[TranscriptionSegment]:
    """テスト用セグメントを生成する。"""
    segments = []
    t = 0.0
    for text in texts:
        segments.append(_make_segment(text, t, t + duration_each))
        t += duration_each
    return segments


def _make_transcription(texts: list[str], duration_each: float = 5.0) -> TranscriptionResult:
    segs = _make_segments(texts, duration_each)
    total_dur = len(texts) * duration_each
    return TranscriptionResult(
        id=str(uuid.uuid4()),
        video_id="test-video",
        language="ja",
        segments=segs,
        duration=total_dur,
    )


# --- TopicRange ---


class TestTopicRange:

    def test_create(self):
        t = TopicRange.create(
            title="テスト話題",
            segment_start_index=0,
            segment_end_index=10,
            score=15,
            category="仕事術",
            reasoning="理由",
            keywords=["kw1"],
        )
        assert t.title == "テスト話題"
        assert t.segment_start_index == 0
        assert t.segment_end_index == 10
        assert t.score == 15
        assert t.id is not None

    def test_to_dict_and_from_dict(self):
        t = TopicRange.create(
            title="タイトル",
            segment_start_index=1,
            segment_end_index=5,
            score=10,
            category="ライフハック",
            reasoning="いい内容",
            keywords=["a", "b"],
        )
        d = t.to_dict()
        restored = TopicRange.from_dict(d)
        assert restored.title == "タイトル"
        assert restored.segment_start_index == 1
        assert restored.segment_end_index == 5
        assert restored.score == 10
        assert restored.keywords == ["a", "b"]

    def test_from_dict_with_defaults(self):
        d = {
            "title": "最小",
            "segment_start_index": 0,
            "segment_end_index": 0,
        }
        t = TopicRange.from_dict(d)
        assert t.title == "最小"
        assert t.score == 0
        assert t.category == ""
        assert t.keywords == []


# --- ClipVariant ---


class TestClipVariant:

    def test_create(self):
        v = ClipVariant.create(
            topic_id="topic-1",
            text="テストテキスト",
            time_ranges=[(1.0, 5.0), (7.0, 10.0)],
            quality_score=80.0,
            label="フル版",
        )
        assert v.topic_id == "topic-1"
        assert v.total_duration == pytest.approx(7.0)
        assert v.label == "フル版"
        assert v.id is not None

    def test_create_empty_ranges(self):
        v = ClipVariant.create(
            topic_id="t",
            text="",
            time_ranges=[],
        )
        assert v.total_duration == 0.0


# --- ClipSuggestion ---


class TestClipSuggestion:

    def test_to_dict_and_from_dict(self):
        s = ClipSuggestion(
            id="test-id",
            title="タイトル",
            text="テキスト",
            time_ranges=[(1.0, 5.0), (7.0, 10.0)],
            total_duration=7.0,
            score=15,
            category="仕事術",
            reasoning="理由",
            keywords=["a"],
            variant_label="3segs",
        )
        d = s.to_dict()
        restored = ClipSuggestion.from_dict(d)
        assert restored.title == "タイトル"
        assert restored.time_ranges == [(1.0, 5.0), (7.0, 10.0)]
        assert restored.total_duration == 7.0
        assert restored.variant_label == "3segs"

    def test_from_dict_with_defaults(self):
        d = {"title": "最小"}
        s = ClipSuggestion.from_dict(d)
        assert s.title == "最小"
        assert s.time_ranges == []
        assert s.total_duration == 0.0
        assert s.variant_label == ""


# --- TopicDetectionRequest / Result ---


class TestTopicDetectionRequest:

    def test_defaults(self):
        r = TopicDetectionRequest(
            transcription_segments=[],
        )
        assert r.num_candidates == 5
        assert r.min_duration == 30
        assert r.max_duration == 60
        assert r.prompt_path is None

    def test_custom_values(self):
        r = TopicDetectionRequest(
            transcription_segments=[{"text": "a", "start": 0, "end": 1}],
            num_candidates=10,
            min_duration=15,
            max_duration=45,
            prompt_path="/custom/prompt.md",
        )
        assert r.num_candidates == 10
        assert r.min_duration == 15


class TestTopicDetectionResult:

    def test_creation(self):
        topic = TopicRange.create(
            title="話題1",
            segment_start_index=0,
            segment_end_index=5,
        )
        result = TopicDetectionResult(
            topics=[topic],
            model_used="gpt-4.1-mini",
            processing_time=1.5,
            token_usage={"prompt_tokens": 100, "completion_tokens": 50},
            estimated_cost_usd=0.001,
        )
        assert len(result.topics) == 1
        assert result.model_used == "gpt-4.1-mini"
        assert result.estimated_cost_usd == 0.001


# --- brute_force_clip_generator ---


class TestBuildCandidate:

    def test_basic(self):
        segs = _make_segments(["こんにちは", "今日は天気です", "ありがとう"])
        seg_list = [(i, seg) for i, seg in enumerate(segs)]
        c = _build_candidate(seg_list)
        assert c is not None
        assert c.total_duration == pytest.approx(15.0)
        assert len(c.segment_indices) == 3
        assert c.text == "こんにちは今日は天気ですありがとう"

    def test_empty_list(self):
        assert _build_candidate([]) is None

    def test_too_short_duration(self):
        """合計5秒未満は None を返す"""
        segs = _make_segments(["短い"], duration_each=3.0)
        c = _build_candidate([(0, segs[0])])
        assert c is None

    def test_merge_close_ranges(self):
        """0.5秒以内のギャップはマージされる"""
        seg1 = _make_segment("A", 0.0, 3.0)
        seg2 = _make_segment("B", 3.3, 6.0)  # 0.3s gap
        seg3 = _make_segment("C", 7.0, 10.0)  # 1.0s gap
        c = _build_candidate([(0, seg1), (1, seg2), (2, seg3)])
        assert c is not None
        # seg1-seg2はマージ、seg3は別range
        assert len(c.time_ranges) == 2


