"""
編集ユースケースのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock
from uuid import uuid4

from domain.entities import TranscriptionResult, TranscriptionSegment, TextDifference
from domain.entities.text_difference import DifferenceType
from domain.value_objects import TimeRange
from use_cases.editing import (
    FindTextDifferencesUseCase,
    FindDifferencesRequest,
    AdjustBoundariesUseCase,
    AdjustBoundariesRequest,
)
from use_cases.exceptions import (
    TextProcessingError,
    InvalidTextFormatError,
)


class TestFindTextDifferencesUseCase:
    """FindTextDifferencesUseCaseのテスト"""
    
    @pytest.fixture
    def mock_gateway(self):
        """モックゲートウェイ"""
        return Mock()
    
    @pytest.fixture
    def mock_transcription_result(self):
        """モック文字起こし結果"""
        segments = [
            TranscriptionSegment(
                id="1",
                text="これはテストです。",
                start=0.0,
                end=2.0,
                words=[{"word": "これは", "start": 0.0, "end": 0.5},
                       {"word": "テスト", "start": 0.5, "end": 1.5},
                       {"word": "です", "start": 1.5, "end": 2.0}]
            ),
            TranscriptionSegment(
                id="2",
                text="削除される部分。",
                start=2.0,
                end=4.0,
                words=[{"word": "削除される", "start": 2.0, "end": 3.0},
                       {"word": "部分", "start": 3.0, "end": 4.0}]
            ),
            TranscriptionSegment(
                id="3",
                text="これも残ります。",
                start=4.0,
                end=6.0,
                words=[{"word": "これも", "start": 4.0, "end": 5.0},
                       {"word": "残ります", "start": 5.0, "end": 6.0}]
            )
        ]
        
        return TranscriptionResult(
            id=str(uuid4()),
            language="ja",
            segments=segments,
            original_audio_path="/test/video.mp4",
            model_size="medium",
            processing_time=10.0
        )
    
    @pytest.fixture
    def mock_text_difference(self):
        """モックテキスト差分"""
        differences = [
            (DifferenceType.UNCHANGED, "これはテストです。", (0.0, 2.0)),
            (DifferenceType.DELETED, "削除される部分。", (2.0, 4.0)),
            (DifferenceType.UNCHANGED, "これも残ります。", (4.0, 6.0))
        ]
        
        return TextDifference(
            id=str(uuid4()),
            original_text="これはテストです。削除される部分。これも残ります。",
            edited_text="これはテストです。これも残ります。",
            differences=differences
        )
    
    def test_successful_difference_detection(self, mock_gateway, mock_transcription_result, mock_text_difference):
        """正常な差分検出"""
        # Arrange
        mock_gateway.find_differences.return_value = mock_text_difference
        mock_gateway.get_time_ranges.return_value = [
            TimeRange(0.0, 2.0),
            TimeRange(4.0, 6.0)
        ]
        
        use_case = FindTextDifferencesUseCase(mock_gateway)
        request = FindDifferencesRequest(
            original_text="これはテストです。削除される部分。これも残ります。",
            edited_text="これはテストです。これも残ります。",
            transcription_result=mock_transcription_result
        )
        
        # Act
        response = use_case(request)
        
        # Assert
        assert response.text_difference == mock_text_difference
        assert len(response.time_ranges) == 2
        assert response.removed_count == 1
        assert response.remaining_count == 2
        assert response.has_changes is True
        assert response.removal_rate == pytest.approx(0.333, rel=0.01)
    
    def test_no_changes(self, mock_gateway, mock_transcription_result):
        """変更なしの場合"""
        # Arrange
        no_change_diff = TextDifference(
            id=str(uuid4()),
            original_text="同じテキスト",
            edited_text="同じテキスト",
            differences=[(DifferenceType.UNCHANGED, "同じテキスト", None)]
        )
        
        mock_gateway.find_differences.return_value = no_change_diff
        mock_gateway.get_time_ranges.return_value = [TimeRange(0.0, 6.0)]
        
        use_case = FindTextDifferencesUseCase(mock_gateway)
        request = FindDifferencesRequest(
            original_text="同じテキスト",
            edited_text="同じテキスト",
            transcription_result=mock_transcription_result
        )
        
        # Act
        response = use_case(request)
        
        # Assert
        assert response.has_changes is False
        assert response.removed_count == 0
        assert response.removal_rate == 0.0
    
    def test_empty_texts_error(self, mock_gateway, mock_transcription_result):
        """空のテキストでエラー"""
        use_case = FindTextDifferencesUseCase(mock_gateway)
        request = FindDifferencesRequest(
            original_text="",
            edited_text="",
            transcription_result=mock_transcription_result
        )
        
        with pytest.raises(InvalidTextFormatError, match="Both original and edited text are empty"):
            use_case(request)
    
    def test_no_segments_error(self, mock_gateway):
        """セグメントなしでエラー"""
        # セグメントを空にするためにモック
        mock_result = Mock()
        mock_result.segments = []
        
        use_case = FindTextDifferencesUseCase(mock_gateway)
        request = FindDifferencesRequest(
            original_text="テキスト",
            edited_text="編集後",
            transcription_result=mock_result
        )
        
        with pytest.raises(TextProcessingError, match="Transcription result has no segments"):
            use_case(request)


class TestAdjustBoundariesUseCase:
    """AdjustBoundariesUseCaseのテスト"""
    
    @pytest.fixture
    def mock_gateway(self):
        """モックゲートウェイ"""
        return Mock()
    
    @pytest.fixture
    def time_ranges(self):
        """テスト用時間範囲"""
        return [
            TimeRange(0.0, 2.0),
            TimeRange(2.0, 4.0),
            TimeRange(4.0, 6.0)
        ]
    
    def test_successful_boundary_adjustment(self, mock_gateway, time_ranges):
        """正常な境界調整"""
        # Arrange
        text_with_markers = "最初のセグメント[1>]\n次のセグメント[<0.5]\n最後のセグメント"
        cleaned_text = "最初のセグメント\n次のセグメント\n最後のセグメント"
        
        adjusted_ranges = [
            TimeRange(0.0, 3.0),  # 1秒延長
            TimeRange(2.5, 4.0),  # 0.5秒早める
            TimeRange(4.0, 6.0)   # 変更なし
        ]
        
        mock_gateway.apply_boundary_adjustments.return_value = (cleaned_text, adjusted_ranges)
        
        use_case = AdjustBoundariesUseCase(mock_gateway)
        request = AdjustBoundariesRequest(
            text_with_markers=text_with_markers,
            time_ranges=time_ranges
        )
        
        # Act
        response = use_case(request)
        
        # Assert
        assert response.cleaned_text == cleaned_text
        assert len(response.adjusted_time_ranges) == 3
        assert response.adjustment_count == 2
        assert response.adjustments[0].adjustment_type == "extend_prev"
        assert response.adjustments[0].amount == 1.0
        assert response.adjustments[1].adjustment_type == "advance_next"
        assert response.adjustments[1].amount == 0.5
    
    def test_multiple_adjustments(self, mock_gateway, time_ranges):
        """複数の調整マーカー"""
        # Arrange
        text_with_markers = "[2>][1<][<1][>0.5]テキスト"
        cleaned_text = "テキスト"
        
        mock_gateway.apply_boundary_adjustments.return_value = (cleaned_text, time_ranges)
        
        use_case = AdjustBoundariesUseCase(mock_gateway)
        request = AdjustBoundariesRequest(
            text_with_markers=text_with_markers,
            time_ranges=time_ranges
        )
        
        # Act
        response = use_case(request)
        
        # Assert
        assert response.adjustment_count == 4
        assert response.total_adjustment == pytest.approx(4.5)  # 2 + 1 + 1 + 0.5
    
    def test_empty_text_error(self, mock_gateway, time_ranges):
        """空のテキストでエラー"""
        use_case = AdjustBoundariesUseCase(mock_gateway)
        request = AdjustBoundariesRequest(
            text_with_markers="",
            time_ranges=time_ranges
        )
        
        with pytest.raises(InvalidTextFormatError, match="Text is empty"):
            use_case(request)
    
    def test_no_time_ranges_error(self, mock_gateway):
        """時間範囲なしでエラー"""
        use_case = AdjustBoundariesUseCase(mock_gateway)
        request = AdjustBoundariesRequest(
            text_with_markers="テキスト[1>]",
            time_ranges=[]
        )
        
        with pytest.raises(TextProcessingError, match="No time ranges provided"):
            use_case(request)
    
    def test_no_markers(self, mock_gateway, time_ranges):
        """マーカーなしの場合"""
        # Arrange
        text_without_markers = "マーカーのないテキスト"
        mock_gateway.apply_boundary_adjustments.return_value = (
            text_without_markers,
            time_ranges  # 変更なし
        )
        
        use_case = AdjustBoundariesUseCase(mock_gateway)
        request = AdjustBoundariesRequest(
            text_with_markers=text_without_markers,
            time_ranges=time_ranges
        )
        
        # Act
        response = use_case(request)
        
        # Assert
        assert response.cleaned_text == text_without_markers
        assert response.adjusted_time_ranges == time_ranges
        assert response.adjustment_count == 0
        assert response.total_adjustment == 0.0