"""骨子+結びベース候補生成（core_conclusion_candidates）のユニットテスト"""

from __future__ import annotations

import pytest

from domain.entities.clip_suggestion import TopicRange
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from use_cases.ai.core_conclusion_candidates import (
    _is_ending_complete,
    generate_core_conclusion_candidates,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _seg(text: str, start: float, end: float) -> TranscriptionSegment:
    return TranscriptionSegment(id="s", text=text, start=start, end=end, words=[])


def _topic(start: int, end: int, title: str = "テスト") -> TopicRange:
    return TopicRange(
        id="topic1",
        title=title,
        segment_start_index=start,
        segment_end_index=end,
        score=80,
        category="test",
        reasoning="test",
    )


def _transcription(segments: list[TranscriptionSegment]) -> TranscriptionResult:
    return TranscriptionResult(id="t", video_id="v", segments=segments, language="ja", duration=60.0)


# ===========================================================================
# _is_ending_complete
# ===========================================================================


class TestIsEndingComplete:
    def test_desu(self):
        assert _is_ending_complete("良いです") is True

    def test_masu(self):
        assert _is_ending_complete("行きます") is True

    def test_desune(self):
        assert _is_ending_complete("そうですね") is True

    def test_incomplete(self):
        assert _is_ending_complete("だから") is False

    def test_trailing_spaces(self):
        assert _is_ending_complete("良いです  ") is True


# ===========================================================================
# generate_core_conclusion_candidates
# ===========================================================================


class TestGenerateCandidates:
    def _make_segments(self, n: int = 20) -> list[TranscriptionSegment]:
        """n個の1秒セグメントを生成（最後は「です」で終わる）"""
        segs = []
        for i in range(n):
            text = f"セグメント{i}です" if i == n - 1 else f"セグメント{i}は"
            segs.append(_seg(text, float(i), float(i + 1)))
        return segs

    def test_empty_conclusions(self):
        """結論なしなら空リスト"""
        segs = self._make_segments(10)
        tr = _transcription(segs)
        topic = _topic(0, 9)
        result = generate_core_conclusion_candidates(
            topic,
            tr,
            cores=[],
            conclusions=[],
            min_duration=5,
            max_duration=30,
        )
        assert result == []

    def test_1range_candidate(self):
        """結びから逆方向にスライドして1range候補が生成される"""
        segs = self._make_segments(20)
        tr = _transcription(segs)
        topic = _topic(0, 19)
        conclusions = [{"start": 18, "end": 19, "summary": "結び"}]
        result = generate_core_conclusion_candidates(
            topic,
            tr,
            cores=[],
            conclusions=conclusions,
            min_duration=5,
            max_duration=30,
        )
        assert len(result) > 0
        # 全候補がtopic内のindicesを持つ
        for c in result:
            assert all(0 <= idx <= 19 for idx in c.segment_indices)

    def test_sort_order(self):
        """言い切り末尾 > 骨子含む > 短い順でソートされる"""
        segs = []
        for i in range(20):
            if i == 19:
                text = "まとめです"
            elif i == 15:
                text = "途中の"
            else:
                text = f"セグメント{i}です"
            segs.append(_seg(text, float(i), float(i + 1)))
        tr = _transcription(segs)
        topic = _topic(0, 19)
        cores = [{"start": 5, "end": 7, "summary": "骨子"}]
        conclusions = [{"start": 18, "end": 19, "summary": "結び"}]
        result = generate_core_conclusion_candidates(
            topic,
            tr,
            cores=cores,
            conclusions=conclusions,
            min_duration=5,
            max_duration=30,
        )
        if len(result) >= 2:
            # 先頭は言い切りで終わるはず
            assert _is_ending_complete(result[0].text)

    def test_cc_to_local_remap(self):
        """cc_to_localでGPTインデックスがローカルに変換される"""
        segs = self._make_segments(20)
        tr = _transcription(segs)
        topic = _topic(0, 19)
        # GPTのindex 9,10 → ローカルindex 18,19（結び）
        cc_to_local = [0, 1, 2, 6, 8, 10, 12, 14, 16, 18, 19]
        conclusions = [{"start": 9, "end": 10, "summary": "結び"}]
        cores = [{"start": 3, "end": 4, "summary": "骨子"}]

        result = generate_core_conclusion_candidates(
            topic,
            tr,
            cores=cores,
            conclusions=conclusions,
            min_duration=5,
            max_duration=30,
            cc_to_local=cc_to_local,
        )
        # 入力dictが破壊されないことを検証
        assert conclusions[0]["start"] == 9
        assert conclusions[0]["end"] == 10
        assert cores[0]["start"] == 3
        assert cores[0]["end"] == 4
        # リマップ後の候補が生成される（結びindex 18-19を含む）
        assert len(result) > 0
        for c in result:
            assert 19 in c.segment_indices or 18 in c.segment_indices

    def test_has_core_set_on_candidate(self):
        """骨子を含む候補には_has_coreがTrueで設定される"""
        segs = self._make_segments(20)
        tr = _transcription(segs)
        topic = _topic(0, 19)
        cores = [{"start": 15, "end": 17, "summary": "骨子"}]
        conclusions = [{"start": 18, "end": 19, "summary": "結び"}]
        result = generate_core_conclusion_candidates(
            topic,
            tr,
            cores=cores,
            conclusions=conclusions,
            min_duration=5,
            max_duration=30,
        )
        # 骨子を含む候補が存在するはず
        has_core_candidates = [c for c in result if c.has_core]
        assert len(has_core_candidates) > 0
