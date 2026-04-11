"""
final_video_generator のユニットテスト

テスト対象:
  - db_to_linear: dB → リニア変換
  - build_filter_complex: filter_complex文字列の構築（純粋関数）
  - generate_concat_list: concatリスト形式の検証
  - _run_ffmpeg: subprocess成功/失敗

外部依存（subprocess.run、ファイルシステム）はすべてモック化する。
"""

from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from use_cases.ai.final_video_generator import (
    _run_ffmpeg,
    build_filter_complex,
    db_to_linear,
    generate_concat_list,
)


# ---------------------------------------------------------------------------
# ヘルパー: テスト用スタブオブジェクト
# ---------------------------------------------------------------------------


@dataclass
class _SubtitleEntry:
    """SubtitleEntry のテスト用スタブ（Pillow不要）"""

    index: int
    start_time: float
    end_time: float
    text: str


@dataclass
class _SEPlacement:
    """SEPlacement のテスト用スタブ"""

    se_file: str
    timestamp: float
    reason: str = ""


# ---------------------------------------------------------------------------
# db_to_linear
# ---------------------------------------------------------------------------


class TestDbToLinear:
    """dB → リニア変換の正確性テスト"""

    def test_0db_is_1(self):
        """0dB はリニアスケールで 1.0"""
        assert db_to_linear(0) == pytest.approx(1.0)

    def test_minus_20db_approx_01(self):
        """-20dB は約 0.1"""
        result = db_to_linear(-20)
        assert result == pytest.approx(0.1, rel=1e-4)

    def test_minus_6db_approx_05(self):
        """-6dB は約 0.5 (半音量の理論値: 10^(-6/20))"""
        result = db_to_linear(-6)
        expected = 10 ** (-6 / 20)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_minus_40db(self):
        """-40dB は 0.01"""
        result = db_to_linear(-40)
        assert result == pytest.approx(0.01, rel=1e-4)

    def test_positive_db_greater_than_1(self):
        """+6dB はリニアスケールで 1 より大きい"""
        result = db_to_linear(6)
        assert result > 1.0

    def test_formula_correctness(self):
        """公式 10^(dB/20) と一致する"""
        for db in [-60, -20, -10, -6, -3, 0, 6]:
            assert db_to_linear(db) == pytest.approx(10 ** (db / 20), rel=1e-9)

    def test_negative_infinity_approaches_zero(self):
        """-120dB は 0 にきわめて近い"""
        result = db_to_linear(-120)
        assert result < 1e-5


# ---------------------------------------------------------------------------
# generate_concat_list
# ---------------------------------------------------------------------------


class TestGenerateConcatList:
    """generate_concat_list の出力形式テスト"""

    def test_single_range(self):
        """1つの時間範囲のコメント行を返す"""
        result = generate_concat_list([(0.0, 5.0)])
        assert "clip 0" in result
        assert "0.000" in result
        assert "5.000" in result

    def test_multiple_ranges(self):
        """複数範囲: clip 0, clip 1, ... が順番に現れる"""
        ranges = [(0.0, 3.0), (5.0, 8.0), (10.0, 15.5)]
        result = generate_concat_list(ranges)
        lines = result.splitlines()
        assert len(lines) == 3
        assert "clip 0" in lines[0]
        assert "clip 1" in lines[1]
        assert "clip 2" in lines[2]

    def test_duration_shown_in_output(self):
        """各行に持続時間（end - start）が表示される"""
        result = generate_concat_list([(2.0, 7.0)])
        # 持続時間 5.000 が含まれること
        assert "5.000" in result

    def test_empty_ranges(self):
        """空リストは空文字列を返す"""
        result = generate_concat_list([])
        assert result == ""

    def test_precise_timestamps(self):
        """タイムスタンプは小数点3桁精度でフォーマットされる"""
        result = generate_concat_list([(1.1234, 4.5678)])
        # 小数点3桁: 1.123, 4.568 (丸め)
        assert "1.123" in result
        assert "4.568" in result

    def test_start_end_both_present(self):
        """開始・終了両方の値が行に含まれる"""
        result = generate_concat_list([(3.5, 9.25)])
        assert "3.500" in result
        assert "9.250" in result


