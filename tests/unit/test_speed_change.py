"""速度変更・ズーム・アンカー・タイムライン設定のユニットテスト"""

import argparse
import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.video import VideoProcessor


class TestCreateSpeedChangedVideo(unittest.TestCase):
    """VideoProcessor.create_speed_changed_video() のテスト"""

    def setUp(self):
        from config import Config

        with patch.object(Config, "__post_init__"):
            self.config = Config.__new__(Config)
        self.vp = VideoProcessor(self.config)

    def test_speed_out_of_range_raises(self):
        """speed が 0.5〜2.0 の範囲外だとValueError"""
        with self.assertRaises(ValueError):
            self.vp.create_speed_changed_video("/tmp/in.mp4", "/tmp/out.mp4", speed=0.3)
        with self.assertRaises(ValueError):
            self.vp.create_speed_changed_video("/tmp/in.mp4", "/tmp/out.mp4", speed=2.5)

    @patch("core.video.subprocess.run")
    @patch("core.video.ensure_directory")
    def test_cache_skips_ffmpeg(self, mock_ensure, mock_run):
        """既存ファイルがあればFFmpegをスキップ"""
        with patch.object(Path, "exists", return_value=True), \
             patch.object(Path, "stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=1000)
            result = self.vp.create_speed_changed_video("/tmp/in.mp4", "/tmp/out.mp4", 1.2)

        self.assertEqual(result, "/tmp/out.mp4")
        mock_run.assert_not_called()

    @patch("core.video.subprocess.run")
    @patch("core.video.ensure_directory")
    def test_ffmpeg_command_correct(self, mock_ensure, mock_run):
        """FFmpegコマンドが正しく構築される"""
        mock_run.return_value = MagicMock(returncode=0)

        with patch.object(Path, "exists", return_value=False):
            result = self.vp.create_speed_changed_video("/tmp/in.mp4", "/tmp/out.mp4", 1.2)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]

        # -itsscale が 1/1.2 ≈ 0.8333
        itsscale_idx = cmd.index("-itsscale")
        itsscale_val = float(cmd[itsscale_idx + 1])
        self.assertAlmostEqual(itsscale_val, 1.0 / 1.2, places=4)

        # -c:v copy
        cv_idx = cmd.index("-c:v")
        self.assertEqual(cmd[cv_idx + 1], "copy")

        # -af atempo=1.2
        af_idx = cmd.index("-af")
        self.assertEqual(cmd[af_idx + 1], "atempo=1.2")

        # -c:a aac -b:a 320k
        ca_idx = cmd.index("-c:a")
        self.assertEqual(cmd[ca_idx + 1], "aac")
        ba_idx = cmd.index("-b:a")
        self.assertEqual(cmd[ba_idx + 1], "320k")

        self.assertEqual(result, "/tmp/out.mp4")

    @patch("core.video.subprocess.run")
    @patch("core.video.ensure_directory")
    def test_ffmpeg_failure_raises(self, mock_ensure, mock_run):
        """FFmpegが失敗したらFFmpegError"""
        mock_run.return_value = MagicMock(returncode=1, stderr="error")

        with patch.object(Path, "exists", return_value=False):
            with self.assertRaises(Exception) as ctx:
                self.vp.create_speed_changed_video("/tmp/in.mp4", "/tmp/out.mp4", 1.2)

        self.assertIn("FFmpeg", type(ctx.exception).__name__)


class TestSuggestAndExportRequest(unittest.TestCase):
    """SuggestAndExportRequest のフィールドテスト"""

    def test_default_values(self):
        """全追加フィールドのデフォルト値を確認"""
        import dataclasses

        from use_cases.ai.suggest_and_export import SuggestAndExportRequest

        fields = {f.name: f.default for f in dataclasses.fields(SuggestAndExportRequest)}
        self.assertEqual(fields["speed"], 1.0)
        self.assertEqual(fields["scale"], (1.0, 1.0))
        self.assertEqual(fields["anchor"], (0.0, 0.0))
        self.assertEqual(fields["timeline_resolution"], "horizontal")

    def test_all_new_fields_exist(self):
        """speed, scale, anchor, timeline_resolution が存在する"""
        import dataclasses

        from use_cases.ai.suggest_and_export import SuggestAndExportRequest

        field_names = [f.name for f in dataclasses.fields(SuggestAndExportRequest)]
        for name in ("speed", "scale", "anchor", "timeline_resolution"):
            self.assertIn(name, field_names)


class TestTimeRangeAdjustment(unittest.TestCase):
    """速度変更時のtime_ranges調整テスト"""

    def test_time_ranges_scaled_correctly(self):
        """time_rangesが1/speedに正しく調整される"""
        speed = 1.2
        original_ranges = [(0.0, 12.0), (24.0, 36.0)]

        adjusted = [(s / speed, e / speed) for s, e in original_ranges]

        self.assertAlmostEqual(adjusted[0][0], 0.0)
        self.assertAlmostEqual(adjusted[0][1], 10.0)
        self.assertAlmostEqual(adjusted[1][0], 20.0)
        self.assertAlmostEqual(adjusted[1][1], 30.0)

    def test_total_duration_after_speed_change(self):
        """速度変更後のtotal_durationが正しい"""
        speed = 1.2
        original_ranges = [(0.0, 12.0), (24.0, 36.0)]
        adjusted = [(s / speed, e / speed) for s, e in original_ranges]
        total = sum(e - s for s, e in adjusted)

        # 元: 12+12=24秒 → 1.2倍速後: 24/1.2=20秒
        self.assertAlmostEqual(total, 20.0)


