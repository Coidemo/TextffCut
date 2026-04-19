"""吃音除去（stammering_remover）のユニットテスト"""

from __future__ import annotations

import pytest

from domain.entities.transcription import TranscriptionSegment, Word
from use_cases.ai.stammering_remover import remove_stammering


def _make_segment(text: str, words: list[Word]) -> TranscriptionSegment:
    """テスト用セグメントを作成"""
    return TranscriptionSegment(
        id="test",
        text=text,
        start=words[0].start if words else 0.0,
        end=words[-1].end if words else 0.0,
        words=words,
    )


def _make_words(text: str, start: float = 0.0, char_duration: float = 0.1) -> list[Word]:
    """テキストの各文字に等間隔のタイムスタンプを付与"""
    words = []
    for i, ch in enumerate(text):
        w_start = start + i * char_duration
        w_end = w_start + char_duration
        words.append(Word(word=ch, start=w_start, end=w_end))
    return words


class TestBasicRepetitionDetection:
    """基本的な反復検出テスト"""

    def test_simple_repetition(self):
        """同一パターンが2回連続 → 1回に縮約"""
        text = "ない人はない人は残り"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, cleaned_ranges, cleaned_dur = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == "ない人は残り"
        assert cleaned_dur < sum(e - s for s, e in time_ranges)

    def test_triple_repetition(self):
        """同一パターンが3回連続 → 1回に縮約"""
        text = "ない人はない人はない人は残り"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, cleaned_ranges, cleaned_dur = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == "ない人は残り"

    def test_short_repetition(self):
        """2文字パターンの反復"""
        text = "ああああ普通"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == "ああ普通"


class TestNoRepetition:
    """反復なしのテスト"""

    def test_no_repetition(self):
        """反復がない場合は入力をそのまま返す"""
        text = "これは正常なテキストです"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, cleaned_ranges, cleaned_dur = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text
        assert cleaned_ranges == time_ranges

    def test_single_char_no_repeat(self):
        """1文字パターンは検出対象外（パターン長2以上）"""
        text = "あいうえお"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text


class TestMultipleLocations:
    """複数箇所の反復テスト"""

    def test_two_locations(self):
        """異なる位置に2つの反復パターン"""
        text = "ああ普通ああ別の内容いいいい終わり"
        # "ああ" は2文字パターン×2回 → "あ" ではなく "ああ" が残る
        # "いい" も2文字パターン×2回 → "いい" が残る
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert "普通" in cleaned_text
        assert "終わり" in cleaned_text


class TestCharTimesLengthMismatch:
    """char_times長さ不一致のfallbackテスト"""

    def test_mismatch_returns_original(self):
        """char_timesがテキストと一致しない場合はそのまま返す"""
        text = "テストテキスト"
        # wordsが少ない（テキスト長と不一致）
        words = [Word(word="テ", start=0.0, end=0.1)]
        seg = TranscriptionSegment(
            id="test",
            text=text,
            start=0.0,
            end=0.7,
            words=words,
        )
        time_ranges = [(0.0, 0.7)]

        cleaned_text, cleaned_ranges, cleaned_dur = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text
        assert cleaned_ranges == time_ranges

    def test_empty_words(self):
        """wordsが空の場合"""
        text = "テスト"
        seg = TranscriptionSegment(
            id="test",
            text=text,
            start=0.0,
            end=0.3,
            words=[],
        )
        time_ranges = [(0.0, 0.3)]

        cleaned_text, cleaned_ranges, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text
        assert cleaned_ranges == time_ranges


class TestReduplicationProtection:
    """畳語保護テスト"""

    def test_reduplication_protected(self):
        """「たまたま」は畳語として保護される"""
        text = "たまたま勝った"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text

    def test_reduplication_iroiro(self):
        """「いろいろ」は畳語として保護される"""
        text = "いろいろあって"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text

    def test_reduplication_triple_protected(self):
        """畳語パターンの3回反復もスキップされる（畳語保護）"""
        text = "たまたまたま勝った"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        # 「たま」は「たまたま」畳語の構成要素なので保護される
        assert cleaned_text == text

    def test_reduplication_katakana(self):
        """カタカナ畳語も保護される"""
        text = "ドンドン進む"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text

    def test_reduplication_with_stammering(self):
        """畳語と吃音が混在するケース"""
        text = "たまたまない人はない人は残り"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert "たまたま" in cleaned_text
        assert cleaned_text == "たまたまない人は残り"


