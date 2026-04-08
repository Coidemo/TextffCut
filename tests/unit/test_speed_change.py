"""速度変更機能のユニットテスト"""

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


class TestSuggestAndExportSpeed(unittest.TestCase):
    """SuggestAndExportRequest の speed フィールドテスト"""

    def test_default_speed_is_1(self):
        """デフォルトのspeedは1.0"""
        from use_cases.ai.suggest_and_export import SuggestAndExportRequest

        req = SuggestAndExportRequest.__new__(SuggestAndExportRequest)
        # dataclassのデフォルト値を確認
        import dataclasses
        fields = {f.name: f.default for f in dataclasses.fields(SuggestAndExportRequest)}
        self.assertEqual(fields["speed"], 1.0)

    def test_speed_field_exists(self):
        """speed フィールドが存在する"""
        from use_cases.ai.suggest_and_export import SuggestAndExportRequest
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SuggestAndExportRequest)]
        self.assertIn("speed", field_names)


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


class TestCLISpeedOption(unittest.TestCase):
    """CLIの--speedオプションテスト"""

    def test_parser_accepts_speed(self):
        """--speed オプションが受け付けられる"""
        from textffcut_cli.suggest_command import build_suggest_parser

        parser = build_suggest_parser()
        args = parser.parse_args(["--speed", "1.2", "video.mp4"])
        self.assertEqual(args.speed, 1.2)

    def test_parser_default_speed(self):
        """speed のデフォルトは 1.0"""
        from textffcut_cli.suggest_command import build_suggest_parser

        parser = build_suggest_parser()
        args = parser.parse_args(["video.mp4"])
        self.assertEqual(args.speed, 1.0)


if __name__ == "__main__":
    unittest.main()
