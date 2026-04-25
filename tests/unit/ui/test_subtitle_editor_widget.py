"""ui/subtitle_editor/widget.py のテスト."""

from __future__ import annotations

import pytest

from ui.subtitle_editor.widget import (
    assign_timing_from_structure,
    entries_to_text,
    flatten_text,
    parse_edited_text,
    validate_edit,
)
from use_cases.ai.srt_edit_log import SRTEntry


def _entry(i: int, s: float, e: float, text: str) -> SRTEntry:
    return SRTEntry(index=i, start_time=s, end_time=e, text=text)


ORIGINAL = [
    _entry(1, 0.0, 2.0, "なのでこれ格差は\n広がるなと思っていて"),
    _entry(2, 2.0, 4.0, "小原さんとかは\nこれを200本ぐらい"),
    _entry(3, 4.0, 6.0, "1日やってる\nらしいんですけど"),
]


class TestTextRoundtrip:
    def test_entries_to_text_and_back(self):
        text = entries_to_text(ORIGINAL)
        parsed = parse_edited_text(text)
        assert len(parsed) == 3
        assert parsed[0] == ["なのでこれ格差は", "広がるなと思っていて"]
        assert parsed[2] == ["1日やってる", "らしいんですけど"]

    def test_flatten_removes_whitespace(self):
        assert flatten_text("abc\ndef\n\nghi") == "abcdefghi"

    def test_nfc_normalization(self):
        """NFC 正規化で結合文字の表現揺れを吸収."""
        import unicodedata

        nfc = unicodedata.normalize("NFC", "が")
        nfd = unicodedata.normalize("NFD", "が")
        assert flatten_text(nfd) == nfc


class TestValidateEdit:
    """タイミング調整のみ許可: 構造変更 OK、文字変更 NG."""

    def test_structure_only_change_ok(self):
        """同文字・改行のみ変更 → OK."""
        orig = "abcdef\nghi\n\njkl"
        edited = "abc\ndefghi\n\njkl"  # 改行位置変更
        v = validate_edit(orig, edited)
        assert v.ok

    def test_entry_merge_ok(self):
        """entry 結合 (空行削除) → OK."""
        orig = "abc\ndef\n\nghi"
        edited = "abc\ndef\nghi"
        v = validate_edit(orig, edited)
        assert v.ok

    def test_entry_split_ok(self):
        """entry 分割 (空行追加) → OK."""
        orig = "abcdef"
        edited = "abc\n\ndef"
        v = validate_edit(orig, edited)
        assert v.ok

    def test_text_change_error(self):
        """文字変更 → NG."""
        orig = "abc\ndef\n\nghi"
        edited = "abc\nxyz\n\nghi"
        v = validate_edit(orig, edited)
        assert not v.ok
        assert "文字内容" in v.error_msg

    def test_char_removal_error(self):
        """文字削除 → NG."""
        orig = "abcdef\n\nghi"
        edited = "abc\n\nghi"  # "def" 削除
        v = validate_edit(orig, edited)
        assert not v.ok

    def test_char_addition_error(self):
        """文字追加 → NG."""
        orig = "abc\n\nghi"
        edited = "abcX\n\nghi"
        v = validate_edit(orig, edited)
        assert not v.ok


class TestParseEditedTextWhitespace:
    """parse_edited_text が line 内 whitespace を全除去することの検証."""

    def test_inline_space_removed(self):
        """line 内の半角スペースは除去される (validate_edit と semantics 揃える)."""
        # ユーザーが誤って半角スペース挿入 → validation は通るが parse でも空白除去
        parsed = parse_edited_text("abc def\n\nghi")
        assert parsed == [["abcdef"], ["ghi"]]

    def test_inline_tab_removed(self):
        parsed = parse_edited_text("a\tb\nc")
        assert parsed == [["ab", "c"]]

    def test_ideographic_space_removed(self):
        """全角スペースも除去."""
        parsed = parse_edited_text("あ　い\n\nう")
        assert parsed == [["あい"], ["う"]]


class TestAssignTimingFromStructure:
    """文字位置比で timing 再配分 (backfill 無い時の fallback)."""

    def test_basic_redistribution(self):
        parsed = [
            ["abc"],  # 3 chars
            ["defghi"],  # 6 chars
            ["j"],  # 1 char
        ]
        # 合計 10 chars, 合計 dur = 6.0s (ORIGINAL の 0.0-6.0)
        result = assign_timing_from_structure(parsed, ORIGINAL)
        assert len(result) == 3
        assert result[0].start_time == 0.0
        assert result[0].end_time == pytest.approx(1.8, abs=0.01)  # 3/10 * 6
        assert result[1].start_time == pytest.approx(1.8, abs=0.01)
        assert result[1].end_time == pytest.approx(5.4, abs=0.01)  # 9/10 * 6
        assert result[2].end_time == pytest.approx(6.0, abs=0.01)

    def test_empty_input(self):
        assert assign_timing_from_structure([], ORIGINAL) == []
        assert assign_timing_from_structure([["a"]], []) == []
