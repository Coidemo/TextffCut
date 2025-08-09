"""
GenerateBuzzClipsUseCaseのテスト
"""

from unittest.mock import Mock

import pytest

from domain.entities.buzz_clip import (
    BuzzClipCandidate,
    BuzzClipGenerationResult,
)
from domain.gateways.ai_gateway import AIGatewayInterface
from use_cases.ai.generate_buzz_clips import (
    GenerateBuzzClipsRequest,
    GenerateBuzzClipsUseCase,
)
from use_cases.exceptions import UseCaseError


class TestGenerateBuzzClipsUseCase:
    """GenerateBuzzClipsUseCaseのテスト"""

    @pytest.fixture
    def mock_ai_gateway(self):
        """モックAIゲートウェイ"""
        return Mock(spec=AIGatewayInterface)

    @pytest.fixture
    def use_case(self, mock_ai_gateway):
        """テスト用ユースケース"""
        return GenerateBuzzClipsUseCase(mock_ai_gateway)

    @pytest.fixture
    def valid_request(self):
        """有効なリクエスト"""
        return GenerateBuzzClipsRequest(
            transcription_text="これはテストです。とても興味深い内容です。",
            transcription_segments=[
                {"text": "これはテストです。", "start": 0.0, "end": 5.0},
                {"text": "とても興味深い内容です。", "start": 5.0, "end": 10.0},
            ],
            num_candidates=3,
            min_duration=30,
            max_duration=40,
        )

    def test_successful_generation(self, use_case, mock_ai_gateway, valid_request):
        """正常な生成のテスト"""
        # モックの設定
        candidates = [
            BuzzClipCandidate.create(
                title="興味深い内容",
                text="とても興味深い内容です。",
                start_time=5.0,
                end_time=40.0,
                score=15,
                category="お役立ち系",
                reasoning="視聴者の関心を引く内容",
                keywords=["興味", "内容"],
            )
        ]

        mock_result = BuzzClipGenerationResult(
            candidates=candidates,
            total_processing_time=2.5,
            model_used="gpt-4-turbo-preview",
            usage={"total_tokens": 1500},
        )

        mock_ai_gateway.generate_buzz_clips.return_value = mock_result

        # 実行
        response = use_case.execute(valid_request)

        # 検証
        assert response.success is True
        assert len(response.candidates) == 1
        assert response.candidates[0].title == "興味深い内容"
        assert response.processing_time == 2.5
        assert response.model_used == "gpt-4-turbo-preview"
        assert response.usage["total_tokens"] == 1500
        assert response.error_message is None

        # モックが呼ばれたことを確認
        mock_ai_gateway.generate_buzz_clips.assert_called_once()

    def test_empty_transcription_text(self, use_case, mock_ai_gateway):
        """空の文字起こしテキストのテスト"""
        request = GenerateBuzzClipsRequest(transcription_text="", transcription_segments=[], num_candidates=3)

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "文字起こしテキストが空です" in str(exc_info.value)

    def test_empty_transcription_segments(self, use_case, mock_ai_gateway):
        """空の文字起こしセグメントのテスト"""
        request = GenerateBuzzClipsRequest(transcription_text="テスト", transcription_segments=[], num_candidates=3)

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "文字起こしセグメントが空です" in str(exc_info.value)

    def test_invalid_num_candidates(self, use_case, mock_ai_gateway):
        """無効な候補数のテスト"""
        request = GenerateBuzzClipsRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            num_candidates=0,
        )

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "候補数は1以上である必要があります" in str(exc_info.value)

    def test_invalid_min_duration(self, use_case, mock_ai_gateway):
        """無効な最小時間のテスト"""
        request = GenerateBuzzClipsRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            min_duration=5,
            max_duration=40,
        )

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "最小時間は10秒以上である必要があります" in str(exc_info.value)

    def test_invalid_max_duration(self, use_case, mock_ai_gateway):
        """無効な最大時間のテスト"""
        request = GenerateBuzzClipsRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            min_duration=30,
            max_duration=70,
        )

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "最大時間は60秒以下である必要があります" in str(exc_info.value)

    def test_invalid_duration_range(self, use_case, mock_ai_gateway):
        """無効な時間範囲のテスト"""
        request = GenerateBuzzClipsRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            min_duration=40,
            max_duration=30,
        )

        with pytest.raises(UseCaseError) as exc_info:
            use_case.execute(request)

        assert "最小時間は最大時間より小さい必要があります" in str(exc_info.value)

    def test_ai_gateway_exception(self, use_case, mock_ai_gateway, valid_request):
        """AIゲートウェイの例外処理テスト"""
        # モックで例外を発生させる
        mock_ai_gateway.generate_buzz_clips.side_effect = Exception("API Error")

        # 実行
        response = use_case.execute(valid_request)

        # 検証
        assert response.success is False
        assert response.candidates == []
        assert response.error_message == "API Error"

    def test_result_validation_duration_outside_range(self, use_case, mock_ai_gateway, valid_request):
        """結果検証：時間範囲外のテスト"""
        # 時間範囲外の候補を含む結果
        candidates = [
            BuzzClipCandidate.create(
                title="短すぎる候補",
                text="短い",
                start_time=0.0,
                end_time=20.0,  # 20秒（最小30秒より短い）
                score=10,
                category="その他",
                reasoning="テスト",
                keywords=[],
            )
        ]

        mock_result = BuzzClipGenerationResult(
            candidates=candidates, total_processing_time=1.0, model_used="test-model", usage={}
        )

        mock_ai_gateway.generate_buzz_clips.return_value = mock_result

        # 実行（警告は出るが、結果は返される）
        response = use_case.execute(valid_request)

        assert response.success is True
        assert len(response.candidates) == 1

    def test_result_validation_invalid_score(self, use_case, mock_ai_gateway, valid_request):
        """結果検証：無効なスコアのテスト"""
        candidates = [
            BuzzClipCandidate.create(
                title="スコアが範囲外",
                text="テスト",
                start_time=0.0,
                end_time=35.0,
                score=25,  # 20を超えている
                category="その他",
                reasoning="テスト",
                keywords=[],
            )
        ]

        mock_result = BuzzClipGenerationResult(
            candidates=candidates, total_processing_time=1.0, model_used="test-model", usage={}
        )

        mock_ai_gateway.generate_buzz_clips.return_value = mock_result

        # 実行（警告は出るが、結果は返される）
        response = use_case.execute(valid_request)

        assert response.success is True
        assert len(response.candidates) == 1

    def test_with_categories(self, use_case, mock_ai_gateway):
        """カテゴリ指定のテスト"""
        request = GenerateBuzzClipsRequest(
            transcription_text="テスト",
            transcription_segments=[{"text": "テスト", "start": 0, "end": 10}],
            categories=["感動系", "驚き系"],
        )

        # モックの設定
        mock_result = BuzzClipGenerationResult(
            candidates=[], total_processing_time=1.0, model_used="test-model", usage={}
        )

        mock_ai_gateway.generate_buzz_clips.return_value = mock_result

        # 実行
        response = use_case.execute(request)

        # AIゲートウェイに渡されたリクエストを確認
        call_args = mock_ai_gateway.generate_buzz_clips.call_args[0][0]
        assert call_args.categories == ["感動系", "驚き系"]
