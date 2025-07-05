"""
Durationクラスの単体テスト

すべてのメソッドとプロパティを網羅的にテストします。
"""

import pytest
from domain.value_objects.duration import Duration


class TestDuration:
    """Duration値オブジェクトのテスト"""

    def test_init_with_valid_seconds(self):
        """有効な秒数で初期化できることを確認"""
        duration = Duration(seconds=120.5)
        assert duration.seconds == 120.5

    def test_init_with_negative_seconds_raises_error(self):
        """負の秒数で初期化するとエラーになることを確認"""
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            Duration(seconds=-1)

    def test_minutes_property(self):
        """minutesプロパティが正しく計算されることを確認"""
        duration = Duration(seconds=150)  # 2分30秒
        assert duration.minutes == 2.5

    def test_hours_property(self):
        """hoursプロパティが正しく計算されることを確認"""
        duration = Duration(seconds=7200)  # 2時間
        assert duration.hours == 2.0

    def test_milliseconds_property(self):
        """millisecondsプロパティが正しく計算されることを確認"""
        duration = Duration(seconds=1.5)
        assert duration.milliseconds == 1500

    def test_is_zero_property(self):
        """is_zeroプロパティが正しく判定されることを確認"""
        assert Duration(seconds=0).is_zero is True
        assert Duration(seconds=0.001).is_zero is False

    def test_to_timecode(self):
        """to_timecodeメソッドが正しいフォーマットを返すことを確認"""
        # 実装は HH:MM:SS:FF 形式（フレーム）
        test_cases = [
            (0, "00:00:00:00"),
            (1.5, "00:00:01:15"),  # 1.5秒 = 1秒 + 15フレーム（30fps）
            (61.25, "00:01:01:07"),  # 61.25秒 = 61秒 + 7.5フレーム
            (3661.5, "01:01:01:15"),  # 3661.5秒
        ]
        for seconds, expected in test_cases:
            duration = Duration(seconds=seconds)
            assert duration.to_timecode() == expected

    def test_to_srt_timecode(self):
        """to_srt_timecodeメソッドが正しいSRTフォーマットを返すことを確認"""
        test_cases = [
            (0, "00:00:00,000"),
            (1.5, "00:00:01,500"),
            (61.25, "00:01:01,250"),
            (3661.5, "01:01:01,500"),
        ]
        for seconds, expected in test_cases:
            duration = Duration(seconds=seconds)
            assert duration.to_srt_timecode() == expected

    def test_to_human_readable(self):
        """to_human_readableメソッドが人間が読みやすい形式を返すことを確認"""
        # 実装は ms, s, m s, h m s 形式
        test_cases = [
            (0, "0ms"),
            (0.5, "500ms"),
            (30, "30.0s"),
            (90, "1m 30.0s"),
            (3690, "1h 1m 30.0s"),
            (7200, "2h 0m 0.0s"),
        ]
        for seconds, expected in test_cases:
            duration = Duration(seconds=seconds)
            assert duration.to_human_readable() == expected

    def test_add(self):
        """addメソッドが正しく動作することを確認"""
        d1 = Duration(seconds=10)
        d2 = Duration(seconds=20)
        result = d1.add(d2)
        assert result.seconds == 30
        # 元のオブジェクトが変更されていないことを確認
        assert d1.seconds == 10
        assert d2.seconds == 20

    def test_subtract(self):
        """subtractメソッドが正しく動作することを確認"""
        d1 = Duration(seconds=30)
        d2 = Duration(seconds=10)
        result = d1.subtract(d2)
        assert result.seconds == 20

    def test_subtract_resulting_negative_clamps_to_zero(self):
        """引き算の結果が負になる場合0にクランプされることを確認"""
        d1 = Duration(seconds=10)
        d2 = Duration(seconds=20)
        # 実装は負の値を0にクランプする
        result = d1.subtract(d2)
        assert result.seconds == 0

    def test_multiply(self):
        """multiplyメソッドが正しく動作することを確認"""
        duration = Duration(seconds=10)
        result = duration.multiply(2.5)
        assert result.seconds == 25

    def test_multiply_with_negative_raises_error(self):
        """負の数で乗算するとエラーになることを確認"""
        duration = Duration(seconds=10)
        # 負の結果はDurationの初期化時にエラーになる
        with pytest.raises(ValueError, match="Duration cannot be negative"):
            duration.multiply(-1)

    def test_divide(self):
        """divideメソッドが正しく動作することを確認"""
        duration = Duration(seconds=20)
        result = duration.divide(4)
        assert result.seconds == 5

    def test_divide_by_zero_raises_error(self):
        """ゼロで除算するとエラーになることを確認"""
        duration = Duration(seconds=10)
        with pytest.raises(ValueError, match="Cannot divide by zero"):
            duration.divide(0)

    def test_from_milliseconds(self):
        """from_millisecondsクラスメソッドが正しく動作することを確認"""
        duration = Duration.from_milliseconds(1500)
        assert duration.seconds == 1.5

    def test_from_minutes(self):
        """from_minutesクラスメソッドが正しく動作することを確認"""
        duration = Duration.from_minutes(2.5)
        assert duration.seconds == 150

    def test_from_hours(self):
        """from_hoursクラスメソッドが正しく動作することを確認"""
        duration = Duration.from_hours(1.5)
        assert duration.seconds == 5400

    def test_from_timecode(self):
        """from_timecodeクラスメソッドが正しく動作することを確認"""
        # 実装は HH:MM:SS:FF 形式のみサポート
        test_cases = [
            ("00:00:00:00", 0),
            ("00:00:01:15", 1.5),  # 1秒 + 15フレーム(30fps) = 1.5秒
            ("00:01:01:07", 61 + 7/30.0),  # 61秒 + 7フレーム
            ("01:01:01:15", 3661.5),  # 1時間1分1秒15フレーム
        ]
        for timecode, expected_seconds in test_cases:
            duration = Duration.from_timecode(timecode)
            assert abs(duration.seconds - expected_seconds) < 0.001  # 浮動小数点誤差を考慮

    def test_from_timecode_invalid_format_raises_error(self):
        """無効なタイムコード形式でエラーになることを確認"""
        invalid_timecodes = [
            "invalid",
            "00:00",
            "00:00:00",  # FF部分が足りない
            "00:00:00.000",  # ドット区切りは無効
        ]
        for invalid_timecode in invalid_timecodes:
            with pytest.raises(ValueError, match="Timecode must be in HH:MM:SS:FF format"):
                Duration.from_timecode(invalid_timecode)

    def test_comparison_operators(self):
        """比較演算子が正しく動作することを確認"""
        d1 = Duration(seconds=10)
        d2 = Duration(seconds=20)
        d3 = Duration(seconds=10)

        # 小なり
        assert d1 < d2
        assert not d2 < d1
        assert not d1 < d3

        # 小なりイコール
        assert d1 <= d2
        assert d1 <= d3
        assert not d2 <= d1

        # 大なり
        assert d2 > d1
        assert not d1 > d2
        assert not d1 > d3

        # 大なりイコール
        assert d2 >= d1
        assert d1 >= d3
        assert not d1 >= d2

        # 等価
        assert d1 == d3
        assert not d1 == d2

        # 非等価
        assert d1 != d2
        assert not d1 != d3

    def test_repr(self):
        """__repr__メソッドが正しい文字列を返すことを確認"""
        duration = Duration(seconds=120.5)
        assert repr(duration) == "Duration(seconds=120.5)"

    def test_str(self):
        """__str__メソッドが正しい文字列を返すことを確認"""
        duration = Duration(seconds=120.5)
        # __str__はto_human_readableを使用
        assert str(duration) == "2m 0.5s"

    def test_immutability(self):
        """Durationオブジェクトが不変であることを確認"""
        duration = Duration(seconds=10)
        with pytest.raises(AttributeError):
            duration.seconds = 20

    def test_precision(self):
        """浮動小数点の精度が保たれることを確認"""
        # 非常に小さい値
        duration = Duration(seconds=0.001)
        assert duration.milliseconds == 1

        # 大きな値
        duration = Duration(seconds=86400.999)  # 約1日
        # 24:00:00 + 29.97フレーム（30fps）
        assert duration.to_timecode() == "24:00:00:29"