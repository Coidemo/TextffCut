"""_snap_ranges_to_word_boundaries のユニットテスト。

filler-only snap: range 境界が filler word の内部を指すときだけ、filler 外側へスナップ。
非 filler word 境界は動かさない (副作用なし)。
"""

from __future__ import annotations

import pytest

from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from use_cases.ai.generate_clip_suggestions import GenerateClipSuggestionsUseCase


def _mk_transcription(words_per_seg: list[list[tuple[str, float, float]]]) -> TranscriptionResult:
    segments = []
    for i, ws in enumerate(words_per_seg):
        words = [Word(word=w, start=s, end=e) for w, s, e in ws]
        text = "".join(w for w, _, _ in ws)
        segments.append(
            TranscriptionSegment(
                id=str(i),
                text=text,
                start=words[0].start if words else 0.0,
                end=words[-1].end if words else 0.0,
                words=words,
            )
        )
    duration = segments[-1].end if segments else 0.0
    return TranscriptionResult(id="t", video_id="v", language="ja", segments=segments, duration=duration)


def _mk_filler_span(start: float, end: float):
    class _Span:
        def __init__(self, s, e):
            self.time_start = s
            self.time_end = e

    return _Span(start, end)


# --- No filler_map: snap は no-op ---


def test_no_filler_map_no_op():
    """filler_map が None なら range はそのまま返る。"""
    tr = _mk_transcription([[("あ", 1.0, 1.2), ("い", 1.2, 1.5)]])
    ranges = [(1.05, 1.4)]
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr)
    assert result == [(1.05, 1.4)]


def test_empty_filler_map_no_op():
    """filler_map が空辞書でも range はそのまま。"""
    tr = _mk_transcription([[("あ", 1.0, 1.2)]])
    ranges = [(1.05, 1.15)]
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map={})
    assert result == [(1.05, 1.15)]


# --- Non-filler words are untouched ---


def test_non_filler_word_boundary_untouched():
    """非 filler word 内部の境界は動かさない (「お金」のような通常 word を壊さない)。"""
    tr = _mk_transcription([[("お", 1.0, 1.5), ("金", 1.5, 1.7)]])
    # filler「あの」(無関係) が別の場所に
    filler_map = {0: [_mk_filler_span(3.0, 3.5)]}
    ranges = [(1.2, 1.7)]  # 「お」の中
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    # 動かない → 元のまま
    assert result == [(1.2, 1.7)]


# --- Filler-inside: snap outward ---


def test_snap_start_inside_filler_moves_to_end():
    """range.start が filler 内部 → filler の end へ前進。"""
    tr = _mk_transcription([[("あ", 1.0, 1.2), ("の", 1.2, 1.4), ("、", 1.4, 1.5)]])
    filler_map = {0: [_mk_filler_span(1.0, 1.4)]}  # あの
    ranges = [(1.3, 1.5)]  # 「の」の中
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    assert result[0][0] == pytest.approx(1.4)


def test_snap_end_inside_filler_moves_to_start():
    """range.end が filler 内部 → filler の start へ後退。"""
    tr = _mk_transcription([[("、", 1.0, 1.2), ("あ", 1.2, 1.4), ("の", 1.4, 1.6)]])
    filler_map = {0: [_mk_filler_span(1.2, 1.6)]}  # あの
    ranges = [(1.0, 1.5)]  # end が「の」の中
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    assert result[0][1] == pytest.approx(1.2)


def test_snap_case1_na_n_ka_filler():
    """CASE 1: filler「なんか」周辺の buffered range が word を切断。"""
    tr = _mk_transcription(
        [
            [
                ("も", 2908.840, 2908.900),
                ("な", 2908.900, 2909.220),
                ("ん", 2909.220, 2909.420),
                ("か", 2909.420, 2910.460),
                ("大", 2910.460, 2910.660),
            ]
        ]
    )
    filler_map = {0: [_mk_filler_span(2908.900, 2910.460)]}
    # buffer 後: end が「な」内部、start が「か」内部
    ranges = [(2908.200, 2908.980), (2910.410, 2910.660)]
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    # [0].end=2908.900, [1].start=2910.460
    assert result[0][1] == pytest.approx(2908.900)
    assert result[1][0] == pytest.approx(2910.460)