# ---------------------------------------------------------------------------
# _run_ffmpeg
# ---------------------------------------------------------------------------


class TestRunFfmpeg:
    """_run_ffmpeg の成功/失敗パスのテスト"""

    def test_success_returns_completed_process(self):
        """returncode=0 のとき CompletedProcess を返す"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            result = _run_ffmpeg(["ffmpeg", "-version"])

        assert result is mock_result
        mock_run.assert_called_once()

    def test_success_passes_correct_kwargs(self):
        """subprocess.run に capture_output=True, text=True が渡される"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _run_ffmpeg(["ffmpeg", "-y", "-i", "input.mp4", "output.mp4"], timeout=60)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True
        assert call_kwargs["text"] is True
        assert call_kwargs["timeout"] == 60

    def test_failure_raises_runtime_error(self):
        """returncode != 0 のとき RuntimeError を送出する"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stderr = "Error: codec not found"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="FFmpeg failed"):
                _run_ffmpeg(["ffmpeg", "-y"])

    def test_failure_includes_return_code_in_message(self):
        """エラーメッセージに returncode が含まれる"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 255
        mock_result.stderr = "fatal error"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match=r"rc=255"):
                _run_ffmpeg(["ffmpeg"])

    def test_failure_includes_stderr_in_message(self):
        """エラーメッセージに stderr の内容が含まれる"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stderr = "Invalid codec: badcodec"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Invalid codec: badcodec"):
                _run_ffmpeg(["ffmpeg"])

    def test_no_stderr_shows_placeholder(self):
        """stderr が None または空のとき代替メッセージを表示する"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="no stderr"):
                _run_ffmpeg(["ffmpeg"])

    def test_stderr_truncated_to_500_chars(self):
        """長い stderr は末尾 500 文字に切り詰められる"""
        long_stderr = "x" * 600
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stderr = long_stderr

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError) as exc_info:
                _run_ffmpeg(["ffmpeg"])

        # エラーメッセージには末尾500文字分 ('x' * 500) が含まれるが
        # 元の600文字全体は含まれない
        error_msg = str(exc_info.value)
        assert "x" * 500 in error_msg
        assert len(error_msg) < 600 + 100  # 600文字全体は含まれない

    def test_default_timeout_is_120(self):
        """デフォルトのタイムアウトは 120 秒"""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 0

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _run_ffmpeg(["ffmpeg"])

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["timeout"] == 120


# ---------------------------------------------------------------------------
# build_filter_complex — メインのテスト群
# ---------------------------------------------------------------------------