class TestCLIOptions(unittest.TestCase):
    """CLIオプションのテスト"""

    def _parse(self, args_str: str) -> argparse.Namespace:
        from textffcut_cli.suggest_command import build_suggest_parser

        return build_suggest_parser().parse_args(args_str.split())

    def test_speed_accepted(self):
        args = self._parse("--speed 1.2 video.mp4")
        self.assertEqual(args.speed, 1.2)

    def test_speed_default(self):
        args = self._parse("video.mp4")
        self.assertEqual(args.speed, 1.0)

    def test_speed_out_of_range_rejected(self):
        """範囲外の --speed はパーサーがエラーにする"""
        from textffcut_cli.suggest_command import build_suggest_parser

        parser = build_suggest_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["--speed", "3.0", "video.mp4"])

    def test_zoom_accepted(self):
        args = self._parse("--zoom 200 video.mp4")
        self.assertEqual(args.zoom, 200)

    def test_zoom_default(self):
        args = self._parse("video.mp4")
        self.assertEqual(args.zoom, 100)

    def test_anchor_accepted(self):
        args = self._parse("--anchor 10.5 -5.0 video.mp4")
        self.assertEqual(args.anchor, [10.5, -5.0])

    def test_anchor_default(self):
        args = self._parse("video.mp4")
        self.assertEqual(args.anchor, [0.0, 0.0])

    def test_vertical_flag(self):
        args = self._parse("--vertical video.mp4")
        self.assertTrue(args.vertical)

    def test_vertical_default(self):
        args = self._parse("video.mp4")
        self.assertFalse(args.vertical)

    def test_all_options_combined(self):
        """全オプションを同時指定"""
        args = self._parse("--speed 1.2 --zoom 200 --anchor 10 5 --vertical video.mp4")
        self.assertEqual(args.speed, 1.2)
        self.assertEqual(args.zoom, 200)
        self.assertEqual(args.anchor, [10.0, 5.0])
        self.assertTrue(args.vertical)


class TestSimpleFcpxmlScaleAndTimeline(unittest.TestCase):
    """_export_simple_fcpxml のscale/anchor/timeline_resolution反映テスト"""

    def _make_suggestion(self):
        from domain.entities.clip_suggestion import ClipSuggestion

        return ClipSuggestion(
            id="test_1",
            title="test",
            text="test text",
            time_ranges=[(0.0, 10.0)],
            total_duration=10.0,
            score=80,
            category="test",
            reasoning="test",
            variant_label="test",
        )

    def test_scale_reflected_in_xml(self):
        """scaleがXMLに反映される"""
        from use_cases.ai.suggest_and_export import SuggestAndExportUseCase

        uc = SuggestAndExportUseCase.__new__(SuggestAndExportUseCase)
        suggestion = self._make_suggestion()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".fcpxml", delete=False) as f:
            output_path = Path(f.name)

        try:
            uc._export_simple_fcpxml(
                suggestion, Path("/tmp/video.mp4"), output_path,
                scale=(2.0, 2.0), anchor=(10.0, 5.0),
            )
            xml = output_path.read_text()
            self.assertIn('scale="2 2"', xml)
            self.assertIn('anchor="10 5"', xml)
        finally:
            output_path.unlink(missing_ok=True)

    def test_vertical_timeline_resolution(self):
        """縦タイムラインでwidth/heightが入れ替わる"""
        from use_cases.ai.suggest_and_export import SuggestAndExportUseCase

        uc = SuggestAndExportUseCase.__new__(SuggestAndExportUseCase)
        suggestion = self._make_suggestion()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".fcpxml", delete=False) as f:
            output_path = Path(f.name)

        try:
            uc._export_simple_fcpxml(
                suggestion, Path("/tmp/video.mp4"), output_path,
                timeline_resolution="vertical",
            )
            xml = output_path.read_text()
            self.assertIn('width="1080"', xml)
            self.assertIn('height="1920"', xml)
        finally:
            output_path.unlink(missing_ok=True)

    def test_horizontal_timeline_default(self):
        """横タイムラインがデフォルト"""
        from use_cases.ai.suggest_and_export import SuggestAndExportUseCase

        uc = SuggestAndExportUseCase.__new__(SuggestAndExportUseCase)
        suggestion = self._make_suggestion()

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".fcpxml", delete=False) as f:
            output_path = Path(f.name)

        try:
            uc._export_simple_fcpxml(
                suggestion, Path("/tmp/video.mp4"), output_path,
            )
            xml = output_path.read_text()
            self.assertIn('width="1920"', xml)
            self.assertIn('height="1080"', xml)
        finally:
            output_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
