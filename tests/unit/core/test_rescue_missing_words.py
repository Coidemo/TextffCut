"""core/video.py::_rescue_missing_words の単体テスト。

word が無音削除で完全に keep 区間外に落ちた場合、そのword が救済されて
keep_ranges に復活することを確認する。救済は word 範囲そのまま（padding 無し）、
word を含む元 time_range に完全に収まっていない word は対象外。
"""

from __future__ import annotations

from dataclasses import dataclass

from core.video import _rescue_missing_words


@dataclass
class _FakeWord:
    word: str
    start: float
    end: float


def test_rescues_word_fully_dropped_in_silence():
    """keep 区間と全く重ならない word のみを救済する（word 範囲そのまま）。"""
    time_ranges = [(435.980, 466.500)]
    keep_ranges = [(436.387, 437.130)]  # silencedetect 後（'そ' が落ちた状態）
    words = [
        _FakeWord("そ", 435.980, 436.000),  # keep と 0 overlap → 救済
        _FakeWord("れ", 436.000, 436.840),  # keep と 0.453s overlap → 救済対象外
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 'そ' のみ救済され、元 keep と合わせて 2 個の range
    assert len(result) == 2
    assert result[0] == (435.980, 436.000)  # word 'そ' の範囲そのまま
    assert result[1] == (436.387, 437.130)  # 元 keep そのまま


def test_does_not_rescue_word_outside_time_ranges():
    """time_ranges 外の word は対象外（そもそもクリップ外）。"""
    time_ranges = [(100.0, 110.0)]
    keep_ranges = [(100.0, 110.0)]
    words = [
        _FakeWord("外", 50.0, 50.5),  # time_ranges の外
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges  # 変化なし


def test_does_not_rescue_word_already_kept():
    """既に keep 範囲と overlap する word は救済対象外。"""
    time_ranges = [(100.0, 110.0)]
    keep_ranges = [(100.0, 110.0)]
    words = [
        _FakeWord("中", 102.0, 103.0),
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges  # 変化なし


def test_partially_cut_word_is_not_rescued():
    """word の一部でも keep 区間と重なっていれば「音として残っている」と見做し救済対象外。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(0.5, 10.0)]
    words = [
        _FakeWord("a", 0.0, 1.0),  # 0.5-1.0 は keep と overlap 有り → 救済対象外
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges  # 変化なし


def test_word_straddles_time_range_boundary_is_skipped():
    """word が複数の time_range に跨ぐ場合、完全に含まれる range が無いので救済しない。"""
    time_ranges = [(0.0, 5.0), (6.0, 10.0)]
    keep_ranges = [(0.0, 5.0), (6.0, 10.0)]
    words = [
        _FakeWord("x", 4.5, 6.5),  # 両 range に跨ぐ → どれにも完全包含されない
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert result == keep_ranges  # 変化なし


def test_empty_words_returns_original():
    """words が空なら keep_ranges をそのまま返す。"""
    keep_ranges = [(1.0, 2.0)]
    result = _rescue_missing_words(keep_ranges, [], [(0.0, 3.0)])
    assert result == keep_ranges


def test_dict_words_supported():
    """Word が dict でも動作する（TranscriptionSegment.words は混在型）。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [
        {"word": "a", "start": 0.0, "end": 0.5},
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    assert (0.0, 0.5) in result


def test_adjacent_rescues_merge():
    """隣接する救済 range は自動でマージされる。"""
    time_ranges = [(0.0, 10.0)]
    keep_ranges = [(5.0, 10.0)]
    words = [
        _FakeWord("a", 0.0, 1.0),
        _FakeWord("b", 1.0, 2.0),  # 直接連続（end=start）でマージ対象
    ]

    result = _rescue_missing_words(keep_ranges, words, time_ranges)

    # 救済範囲がマージされて 1 個の range (0.0, 2.0) + 元 keep (5.0, 10.0)
    assert (0.0, 2.0) in result
    assert (5.0, 10.0) in result
    assert len(result) == 2
