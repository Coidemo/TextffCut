"""
OpenAIGatewayのテスト
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from domain.entities.buzz_clip import (
    BuzzClipGenerationRequest,
    BuzzClipGenerationResult,
)
from infrastructure.external.gateways.openai_gateway import OpenAIGateway


class TestOpenAIGateway:
    """OpenAIGatewayのテスト"""

    @pytest.fixture
    def mock_openai_client(self):
        """モックOpenAIクライアント"""
        with patch("infrastructure.external.gateways.openai_gateway.OpenAI") as mock_class:
            mock_client = MagicMock()
            mock_class.return_value = mock_client
            yield mock_client

    @pytest.fixture
    def gateway(self, mock_openai_client):
        """テスト用ゲートウェイ"""
        return OpenAIGateway(api_key="test-api-key")

    @pytest.fixture
    def sample_request(self):
        """サンプルリクエスト"""
        return BuzzClipGenerationRequest(
            transcription_text="これはテストです。興味深い内容が含まれています。",
            transcription_segments=[
                {"text": "これはテストです。", "start": 0.0, "end": 5.0},
                {"text": "興味深い内容が含まれています。", "start": 5.0, "end": 12.0},
            ],
            num_candidates=2,
            min_duration=30,
            max_duration=40,
        )

    def test_successful_generation(self, gateway, mock_openai_client, sample_request):
        """正常な生成のテスト"""
        # モックレスポンスの設定
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps(
            {
                "clips": [
                    {
                        "title": "興味深い発見",
                        "text": "これはテストです。興味深い内容が含まれています。",
                        "start_time": 0.0,
                        "end_time": 35.0,
                        "score": 15,
                        "category": "お役立ち系",
                        "reasoning": "新しい情報を提供している",
                        "keywords": ["テスト", "興味深い"],
                    },
                    {
                        "title": "重要な内容",
                        "text": "興味深い内容が含まれています。",
                        "start_time": 5.0,
                        "end_time": 40.0,
                        "score": 12,
                        "category": "その他",
                        "reasoning": "視聴者の関心を引く",
                        "keywords": ["内容"],
                    },
                ]
            }
        )
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 200
        mock_response.usage.total_tokens = 300

        mock_openai_client.chat.completions.create.return_value = mock_response

        # 実行
        result = gateway.generate_buzz_clips(sample_request)

        # 検証
        assert isinstance(result, BuzzClipGenerationResult)
        assert len(result.candidates) == 2

        # 1つ目の候補
        candidate1 = result.candidates[0]
        assert candidate1.title == "興味深い発見"
        assert candidate1.score == 15
        assert candidate1.duration == 35.0

        # 2つ目の候補
        candidate2 = result.candidates[1]
        assert candidate2.title == "重要な内容"
        assert candidate2.score == 12

        # 使用量情報
        assert result.usage["total_tokens"] == 300
        assert result.model_used == "gpt-4-turbo-preview"

        # APIが正しく呼ばれたか確認
        mock_openai_client.chat.completions.create.assert_called_once()
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == "gpt-4-turbo-preview"
        assert call_args.kwargs["temperature"] == 0.7
        assert call_args.kwargs["response_format"] == {"type": "json_object"}

    def test_prompt_creation(self, gateway, sample_request):
        """プロンプト作成のテスト"""
        prompt = gateway._create_prompt(sample_request)

        # プロンプトに必要な要素が含まれているか確認
        assert "30〜40秒" in prompt
        assert "2個選んでください" in prompt
        assert "[0.0s - 5.0s] これはテストです。" in prompt
        assert "[5.0s - 12.0s] 興味深い内容が含まれています。" in prompt
        assert "JSON形式" in prompt

    def test_with_categories(self, gateway):
        """カテゴリ指定のテスト"""
        request = BuzzClipGenerationRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            categories=["感動系", "驚き系"],
        )

        prompt = gateway._create_prompt(request)

        assert "優先カテゴリ: 感動系, 驚き系" in prompt

    def test_system_prompt(self, gateway):
        """システムプロンプトのテスト"""
        system_prompt = gateway._get_system_prompt()

        # 重要な指示が含まれているか確認
        assert "ソーシャルメディア" in system_prompt
        assert "0-20のスコア" in system_prompt
        assert "感情的インパクト" in system_prompt
        assert "情報価値" in system_prompt

    def test_api_error_handling(self, gateway, mock_openai_client, sample_request):
        """APIエラーハンドリングのテスト"""
        # APIエラーを発生させる
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        with pytest.raises(Exception) as exc_info:
            gateway.generate_buzz_clips(sample_request)

        assert "API Error" in str(exc_info.value)

    def test_invalid_json_response(self, gateway, mock_openai_client, sample_request):
        """無効なJSONレスポンスのテスト"""
        # 無効なJSONを返す
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Invalid JSON"

        mock_openai_client.chat.completions.create.return_value = mock_response

        with pytest.raises(json.JSONDecodeError):
            gateway.generate_buzz_clips(sample_request)

    def test_check_connection(self, gateway, mock_openai_client):
        """接続確認のテスト"""
        # 正常な場合
        mock_openai_client.models.list.return_value = MagicMock()
        assert gateway.check_connection() is True

        # エラーの場合
        mock_openai_client.models.list.side_effect = Exception("Connection failed")
        assert gateway.check_connection() is False

    def test_empty_clips_response(self, gateway, mock_openai_client, sample_request):
        """空のクリップレスポンスのテスト"""
        # 空のクリップリストを返す
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"clips": []})
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_response.usage.total_tokens = 150

        mock_openai_client.chat.completions.create.return_value = mock_response

        # 実行
        result = gateway.generate_buzz_clips(sample_request)

        # 検証
        assert len(result.candidates) == 0
        assert result.usage["total_tokens"] == 150
