"""統合テスト: 無音削除の word 救済 → SRT 生成で short word が保持される。

core/video.py::_rescue_missing_words と
use_cases/ai/srt_subtitle_generator.py::_collect_parts_core を連携させ、
「無音削除で silence 判定された short word が最終 SRT に残る」ことを担保する。

ffmpeg は呼ばず、純粋なロジックレベルで回帰を検出する。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from core.video import _rescue_missing_words
from use_cases.ai.srt_subtitle_generator import build_timeline_map, collect_parts


def _word(text: str, start: float, end: float):
    w = MagicMock()
    w.word = text
    w.start = start
    w.end = end
    return w


def _seg(start: float, end: float, text: str, words: list):
    s = MagicMock()
    s.start = start
    s.end = end
    s.text = text
    s.words = words
    return s


def test_short_word_at_range_head_survives_through_srt():
    """word 'そ' (20ms) が無音削除で切り落ちた keep_ranges に対し、
    _rescue_missing_words で救済 → SRT にも含まれることを確認する。

    実事例 20260205 clip 01 のミニ再現: word 'そ' (435.980-436.000) と
    word 'れ' 以降 (436.000-436.840) を持つ seg を、無音削除で 'そ' が
    drop された keep_ranges = [(436.387, 437.130)] と組み合わせる。
    """
    words = [
        _word("そ", 435.980, 436.000),  # 20ms → silencedetect で drop される想定
        _word("れ", 436.000, 436.840),
        _word("も", 436.840, 436.860),
        _word("減", 436.860, 437.130),
    ]
    seg = _seg(435.980, 437.130, "それも減", words)
    transcription = MagicMock()
    transcription.segments = [seg]

    time_ranges_orig = [(435.980, 437.130)]  # 候補生成時の元 range
    keep_after_silence = [(436.387, 437.130)]  # silencedetect で 'そ' が drop された状態

    # word 救済後の keep_ranges を取得
    rescued = _rescue_missing_words(keep_after_silence, words, time_ranges_orig)

    # 'そ' の range が復活している
    assert any(s <= 435.980 and e >= 436.000 for s, e in rescued), (
        f"word 'そ' が rescued に含まれない: {rescued}"
    )

    # 救済後 time_ranges を SRT 生成に流す
    tmap = build_timeline_map(rescued)
    parts = collect_parts(rescued, tmap, transcription, speed=1.0)

    combined = "".join(p[0] for p in parts)
    assert "そ" in combined, f"SRT に 'そ' が含まれない: parts={parts}"
    # 語順が保たれる
    assert combined.startswith("そ"), f"先頭が 'そ' でない: {combined!r}"


def test_out_of_range_word_is_not_picked_up_by_srt():
    """元 time_ranges 外の前 seg word は救済対象外かつ SRT にも入らない
    （「すが」巻き込みバグの回帰防止）。
    """
    prev_words = [
        _word("す", 435.560, 435.680),
        _word("が", 435.680, 435.960),
    ]
    curr_words = [
        _word("そ", 435.980, 436.000),  # 救済対象
        _word("れ", 436.000, 436.840),
    ]
    seg_prev = _seg(435.560, 435.960, "すが", prev_words)
    seg_curr = _seg(435.980, 436.840, "それ", curr_words)
    transcription = MagicMock()
    transcription.segments = [seg_prev, seg_curr]

    # AI 選定は curr seg のみ = 時間範囲 (435.980, 436.840)
    time_ranges_orig = [(435.980, 436.840)]
    keep_after_silence = [(436.387, 436.840)]

    rescued = _rescue_missing_words(
        keep_after_silence, prev_words + curr_words, time_ranges_orig
    )

    tmap = build_timeline_map(rescued)
    parts = collect_parts(rescued, tmap, transcription, speed=1.0)
    combined = "".join(p[0] for p in parts)

    assert "そ" in combined
    # 元 time_ranges 外の 'す' 'が' は含まれない
    assert "す" not in combined, f"前 seg word 'す' が混入: {combined!r}"
    assert "が" not in combined, f"前 seg word 'が' が混入: {combined!r}"


def test_filler_removed_word_does_not_get_rescued():
    """Phase 3.6 で filler が time_ranges から削除された場合、その filler word は
    _rescue_missing_words にも SRT にも拾われないことを確認する。
    """
    words = [
        _word("あ", 10.0, 10.2),
        _word("ー", 10.2, 10.6),  # filler として Phase 3.6 で削られた想定
        _word("実", 10.6, 11.0),
        _word("際", 11.0, 11.3),
    ]
    seg = _seg(10.0, 11.3, "あー実際", words)
    transcription = MagicMock()
    transcription.segments = [seg]

    # filler (10.2-10.6) を Phase 3.6 が time_ranges から削除済み
    time_ranges_after_filler_removal = [(10.0, 10.2), (10.6, 11.3)]
    # 無音削除は特に切らない想定
    keep_after_silence = [(10.0, 10.2), (10.6, 11.3)]

    rescued = _rescue_missing_words(
        keep_after_silence, words, time_ranges_after_filler_removal
    )

    # filler word 'ー' は time_ranges 外なので救済されない
    assert not any(s <= 10.2 and e >= 10.6 for s, e in rescued), (
        f"filler 'ー' が誤って救済された: {rescued}"
    )

    tmap = build_timeline_map(rescued)
    parts = collect_parts(rescued, tmap, transcription, speed=1.0)
    combined = "".join(p[0] for p in parts)
    assert "ー" not in combined, f"filler 'ー' が SRT に残存: {combined!r}"
    assert "あ" in combined
    assert "実" in combined
