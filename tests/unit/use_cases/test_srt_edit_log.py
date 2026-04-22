"""srt_edit_log のテスト."""

from __future__ import annotations

from pathlib import Path

import pytest

from use_cases.ai.srt_edit_log import (
    SRTEntry,
    append_edit_log,
    compute_edit_diff,
    load_edit_log,
    parse_srt,
    write_srt,
)


def _entry(i: int, s: float, e: float, text: str) -> SRTEntry:
    return SRTEntry(index=i, start_time=s, end_time=e, text=text)


class TestWriteParseRoundtrip:
    def test_write_and_parse(self, tmp_path: Path):
        entries = [
            _entry(1, 0.0, 2.5, "なのでこれ格差は\n広がるなと思っていて"),
            _entry(2, 2.5, 4.0, "小原さんとかは"),
        ]
        srt_path = tmp_path / "test.srt"
        write_srt(entries, srt_path)
        loaded = parse_srt(srt_path)
        assert len(loaded) == 2
        assert loaded[0].text == "なのでこれ格差は\n広がるなと思っていて"
        assert loaded[0].start_time == pytest.approx(0.0, abs=0.002)
        assert loaded[0].end_time == pytest.approx(2.5, abs=0.002)
        assert loaded[1].text == "小原さんとかは"

    def test_srt_time_format(self, tmp_path: Path):
        """SRT 時刻フォーマット HH:MM:SS,mmm."""
        entries = [_entry(1, 3661.5, 3665.123, "テスト")]
        srt_path = tmp_path / "t.srt"
        write_srt(entries, srt_path)
        content = srt_path.read_text(encoding="utf-8")
        assert "01:01:01,500 --> 01:01:05,123" in content

    def test_clamp_ms(self, tmp_path: Path):
        """ms が 1000 以上にならないよう clamp される."""
        entries = [_entry(1, 0.0, 1.9999999, "x")]
        srt_path = tmp_path / "t.srt"
        write_srt(entries, srt_path)
        content = srt_path.read_text(encoding="utf-8")
        # 小数が 999 ms に clamp される or 2.000 に round される
        assert "00:00:01,999" in content or "00:00:02,000" in content


class TestComputeEditDiff:
    def test_no_changes(self):
        entries = [_entry(1, 0, 1, "a"), _entry(2, 1, 2, "b")]
        d = compute_edit_diff(entries, entries)
        assert d["content_unchanged"] is True
        assert d["entries_before"] == 2
        assert d["entries_after"] == 2
        assert d["line_break_changes"] == 0

    def test_merge_reduces_count(self):
        orig = [_entry(1, 0, 1, "a"), _entry(2, 1, 2, "b")]
        edited = [_entry(1, 0, 2, "a\nb")]
        d = compute_edit_diff(orig, edited)
        assert d["entries_before"] == 2
        assert d["entries_after"] == 1
        assert d["entries_delta"] == -1

    def test_line_break_change_detected(self):
        # 同一 flat content だが改行位置だけ変更
        orig = [_entry(1, 0, 2, "abc\ndef")]
        edited = [_entry(1, 0, 2, "ab\ncdef")]
        d = compute_edit_diff(orig, edited)
        assert d["content_unchanged"] is True
        assert d["line_break_changes"] == 1

    def test_content_changed_flag(self):
        orig = [_entry(1, 0, 1, "abc")]
        edited = [_entry(1, 0, 1, "xyz")]
        d = compute_edit_diff(orig, edited)
        assert d["content_unchanged"] is False


