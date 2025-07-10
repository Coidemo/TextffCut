"""
LCSベーステキスト処理の統合テスト
"""

import pytest
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from domain.use_cases.time_range_calculator_lcs import TimeRangeCalculatorLCS
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType


class TestLCSTextProcessingIntegration:
    """LCSベーステキスト処理の統合テスト"""

    @pytest.fixture
    def detector(self):
        return TextDifferenceDetectorLCS()

    @pytest.fixture
    def calculator(self):
        return TimeRangeCalculatorLCS()

    @pytest.fixture
    def sample_transcription(self):
        """実際のWhisperX出力を模したサンプル"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=3.0,
                text="えーっと今日は",
                words=[
                    Word(word="え", start=0.0, end=0.3, confidence=0.8),
                    Word(word="ー", start=0.3, end=0.5, confidence=0.7),
                    Word(word="っ", start=0.5, end=0.6, confidence=0.8),
                    Word(word="と", start=0.6, end=0.8, confidence=0.9),
                    Word(word="今", start=1.0, end=1.2, confidence=0.95),
                    Word(word="日", start=1.2, end=1.4, confidence=0.95),
                    Word(word="は", start=1.4, end=1.6, confidence=0.9),
                ],
            ),
            TranscriptionSegment(
                id="seg2",
                start=3.0,
                end=6.0,
                text="あのー天気がいいですね",
                words=[
                    Word(word="あ", start=3.0, end=3.2, confidence=0.8),
                    Word(word="の", start=3.2, end=3.4, confidence=0.7),
                    Word(word="ー", start=3.4, end=3.6, confidence=0.6),
                    Word(word="天", start=4.0, end=4.2, confidence=0.95),
                    Word(word="気", start=4.2, end=4.4, confidence=0.95),
                    Word(word="が", start=4.4, end=4.6, confidence=0.9),
                    Word(word="い", start=4.6, end=4.8, confidence=0.9),
                    Word(word="い", start=4.8, end=5.0, confidence=0.9),
                    Word(word="で", start=5.0, end=5.2, confidence=0.9),
                    Word(word="す", start=5.2, end=5.4, confidence=0.9),
                    Word(word="ね", start=5.4, end=5.6, confidence=0.9),
                ],
            ),
        ]

        return TranscriptionResult(
            id="test_transcription",
            language="ja",
            segments=segments,
            original_audio_path="/tmp/test.wav",
            model_size="medium",
            processing_time=2.5,
        )

    def test_full_workflow_with_filler_removal(self, detector, calculator, sample_transcription):
        """フィラー除去を含む完全なワークフロー"""
        # 元のテキスト（フィラー含む）
        original_text = "えーっと今日はあのー天気がいいですね"
        # 編集後のテキスト（フィラー削除）
        edited_text = "今日は天気がいいですね"

        # 差分検出
        text_diff, diff_blocks = detector.detect_differences_with_blocks(
            original_text, edited_text, sample_transcription
        )

        # UNCHANGEDブロックの確認
        unchanged_blocks = [b for b in diff_blocks if b.type == DifferenceType.UNCHANGED]
        assert len(unchanged_blocks) >= 2  # "今日は"と"天気がいいですね"

        # 時間範囲の計算
        time_ranges = calculator.calculate_from_blocks(diff_blocks)
        assert len(time_ranges) >= 2

        # 時間範囲の妥当性確認
        for tr in time_ranges:
            assert tr.start >= 0
            assert tr.end > tr.start
            assert tr.text  # テキストが含まれている

        # マージされた時間範囲
        merged_ranges = calculator.merge_adjacent_ranges(time_ranges, gap_threshold=0.5)
        assert len(merged_ranges) <= len(time_ranges)

        # 合計時間の計算
        total_duration = calculator.calculate_total_duration(merged_ranges)
        assert total_duration > 0

    def test_continuous_speech_extraction(self, detector, calculator, sample_transcription):
        """連続した発話の抽出"""
        original_text = "えーっと今日はあのー天気がいいですね"
        edited_text = "今日は天気がいい"  # "ですね"も削除

        # 差分検出
        text_diff, diff_blocks = detector.detect_differences_with_blocks(
            original_text, edited_text, sample_transcription
        )

        # 時間範囲の計算
        time_ranges = calculator.calculate_from_blocks(diff_blocks)

        # 隣接範囲のマージ（ギャップが小さい場合は結合）
        merged_ranges = calculator.merge_adjacent_ranges(time_ranges, gap_threshold=1.0)

        # "今日は"と"天気がいい"が近い場合は1つにマージされる可能性
        assert len(merged_ranges) >= 1

        # マージされた範囲のテキストが正しいか
        all_text = " ".join(r.text for r in merged_ranges)
        assert "今日は" in all_text
        assert "天気がいい" in all_text

    def test_time_range_validation(self, detector, calculator, sample_transcription):
        """時間範囲の検証機能"""
        original_text = "えーっと今日はあのー天気がいいですね"
        edited_text = "今日は天気"

        # 差分検出と時間範囲計算
        text_diff, diff_blocks = detector.detect_differences_with_blocks(
            original_text, edited_text, sample_transcription
        )
        time_ranges = calculator.calculate_from_blocks(diff_blocks)

        # 検証
        is_valid, errors = calculator.validate_ranges(time_ranges, total_duration=10.0)
        assert is_valid
        assert len(errors) == 0

        # 重複がないことを確認
        sorted_ranges = sorted(time_ranges, key=lambda r: r.start)
        for i in range(len(sorted_ranges) - 1):
            assert sorted_ranges[i].end <= sorted_ranges[i + 1].start

    def test_gap_detection(self, detector, calculator, sample_transcription):
        """削除部分（ギャップ）の検出"""
        original_text = "えーっと今日はあのー天気がいいですね"
        edited_text = "今日は天気"

        # 差分検出と時間範囲計算
        text_diff, diff_blocks = detector.detect_differences_with_blocks(
            original_text, edited_text, sample_transcription
        )
        time_ranges = calculator.calculate_from_blocks(diff_blocks)

        # ギャップの検出
        gaps = calculator.find_gaps(time_ranges, total_duration=6.0)

        # フィラー部分がギャップとして検出される
        assert len(gaps) >= 1

        # ギャップの妥当性
        for gap_start, gap_end in gaps:
            assert gap_start >= 0
            assert gap_end > gap_start

    def test_empty_edited_text(self, detector, calculator, sample_transcription):
        """編集テキストが空の場合"""
        original_text = "えーっと今日はあのー天気がいいですね"
        edited_text = ""

        # 差分検出
        text_diff = detector.detect_differences(original_text, edited_text, sample_transcription)

        # 編集テキストが空の場合、元のテキスト全体が削除として検出される
        deleted_parts = [d for d in text_diff.differences if d[0] == DifferenceType.DELETED]
        assert len(deleted_parts) == 1
        assert deleted_parts[0][1] == original_text

    def test_partial_word_matching(self, detector, calculator):
        """部分的な単語マッチング（TranscriptionResultなし）"""
        original_text = "本日の天気予報"
        edited_text = "本日天気"

        # TranscriptionResultなしでも基本的な差分検出が動作
        text_diff = detector.detect_differences(original_text, edited_text)

        # UNCHANGEDとDELETEDが検出される
        unchanged_count = sum(1 for d in text_diff.differences if d[0] == DifferenceType.UNCHANGED)
        deleted_count = sum(1 for d in text_diff.differences if d[0] == DifferenceType.DELETED)

        assert unchanged_count >= 2  # "本日"と"天気"
        assert deleted_count >= 1  # "の"と"予報"

    def test_performance_with_large_text(self, detector):
        """大きなテキストでのパフォーマンス"""
        # 1000文字程度のテキスト
        original_text = "あ" * 500 + "い" * 500
        edited_text = "あ" * 250 + "い" * 250

        # 分割処理は100,000,000文字を超える場合のみ発動
        text_diff = detector.detect_differences(original_text, edited_text)

        # 基本的な動作確認
        assert len(text_diff.differences) > 0

        # UNCHANGEDとDELETEDが含まれる
        types = {d[0] for d in text_diff.differences}
        assert DifferenceType.UNCHANGED in types
        assert DifferenceType.DELETED in types
