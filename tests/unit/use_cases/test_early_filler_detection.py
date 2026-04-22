"""早期フィラー検出（early_filler_detection）のユニットテスト"""

from __future__ import annotations

import pytest

from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from use_cases.ai.early_filler_detection import (
    CleanSegment,
    FillerSpan,
    expand_words_to_chars,
    _extract_char_times,
    _is_grammatical_by_context,
    build_clean_segments,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _word(text: str, start: float, end: float) -> Word:
    return Word(word=text, start=start, end=end)


def _seg(text: str, words: list[Word], seg_id: str = "s") -> TranscriptionSegment:
    return TranscriptionSegment(
        id=seg_id,
        text=text,
        start=words[0].start if words else 0.0,
        end=words[-1].end if words else 0.0,
        words=words,
    )


def _transcription(segments: list[TranscriptionSegment]) -> TranscriptionResult:
    return TranscriptionResult(id="t", video_id="v", segments=segments, language="ja", duration=60.0)


# ===========================================================================
# expand_words_to_chars
# ===========================================================================


class TestExpandWordsToChars:
    def test_single_char_words(self):
        """1文字ずつのWordリストはそのまま返る"""
        words = [_word("あ", 0.0, 0.1), _word("い", 0.1, 0.2)]
        result = expand_words_to_chars(words)
        assert len(result) == 2
        assert result[0].word == "あ"
        assert result[1].word == "い"

    def test_multi_char_word(self):
        """複数文字のWordは文字数分に展開される"""
        words = [_word("これは", 0.0, 0.3), _word("テスト", 0.3, 0.6)]
        result = expand_words_to_chars(words)
        assert len(result) == 6  # 3 + 3
        # 最初の3文字は同じWordオブジェクト
        assert all(r is words[0] for r in result[:3])
        # 後半3文字は同じWordオブジェクト
        assert all(r is words[1] for r in result[3:])

    def test_empty_list(self):
        assert expand_words_to_chars([]) == []

    def test_empty_word_text(self):
        """空文字列のWordは展開されない"""
        words = [_word("", 0.0, 0.1), _word("あ", 0.1, 0.2)]
        result = expand_words_to_chars(words)
        assert len(result) == 1

    def test_dict_input(self):
        """dict形式のwordも処理できる"""
        words = [{"word": "テスト", "start": 0.0, "end": 0.3}]
        result = expand_words_to_chars(words)
        assert len(result) == 3


# ===========================================================================
# _extract_char_times
# ===========================================================================


class TestExtractCharTimes:
    def test_multi_char_words(self):
        """複数文字のWordが正しく展開される"""
        words = [_word("これ", 0.0, 0.2), _word("は", 0.2, 0.3)]
        seg = _seg("これは", words)
        result = _extract_char_times("これは", words, seg)
        assert len(result) == 3
        # "これ" の2文字は同じ時刻
        assert result[0] == (0.0, 0.2)
        assert result[1] == (0.0, 0.2)
        # "は" は別の時刻
        assert result[2] == (0.2, 0.3)

    def test_short_words_fallback(self):
        """wordsが足りない場合はlast_endでfallback"""
        words = [_word("あ", 0.0, 0.1)]
        seg = _seg("あいう", words)
        result = _extract_char_times("あいう", words, seg)
        assert len(result) == 3
        assert result[0] == (0.0, 0.1)
        assert result[1] == (0.1, 0.1)
        assert result[2] == (0.1, 0.1)


# ===========================================================================
# build_clean_segments
# ===========================================================================


class TestBuildCleanSegments:
    def test_no_fillers(self):
        """フィラーなしならそのまま1セグメント"""
        seg = _seg("テスト", [_word("テスト", 0.0, 0.3)])
        tr = _transcription([seg])
        result = build_clean_segments(tr, {})
        assert len(result) == 1
        assert result[0].clean_text == "テスト"
        assert len(result[0].char_times) == 3

    def test_with_filler(self):
        """フィラーがあるとセグメントが分割される"""
        seg = _seg(
            "あのテスト",
            [_word("あの", 0.0, 0.2), _word("テスト", 0.2, 0.5)],
        )
        tr = _transcription([seg])
        filler_map = {0: [FillerSpan(char_start=0, char_end=2, filler_text="あの", time_start=0.0, time_end=0.2)]}
        result = build_clean_segments(tr, filler_map)
        assert len(result) == 1
        assert result[0].clean_text == "テスト"
        assert len(result[0].char_times) == 3

    def test_multi_char_word_char_times(self):
        """複数文字Wordの場合、char_timesが文字数と一致する"""
        seg = _seg(
            "こんにちは世界",
            [_word("こんにちは", 0.0, 0.5), _word("世界", 0.5, 0.7)],
        )
        tr = _transcription([seg])
        result = build_clean_segments(tr, {})
        assert len(result) == 1
        assert len(result[0].char_times) == 7  # "こんにちは世界" = 7文字


# ===========================================================================
# _is_grammatical_by_context (主要分岐のみ)
# ===========================================================================


class TestIsGrammaticalByContext:
    def test_nanka_after_na(self):
        """「な」の後の「なんか」は文法的用法（何か）"""
        result = _is_grammatical_by_context("なんか", "異常ななんか変な", 3)
        assert result is True

    def test_nanka_at_start(self):
        """文頭の「なんか」はフィラー"""
        result = _is_grammatical_by_context("なんか", "なんか変なんだよね", 0)
        assert result is False

    def test_youwa_at_start_is_filler(self):
        """文頭の「要は」はフィラー扱い"""
        result = _is_grammatical_by_context("要は", "要は昔だったら", 0)
        assert result is False

    def test_youwa_after_period_is_filler(self):
        """句点の後の「要は」もフィラー扱い"""
        result = _is_grammatical_by_context("要は", "だよね。要は簡単に言うと", 4)
        assert result is False

    def test_youwa_midsentence_ambiguous(self):
        """文中の「要は」は判定不能 (LLM/aggressive に委譲)"""
        result = _is_grammatical_by_context("要は", "これ要はこういうこと", 2)
        assert result is None
