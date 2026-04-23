"""core/video.py::_rescue_missing_words の単体テスト。

word が無音削除で完全に keep 区間外に落ちた場合、その word を救済する。

救済挙動:
- 救済 range = word 範囲 + 1 frame padding (30fps 丸めで 0 duration にならない長さを確保)
- 元 time_range 境界内に clip (前後 segment に食み込まない)
- 近接既存 keep (gap < _RESCUE_MERGE_GAP) があれば強制マージ (独立 super short clip を出さない)
"""

from __future__ import annotations

from dataclasses import dataclass

from core.video import _RESCUE_MERGE_GAP, _RESCUE_PADDING, _rescue_missing_words


@dataclass
class _FakeWord:
    word: str
    start: float
    end: float


PAD = _RESCUE_PADDING  # 1.0 / 30.0
GAP = _RESCUE_MERGE_GAP  # 0.5


def test_rescues_word_and_merges_into_adjacent_keep():
    """word 'そ' (20ms) が silence で drop され、後方 keep と gap < MERGE_GAP → merge。"""
    time_ranges = [(435.980, 466.500)]
    keep_ranges = [(436.387, 437.130)]  # silencedetect 後
    words = [
        _FakeWord("そ", 435.980, 436.000),  # keep の 0.387s 前、gap < 0.5s
        _FakeWord("れ", 436.000, 436.840),  # keep と overlap → 救済対象外
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 'そ' が後方 keep に merge されて 1 個の range になる
    assert len(result) == 1
    start, end = result[0]
    # start は word 'そ' の padding 付き位置 (time_range 境界 435.980 で clip)
    assert start == 435.980
    # end は元の keep 終端
    assert end == 437.130


def test_rescue_with_no_adjacent_keep_becomes_independent_clip():
    """近接 keep が無い場合、救済 range は単独で追加される。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]  # word から距離 3.0s > MERGE_GAP
    words = [
        _FakeWord("x", 2.0, 2.1),
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 独立 range (padding 付き) + 元 keep = 2 個
    assert len(result) == 2
    independent = [r for r in result if r[0] < 5.0][0]
    s, e = independent
    assert abs(s - (2.0 - PAD)) < 1e-6
    assert abs(e - (2.1 + PAD)) < 1e-6
    assert (5.0, 10.0) in result


def test_merge_with_prev_keep_extends_end():
    """word が前方 keep の直後にある場合、keep の end が word 終端に拡張される。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(0.0, 3.0)]
    words = [
        _FakeWord("x", 3.2, 3.3),  # keep との gap = 0.2s < MERGE_GAP
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 前方 keep の end が word.end + PAD まで拡張
    assert len(result) == 1
    s, e = result[0]
    assert s == 0.0
    assert abs(e - (3.3 + PAD)) < 1e-6


def test_does_not_rescue_word_outside_time_ranges():
    """time_ranges 外の word は対象外（そもそもクリップ外）。"""
    time_ranges = [(100.0, 110.0)]
    keep_ranges = [(100.0, 110.0)]
    words = [_FakeWord("外", 50.0, 50.5)]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges


def test_does_not_rescue_word_already_kept():
    """既に keep 範囲と overlap する word は救済対象外。"""
    time_ranges = [(100.0, 110.0)]
    keep_ranges = [(100.0, 110.0)]
    words = [_FakeWord("中", 102.0, 103.0)]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges


def test_partially_cut_word_is_not_rescued():
    """word の一部でも keep と overlap なら救済対象外 (音として残っている扱い)。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(0.5, 10.0)]
    words = [_FakeWord("a", 0.0, 1.0)]  # 0.5-1.0 は overlap

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges


def test_word_straddles_time_range_boundary_is_skipped():
    """word が複数の time_range に跨ぐ場合、救済しない。"""
    time_ranges = [(0.0, 5.0), (6.0, 10.0)]
    keep_ranges = [(0.0, 5.0), (6.0, 10.0)]
    words = [_FakeWord("x", 4.5, 6.5)]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges


def test_empty_words_returns_original():
    keep_ranges = [(1.0, 2.0)]
    result = _rescue_missing_words(keep_ranges, [], [(0.0, 3.0)])
    assert result == keep_ranges


def test_dict_words_supported():
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [{"word": "a", "start": 0.0, "end": 0.5}]  # keep との gap = 4.5s > MERGE_GAP → 独立

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert any(s == 0.0 and abs(e - (0.5 + PAD)) < 1e-6 for s, e in result)


def test_adjacent_rescues_merge():
    """隣接する救済 range 同士もマージされる。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [
        _FakeWord("a", 0.5, 1.0),
        _FakeWord("b", 1.0, 1.5),  # a の直後、最終 merge で繋がる
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 両 word が近接マージ後の最終 merge で 1 個の range に統合
    merged = [(s, e) for s, e in result if s < 5.0]
    assert len(merged) == 1
    s, e = merged[0]
    assert abs(s - (0.5 - PAD)) < 1e-6
    assert abs(e - (1.5 + PAD)) < 1e-6


def test_empty_keep_ranges_with_word_in_time_range():
    """silencedetect で全区間 silence の場合でも word が救済される (近接 keep なし→独立)。"""
    time_ranges = [(0.0, 5.0)]
    keep_ranges: list[tuple[float, float]] = []
    words = [
        _FakeWord("a", 0.5, 0.7),
        _FakeWord("b", 3.0, 3.3),  # a と離れている
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 独立 range 2 個
    assert len(result) == 2


def test_word_end_touching_keep_start_merges():
    """word.end == keep.start の接触は gap=0 で merge 条件を満たす。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(1.0, 10.0)]
    words = [_FakeWord("a", 0.5, 1.0)]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # word 先頭 (0.5 - PAD は time_range 境界内) から keep 末尾まで merge
    assert len(result) == 1
    s, e = result[0]
    assert abs(s - (0.5 - PAD)) < 1e-6
    assert e == 10.0


def test_word_with_none_timestamp_is_skipped():
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [
        _FakeWord("broken", None, None),  # type: ignore[arg-type]
        _FakeWord("ok", 1.0, 2.0),  # keep との gap = 3.0s > MERGE_GAP → 独立
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert any(abs(s - (1.0 - PAD)) < 1e-6 and abs(e - (2.0 + PAD)) < 1e-6 for s, e in result)
    assert (5.0, 10.0) in result


def test_word_with_zero_or_negative_duration_is_skipped():
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [
        _FakeWord("zero", 2.0, 2.0),
        _FakeWord("neg", 3.0, 2.9),
        _FakeWord("ok", 1.0, 1.5),  # keep との gap = 3.5s > MERGE_GAP → 独立
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert any(abs(s - (1.0 - PAD)) < 1e-6 and abs(e - (1.5 + PAD)) < 1e-6 for s, e in result)
    assert (5.0, 10.0) in result


def test_merge_gap_threshold_boundary():
    """gap = MERGE_GAP ちょうどの場合は merge しない (strict inequality)。"""
    time_ranges = [(0.0, 10.0)]
    # gap を MERGE_GAP ちょうどに設定
    gap_exact_start = 3.0 + GAP  # keep の start = 3.5
    keep_ranges = [(gap_exact_start, 10.0)]
    words = [_FakeWord("x", 2.9, 3.0)]  # word.end + PAD = 3.033, keep.start = 3.5, gap = 0.467

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # gap 0.467 < 0.5 → merge される
    merged = [r for r in result if r[0] < gap_exact_start]
    assert len(merged) == 1
    s, e = merged[0]
    assert abs(s - (2.9 - PAD)) < 1e-6
    # keep の end まで拡張されている
    assert e == 10.0