class TestMultiCharWords:
    """複数文字Wordを使った吃音除去テスト"""

    def test_multi_char_word_repetition(self):
        """複数文字Word（"ない人は"）が反復 → 正しく検出・除去"""
        text = "ない人はない人は残り"
        words = [
            Word(word="ない", start=0.0, end=0.2),
            Word(word="人", start=0.2, end=0.3),
            Word(word="は", start=0.3, end=0.4),
            Word(word="ない", start=0.4, end=0.6),
            Word(word="人", start=0.6, end=0.7),
            Word(word="は", start=0.7, end=0.8),
            Word(word="残り", start=0.8, end=1.0),
        ]
        seg = _make_segment(text, words)
        time_ranges = [(0.0, 1.0)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == "ない人は残り"

    def test_multi_char_word_char_times_correct_length(self):
        """複数文字Wordのchar_timesが文字数と一致する"""
        text = "テスト"
        words = [Word(word="テスト", start=0.0, end=0.3)]
        seg = _make_segment(text, words)
        time_ranges = [(0.0, 0.3)]

        # 変化なし → そのまま返る
        cleaned_text, cleaned_ranges, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text
        assert cleaned_ranges == time_ranges


class TestNewReduplicationProtection:
    """新規追加畳語の保護テスト"""

    @pytest.mark.parametrize(
        "word",
        ["まあまあ", "もしもし", "はいはい", "いやいや", "ねえねえ", "おいおい", "なになに"],
    )
    def test_response_reduplications(self, word):
        """応答系畳語が保護される"""
        text = f"{word}良かった"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text

    @pytest.mark.parametrize(
        "word",
        ["ゾクゾク", "ビクビク", "サラサラ", "コロコロ", "ジワジワ", "メキメキ"],
    )
    def test_katakana_reduplications(self, word):
        """カタカナ畳語が保護される"""
        text = f"{word}する"
        words = _make_words(text)
        seg = _make_segment(text, words)
        time_ranges = [(0.0, len(text) * 0.1)]

        cleaned_text, _, _ = remove_stammering(text, [seg], time_ranges)

        assert cleaned_text == text


class TestTimeRangesReconstruction:
    """time_ranges再構築テスト"""

    def test_gap_merge(self):
        """0.5秒以内のギャップはマージされる"""
        text = "ああ普通"
        # "あ"×2文字パターンが2回 → 最初の"ああ"を除去
        # char_times: あ(0.0-0.1), あ(0.2-0.3), 普(0.4-0.5), 通(0.6-0.7)
        words = [
            Word(word="あ", start=0.0, end=0.1),
            Word(word="あ", start=0.2, end=0.3),
            Word(word="普", start=0.4, end=0.5),
            Word(word="通", start=0.6, end=0.7),
        ]
        seg = _make_segment(text, words)
        time_ranges = [(0.0, 0.7)]

        _, cleaned_ranges, _ = remove_stammering(text, [seg], time_ranges)

        # "ああ"が除去され、"普通"のみ残る → (0.2, 0.7) に近い1つのrangeになる
        assert len(cleaned_ranges) >= 1
        # マージされて1つのrangeになるはず（ギャップ0.1s < 0.5s閾値）
        assert len(cleaned_ranges) == 1

    def test_large_gap_splits_ranges(self):
        """0.5秒超のギャップは別rangeになる"""
        text = "あいあい普通"
        words = [
            Word(word="あ", start=0.0, end=0.1),
            Word(word="い", start=0.1, end=0.2),
            Word(word="あ", start=0.2, end=0.3),
            Word(word="い", start=0.3, end=0.4),
            Word(word="普", start=1.0, end=1.1),  # 大きなギャップ
            Word(word="通", start=1.1, end=1.2),
        ]
        seg = _make_segment(text, words)
        time_ranges = [(0.0, 1.2)]

        _, cleaned_ranges, _ = remove_stammering(text, [seg], time_ranges)

        # "あいあい"→"あい"に縮約後、"あい"(0.2-0.4)と"普通"(1.0-1.2)は0.6sギャップ → 2 ranges
        assert len(cleaned_ranges) == 2