class TestBuildFilterComplexNoFilters:
    """フィルタが不要なケース: 空文字列タプルを返す"""

    def test_no_filters_returns_empty_tuple(self):
        """すべてのオプションが None のとき ("", "", "") を返す"""
        result = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
        )
        assert result == ("", "", "")

    def test_only_base_video_no_audio(self):
        """フレーム・タイトル・字幕・BGM・SEが全てNoneなら空タプル"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=None,
            title_idx=None,
            subtitle_indices=None,
            bgm_idx=None,
            se_indices=None,
        )
        assert filters == ""
        assert vid == ""
        assert aud == ""


class TestBuildFilterComplexFrameOnly:
    """フレームオーバーレイのみのケース"""

    def test_returns_non_empty_filter(self):
        """frame_idx が指定されると filter_complex が生成される"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert filters != ""
        assert vid != ""

    def test_scale_filter_present(self):
        """スケールフィルタが含まれる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert "scale=1080:1920" in filters

    def test_frame_overlay_label(self):
        """フレームオーバーレイの出力ラベル 'framed' が含まれる"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert "framed" in filters
        assert vid == "framed"

    def test_frame_input_index_used(self):
        """frame_idx の入力インデックスがフィルタに現れる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=2,
        )
        assert "[2:v]" in filters

    def test_overlay_at_origin(self):
        """フレームオーバーレイは 0:0 に配置される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert "overlay=0:0" in filters

    def test_audio_is_passthrough_when_no_audio_filters(self):
        """音声フィルタなしの場合、audio_out は 'base_idx:a' 形式"""
        _, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert aud == "0:a"

    def test_filter_uses_semicolons_as_separator(self):
        """複数のフィルタはセミコロンで区切られる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert ";" in filters

    def test_non_zero_base_idx(self):
        """base_idx が 0 以外でも正しく動作する"""
        filters, _, aud = build_filter_complex(
            base_idx=2,
            resolution=(1080, 1920),
            frame_idx=3,
        )
        assert "[2:v]" in filters
        assert "[3:v]" in filters
        assert aud == "2:a"


class TestBuildFilterComplexTitleOnly:
    """タイトル画像オーバーレイのみのケース"""

    def test_title_overlay_label(self):
        """タイトルオーバーレイの出力ラベル 'titled' が含まれる"""
        filters, vid, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            title_idx=1,
            title_duration=5.0,
        )
        assert "titled" in filters
        assert vid == "titled"

    def test_title_duration_in_filter(self):
        """タイトル表示秒数が enable='between(t,0,N)' として含まれる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            title_idx=1,
            title_duration=3.5,
        )
        assert "between(t,0,3.5)" in filters

    def test_title_input_index_used(self):
        """title_idx の入力インデックスがフィルタに現れる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            title_idx=2,
        )
        assert "[2:v]" in filters

    def test_title_scale_applied(self):
        """タイトル画像にもスケールが適用される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            title_idx=1,
        )
        assert "title_scaled" in filters


class TestBuildFilterComplexSubtitles:
    """字幕画像オーバーレイのテスト"""

    def _make_entry(self, start: float, end: float, idx: int = 0) -> _SubtitleEntry:
        return _SubtitleEntry(index=idx, start_time=start, end_time=end, text="テスト字幕")

    def test_single_subtitle_label(self):
        """1枚の字幕は 'sub0' ラベルを持つ"""
        entry = self._make_entry(1.0, 3.0)
        filters, vid, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
        )
        assert "sub0" in filters
        assert vid == "sub0"

    def test_multiple_subtitles_chained(self):
        """複数字幕は sub0 → sub1 → ... とチェーンされる"""
        entries = [
            (1, self._make_entry(0.0, 2.0)),
            (2, self._make_entry(2.5, 5.0)),
            (3, self._make_entry(5.5, 8.0)),
        ]
        filters, vid, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=entries,
        )
        assert "sub0" in filters
        assert "sub1" in filters
        assert "sub2" in filters
        assert vid == "sub2"

    def test_subtitle_timing_in_filter(self):
        """字幕の開始・終了時刻が enable='between(t,...)' として含まれる"""
        entry = self._make_entry(2.5, 7.123)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
        )
        assert "between(t,2.500,7.123)" in filters

    def test_subtitle_bottom_position(self):
        """subtitle_position='bottom' のとき y='H-h-margin' 式が使われる"""
        entry = self._make_entry(0.0, 2.0)
        margin = 80
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
            subtitle_position="bottom",
            subtitle_margin_bottom=margin,
        )
        assert f"H-h-{margin}" in filters

    def test_subtitle_top_position(self):
        """subtitle_position='top' のとき y='margin' の数値が使われる"""
        entry = self._make_entry(0.0, 2.0)
        margin = 50
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
            subtitle_position="top",
            subtitle_margin_bottom=margin,
        )
        assert f":y={margin}:" in filters

    def test_subtitle_x_centered(self):
        """字幕の x 座標は (W-w)/2 で水平中央に配置される"""
        entry = self._make_entry(0.0, 2.0)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
        )
        assert "x=(W-w)/2" in filters

    def test_subtitle_input_index_used(self):
        """指定した入力インデックスがフィルタに使われる"""
        entry = self._make_entry(0.0, 2.0)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(3, entry)],
        )
        assert "[3:v]" in filters


