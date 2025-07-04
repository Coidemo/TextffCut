"""
TextProcessorGatewayAdapterのテスト
"""

from unittest.mock import Mock, patch

import pytest

from adapters.gateways.text_processing.text_processor_gateway import TextProcessorGatewayAdapter
from core.text_processor import TextDifference as LegacyTextDifference
from core.text_processor import TextPosition as LegacyTextPosition
from domain.entities import TextDifference, TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType
from domain.value_objects import TimeRange
from use_cases.exceptions import TextProcessingError


class TestTextProcessorGatewayAdapter:
    """TextProcessorGatewayAdapterのテスト"""

    @pytest.fixture
    def gateway(self):
        """テスト用ゲートウェイ"""
        return TextProcessorGatewayAdapter()

    @pytest.fixture
    def mock_legacy_processor(self):
        """モックレガシーTextProcessor"""
        with patch("adapters.gateways.text_processing.text_processor_gateway.LegacyTextProcessor") as mock:
            yield mock

    @pytest.fixture
    def transcription_result(self):
        """テスト用文字起こし結果"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                text="これはテストです",
                start=0.0,
                end=2.0,
                words=[
                    Word(word="これは", start=0.0, end=1.0, confidence=0.95),
                    Word(word="テストです", start=1.0, end=2.0, confidence=0.93),
                ],
                chars=[],
            ),
            TranscriptionSegment(id="seg2", text="文字起こしのテスト", start=2.5, end=4.0, words=[], chars=[]),
        ]

        return TranscriptionResult(
            id="test-id",
            language="ja",
            segments=segments,
            original_audio_path="/test/video.mp4",
            model_size="large-v3",
            processing_time=5.0,
        )

    def test_find_differences_success(self, mock_legacy_processor):
        """差分検出の成功テスト"""
        # モックの設定
        mock_instance = Mock()
        legacy_diff = LegacyTextDifference(
            original_text="元のテキスト",
            edited_text="編集後のテキスト",
            common_positions=[LegacyTextPosition(start=0, end=2, text="のテ")],
            added_chars={"編", "集", "後"},
            added_positions=None,
        )
        mock_instance.find_differences.return_value = legacy_diff
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成と実行
        gateway = TextProcessorGatewayAdapter()
        result = gateway.find_differences("元のテキスト", "編集後のテキスト")

        # 検証
        assert isinstance(result, TextDifference)
        assert result.original_text == "元のテキスト"
        assert result.edited_text == "編集後のテキスト"
        # differences の検証
        assert len(result.differences) >= 1
        # UNCHANGED部分があることを確認
        unchanged_diffs = [d for d in result.differences if d[0] == DifferenceType.UNCHANGED]
        assert len(unchanged_diffs) >= 1
        assert unchanged_diffs[0][1] == "のテ"  # common_positionsのテキスト
        # ADDED部分があることを確認
        added_diffs = [d for d in result.differences if d[0] == DifferenceType.ADDED]
        assert len(added_diffs) >= 1

        # レガシーメソッドが呼ばれたことを確認
        mock_instance.find_differences.assert_called_once_with(original="元のテキスト", edited="編集後のテキスト")

    def test_find_differences_error_handling(self, mock_legacy_processor):
        """差分検出のエラーハンドリング"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.find_differences.side_effect = Exception("Processing failed")
        mock_legacy_processor.return_value = mock_instance

        # ゲートウェイの作成
        gateway = TextProcessorGatewayAdapter()

        # エラーが適切に変換されることを確認
        with pytest.raises(TextProcessingError, match="Failed to find text differences"):
            gateway.find_differences("text1", "text2")

    def test_get_time_ranges_from_differences(self, transcription_result):
        """差分から時間範囲を取得"""
        # 差分情報
        differences = TextDifference(
            id="diff1",
            original_text="これはテストです文字起こしのテスト",
            edited_text="これはテストです",
            differences=[
                (DifferenceType.UNCHANGED, "これはテストです", None),
                (DifferenceType.DELETED, "文字起こしのテスト", None),
            ],
        )

        # モックレガシー差分のget_time_rangesメソッド
        with patch.object(TextProcessorGatewayAdapter, "_convert_to_legacy_difference") as mock_convert_diff:
            with patch.object(TextProcessorGatewayAdapter, "_convert_to_legacy_transcription") as mock_convert_trans:
                # モックレガシー差分
                mock_legacy_diff = Mock()
                mock_legacy_diff.get_time_ranges.return_value = [(0.0, 2.0)]
                mock_convert_diff.return_value = mock_legacy_diff

                # モックレガシー文字起こし
                mock_legacy_trans = Mock()
                mock_convert_trans.return_value = mock_legacy_trans

                # 実行
                gateway = TextProcessorGatewayAdapter()
                time_ranges = gateway.get_time_ranges_from_differences(differences, transcription_result)

                # 検証
                assert len(time_ranges) == 1
                assert isinstance(time_ranges[0], TimeRange)
                assert time_ranges[0].start == 0.0
                assert time_ranges[0].end == 2.0

    def test_adjust_boundaries(self, transcription_result):
        """境界調整のテスト"""
        gateway = TextProcessorGatewayAdapter()

        text = "<<これはテストです>>文字起こしのテスト"
        time_ranges = [TimeRange(0.0, 4.0)]

        # 境界調整（現在の実装では入力をそのまま返す）
        adjusted = gateway.adjust_boundaries(
            text=text,
            time_ranges=time_ranges,
            transcription_segments=transcription_result.segments,
            markers=["<<", ">>"],
        )

        # 簡易実装なので入力と同じ
        assert len(adjusted) == len(transcription_result.segments)
        assert adjusted[0].text == transcription_result.segments[0].text

    def test_normalize_text(self, mock_legacy_processor):
        """テキスト正規化のテスト"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.normalize_text.return_value = "正規化されたテキスト"
        mock_legacy_processor.return_value = mock_instance

        # 実行
        gateway = TextProcessorGatewayAdapter()
        result = gateway.normalize_text("　元の　　テキスト　")

        # 検証
        assert result == "正規化されたテキスト"
        mock_instance.normalize_text.assert_called_once_with("　元の　　テキスト　", False)

    def test_normalize_text_preserve_newlines(self, mock_legacy_processor):
        """改行保持でのテキスト正規化"""
        # モックの設定
        mock_instance = Mock()
        mock_instance.normalize_text.return_value = "正規化\nされた\nテキスト"
        mock_legacy_processor.return_value = mock_instance

        # 実行
        gateway = TextProcessorGatewayAdapter()
        result = gateway.normalize_text("元の\n\nテキスト", preserve_newlines=True)

        # 検証
        assert result == "正規化\nされた\nテキスト"
        mock_instance.normalize_text.assert_called_once_with("元の\n\nテキスト", True)

    def test_split_into_sentences_japanese(self):
        """日本語の文分割"""
        gateway = TextProcessorGatewayAdapter()

        text = "これは最初の文です。次の文です！最後の文？"
        sentences = gateway.split_into_sentences(text, language="ja")

        assert len(sentences) == 3
        assert sentences[0] == "これは最初の文です"
        assert sentences[1] == "次の文です"
        assert sentences[2] == "最後の文"

    def test_split_into_sentences_english(self):
        """英語の文分割"""
        gateway = TextProcessorGatewayAdapter()

        text = "This is the first sentence. Here's another! And the last?"
        sentences = gateway.split_into_sentences(text, language="en")

        assert len(sentences) == 3
        assert sentences[0] == "This is the first sentence"
        assert sentences[1] == "Here's another"
        assert sentences[2] == "And the last"

    def test_split_into_sentences_error_handling(self):
        """文分割のエラーハンドリング"""
        gateway = TextProcessorGatewayAdapter()

        # エラーをシミュレート（実際にはこのエラーは起きにくいが）
        with patch("re.split", side_effect=Exception("Split failed")):
            sentences = gateway.split_into_sentences("テスト文")

            # エラー時は全体を1文として返す
            assert len(sentences) == 1
            assert sentences[0] == "テスト文"
