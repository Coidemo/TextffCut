"""infrastructure/davinci_resolve.py の pure function ユニットテスト。

Resolve 本体の API に依存する関数 (connect_resolve, send_clip_to_resolve) は
Resolve が起動していないと動かないので、ここでは純粋関数 + MagicMock で
Resolve API を組み立てたロジック検証のみ対象。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from infrastructure.davinci_resolve import (
    ResolveError,
    SendResult,
    TextPlusResult,
    _compute_next_seq,
    _extract_mmdd_from_path,
    convert_subtitles_to_text_plus,
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


# --- convert_subtitles_to_text_plus ---


def _make_subtitle(text: str, start: int, end: int) -> MagicMock:
    sub = MagicMock()
    sub.GetName.return_value = text
    sub.GetStart.return_value = start
    sub.GetEnd.return_value = end
    return sub


def _make_text_plus_timeline_item(
    *, name: str = "Text+", duration: int = 99, with_fusion: bool = True
) -> MagicMock:
    """AppendToTimeline 後に返される timeline_item の mock。"""
    item = MagicMock()
    item.GetName.return_value = name
    item.GetDuration.return_value = duration
    if with_fusion:
        item.GetFusionCompCount.return_value = 1
        comp = MagicMock()
        text_tool = MagicMock()
        comp.GetToolList.return_value = [text_tool]
        item.GetFusionCompByIndex.return_value = comp
        item._text_tool = text_tool  # テスト検証用に保持
    else:
        item.GetFusionCompCount.return_value = 0
    return item


def _make_setup(
    subtitles: list,
    *,
    with_bin: bool = True,
    with_template: bool = True,
    timeline_start: int = 0,
    timeline_end: int = 1000,
    test_real_duration: int = 99,
    fail_appends_after: int | None = None,
) -> dict:
    """convert_subtitles_to_text_plus() 用のフルモックセットアップ。

    Args:
        fail_appends_after: 指定回数より後の AppendToTimeline 呼び出しを `[None]` 失敗扱いにする
    """
    project = MagicMock()
    media_pool = MagicMock()
    timeline = MagicMock()
    project.GetMediaPool.return_value = media_pool

    # ビン構造
    root = MagicMock()
    folder = MagicMock()
    if with_bin:
        folder.GetName.return_value = "TextffCut"
        if with_template:
            tmpl = MagicMock()
            tmpl.GetName.return_value = "Caption_Default"
            folder.GetClipList.return_value = [tmpl]
        else:
            folder.GetClipList.return_value = []
        root.GetSubFolderList.return_value = [folder]
    else:
        root.GetSubFolderList.return_value = []
    media_pool.GetRootFolder.return_value = root

    timeline.GetItemListInTrack.return_value = subtitles
    timeline.GetStartFrame.return_value = timeline_start
    timeline.GetEndFrame.return_value = timeline_end
    timeline.SetTrackEnable.return_value = True
    timeline.DeleteClips.return_value = True

    track_counts = {"video": 1, "subtitle": 1}
    timeline.GetTrackCount.side_effect = lambda kind: track_counts.get(kind, 0)

    def add_track(kind):
        track_counts[kind] = track_counts.get(kind, 0) + 1
        return True

    timeline.AddTrack.side_effect = add_track

    # AppendToTimeline: 1回目=duration test、2回目以降=本配置
    call_state = {"count": 0, "items": []}

    def append(infos):
        call_state["count"] += 1
        if (
            fail_appends_after is not None
            and call_state["count"] > fail_appends_after
        ):
            return [None]
        if call_state["count"] == 1:
            # test_real_duration が 0 なら無効値テスト
            return [
                _make_text_plus_timeline_item(duration=test_real_duration)
            ]
        items = [_make_text_plus_timeline_item() for _ in infos]
        call_state["items"].extend(items)
        return items

    media_pool.AppendToTimeline.side_effect = append

    return {
        "project": project,
        "timeline": timeline,
        "media_pool": media_pool,
        "track_counts": track_counts,
        "call_state": call_state,
    }


class TestConvertSubtitlesToTextPlus:
    def test_no_bin_raises(self):
        ctx = _make_setup([_make_subtitle("hi", 0, 30)], with_bin=False)
        with pytest.raises(ResolveError, match="ビンが見つかりません"):
            convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])

    def test_no_template_raises(self):
        ctx = _make_setup([_make_subtitle("hi", 0, 30)], with_template=False)
        with pytest.raises(ResolveError, match="テンプレートが見つかりません"):
            convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])

    def test_no_subtitles_raises(self):
        ctx = _make_setup([])
        with pytest.raises(ResolveError, match="字幕クリップがありません"):
            convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])

    def test_subtitle_track_out_of_range_raises(self):
        ctx = _make_setup([_make_subtitle("hi", 0, 30)])
        with pytest.raises(ResolveError, match="subtitle track 5 がタイムラインにありません"):
            convert_subtitles_to_text_plus(
                ctx["project"], ctx["timeline"], subtitle_track=5
            )

    def test_basic_flow_counts(self):
        subs = [
            _make_subtitle("first", 10, 50),
            _make_subtitle("second", 50, 90),
        ]
        ctx = _make_setup(subs, timeline_end=100)
        result = convert_subtitles_to_text_plus(
            ctx["project"],
            ctx["timeline"],
            extend_edges=False,
            fill_gaps=False,
            disable_subtitle_after=False,
        )
        assert isinstance(result, TextPlusResult)
        assert result.success == 2
        assert result.failed == 0

    def test_video_track_added_on_top(self):
        subs = [_make_subtitle("hi", 0, 30)]
        ctx = _make_setup(subs)
        result = convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])
        # 既存 video=1 → 追加後 video=2、配置先は V2
        assert ctx["track_counts"]["video"] == 2
        assert result.video_track == 2

    def test_extend_edges(self):
        subs = [
            _make_subtitle("first", 10, 50),
            _make_subtitle("last", 60, 90),
        ]
        ctx = _make_setup(subs, timeline_start=0, timeline_end=100)
        result = convert_subtitles_to_text_plus(
            ctx["project"],
            ctx["timeline"],
            extend_edges=True,
            fill_gaps=False,
            disable_subtitle_after=False,
        )
        assert result.head_extended == 10  # 10 - 0
        assert result.tail_extended == 10  # 100 - 90

    def test_fill_gaps_only_within_max_fill(self):
        subs = [
            _make_subtitle("first", 0, 30),
            _make_subtitle("second", 35, 60),  # gap=5 → 埋める
            _make_subtitle("third", 80, 100),  # gap=20 → 埋めない
        ]
        ctx = _make_setup(subs, timeline_end=200)
        result = convert_subtitles_to_text_plus(
            ctx["project"],
            ctx["timeline"],
            fill_gaps=True,
            max_fill_frames=10,
            extend_edges=False,
            disable_subtitle_after=False,
        )
        assert result.gap_filled == 1

    def test_subtitle_disabled_after_success(self):
        subs = [_make_subtitle("hi", 0, 30)]
        ctx = _make_setup(subs)
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=True
        )
        assert result.subtitle_disabled is True
        ctx["timeline"].SetTrackEnable.assert_called_with("subtitle", 1, False)

    def test_keep_subtitle_when_flag_false(self):
        subs = [_make_subtitle("hi", 0, 30)]
        ctx = _make_setup(subs)
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=False
        )
        assert result.subtitle_disabled is False
        ctx["timeline"].SetTrackEnable.assert_not_called()

    def test_u2028_converted_to_newline(self):
        u2028 = chr(0x2028)
        subs = [_make_subtitle(f"前{u2028}後", 0, 30)]
        ctx = _make_setup(subs)
        convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])
        # SetInput が \n 変換後の文字列で呼ばれる
        item = ctx["call_state"]["items"][0]
        item._text_tool.SetInput.assert_called_once_with("StyledText", "前\n後")

    def test_append_failure_counts_as_failed(self):
        subs = [
            _make_subtitle("a", 0, 30),
            _make_subtitle("b", 30, 60),
        ]
        # 1回目 (test) は成功、2回目 (1件目本配置) は成功、3回目 (2件目) で失敗
        ctx = _make_setup(subs, fail_appends_after=2)
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=False
        )
        assert result.success == 1
        assert result.failed == 1

    def test_duration_multiplier_invalid_falls_back_to_1(self):
        """test clip の GetDuration() が 0 の場合、multiplier=1.0 で続行する。"""
        subs = [_make_subtitle("hi", 0, 30)]
        ctx = _make_setup(subs, test_real_duration=0)
        # 例外を出さずに完了することを確認
        result = convert_subtitles_to_text_plus(ctx["project"], ctx["timeline"])
        assert result.success == 1

    def test_rollback_video_track_when_all_failed(self):
        """全件失敗時、追加した空 video track を DeleteTrack で削除する。"""
        subs = [_make_subtitle("a", 0, 30)]
        # fail_appends_after=1: test 配置 (1回目) のみ成功、本配置 (2回目) で失敗
        ctx = _make_setup(subs, fail_appends_after=1)
        ctx["timeline"].DeleteTrack.return_value = True
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=False
        )
        assert result.success == 0
        assert result.failed == 1
        # rollback で video_track=0 にマーク、DeleteTrack が呼ばれる
        assert result.video_track == 0
        ctx["timeline"].DeleteTrack.assert_called_with("video", 2)

    def test_no_rollback_when_partial_success(self):
        """部分成功時は video track を残す (DeleteTrack 呼ばれない)。"""
        subs = [
            _make_subtitle("a", 0, 30),
            _make_subtitle("b", 30, 60),
        ]
        # test (1) + 本配置1 (2) は成功、本配置2 (3) で失敗
        ctx = _make_setup(subs, fail_appends_after=2)
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=False
        )
        assert result.success == 1
        assert result.failed == 1
        assert result.video_track == 2
        ctx["timeline"].DeleteTrack.assert_not_called()

    def test_rollback_handles_delete_track_failure(self):
        """DeleteTrack が False を返しても例外なく続行する。"""
        subs = [_make_subtitle("a", 0, 30)]
        ctx = _make_setup(subs, fail_appends_after=1)
        ctx["timeline"].DeleteTrack.return_value = False
        # 例外なし
        result = convert_subtitles_to_text_plus(
            ctx["project"], ctx["timeline"], disable_subtitle_after=False
        )
        # 削除失敗のため video_track はそのまま残る
        assert result.video_track == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