class TestAppendEditLog:
    def test_append_and_reload(self, tmp_path: Path):
        orig = [_entry(1, 0, 1, "a"), _entry(2, 1, 2, "b")]
        edited = [_entry(1, 0, 2, "a\nb")]

        path = append_edit_log(
            base_dir=tmp_path,
            clip_id="clip01",
            original=orig,
            edited=edited,
            algorithm_version="v2",
            full_text="ab",
        )
        assert path.exists()
        assert path.parent.name == "subtitle_edits"
        assert path.name == "edits.jsonl"

        logs = load_edit_log(tmp_path)
        assert len(logs) == 1
        log = logs[0]
        assert log["clip_id"] == "clip01"
        assert log["algorithm_version"] == "v2"
        assert len(log["generated_entries"]) == 2
        assert len(log["edited_entries"]) == 1
        assert log["diff_summary"]["entries_delta"] == -1

    def test_multiple_appends(self, tmp_path: Path):
        orig = [_entry(1, 0, 1, "a")]
        edited = orig.copy()
        for i in range(3):
            append_edit_log(
                base_dir=tmp_path,
                clip_id=f"clip{i}",
                original=orig,
                edited=edited,
            )
        logs = load_edit_log(tmp_path)
        assert len(logs) == 3
        assert [L["clip_id"] for L in logs] == ["clip0", "clip1", "clip2"]

    def test_load_empty(self, tmp_path: Path):
        """ログファイルが無い場合は空 list."""
        assert load_edit_log(tmp_path) == []

    def test_skip_malformed_lines(self, tmp_path: Path):
        """壊れた JSON 行はスキップ."""
        log_dir = tmp_path / "subtitle_edits"
        log_dir.mkdir()
        (log_dir / "edits.jsonl").write_text(
            '{"valid": 1}\n{broken json\n{"valid": 2}\n',
            encoding="utf-8",
        )
        logs = load_edit_log(tmp_path)
        assert len(logs) == 2
        assert logs[0] == {"valid": 1}
        assert logs[1] == {"valid": 2}


class TestSRTEntry:
    def test_lines_property(self):
        e = _entry(1, 0, 1, "a\nb")
        assert e.lines == ["a", "b"]

    def test_lines_single(self):
        e = _entry(1, 0, 1, "abc")
        assert e.lines == ["abc"]


class TestSRTMeta:
    """save/load_srt_meta round trip."""

    def test_save_and_load(self, tmp_path: Path):
        from use_cases.ai.srt_edit_log import load_srt_meta, save_srt_meta

        srt_path = tmp_path / "test.srt"
        full_text = "abcdef"
        char_times = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3), (0.3, 0.4), (0.4, 0.5), (0.5, 0.6)]
        save_srt_meta(srt_path, full_text, char_times)
        loaded = load_srt_meta(srt_path)
        assert loaded is not None
        lt, lc = loaded
        assert lt == full_text
        assert len(lc) == len(char_times)
        for (a, b), (c, d) in zip(lc, char_times, strict=False):
            assert abs(a - c) < 1e-3
            assert abs(b - d) < 1e-3

    def test_load_missing(self, tmp_path: Path):
        from use_cases.ai.srt_edit_log import load_srt_meta

        srt_path = tmp_path / "nothere.srt"
        assert load_srt_meta(srt_path) is None

    def test_save_length_mismatch(self, tmp_path: Path):
        from use_cases.ai.srt_edit_log import save_srt_meta

        with pytest.raises(ValueError):
            save_srt_meta(tmp_path / "x.srt", "abc", [(0, 1), (1, 2)])

    def test_save_nfc_normalization(self, tmp_path: Path):
        """NFC 化で長さが変わらない場合は正規化されて保存される."""
        import unicodedata

        from use_cases.ai.srt_edit_log import load_srt_meta, save_srt_meta

        # ASCII なら NFC/NFD で変わらない
        srt_path = tmp_path / "t.srt"
        # NFC 化で同じ長さ (純粋 ASCII)
        full_text = "abc"
        char_times = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3)]
        save_srt_meta(srt_path, full_text, char_times)
        lt, _ = load_srt_meta(srt_path)
        assert lt == unicodedata.normalize("NFC", lt)

    def test_save_preserves_nfd_when_length_would_change(self, tmp_path: Path):
        """NFC 化で結合文字が base に吸収され長さが変わる場合は元のまま保存."""
        from use_cases.ai.srt_edit_log import load_srt_meta, save_srt_meta

        srt_path = tmp_path / "t.srt"
        # NFD 形式の "が" (か + 濁点)  2 codepoints
        full_text = "が"  # = "が"
        char_times = [(0.0, 0.1), (0.1, 0.2)]  # 2 entries
        save_srt_meta(srt_path, full_text, char_times)
        lt, lc = load_srt_meta(srt_path)
        # NFC 化すると 1 codepoint になるので char_times と不整合
        # → 元のまま保持されること
        assert len(lt) == 2
        assert len(lc) == 2


