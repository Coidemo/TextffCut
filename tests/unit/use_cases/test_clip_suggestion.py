"""
AI切り抜き候補生成のユニットテスト

domain/entities のエンティティと brute_force_clip_generator のスコアリングロジックを検証する。
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
    generate_candidates,
    _build_candidate,
    _calculate_score,
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


class TestCalculateScore:

    def _make_candidate(
        self,
        text: str = "テスト" * 10,
        total_duration: float = 45.0,
        time_ranges: list[tuple[float, float]] | None = None,
        segments: list[TranscriptionSegment] | None = None,
    ) -> ClipCandidate:
        if time_ranges is None:
            time_ranges = [(0.0, total_duration)]
        if segments is None:
            segments = [_make_segment(text, 0, total_duration)]
        return ClipCandidate(
            segments=segments,
            segment_indices=[0],
            text=text,
            time_ranges=time_ranges,
            total_duration=total_duration,
        )

    def test_in_range_bonus(self):
        """デュレーションが範囲内なら50+のスコア"""
        c = self._make_candidate(total_duration=45.0)
        score = _calculate_score(c, 30.0, 60.0)
        assert score > 50.0

    def test_center_is_best(self):
        """範囲の中央値に近いほど高スコア"""
        c_center = self._make_candidate(total_duration=45.0)
        c_edge = self._make_candidate(total_duration=59.0)
        assert _calculate_score(c_center, 30.0, 60.0) > _calculate_score(c_edge, 30.0, 60.0)

    def test_out_of_range_penalty(self):
        """範囲外はペナルティ"""
        c_out = self._make_candidate(text="テスト" * 50, total_duration=120.0)
        c_in = self._make_candidate(text="テスト" * 50, total_duration=45.0)
        score_out = _calculate_score(c_out, 30.0, 60.0)
        score_in = _calculate_score(c_in, 30.0, 60.0)
        assert score_out < score_in, f"範囲外({score_out})は範囲内({score_in})より低スコアであるべき"

    def test_single_range_bonus(self):
        """time_rangesが1つだとボーナス"""
        c1 = self._make_candidate(time_ranges=[(0, 45)])
        c_multi = self._make_candidate(
            time_ranges=[(0, 10), (12, 22), (24, 34), (36, 45), (47, 57), (59, 65), (67, 72), (74, 80), (82, 88)],
            total_duration=45.0,
        )
        assert _calculate_score(c1, 30.0, 60.0) > _calculate_score(c_multi, 30.0, 60.0)

    def test_good_ending_bonus(self):
        """良い文末はボーナス"""
        c_good = self._make_candidate(text="AIを活用すると生産性が上がります")
        c_bad = self._make_candidate(text="AIを活用するとなんか")
        assert _calculate_score(c_good, 30.0, 60.0) > _calculate_score(c_bad, 30.0, 60.0)

    def test_bad_ending_penalty(self):
        """悪い文末はペナルティ"""
        c = self._make_candidate(text="これはけど")
        score = _calculate_score(c, 30.0, 60.0)
        c_neutral = self._make_candidate(text="テスト" * 10)
        assert score < _calculate_score(c_neutral, 30.0, 60.0)

    def test_filler_segment_penalty(self):
        """フィラーセグメントが含まれているとペナルティ"""
        # total_duration=25.0（範囲外）にしてスコア上限100への到達を回避
        filler_seg = _make_segment("えー", 0, 2)
        normal_seg = _make_segment("今日の話題はAIです", 2, 25)
        c = ClipCandidate(
            segments=[filler_seg, normal_seg],
            segment_indices=[0, 1],
            text="えー今日の話題はAIです",
            time_ranges=[(0, 25)],
            total_duration=25.0,
        )
        c_clean = self._make_candidate(text="今日の話題はAIです" * 3, total_duration=25.0)
        assert _calculate_score(c, 30.0, 60.0) < _calculate_score(c_clean, 30.0, 60.0)

    def test_score_clamped_0_100(self):
        """スコアは0-100の範囲"""
        c = self._make_candidate(text="", total_duration=1.0)
        score = _calculate_score(c, 30.0, 60.0)
        assert 0 <= score <= 100


class TestGenerateCandidates:

    def test_basic_generation(self):
        """基本的な候補生成"""
        texts = ["今日は"] + ["AIについて話します" + str(i) for i in range(10)] + ["以上です"]
        transcription = _make_transcription(texts, duration_each=5.0)
        topic = TopicRange.create(
            title="テスト",
            segment_start_index=0,
            segment_end_index=len(texts) - 1,
        )
        candidates = generate_candidates(topic, transcription, 30.0, 60.0)
        assert len(candidates) > 0
        for c in candidates:
            assert c.mechanical_score > 0

    def test_filler_segments_excluded(self):
        """フィラーセグメントは除外される"""
        texts = [
            "えー",
            "今日は",
            "まあ",
            "AIの話です",
            "うーん",
            "すごいですね",
            "はい",
            "以上です",
            "ありがとう",
            "テスト長い文章です" * 3,
        ]
        transcription = _make_transcription(texts, duration_each=5.0)
        topic = TopicRange.create(
            title="テスト",
            segment_start_index=0,
            segment_end_index=len(texts) - 1,
        )
        candidates = generate_candidates(topic, transcription, 15.0, 50.0)
        # フィラーのみのセグメントが含まれていないか確認
        for c in candidates:
            for seg in c.segments:
                assert seg.text.strip() not in {"えー", "まあ", "うーん", "はい"}

    def test_invalid_range_returns_empty(self):
        """無効な範囲では空リスト"""
        transcription = _make_transcription(["テスト"], duration_each=5.0)
        topic = TopicRange.create(
            title="テスト",
            segment_start_index=5,
            segment_end_index=10,
        )
        candidates = generate_candidates(topic, transcription, 30.0, 60.0)
        assert candidates == []

    def test_sorted_by_score(self):
        """候補はスコア降順でソートされる"""
        texts = ["今日の話題は" + str(i) for i in range(15)]
        transcription = _make_transcription(texts, duration_each=4.0)
        topic = TopicRange.create(
            title="テスト",
            segment_start_index=0,
            segment_end_index=14,
        )
        candidates = generate_candidates(topic, transcription, 20.0, 50.0)
        if len(candidates) > 1:
            for i in range(len(candidates) - 1):
                assert candidates[i].mechanical_score >= candidates[i + 1].mechanical_score

    def test_max_candidates_limit(self):
        """返される候補数はTOP_N_FOR_AI以下"""
        from use_cases.ai.brute_force_clip_generator import TOP_N_FOR_AI

        texts = ["セグメント" + str(i) for i in range(30)]
        transcription = _make_transcription(texts, duration_each=3.0)
        topic = TopicRange.create(
            title="テスト",
            segment_start_index=0,
            segment_end_index=29,
        )
        candidates = generate_candidates(topic, transcription, 20.0, 60.0)
        assert len(candidates) <= TOP_N_FOR_AI