def test_snap_case4_tiny_fragment_removed():
    """CASE 4: 40ms の短 filler「か」も filler-aware なら完全除去。"""
    tr = _mk_transcription(
        [
            [
                ("な", 2678.360, 2678.640),
                ("ん", 2678.640, 2678.840),
                ("か", 2678.840, 2678.880),
                ("仕", 2678.880, 2678.980),
            ]
        ]
    )
    filler_map = {0: [_mk_filler_span(2678.360, 2678.880)]}
    # buffer 後 range.start = 2678.830 (「ん」内部、head_buffer が「か」40ms を飛び越えた)
    ranges = [(2678.830, 2678.980)]
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    # filler 全体を抜けて 2678.880 (「仕」start)
    assert result[0][0] == pytest.approx(2678.880)


def test_snap_consecutive_fillers_merged():
    """連続 filler「まあ」+「なんか」は 1 区間にマージされて全部通り抜ける。"""
    tr = _mk_transcription(
        [
            [
                ("ま", 1.10, 1.15),
                ("あ", 1.15, 1.20),
                ("な", 1.20, 1.22),
                ("ん", 1.22, 1.24),
                ("か", 1.24, 1.26),
                ("仕", 1.26, 1.40),
            ]
        ]
    )
    filler_map = {
        0: [
            _mk_filler_span(1.10, 1.20),
            _mk_filler_span(1.20, 1.26),  # 隣接 → マージ
        ]
    }
    ranges = [(1.12, 1.40)]  # start が「ま」の中
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    # 最終的に「仕」start (1.26) へ
    assert result[0][0] == pytest.approx(1.26)


def test_snap_boundary_exactly_at_filler_edge_untouched():
    """range 境界が filler start/end と厳密一致なら動かさない (既に filler の外)。"""
    tr = _mk_transcription(
        [
            [
                ("あ", 1.0, 1.2),
                ("の", 1.2, 1.4),
                ("キ", 1.4, 1.6),
            ]
        ]
    )
    filler_map = {0: [_mk_filler_span(1.0, 1.4)]}
    # start = 1.4 (filler.end と一致) → 動かない
    ranges = [(1.4, 1.6)]
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    assert result == [(1.4, 1.6)]


def test_snap_range_dropped_when_fully_inside_filler():
    """range が filler 内部に完全包含 → start も end も filler 外側へ動いて空になり drop。"""
    tr = _mk_transcription([[("な", 1.0, 1.2), ("ん", 1.2, 1.4), ("か", 1.4, 1.6)]])
    filler_map = {0: [_mk_filler_span(1.0, 1.6)]}
    ranges = [(1.1, 1.5)]  # filler の中
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    # start → 1.6, end → 1.0 → new_e < new_s → drop
    assert result == []


def test_snap_multiple_ranges_only_filler_affected():
    """filler と関係ない range は動かない、filler 絡みだけスナップ。"""
    tr = _mk_transcription(
        [
            [
                ("普", 1.0, 1.2),
                ("通", 1.2, 1.4),
                ("な", 2.0, 2.1),
                ("ん", 2.1, 2.2),
                ("か", 2.2, 2.3),
                ("大", 2.3, 2.5),
            ]
        ]
    )
    filler_map = {0: [_mk_filler_span(2.0, 2.3)]}  # なんか
    ranges = [(1.0, 1.4), (2.05, 2.5)]  # 1 個目 filler 無関係、2 個目 start が filler 内部
    result = GenerateClipSuggestionsUseCase._snap_ranges_to_word_boundaries(ranges, tr, filler_map=filler_map)
    assert result[0] == (1.0, 1.4)  # 変更なし
    assert result[1][0] == pytest.approx(2.3)  # filler 抜けて「大」start
