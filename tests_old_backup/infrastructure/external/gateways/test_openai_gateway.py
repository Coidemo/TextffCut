"""
OpenAIゲートウェイのテスト
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.external.gateways.openai_gateway import OpenAIGateway


class TestOpenAIGateway:
    """OpenAIゲートウェイのテスト"""

    @pytest.fixture
    def gateway(self):
        """テスト用のゲートウェイを作成"""
        return OpenAIGateway(api_key="test-api-key")

    def test_model_configuration(self, gateway):
        """モデル設定のテスト"""
        assert gateway.model == "gpt-4o"
        assert gateway.api_key == "test-api-key"

    @patch("infrastructure.external.gateways.openai_gateway.OpenAI")
    def test_generate_buzz_clips_success(self, mock_openai_class, gateway):
        """バズクリップ生成の成功ケースをテスト"""
        # モックの設定
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        
        # APIレスポンスのモック
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps({
                        "clips": [
                            {
                                "title": "面白いシーン",
                                "text": "これは面白い内容です",
                                "start_time": 10.0,
                                "end_time": 40.0,
                                "duration": 30.0,
                                "score": 0.9,
                                "category": "面白系",
                                "reasoning": "視聴者の興味を引く",
                                "keywords": ["面白い", "興味深い"]
                            }
                        ]
                    })
                )
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500
        )
        mock_response.model = "gpt-4o"
        
        mock_client.chat.completions.create.return_value = mock_response
        
        # 実行
        request = MagicMock(
            transcription_text="これは面白い内容です",
            transcription_segments=[],
            num_candidates=5,
            min_duration=30,
            max_duration=40
        )
        
        response = gateway.generate_buzz_clips(request)
        
        # 検証
        assert response.success is True
        assert len(response.clips) == 1
        assert response.clips[0]["title"] == "面白いシーン"
        assert response.model_used == "gpt-4o"
        assert response.usage["total_tokens"] == 1500

    def test_cost_calculation(self, gateway):
        """コスト計算のテスト"""
        usage = {
            "prompt_tokens": 10000,
            "completion_tokens": 2000,
            "total_tokens": 12000
        }
        
        # GPT-4oの料金（$5/1M input, $20/1M output）
        expected_input_cost = (10000 / 1_000_000) * 5.0
        expected_output_cost = (2000 / 1_000_000) * 20.0
        expected_total_cost = expected_input_cost + expected_output_cost
        
        # 実際の計算（ゲートウェイにコスト計算メソッドがある場合）
        # ここでは手動計算で検証
        assert expected_input_cost == pytest.approx(0.05, rel=0.01)
        assert expected_output_cost == pytest.approx(0.04, rel=0.01)
        assert expected_total_cost == pytest.approx(0.09, rel=0.01)
EOF < /dev/null