class TestBuildFilterComplexBGM:
    """BGMフィルタのテスト"""

    def test_bgm_volume_filter_present(self):
        """BGMの volume フィルタが含まれる"""
        filters, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,  # ビデオフィルタが必要（そうでなければ空タプル）
            bgm_idx=2,
            bgm_volume_db=-25,
        )
        assert "volume=" in filters
        assert "bgm_vol" in filters

    def test_bgm_volume_value_correct(self):
        """BGM音量の数値が db_to_linear(-25) と一致する"""
        expected_vol = db_to_linear(-25)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            bgm_idx=2,
            bgm_volume_db=-25,
        )
        assert f"volume={expected_vol:.6f}" in filters

    def test_bgm_mixed_in_amix(self):
        """BGMが有効な場合、amix フィルタが追加される"""
        filters, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            bgm_idx=2,
        )
        assert "amix" in filters
        assert aud == "outa"

    def test_bgm_input_index_used(self):
        """bgm_idx の入力インデックスがフィルタに現れる"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            bgm_idx=3,
        )
        assert "[3:a]" in filters

    def test_amix_dropout_transition(self):
        """amix の dropout_transition が設定されている"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            bgm_idx=2,
        )
        assert "dropout_transition=2" in filters

    def test_amix_duration_first(self):
        """amix の duration パラメータが first に設定される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            bgm_idx=2,
        )
        assert "duration=first" in filters

    def test_audio_only_bgm_no_video_filters(self):
        """音声フィルタのみ（ビデオフィルタなし）でも filter_complex は生成される"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            bgm_idx=1,
        )
        assert filters != ""
        assert aud == "outa"


class TestBuildFilterComplexSE:
    """SEフィルタのテスト"""

    def _make_placement(self, timestamp: float, se_file: str = "se.mp3") -> _SEPlacement:
        return _SEPlacement(se_file=se_file, timestamp=timestamp)

    def test_se_volume_filter_present(self):
        """SE の volume フィルタが含まれる"""
        placement = self._make_placement(timestamp=1.5)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[(2, placement)],
            se_volume_db=-20,
        )
        assert "volume=" in filters

    def test_se_adelay_uses_timestamp_ms(self):
        """SE の adelay がタイムスタンプ（ミリ秒）で設定される"""
        placement = self._make_placement(timestamp=2.5)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[(2, placement)],
        )
        # 2.5秒 = 2500ミリ秒
        assert "adelay=2500|2500" in filters

    def test_se_label_indexed(self):
        """SE ラベルは se0, se1, ... の形式"""
        placements = [
            (2, self._make_placement(1.0)),
            (3, self._make_placement(3.0)),
        ]
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=placements,
        )
        assert "se0" in filters
        assert "se1" in filters

    def test_multiple_se_in_amix(self):
        """複数SEがある場合、amix の inputs 数が正しい（元音声 + BGM + SE数）"""
        placements = [
            (2, self._make_placement(1.0)),
            (3, self._make_placement(3.0)),
        ]
        filters, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=placements,
        )
        # 元音声 + SE×2 = 3 inputs
        assert "amix=inputs=3" in filters
        assert aud == "outa"

    def test_se_volume_value_correct(self):
        """SE音量の数値が db_to_linear(se_volume_db) と一致する"""
        placement = self._make_placement(timestamp=1.0)
        se_db = -15
        expected_vol = db_to_linear(se_db)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[(2, placement)],
            se_volume_db=se_db,
        )
        assert f"volume={expected_vol:.6f}" in filters

    def test_se_timestamp_zero_delay(self):
        """timestamp=0 は adelay=0|0 となる"""
        placement = self._make_placement(timestamp=0.0)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[(2, placement)],
        )
        assert "adelay=0|0" in filters


