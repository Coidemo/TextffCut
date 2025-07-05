"""
TextProcessorGatewayAdapterの単体テスト

レガシーコードとの統合を担うアダプターの動作を網羅的にテストします。
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter
from domain.entities.text_difference import TextDifference, DifferenceType
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment
from domain.value_objects.time_range import TimeRange
from domain.value_objects.duration import Duration


class TestTextProcessorGatewayAdapter:
    """TextProcessorGatewayAdapterのテスト"""

    @pytest.fixture
    def mock_text_processor(self):
        """モックのレガシーTextProcessorを作成"""
        with patch('adapters.gateways.text_processing.text_processor_gateway.TextProcessor') as mock:
            processor = Mock()
            mock.return_value = processor
            yield processor

    @pytest.fixture
    def gateway(self, mock_text_processor):
        """テスト用のGatewayインスタンスを作成"""
        return TextProcessorGatewayAdapter()

    @pytest.fixture
    def sample_transcription_result(self):
        """サンプルの文字起こし結果を作成"""
        segments = [
            TranscriptionSegment(id="seg1", start=0.0, end=5.0, text="これはテストです。"),
            TranscriptionSegment(id="seg2", start=5.0, end=10.0, text="文字起こしのテスト。"),
            TranscriptionSegment(id="seg3", start=10.0, end=15.0, text="サンプルテキスト。")
        ]
        return TranscriptionResult(
            segments=segments,
            language="ja",
            duration=Duration(seconds=15.0),
            model_size="medium"
        )

    def test_find_differences_with_matching_text(self, gateway, mock_text_processor, sample_transcription_result):
        """find_differencesメソッドがマッチするテキストを正しく処理することを確認"""
        # モックの設定
        mock_text_processor.find_differences.return_value = {
            "original_text": "これはテストです。文字起こしのテスト。サンプルテキスト。",
            "edited_text": "文字起こしのテスト。",
            "differences": [
                ("deleted", "これはテストです。", 0),
                ("unchanged", "文字起こしのテスト。", 1),
                ("deleted", "サンプルテキスト。", 2)
            ],
            "common_positions": [(1, 1)]
        }
        
        result = gateway.find_differences(
            transcription_result=sample_transcription_result,
            edited_text="文字起こしのテスト。"
        )
        
        # 結果の検証
        assert isinstance(result, TextDifference)
        assert result.original_text == "これはテストです。文字起こしのテスト。サンプルテキスト。"
        assert result.edited_text == "文字起こしのテスト。"
        assert len(result.differences) == 3
        
        # 差分の詳細を確認
        assert result.differences[0] == (DifferenceType.DELETED, "これはテストです。", 0)
        assert result.differences[1] == (DifferenceType.UNCHANGED, "文字起こしのテスト。", 1)
        assert result.differences[2] == (DifferenceType.DELETED, "サンプルテキスト。", 2)

    def test_find_differences_with_added_text(self, gateway, mock_text_processor, sample_transcription_result):
        """追加されたテキストがある場合の処理を確認"""
        mock_text_processor.find_differences.return_value = {
            "original_text": "これはテストです。",
            "edited_text": "これはテストです。追加テキスト。",
            "differences": [
                ("unchanged", "これはテストです。", 0),
                ("added", "追加テキスト。", -1)
            ],
            "common_positions": [(0, 0)]
        }
        
        result = gateway.find_differences(
            transcription_result=sample_transcription_result,
            edited_text="これはテストです。追加テキスト。"
        )
        
        assert len(result.differences) == 2
        assert result.differences[1] == (DifferenceType.ADDED, "追加テキスト。", -1)

    def test_get_time_ranges_from_differences(self, gateway, mock_text_processor, sample_transcription_result):
        """get_time_ranges_from_differencesメソッドが正しく時間範囲を返すことを確認"""
        # TextDifferenceを作成
        text_diff = TextDifference(
            original_text="これはテストです。文字起こしのテスト。サンプルテキスト。",
            edited_text="文字起こしのテスト。",
            differences=[
                (DifferenceType.DELETED, "これはテストです。", 0),
                (DifferenceType.UNCHANGED, "文字起こしのテスト。", 1),
                (DifferenceType.DELETED, "サンプルテキスト。", 2)
            ]
        )
        
        # モックの設定
        mock_text_processor.get_time_ranges_for_segments.return_value = [
            (5.0, 10.0)  # seg2の時間範囲
        ]
        
        result = gateway.get_time_ranges_from_differences(
            transcription_result=sample_transcription_result,
            differences=text_diff
        )
        
        assert len(result) == 1
        assert isinstance(result[0], TimeRange)
        assert result[0].start == 5.0
        assert result[0].end == 10.0

    def test_adjust_boundaries(self, gateway, mock_text_processor):
        """adjust_boundariesメソッドが境界調整を正しく処理することを確認"""
        # モックの設定
        mock_text_processor.adjust_boundaries.return_value = [
            (0.0, 5.5),   # 0.5秒延長
            (4.5, 10.0)   # 0.5秒前倒し
        ]
        
        time_ranges = [
            TimeRange(start=0.0, end=5.0),
            TimeRange(start=5.0, end=10.0)
        ]
        markers = {
            0: {"end_adjust": 0.5},
            1: {"start_adjust": -0.5}
        }
        
        result = gateway.adjust_boundaries(
            time_ranges=time_ranges,
            boundary_markers=markers
        )
        
        assert len(result) == 2
        assert result[0] == TimeRange(start=0.0, end=5.5)
        assert result[1] == TimeRange(start=4.5, end=10.0)

    def test_normalize_text(self, gateway, mock_text_processor):
        """normalize_textメソッドが正しくテキストを正規化することを確認"""
        mock_text_processor.normalize_text.return_value = "正規化されたテキスト"
        
        result = gateway.normalize_text("  正規化される\nテキスト  ")
        
        assert result == "正規化されたテキスト"
        mock_text_processor.normalize_text.assert_called_once_with("  正規化される\nテキスト  ")

    def test_split_into_sentences(self, gateway, mock_text_processor):
        """split_into_sentencesメソッドが文を正しく分割することを確認"""
        mock_text_processor.split_into_sentences.return_value = [
            "これは最初の文です。",
            "これは二番目の文です。"
        ]
        
        result = gateway.split_into_sentences("これは最初の文です。これは二番目の文です。")
        
        assert len(result) == 2
        assert result[0] == "これは最初の文です。"
        assert result[1] == "これは二番目の文です。"

    def test_split_text_by_separator(self, gateway, mock_text_processor):
        """split_text_by_separatorメソッドがセパレータで正しく分割することを確認"""
        mock_text_processor.split_text_by_separator.return_value = [
            "パート1",
            "パート2",
            "パート3"
        ]
        
        result = gateway.split_text_by_separator("パート1|パート2|パート3", separator="|")
        
        assert len(result) == 3
        assert result[0] == "パート1"
        assert result[2] == "パート3"

    def test_remove_boundary_markers(self, gateway, mock_text_processor):
        """remove_boundary_markersメソッドがマーカーを正しく除去することを確認"""
        mock_text_processor.remove_boundary_markers.return_value = "クリーンなテキスト"
        
        result = gateway.remove_boundary_markers("[1.5<]マーカー付きテキスト[>2.0]")
        
        assert result == "クリーンなテキスト"

    def test_extract_existing_markers(self, gateway, mock_text_processor):
        """extract_existing_markersメソッドが既存マーカーを正しく抽出することを確認"""
        mock_text_processor.extract_existing_markers.return_value = [
            {"index": 0, "type": "end", "value": 1.5},
            {"index": 1, "type": "start", "value": -0.5}
        ]
        
        result = gateway.extract_existing_markers("[1.5>]テキスト[<0.5]")
        
        assert len(result) == 2
        assert result[0]["type"] == "end"
        assert result[0]["value"] == 1.5

    def test_find_differences_with_separator(self, gateway, mock_text_processor, sample_transcription_result):
        """find_differences_with_separatorメソッドがセパレータ付きで処理することを確認"""
        mock_text_processor.find_differences_with_separator.return_value = {
            "sections": [
                {
                    "original_text": "セクション1",
                    "edited_text": "セクション1",
                    "differences": [("unchanged", "セクション1", 0)],
                    "common_positions": [(0, 0)]
                },
                {
                    "original_text": "セクション2",
                    "edited_text": "変更されたセクション2",
                    "differences": [
                        ("deleted", "セクション2", 0),
                        ("added", "変更されたセクション2", -1)
                    ],
                    "common_positions": []
                }
            ]
        }
        
        result = gateway.find_differences_with_separator(
            transcription_result=sample_transcription_result,
            edited_text="セクション1|||変更されたセクション2",
            separator="|||"
        )
        
        assert "sections" in result
        assert len(result["sections"]) == 2

    def test_get_time_ranges(self, gateway, mock_text_processor, sample_transcription_result):
        """get_time_rangesメソッドが複雑な入力を処理することを確認"""
        # 差分情報付きの場合
        mock_text_processor.get_time_ranges.return_value = [(0.0, 5.0), (10.0, 15.0)]
        
        diff_info = {
            "common_positions": [(0, 0), (2, 1)]
        }
        
        result = gateway.get_time_ranges(
            transcription_result=sample_transcription_result,
            edited_text="一致するテキスト",
            diff_info=diff_info
        )
        
        assert len(result) == 2
        assert result[0] == TimeRange(start=0.0, end=5.0)
        assert result[1] == TimeRange(start=10.0, end=15.0)

    def test_convert_to_legacy_segments(self, gateway, sample_transcription_result):
        """_convert_to_legacy_segmentsヘルパーメソッドのテスト"""
        # プライベートメソッドだが重要なので直接テスト
        legacy_segments = gateway._convert_to_legacy_segments(sample_transcription_result)
        
        assert len(legacy_segments) == 3
        assert legacy_segments[0]["text"] == "これはテストです。"
        assert legacy_segments[0]["start"] == 0.0
        assert legacy_segments[0]["end"] == 5.0
        assert "words" in legacy_segments[0]
        assert "chars" in legacy_segments[0]

    def test_convert_to_legacy_diff_info(self, gateway):
        """_convert_to_legacy_diff_infoヘルパーメソッドのテスト"""
        text_diff = TextDifference(
            original_text="元のテキスト",
            edited_text="編集されたテキスト",
            differences=[
                (DifferenceType.UNCHANGED, "共通部分", 0),
                (DifferenceType.ADDED, "追加部分", -1)
            ]
        )
        
        legacy_diff = gateway._convert_to_legacy_diff_info(text_diff)
        
        assert legacy_diff["original_text"] == "元のテキスト"
        assert legacy_diff["edited_text"] == "編集されたテキスト"
        assert len(legacy_diff["differences"]) == 2
        assert legacy_diff["differences"][0] == ("unchanged", "共通部分", 0)
        assert legacy_diff["differences"][1] == ("added", "追加部分", -1)

    def test_convert_to_legacy_time_ranges(self, gateway):
        """_convert_to_legacy_time_rangesヘルパーメソッドのテスト"""
        time_ranges = [
            TimeRange(start=0.0, end=5.0),
            TimeRange(start=10.0, end=15.0)
        ]
        
        legacy_ranges = gateway._convert_to_legacy_time_ranges(time_ranges)
        
        assert len(legacy_ranges) == 2
        assert legacy_ranges[0] == (0.0, 5.0)
        assert legacy_ranges[1] == (10.0, 15.0)

    def test_convert_from_legacy_time_ranges(self, gateway):
        """_convert_from_legacy_time_rangesヘルパーメソッドのテスト"""
        legacy_ranges = [(0.0, 5.0), (10.0, 15.0)]
        
        time_ranges = gateway._convert_from_legacy_time_ranges(legacy_ranges)
        
        assert len(time_ranges) == 2
        assert isinstance(time_ranges[0], TimeRange)
        assert time_ranges[0].start == 0.0
        assert time_ranges[0].end == 5.0

    def test_error_handling_in_find_differences(self, gateway, mock_text_processor, sample_transcription_result):
        """find_differencesでのエラーハンドリングを確認"""
        mock_text_processor.find_differences.side_effect = Exception("Processing error")
        
        with pytest.raises(Exception, match="Processing error"):
            gateway.find_differences(
                transcription_result=sample_transcription_result,
                edited_text="テキスト"
            )

    def test_empty_transcription_result(self, gateway, mock_text_processor):
        """空の文字起こし結果の処理を確認"""
        empty_result = TranscriptionResult(
            segments=[],
            language="ja",
            duration=Duration(seconds=0),
            model_size="medium"
        )
        
        mock_text_processor.find_differences.return_value = {
            "original_text": "",
            "edited_text": "新しいテキスト",
            "differences": [("added", "新しいテキスト", -1)],
            "common_positions": []
        }
        
        result = gateway.find_differences(
            transcription_result=empty_result,
            edited_text="新しいテキスト"
        )
        
        assert result.original_text == ""
        assert result.edited_text == "新しいテキスト"
        assert len(result.differences) == 1
        assert result.differences[0][0] == DifferenceType.ADDED