"""
LCSTextProcessorGatewayの単体テスト
"""

import pytest
from unittest.mock import Mock, patch
from adapters.gateways.text_processing.lcs_text_processor_gateway import LCSTextProcessorGateway
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from domain.value_objects.lcs_match import DifferenceBlock
from domain.entities.character_timestamp import CharacterWithTimestamp


class TestLCSTextProcessorGateway:
    """LCSTextProcessorGatewayのテスト"""

    @pytest.fixture
    def gateway(self):
        return LCSTextProcessorGateway()

    @pytest.fixture
    def sample_transcription(self):
        """サンプルの文字起こし結果"""
        words = [
            {"word": "こんにちは", "start": 0.0, "end": 0.5},
            {"word": "えー", "start": 0.5, "end": 0.7},
            {"word": "今日は", "start": 0.7, "end": 1.0},
            {"word": "いい", "start": 1.0, "end": 1.2},
            {"word": "天気", "start": 1.2, "end": 1.5},
            {"word": "ですね", "start": 1.5, "end": 1.8},
        ]
        
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=1.8,
                text="こんにちはえー今日はいい天気ですね",
                words=words
            )
        ]
        
        return TranscriptionResult(
            id="test-transcription",
            segments=segments,
            language="ja",
            original_audio_path="/path/to/audio.wav",
            model_size="base",
            processing_time=1.5
        )

    def test_find_differences_basic(self, gateway, sample_transcription):
        """基本的な差分検出"""
        original_text = "こんにちはえー今日はいい天気ですね"
        edited_text = "こんにちは今日はいい天気ですね"  # "えー"を削除
        
        with patch.object(gateway.detector, 'detect_differences') as mock_detect:
            # モックの戻り値を設定
            mock_text_diff = TextDifference(
                id="test-id",
                original_text=original_text,
                edited_text=edited_text,
                differences=[
                    (DifferenceType.UNCHANGED, "こんにちは", (0.0, 0.5)),
                    (DifferenceType.DELETED, "えー", (0.5, 0.7)),
                    (DifferenceType.UNCHANGED, "今日はいい天気ですね", (0.7, 1.8)),
                ]
            )
            mock_detect.return_value = mock_text_diff
            
            result = gateway.find_differences(original_text, edited_text)
            
            # 検証
            assert result == mock_text_diff
            mock_detect.assert_called_once_with(
                original_text,
                edited_text,
                None  # TranscriptionResultはNone
            )

    def test_get_time_ranges_basic(self, gateway, sample_transcription):
        """時間範囲の計算"""
        text_diff = TextDifference(
            id="test-id",
            original_text="こんにちはえー今日はいい天気ですね",
            edited_text="こんにちは今日はいい天気ですね",
            differences=[]
        )
        
        # 差分ブロックのモック
        mock_blocks = [
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="こんにちは",
                start_time=0.0,
                end_time=0.5,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="えー",
                start_time=0.5,
                end_time=0.7,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="今日はいい天気ですね",
                start_time=0.7,
                end_time=1.8,
                char_positions=[]
            ),
        ]
        
        with patch.object(gateway.detector, 'detect_differences_with_blocks') as mock_detect:
            mock_detect.return_value = (text_diff, mock_blocks)
            
            # TimeRangeCalculatorのモック
            with patch.object(gateway.calculator, 'calculate_from_blocks') as mock_calc:
                with patch.object(gateway.calculator, 'merge_adjacent_ranges') as mock_merge:
                    from domain.use_cases.time_range_calculator_lcs import TimeRangeWithText
                    from domain.value_objects import TimeRange
                    
                    mock_calc.return_value = [
                        TimeRangeWithText(0.0, 0.5, "こんにちは"),
                        TimeRangeWithText(0.7, 1.8, "今日はいい天気ですね"),
                    ]
                    
                    mock_merge.return_value = [
                        TimeRangeWithText(0.0, 0.5, "こんにちは"),
                        TimeRangeWithText(0.7, 1.8, "今日はいい天気ですね"),
                    ]
                    
                    result = gateway.get_time_ranges(text_diff, sample_transcription)
                    
                    # TimeRangeオブジェクトで返されることを確認
                    assert len(result) == 2
                    assert all(isinstance(r, TimeRange) for r in result)
                    assert result[0].start == 0.0
                    assert result[0].end == 0.5
                    assert result[1].start == 0.7
                    assert result[1].end == 1.8
                    
                    mock_calc.assert_called_once_with(mock_blocks)
                    mock_merge.assert_called_once()

    def test_get_highlight_data(self, gateway, sample_transcription):
        """ハイライトデータの生成"""
        edited_text = "こんにちは今日はいい天気ですね"
        
        # 差分ブロックのモック
        mock_blocks = [
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="こんにちは",
                start_time=0.0,
                end_time=0.5,
                char_positions=[],
                original_start_pos=0,
                original_end_pos=4
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="えー",
                start_time=0.5,
                end_time=0.7,
                char_positions=[],
                original_start_pos=5,
                original_end_pos=7
            ),
        ]
        
        with patch.object(gateway.detector, 'detect_differences_with_blocks') as mock_detect:
            mock_detect.return_value = (Mock(), mock_blocks)
            
            result = gateway.get_highlight_data(sample_transcription, edited_text)
            
            # ハイライトデータの検証
            assert len(result) == 2
            
            # UNCHANGEDブロック
            assert result[0]["type"] == "unchanged"
            assert result[0]["text"] == "こんにちは"
            assert result[0]["start_pos"] == 0
            assert result[0]["end_pos"] == 4
            assert result[0]["start_time"] == 0.0
            assert result[0]["end_time"] == 0.5
            
            # DELETEDブロック（フィラー）
            assert result[1]["type"] == "deleted"
            assert result[1]["text"] == "えー"
            assert result[1]["is_filler"] is True
            assert result[1]["char_count"] == 2

    def test_get_deletion_summary(self, gateway, sample_transcription):
        """削除サマリーの生成"""
        edited_text = "こんにちは今日は天気ですね"  # "えー"と"いい"を削除
        
        # 差分ブロックのモック
        mock_blocks = [
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="こんにちは",
                start_time=0.0,
                end_time=0.5,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="えー",
                start_time=0.5,
                end_time=0.7,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.UNCHANGED,
                text="今日は",
                start_time=0.7,
                end_time=1.0,
                char_positions=[]
            ),
            DifferenceBlock(
                type=DifferenceType.DELETED,
                text="いい",
                start_time=1.0,
                end_time=1.2,
                char_positions=[]
            ),
        ]
        
        with patch.object(gateway.detector, 'detect_differences_with_blocks') as mock_detect:
            mock_detect.return_value = (Mock(), mock_blocks)
            
            result = gateway.get_deletion_summary(sample_transcription, edited_text)
            
            # 削除サマリーの検証
            assert result["total_deletions"] == 2
            assert result["filler_deletions"] == 1  # "えー"
            assert result["content_deletions"] == 1  # "いい"
            assert result["total_deletion_time"] == pytest.approx(0.4)  # 0.2 + 0.2
            
            # フィラーの例
            assert "えー" in result["filler_examples"]
            
            # 内容の例
            assert "いい" in result["content_examples"]
            
            # 削除ブロックの詳細
            assert len(result["deletion_blocks"]) == 2

    def test_is_filler(self, gateway):
        """フィラー判定のテスト"""
        # フィラー
        assert gateway._is_filler("えー") is True
        assert gateway._is_filler("あのー") is True
        assert gateway._is_filler("まあ") is True
        assert gateway._is_filler("えー、") is True  # 句読点あり
        assert gateway._is_filler("あの。") is True  # 句読点あり
        
        # フィラーではない
        assert gateway._is_filler("こんにちは") is False
        assert gateway._is_filler("今日") is False
        assert gateway._is_filler("です") is False

    def test_empty_transcription(self, gateway):
        """空の文字起こし結果の処理"""
        with patch.object(gateway.detector, 'detect_differences') as mock_detect:
            mock_text_diff = TextDifference(
                id="test-id",
                original_text="",
                edited_text="追加テキスト",
                differences=[(DifferenceType.ADDED, "追加テキスト", None)]
            )
            mock_detect.return_value = mock_text_diff
            
            result = gateway.find_differences("", "追加テキスト")
            
            assert result == mock_text_diff

    def test_get_time_ranges_empty(self, gateway):
        """空の差分での時間範囲計算"""
        # 空のテキストではTextDifferenceが作成できないため、モックで対応
        from unittest.mock import Mock
        text_diff = Mock()
        text_diff.original_text = ""
        text_diff.edited_text = ""
        text_diff.differences = []
        
        # セグメントが必要なため、空のセグメントを追加
        empty_segment = TranscriptionSegment(
            id="empty-seg",
            text="",
            start=0.0,
            end=0.0,
            words=[]
        )
        
        empty_transcription = TranscriptionResult(
            id="empty-transcription",
            segments=[empty_segment],
            language="ja",
            original_audio_path="/path/to/empty.wav",
            model_size="base",
            processing_time=0.0
        )
        
        with patch.object(gateway.detector, 'detect_differences_with_blocks') as mock_detect:
            mock_detect.return_value = (text_diff, [])
            
            with patch.object(gateway.calculator, 'calculate_from_blocks') as mock_calc:
                mock_calc.return_value = []
                
                with patch.object(gateway.calculator, 'merge_adjacent_ranges') as mock_merge:
                    mock_merge.return_value = []
                    
                    result = gateway.get_time_ranges(text_diff, empty_transcription)
                    
                    assert result == []