class TestBuildFilterComplexAllCombined:
    """全オプションを組み合わせた統合テスト"""

    def _make_entry(self, start: float, end: float) -> _SubtitleEntry:
        return _SubtitleEntry(index=0, start_time=start, end_time=end, text="字幕")

    def _make_placement(self, timestamp: float) -> _SEPlacement:
        return _SEPlacement(se_file="se.mp3", timestamp=timestamp)

    def setup_method(self):
        """共通パラメータをセットアップ"""
        self.base_idx = 0
        self.frame_idx = 1
        self.title_idx = 2
        self.subtitle_entry = self._make_entry(3.0, 6.0)
        self.subtitle_indices = [(3, self.subtitle_entry)]
        self.bgm_idx = 4
        self.se_placement = self._make_placement(1.5)
        self.se_indices = [(5, self.se_placement)]
        self.resolution = (1080, 1920)

    def _build_all(self):
        return build_filter_complex(
            base_idx=self.base_idx,
            resolution=self.resolution,
            frame_idx=self.frame_idx,
            title_idx=self.title_idx,
            title_duration=5.0,
            subtitle_indices=self.subtitle_indices,
            subtitle_position="bottom",
            subtitle_margin_bottom=80,
            bgm_idx=self.bgm_idx,
            bgm_volume_db=-25,
            se_indices=self.se_indices,
            se_volume_db=-20,
        )

    def test_returns_three_tuple(self):
        """戻り値は (filter_str, video_label, audio_label) の3要素タプル"""
        result = self._build_all()
        assert len(result) == 3

    def test_filter_string_not_empty(self):
        """filter_complex 文字列が空でない"""
        filters, _, _ = self._build_all()
        assert filters != ""

    def test_video_out_label_is_last_subtitle(self):
        """字幕が最後のビデオフィルタなので、vid は 'sub0'"""
        _, vid, _ = self._build_all()
        assert vid == "sub0"

    def test_audio_out_is_outa(self):
        """BGMとSEが有効なので audio_out は 'outa'"""
        _, _, aud = self._build_all()
        assert aud == "outa"

    def test_all_labels_present(self):
        """全フィルタラベルが filter_complex に含まれる"""
        filters, _, _ = self._build_all()
        expected_labels = ["scaled", "frame_scaled", "framed", "title_scaled", "titled", "sub0", "bgm_vol", "se0"]
        for label in expected_labels:
            assert label in filters, f"ラベル '{label}' が filter_complex に見つからない"

    def test_semicolons_separate_filter_chains(self):
        """フィルタはセミコロン区切りで結合される"""
        filters, _, _ = self._build_all()
        assert ";" in filters

    def test_filter_order_scale_first(self):
        """スケールフィルタが最初に現れる"""
        filters, _, _ = self._build_all()
        scale_pos = filters.find("scale=")
        frame_pos = filters.find("framed")
        title_pos = filters.find("titled")
        assert scale_pos < frame_pos < title_pos

    def test_amix_inputs_count(self):
        """amix の inputs 数 = 元音声(1) + BGM(1) + SE(1) = 3"""
        filters, _, _ = self._build_all()
        assert "amix=inputs=3" in filters

    def test_overlay_syntax_correct(self):
        """overlay フィルタの構文が正しい（overlay=x=...:y=...）"""
        filters, _, _ = self._build_all()
        # 字幕オーバーレイは x=(W-w)/2 の形式
        assert "overlay=x=(W-w)/2" in filters
        # フレームオーバーレイは overlay=0:0
        assert "overlay=0:0" in filters