class TestReconstructEntryTiming:
    """編集後テキスト → 元 char_times で timing 復元."""

    def test_identity_no_edit(self):
        """編集なし: entry 数・timing が元と一致."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        full_text = "abcdef"
        char_times = [(i * 0.1, (i + 1) * 0.1) for i in range(6)]
        # 編集ブロック: entry1="abc", entry2="def"
        blocks = [["abc"], ["def"]]
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        assert len(result) == 2
        assert result[0].start_time == pytest.approx(0.0)
        assert result[0].end_time == pytest.approx(0.3)
        assert result[1].start_time == pytest.approx(0.3)
        assert result[1].end_time == pytest.approx(0.6)

    def test_char_removal(self):
        """中間文字を削除: 削除部分の timing はスキップされる."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        # 元: "abcdef" (0.0-0.6), "cd" を削除 → "abef"
        full_text = "abcdef"
        char_times = [(i * 0.1, (i + 1) * 0.1) for i in range(6)]
        blocks = [["abef"]]  # 1 entry, 4 chars
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        assert len(result) == 1
        # 'a' は元 index 0 → start 0.0
        # 'f' は元 index 5 → end 0.6
        assert result[0].start_time == pytest.approx(0.0)
        assert result[0].end_time == pytest.approx(0.6)

    def test_filler_removal_shrinks_entry(self):
        """フィラー削除: entry の timing が削除後文字の実音響位置に."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        # "あのこれは" を "これは" に削除
        # あの=前2char (0.0-0.4), これは=後3char (0.4-1.0)
        full_text = "あのこれは"
        char_times = [
            (0.0, 0.2),  # あ
            (0.2, 0.4),  # の
            (0.4, 0.6),  # こ
            (0.6, 0.8),  # れ
            (0.8, 1.0),  # は
        ]
        blocks = [["これは"]]
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        # "これは" の実音響位置は 0.4-1.0
        assert result[0].start_time == pytest.approx(0.4)
        assert result[0].end_time == pytest.approx(1.0)

    def test_entry_split(self):
        """entry 分割: 各 entry が対応する文字の実音響位置."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        full_text = "abcdef"
        char_times = [(i * 0.1, (i + 1) * 0.1) for i in range(6)]
        # 1 entry "abcdef" を "ab" / "cdef" に分割
        blocks = [["ab"], ["cdef"]]
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        assert len(result) == 2
        assert result[0].start_time == pytest.approx(0.0)
        assert result[0].end_time == pytest.approx(0.2)
        assert result[1].start_time == pytest.approx(0.2)
        assert result[1].end_time == pytest.approx(0.6)

    def test_multiline_entry(self):
        """複数行 entry: 全行を連結して timing 計算."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        full_text = "abcdef"
        char_times = [(i * 0.1, (i + 1) * 0.1) for i in range(6)]
        blocks = [["abc", "def"]]  # 1 entry, 2 lines
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        assert len(result) == 1
        assert result[0].text == "abc\ndef"
        assert result[0].start_time == pytest.approx(0.0)
        assert result[0].end_time == pytest.approx(0.6)

    def test_invalid_edit_returns_none(self):
        """存在しない文字を追加: マッピング不可で None."""
        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        full_text = "abc"
        char_times = [(0.0, 0.1), (0.1, 0.2), (0.2, 0.3)]
        blocks = [["abcxyz"]]  # 'xyz' は元に無い
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is None

    def test_nfd_meta_full_text_accepted(self):
        """NFD full_text (save_srt_meta が alignment 保護のため保存した形) でも復元可能."""
        import unicodedata

        from use_cases.ai.srt_edit_log import reconstruct_entry_timing

        # NFD 「が」 = U+304B + U+3099 (2 codepoints)
        nfd_ga = unicodedata.normalize("NFD", "が")
        assert len(nfd_ga) == 2
        full_text = nfd_ga  # NFD のまま
        char_times = [(0.0, 0.1), (0.1, 0.2)]  # 2 entry で alignment
        # 編集側は NFD のまま操作する前提（同じ文字列を blocks に入れる）
        blocks = [[nfd_ga]]
        result = reconstruct_entry_timing(blocks, full_text, char_times)
        assert result is not None
        assert len(result) == 1
        assert result[0].start_time == pytest.approx(0.0)
        assert result[0].end_time == pytest.approx(0.2)
