"""
core/export.py のユニットテスト
"""

import math

import pytest

from core.export import _safe_volume_db


class TestSafeVolumeDb:
    """_safe_volume_db() のテスト

    adjust-volume amount用の安全な文字列を返す関数。
    dB範囲 [-96, 12] にクランプし、不正入力は "0" にフォールバックする。
    """

    # --- 正常な数値入力 ---

    def test_normal_negative_value(self):
        assert _safe_volume_db(-20.0) == "-20"

    def test_normal_positive_value(self):
        assert _safe_volume_db(5) == "5"

    # --- 範囲クランプ ---

    def test_clamp_below_minimum(self):
        """下限 -96 未満の値は -96 にクランプ"""
        assert _safe_volume_db(-200) == "-96"

    def test_clamp_above_maximum(self):
        """上限 12 超の値は 12 にクランプ"""
        assert _safe_volume_db(100) == "12"

    # --- 境界値 ---

    def test_boundary_minimum(self):
        assert _safe_volume_db(-96) == "-96"

    def test_boundary_maximum(self):
        assert _safe_volume_db(12) == "12"

    def test_boundary_just_inside_min(self):
        assert _safe_volume_db(-95.9) == "-95.9"

    def test_boundary_just_inside_max(self):
        assert _safe_volume_db(11.9) == "11.9"

    # --- ゼロ ---

    def test_zero(self):
        assert _safe_volume_db(0) == "0"

    def test_zero_float(self):
        assert _safe_volume_db(0.0) == "0"

    # --- 小数値 ---

    def test_decimal_value(self):
        assert _safe_volume_db(-3.5) == "-3.5"

    def test_decimal_positive(self):
        assert _safe_volume_db(1.5) == "1.5"

    # --- 不正入力のフォールバック ---

    def test_string_input_returns_zero(self):
        assert _safe_volume_db("abc") == "0"

    def test_none_input_returns_zero(self):
        assert _safe_volume_db(None) == "0"

    # --- 特殊な浮動小数点値 ---

    def test_positive_inf_clamped_to_max(self):
        """float('inf') は上限 12 にクランプ"""
        assert _safe_volume_db(float("inf")) == "12"

    def test_negative_inf_clamped_to_min(self):
        """float('-inf') は下限 -96 にクランプ"""
        assert _safe_volume_db(float("-inf")) == "-96"

    def test_nan_does_not_crash(self):
        """float('nan') でクラッシュせず、有効な文字列を返す"""
        result = _safe_volume_db(float("nan"))
        # NaN は比較が特殊だが、クラッシュせず文字列を返すことを確認
        assert isinstance(result, str)
        # 結果が有効なdB範囲内の数値であることを確認
        assert float(result) <= 12
        assert float(result) >= -96

    # --- 文字列で渡された数値 ---

    def test_numeric_string(self):
        """数値文字列は正常に変換される"""
        assert _safe_volume_db("-10") == "-10"

    def test_numeric_string_float(self):
        assert _safe_volume_db("3.5") == "3.5"
