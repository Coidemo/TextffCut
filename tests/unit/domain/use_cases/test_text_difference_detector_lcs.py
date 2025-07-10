"""
TextDifferenceDetectorLCSの単体テスト
"""

import pytest
from domain.use_cases.text_difference_detector_lcs import TextDifferenceDetectorLCS
from domain.entities.text_difference import DifferenceType
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word


class TestTextDifferenceDetectorLCS:
    """LCSベースの差分検出器のテスト"""

    @pytest.fixture
    def detector(self):
        return TextDifferenceDetectorLCS()

    @pytest.fixture
    def sample_transcription_with_fillers(self):
        """フィラーを含む文字起こし結果"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=5.0,
                text="えーっと今日はあのー天気がいいですね",
                words=[
                    Word(word="え", start=0.0, end=0.2),
                    Word(word="ー", start=0.2, end=0.4),
                    Word(word="っ", start=0.4, end=0.5),
                    Word(word="と", start=0.5, end=0.6),
                    Word(word="今", start=0.8, end=1.0),
                    Word(word="日", start=1.0, end=1.2),
                    Word(word="は", start=1.2, end=1.4),
                    Word(word="あ", start=1.6, end=1.8),
                    Word(word="の", start=1.8, end=2.0),
                    Word(word="ー", start=2.0, end=2.2),
                    Word(word="天", start=2.4, end=2.6),
                    Word(word="気", start=2.6, end=2.8),
                    Word(word="が", start=2.8, end=3.0),
                    Word(word="い", start=3.2, end=3.4),
                    Word(word="い", start=3.4, end=3.6),
                    Word(word="で", start=3.6, end=3.8),
                    Word(word="す", start=3.8, end=4.0),
                    Word(word="ね", start=4.0, end=4.2),
                ],
            )
        ]
        return TranscriptionResult(
            id="test_transcription",
            language="ja",
            segments=segments,
            original_audio_path="/tmp/test.wav",
            model_size="medium",
            processing_time=1.0,
        )

    def test_lcs_basic_exact_match(self, detector):
        """完全一致の場合"""
        original = "こんにちは"
        edited = "こんにちは"

        result = detector.detect_differences(original, edited)

        assert len(result.differences) == 1
        assert result.differences[0][0] == DifferenceType.UNCHANGED
        assert result.differences[0][1] == "こんにちは"

    def test_lcs_partial_match(self, detector):
        """部分一致の場合"""
        original = "今日はいい天気ですね"
        edited = "今日は天気"

        result = detector.detect_differences(original, edited)

        # UNCHANGEDの部分を確認
        unchanged_parts = [d for d in result.differences if d[0] == DifferenceType.UNCHANGED]
        unchanged_texts = [d[1] for d in unchanged_parts]

        assert "今日は" in unchanged_texts
        assert "天気" in unchanged_texts

    def test_lcs_with_fillers(self, detector, sample_transcription_with_fillers):
        """フィラーをスキップした一致"""
        original = "えーっと今日はあのー天気がいいですね"
        edited = "今日は天気がいいですね"

        result = detector.detect_differences(original, edited, sample_transcription_with_fillers)

        # フィラーを除いた部分が正しく検出されるか
        unchanged_parts = [d for d in result.differences if d[0] == DifferenceType.UNCHANGED]
        unchanged_text = "".join([d[1] for d in unchanged_parts])

        assert "今日は" in unchanged_text
        assert "天気がいいですね" in unchanged_text

    def test_lcs_no_match(self, detector):
        """完全不一致の場合"""
        original = "ABC"
        edited = "XYZ"

        result = detector.detect_differences(original, edited)

        # ADDEDが検出される（完全不一致の場合）
        added_parts = [d for d in result.differences if d[0] == DifferenceType.ADDED]
        assert len(added_parts) == 1
        assert added_parts[0][1] == "XYZ"

    def test_lcs_empty_strings(self, detector):
        """空文字列の処理"""
        # 両方空 - TextDifferenceのバリデーションを考慮
        try:
            result = detector.detect_differences("", "")
            assert len(result.differences) == 0
        except ValueError:
            # TextDifferenceがバリデーションエラーを投げる場合はOK
            pass

        # 元が空
        result = detector.detect_differences("", "テスト")
        assert len(result.differences) == 1
        assert result.differences[0][0] == DifferenceType.ADDED

        # 編集が空
        result = detector.detect_differences("テスト", "")
        assert len(result.differences) == 0  # 編集テキストが空の場合、差分なし

    def test_lcs_positions_calculation(self, detector):
        """LCS位置計算の正確性"""
        text1 = "ABCDEF"
        text2 = "ACDF"

        positions = detector._compute_lcs_positions(text1, text2)

        # A(0,0), C(2,1), D(3,2), F(5,3)
        expected = [(0, 0), (2, 1), (3, 2), (5, 3)]
        assert positions == expected

    def test_lcs_with_repeated_characters(self, detector):
        """繰り返し文字を含む場合"""
        original = "aaabbbccc"
        edited = "abc"

        positions = detector._compute_lcs_positions(original, edited)

        # 最初のa, 最初のb, 最初のcがマッチ
        assert len(positions) == 3
        assert positions[0][1] == 0  # 'a'
        assert positions[1][1] == 1  # 'b'
        assert positions[2][1] == 2  # 'c'

    def test_continuous_match_grouping(self, detector):
        """連続したマッチのグループ化"""
        positions = [(0, 0), (1, 1), (2, 2), (5, 3), (6, 4)]
        groups = detector._group_continuous_matches(positions)

        assert len(groups) == 2
        assert groups[0] == [(0, 0), (1, 1), (2, 2)]
        assert groups[1] == [(5, 3), (6, 4)]

    def test_difference_blocks_with_timestamps(self, detector, sample_transcription_with_fillers):
        """タイムスタンプ付き差分ブロックの生成"""
        original = "えーっと今日はあのー天気がいいですね"
        edited = "今日は天気"

        _, blocks = detector.detect_differences_with_blocks(original, edited, sample_transcription_with_fillers)

        # UNCHANGEDブロックの時間情報を確認
        unchanged_blocks = [b for b in blocks if b.type == DifferenceType.UNCHANGED]

        for block in unchanged_blocks:
            assert block.start_time is not None
            assert block.end_time is not None
            assert block.start_time < block.end_time
            assert len(block.char_positions) > 0

    def test_deletion_blocks_identification(self, detector, sample_transcription_with_fillers):
        """削除ブロックの特定"""
        original = "えーっと今日はあのー天気がいいですね"
        edited = "今日は天気がいいですね"

        _, blocks = detector.detect_differences_with_blocks(original, edited, sample_transcription_with_fillers)

        # DELETEDブロックを確認
        deleted_blocks = [b for b in blocks if b.type == DifferenceType.DELETED]

        # フィラー部分が削除として検出される
        deleted_texts = [b.text for b in deleted_blocks]
        assert any("えーっと" in text for text in deleted_texts)
        assert any("あのー" in text for text in deleted_texts)

    def test_large_text_chunking(self, detector):
        """大きなテキストの分割処理"""
        # 10000文字のテキスト
        text1 = "あ" * 10000
        text2 = "あ" * 100

        positions = detector._compute_lcs_positions_chunked(text1, text2)

        # 100個の位置が検出される
        assert len(positions) == 100

    def test_difference_block_properties(self):
        """DifferenceBlockのプロパティテスト"""
        from domain.value_objects.lcs_match import DifferenceBlock
        from domain.entities.character_timestamp import CharacterWithTimestamp

        chars = [
            CharacterWithTimestamp(char="あ", start=0.0, end=0.5, segment_id="seg1", word_index=0, original_position=0),
            CharacterWithTimestamp(char="い", start=0.5, end=1.0, segment_id="seg1", word_index=1, original_position=1),
        ]

        block = DifferenceBlock(type=DifferenceType.UNCHANGED, text="あい", char_positions=chars)

        assert block.duration == 1.0
        assert block.char_count == 2
        assert block.start_time == 0.0
        assert block.end_time == 1.0

    def test_adjacent_blocks(self):
        """隣接ブロックの判定"""
        from domain.value_objects.lcs_match import DifferenceBlock

        block1 = DifferenceBlock(type=DifferenceType.UNCHANGED, text="あ", start_time=0.0, end_time=1.0)

        block2 = DifferenceBlock(type=DifferenceType.UNCHANGED, text="い", start_time=1.05, end_time=2.0)

        block3 = DifferenceBlock(type=DifferenceType.UNCHANGED, text="う", start_time=2.0, end_time=3.0)

        # 0.05秒の差は隣接とみなす（デフォルト閾値0.1秒）
        assert block1.is_adjacent_to(block2) is True

        # ちょうど接している場合も隣接
        assert block2.is_adjacent_to(block3) is True

        # 離れている場合は隣接しない
        block5 = DifferenceBlock(type=DifferenceType.UNCHANGED, text="お", start_time=3.2, end_time=4.0)
        assert block3.is_adjacent_to(block5) is False

        # 異なるタイプは隣接とみなさない
        block4 = DifferenceBlock(type=DifferenceType.DELETED, text="え", start_time=1.05, end_time=2.0)
        assert block1.is_adjacent_to(block4) is False
