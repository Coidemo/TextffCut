"""textffcut_cli/send_command.py の argparse テスト."""

from __future__ import annotations

from textffcut_cli.send_command import _build_parser


class TestSendCommandArgparse:
    """`textffcut send` の引数解析テスト."""

    def test_text_plus_max_fill_frames_default_is_constant(self):
        """--text-plus-max-fill-frames を指定しない場合は定数 9999 が使われる."""
        from infrastructure.davinci_resolve import TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES

        parser = _build_parser()
        args = parser.parse_args(["clip.fcpxml"])
        assert args.text_plus_max_fill_frames == TEXT_PLUS_DEFAULT_MAX_FILL_FRAMES
        assert args.text_plus_max_fill_frames == 9999

    def test_text_plus_max_fill_frames_explicit_value(self):
        """ユーザーが明示指定した値が args に反映される."""
        parser = _build_parser()
        args = parser.parse_args(["clip.fcpxml", "--text-plus-max-fill-frames", "300"])
        assert args.text_plus_max_fill_frames == 300

    def test_text_plus_max_fill_frames_zero(self):
        """0 を明示指定すると Fill Gaps を無効化する意図が伝わる."""
        parser = _build_parser()
        args = parser.parse_args(["clip.fcpxml", "--text-plus-max-fill-frames", "0"])
        assert args.text_plus_max_fill_frames == 0

    def test_text_plus_max_fill_frames_int_type(self):
        """type=int により文字列引数も int に変換される."""
        parser = _build_parser()
        args = parser.parse_args(["clip.fcpxml", "--text-plus-max-fill-frames", "1234"])
        assert isinstance(args.text_plus_max_fill_frames, int)
