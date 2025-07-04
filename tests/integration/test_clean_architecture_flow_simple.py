"""
クリーンアーキテクチャの簡易統合テスト

基本的な動作を確認する最小限のテスト。
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from di.bootstrap import bootstrap_di
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.value_objects.time_range import TimeRange
from use_cases.transcription.transcribe_video import TranscribeVideoRequest


class TestCleanArchitectureFlowSimple:
    """クリーンアーキテクチャの簡易統合フローテスト"""

    @pytest.fixture
    def app_container(self):
        """DIコンテナを初期化"""
        container = bootstrap_di()
        return container

    @pytest.fixture
    def sample_video_path(self):
        """テスト用の動画パスを作成"""
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            return Path(f.name)

    @pytest.fixture
    def sample_transcription_result(self):
        """サンプルの文字起こし結果を作成"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=5.0,
                text="これはテストです。"
            ),
            TranscriptionSegment(
                id="seg2",
                start=5.0,
                end=10.0,
                text="統合テストを実行しています。"
            ),
        ]
        return TranscriptionResult(
            id="test-result-1",
            segments=segments,
            language="ja",
            original_audio_path="/tmp/test.wav",
            model_size="medium",
            processing_time=5.0
        )

    def test_transcribe_video_use_case(self, app_container, sample_video_path, sample_transcription_result):
        """文字起こしユースケースのテスト"""
        # Gatewayをモック
        with patch.object(
            app_container.gateways.transcription_gateway(),
            'transcribe',
            return_value=sample_transcription_result
        ):
            # UseCaseを取得
            use_cases = app_container.use_cases()
            transcribe_use_case = use_cases.transcribe_video()
            
            # リクエストを作成
            request = TranscribeVideoRequest(
                video_path=sample_video_path,
                model_size="medium",
                language="ja"
            )
            
            # 実行
            result = transcribe_use_case.execute(request)
            
            # 結果を確認
            assert result is not None
            assert isinstance(result, TranscriptionResult)
            assert len(result.segments) == 2

    def test_dependency_injection_integrity(self, app_container):
        """依存性注入の整合性をテスト"""
        # 同じインスタンスが共有されていることを確認
        gateways = app_container.gateways()
        use_cases = app_container.use_cases()
        
        # Gatewayがシングルトンであることを確認
        gateway1 = gateways.transcription_gateway()
        gateway2 = gateways.transcription_gateway()
        assert gateway1 is gateway2
        
        # UseCaseは毎回新しいインスタンスであることを確認
        use_case1 = use_cases.transcribe_video()
        use_case2 = use_cases.transcribe_video()
        assert use_case1 is not use_case2
        
        # しかし、同じGatewayを使用していることを確認
        assert use_case1.gateway is use_case2.gateway

    def test_error_handling_in_use_case(self, app_container, sample_video_path):
        """ユースケースでのエラーハンドリングをテスト"""
        # 文字起こしでエラーを発生させる
        with patch.object(
            app_container.gateways.transcription_gateway(),
            'transcribe',
            side_effect=Exception("Transcription failed")
        ):
            use_cases = app_container.use_cases()
            transcribe_use_case = use_cases.transcribe_video()
            
            request = TranscribeVideoRequest(
                video_path=sample_video_path,
                model_size="medium",
                language="ja"
            )
            
            # エラーが適切に処理されることを確認
            with pytest.raises(Exception) as exc_info:
                transcribe_use_case.execute(request)
            
            assert "Transcription failed" in str(exc_info.value)

    def test_gateway_adapter_integration(self, app_container):
        """Gatewayアダプターの統合テスト"""
        # TextProcessorGatewayのテスト
        gateways = app_container.gateways()
        text_processor_gateway = gateways.text_processor_gateway()
        
        # モックデータで動作確認
        original_text = "これはテストです。"
        edited_text = "これは修正されたテストです。"
        
        # TextDifferenceとTextPositionをインポート
        from core.text_processor import TextDifference, TextPosition
        
        with patch('core.text_processor.TextProcessor.find_differences') as mock_find_diff:
            # 実装に合わせたTextDifferenceオブジェクトを返す
            mock_find_diff.return_value = TextDifference(
                original_text=original_text,
                edited_text=edited_text,
                common_positions=[
                    TextPosition(start=0, end=3, text="これは"),
                    TextPosition(start=3, end=9, text="テストです。")
                ],
                added_chars={"修", "正", "さ", "れ", "た"},
                added_positions=[]
            )
            
            result = text_processor_gateway.find_differences(original_text, edited_text)
            
            assert result is not None
            assert result.original_text == original_text
            assert result.edited_text == edited_text
            # domain層のTextDifferenceオブジェクトのdifferencesをチェック
            assert len(result.differences) > 0
            assert result.unchanged_count == 2
            assert result.added_count == 1