class TestBuildFilterComplexReturnTypes:
    """戻り値の型と構造の検証"""

    def test_empty_case_types(self):
        """空の場合の戻り値はすべて str"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
        )
        assert isinstance(filters, str)
        assert isinstance(vid, str)
        assert isinstance(aud, str)

    def test_non_empty_case_types(self):
        """非空の場合の戻り値もすべて str"""
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert isinstance(filters, str)
        assert isinstance(vid, str)
        assert isinstance(aud, str)

    def test_video_out_does_not_have_brackets(self):
        """video_out ラベルは角括弧なしの文字列"""
        _, vid, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert not vid.startswith("[")
        assert not vid.endswith("]")

    def test_audio_out_passthrough_format(self):
        """音声フィルタなしの audio_out は 'N:a' 形式（角括弧なし）"""
        _, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        # "0:a" の形式：角括弧なし
        assert ":" in aud
        assert not aud.startswith("[")

    def test_audio_out_with_filter_no_brackets(self):
        """音声フィルタあり（outa）も角括弧なし"""
        _, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            bgm_idx=1,
        )
        assert aud == "outa"
        assert not aud.startswith("[")


class TestBuildFilterComplexResolution:
    """解像度パラメータのテスト"""

    def test_custom_resolution_in_scale_filter(self):
        """指定した解像度がスケールフィルタに反映される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1920, 1080),
            frame_idx=1,
        )
        assert "scale=1920:1080" in filters

    def test_square_resolution(self):
        """正方形解像度でもスケールフィルタが正しく生成される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1080),
            frame_idx=1,
        )
        assert "scale=1080:1080" in filters

    def test_pad_filter_present(self):
        """pad フィルタがスケールフィルタとセットで追加される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert "pad=" in filters

    def test_pad_centering_formula(self):
        """pad の位置式が (ow-iw)/2:(oh-ih)/2 形式"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
        )
        assert "(ow-iw)/2:(oh-ih)/2" in filters


class TestBuildFilterComplexEdgeCases:
    """エッジケースのテスト"""

    def test_title_duration_integer_displayed_correctly(self):
        """title_duration が整数のとき、between 式に正確に反映される"""
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            title_idx=1,
            title_duration=10,
        )
        assert "between(t,0,10)" in filters

    def test_subtitle_with_zero_margin(self):
        """subtitle_margin_bottom=0 のとき y=H-h-0 が生成される"""
        entry = _SubtitleEntry(index=0, start_time=0.0, end_time=2.0, text="test")
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[(1, entry)],
            subtitle_position="bottom",
            subtitle_margin_bottom=0,
        )
        assert "H-h-0" in filters

    def test_bgm_and_se_without_video_filter(self):
        """ビデオフィルタなし + BGM + SE の組み合わせ"""
        placement = _SEPlacement(se_file="se.mp3", timestamp=1.0)
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            bgm_idx=1,
            se_indices=[(2, placement)],
        )
        # ビデオフィルタがあるかどうかは問わない（スケールが追加されうる）
        assert "amix" in filters
        assert aud == "outa"

    def test_se_delay_large_timestamp(self):
        """大きなタイムスタンプ（60秒）が正しくミリ秒変換される"""
        placement = _SEPlacement(se_file="se.mp3", timestamp=60.0)
        filters, _, _ = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[(2, placement)],
        )
        assert "adelay=60000|60000" in filters

    def test_empty_subtitle_list_treated_as_no_subtitle(self):
        """subtitle_indices=[] は字幕なしと同等（ビデオフィルタは None と同じ扱い）"""
        # フレームもタイトルも字幕もなく BGM もなければ空タプル
        filters, vid, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            subtitle_indices=[],
        )
        assert filters == ""
        assert vid == ""
        assert aud == ""

    def test_empty_se_list_treated_as_no_se(self):
        """se_indices=[] は SE なしと同等"""
        filters, _, aud = build_filter_complex(
            base_idx=0,
            resolution=(1080, 1920),
            frame_idx=1,
            se_indices=[],
        )
        # BGM なし、SE なしなので amix は生成されない
        assert "amix" not in filters
        assert aud == "0:a"
