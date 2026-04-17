"""is_sentence_complete() の単体テスト"""

import pytest

from core.japanese_line_break import JapaneseLineBreakRules


class TestIsSentenceComplete:
    """GiNZA形態素解析による文末完結判定のテスト"""

    @pytest.mark.parametrize(
        "text",
        [
            "それは大事です",
            "頑張ります",
            "成功しました",
            "面白いですね",
            "そう思いますよね",
            "やるべきですよ",
            "いいと思います",
            "知らないかもしれません",
            "これがポイントですか",
            "やってみてください",
        ],
    )
    def test_complete_sentences(self, text: str) -> None:
        assert JapaneseLineBreakRules.is_sentence_complete(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "それは大事なので",
            "やっぱりこれはけど",
            "今日の話題を",
            "最近話題になっているのが",
            "具体的には何かに",
        ],
    )
    def test_incomplete_sentences(self, text: str) -> None:
        assert JapaneseLineBreakRules.is_sentence_complete(text) is False

    def test_empty_string(self) -> None:
        assert JapaneseLineBreakRules.is_sentence_complete("") is False

    def test_whitespace_only(self) -> None:
        assert JapaneseLineBreakRules.is_sentence_complete("   ") is False

    def test_trailing_whitespace_ignored(self) -> None:
        assert JapaneseLineBreakRules.is_sentence_complete("大事です   ") is True
