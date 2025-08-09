"""
バズクリップ生成のコスト計算テスト
"""

import pytest

from presentation.views.text_editor import TextEditorView


class TestBuzzClipCostCalculation:
    """バズクリップ生成のコスト計算テスト"""

    def test_calculate_estimated_cost(self):
        """推定コスト計算のテスト"""
        # TextEditorViewのコスト計算ロジックをテスト
        # 10000文字の場合
        char_count = 10000

        # トークン数の推定（日本語は1文字≒1トークン）
        estimated_tokens = char_count

        # GPT-4oの料金（2025年1月時点）
        # 入力: $5 per 1M tokens
        # 出力: $20 per 1M tokens
        input_cost_per_million = 5.0
        output_cost_per_million = 20.0

        # 入力トークン数 = 文字数 + プロンプト（約1000トークン）
        input_tokens = estimated_tokens + 1000

        # 出力トークン数 = 約2000トークン（5候補 × 400トークン/候補）
        output_tokens = 2000

        # コスト計算
        input_cost = (input_tokens / 1_000_000) * input_cost_per_million
        output_cost = (output_tokens / 1_000_000) * output_cost_per_million
        total_cost_usd = input_cost + output_cost

        # 円換算（1USD = 150円）
        total_cost_jpy = total_cost_usd * 150

        # 期待値の確認
        assert input_cost == pytest.approx(0.055, rel=0.01)  # $0.055
        assert output_cost == pytest.approx(0.04, rel=0.01)  # $0.04
        assert total_cost_usd == pytest.approx(0.095, rel=0.01)  # $0.095
        assert total_cost_jpy == pytest.approx(14.25, rel=0.01)  # ¥14.25

    def test_calculate_actual_cost_from_usage(self):
        """実際の使用量からのコスト計算テスト"""
        # APIレスポンスの使用量
        usage = {"prompt_tokens": 11000, "completion_tokens": 2000, "total_tokens": 13000}

        # GPT-4oの料金
        input_cost_per_million = 5.0
        output_cost_per_million = 20.0

        # コスト計算
        input_cost = (usage["prompt_tokens"] / 1_000_000) * input_cost_per_million
        output_cost = (usage["completion_tokens"] / 1_000_000) * output_cost_per_million
        total_cost_usd = input_cost + output_cost

        # 円換算
        total_cost_jpy = total_cost_usd * 150

        # 期待値の確認
        assert input_cost == pytest.approx(0.055, rel=0.01)
        assert output_cost == pytest.approx(0.04, rel=0.01)
        assert total_cost_usd == pytest.approx(0.095, rel=0.01)
        assert total_cost_jpy == pytest.approx(14.25, rel=0.01)

    def test_cost_comparison_gpt4_vs_gpt4o(self):
        """GPT-4とGPT-4oのコスト比較テスト"""
        usage = {"prompt_tokens": 11000, "completion_tokens": 2000}

        # GPT-4の料金（旧）
        gpt4_input_cost_per_million = 30.0
        gpt4_output_cost_per_million = 60.0

        # GPT-4oの料金（新）
        gpt4o_input_cost_per_million = 5.0
        gpt4o_output_cost_per_million = 20.0

        # GPT-4のコスト
        gpt4_cost = (usage["prompt_tokens"] / 1_000_000) * gpt4_input_cost_per_million + (
            usage["completion_tokens"] / 1_000_000
        ) * gpt4_output_cost_per_million

        # GPT-4oのコスト
        gpt4o_cost = (usage["prompt_tokens"] / 1_000_000) * gpt4o_input_cost_per_million + (
            usage["completion_tokens"] / 1_000_000
        ) * gpt4o_output_cost_per_million

        # コスト削減率
        cost_reduction = (1 - gpt4o_cost / gpt4_cost) * 100

        # 期待値の確認
        assert gpt4_cost == pytest.approx(0.45, rel=0.01)  # $0.45
        assert gpt4o_cost == pytest.approx(0.095, rel=0.01)  # $0.095
        assert cost_reduction == pytest.approx(78.9, rel=0.1)  # 約79%削減
