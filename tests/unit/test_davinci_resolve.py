"""infrastructure/davinci_resolve.py の pure function ユニットテスト。

Resolve 本体の API に依存する関数 (connect_resolve, send_clip_to_resolve) は
Resolve が起動していないと動かないので、ここでは純粋関数のみ対象。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.davinci_resolve import (
    SendResult,
    _compute_next_seq,
    _extract_mmdd_from_path,
    is_se_clip_name,
)


# --- _extract_mmdd_from_path ---


class TestExtractMmddFromPath:
    def test_standard_format(self):
        p = Path("videos/20260210_生成AIをExcelみたいな_TextffCut/fcpxml/01.fcpxml")
        assert _extract_mmdd_from_path(p) == "0210"

    def test_month_day_extraction(self):
        p = Path("videos/20260103_test_TextffCut/fcpxml/01.fcpxml")
        assert _extract_mmdd_from_path(p) == "0103"

    def test_path_without_textffcut_suffix(self):
        p = Path("videos/20260210_test/fcpxml/01.fcpxml")
        assert _extract_mmdd_from_path(p) is None

    def test_path_with_invalid_date_format(self):
        p = Path("videos/xxx_TextffCut/fcpxml/01.fcpxml")
        assert _extract_mmdd_from_path(p) is None

    def test_deeply_nested_path(self):
        p = Path("/abs/path/videos/20261231_xxx_TextffCut/fcpxml/sub/dir/01.fcpxml")
        assert _extract_mmdd_from_path(p) == "1231"


# --- is_se_clip_name ---


class TestIsSeClipName:
    def test_pure_se_keyword(self):
        assert is_se_clip_name("_ジャン！.mp3") is True
        assert is_se_clip_name("シャキーン1.mp3") is True
        assert is_se_clip_name("和太鼓でドドン.mp3") is True

    def test_bgm_excluded(self):
        assert is_se_clip_name("bgm.mp3") is False
        assert is_se_clip_name("BGM_quiet.mp3") is False

    def test_source_video_excluded(self):
        assert is_se_clip_name("source_1.2x.mp4") is False
        assert is_se_clip_name("source_original.mp3") is False

    def test_mp3_alone_not_se(self):
        """.mp3 だけでは SE 判定しない (keyword 必須)"""
        assert is_se_clip_name("narration.mp3") is False
        assert is_se_clip_name("voiceover.mp3") is False

    def test_non_audio_not_se(self):
        assert is_se_clip_name("frame.png") is False
        assert is_se_clip_name("title.png") is False


# --- _compute_next_seq ---


class TestComputeNextSeq:
    @staticmethod
    def _mk_folder(names: list[str]):
        folder = MagicMock()
        clips = [MagicMock() for _ in names]
        for c, name in zip(clips, names, strict=True):
            c.GetName.return_value = name
        folder.GetClipList.return_value = clips
        return folder

    def test_empty_folder(self):
        folder = self._mk_folder([])
        assert _compute_next_seq(folder, "0210") == 1

    def test_single_existing(self):
        folder = self._mk_folder(["00_0210_Clip01"])
        assert _compute_next_seq(folder, "0210") == 2

    def test_multiple_consecutive(self):
        folder = self._mk_folder(["00_0210_Clip01", "00_0210_Clip02", "00_0210_Clip03"])
        assert _compute_next_seq(folder, "0210") == 4

    def test_gap_in_sequence_returns_max_plus_one(self):
        """歯抜けがあっても max+1 を返す (ユーザー仕様: 歯抜け埋めなし)"""
        folder = self._mk_folder(["00_0210_Clip01", "00_0210_Clip04"])
        assert _compute_next_seq(folder, "0210") == 5

    def test_different_date_not_counted(self):
        folder = self._mk_folder(["00_0210_Clip01", "00_0211_Clip01", "00_0211_Clip02"])
        assert _compute_next_seq(folder, "0210") == 2
        assert _compute_next_seq(folder, "0211") == 3

    def test_non_matching_clips_ignored(self):
        folder = self._mk_folder(
            ["00_0210_Clip01", "source_1.2x.mp4", "bgm.mp3", "その他のクリップ"]
        )
        assert _compute_next_seq(folder, "0210") == 2

    def test_two_digit_seq(self):
        names = [f"00_0210_Clip{i:02d}" for i in range(1, 15)]
        folder = self._mk_folder(names)
        assert _compute_next_seq(folder, "0210") == 15

    def test_folder_returns_none(self):
        """GetClipList が None を返す Resolve 挙動にも耐える"""
        folder = MagicMock()
        folder.GetClipList.return_value = None
        assert _compute_next_seq(folder, "0210") == 1


# --- SendResult dataclass ---


class TestSendResult:
    def test_defaults(self):
        r = SendResult(timeline_name="00_0210_Clip01", bin_name="0210")
        assert r.srt_imported is False
        assert r.se_muted == []
        assert r.se_kept == []

    def test_full(self):
        r = SendResult(
            timeline_name="00_0210_Clip03",
            bin_name="TestBin",
            srt_imported=True,
            se_muted=[2],
            se_kept=[1],
        )
        assert r.timeline_name == "00_0210_Clip03"
        assert r.se_muted == [2]
        assert r.se_kept == [1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
