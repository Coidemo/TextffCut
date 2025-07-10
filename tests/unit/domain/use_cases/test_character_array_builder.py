"""
CharacterArrayBuilderの単体テスト
"""

import pytest
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.entities.character_timestamp import CharacterWithTimestamp
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word


class TestCharacterArrayBuilder:
    """CharacterArrayBuilderのテスト"""

    @pytest.fixture
    def builder(self):
        return CharacterArrayBuilder()

    @pytest.fixture
    def sample_segments_dict(self):
        """辞書形式のセグメント（レガシー互換）"""
        return [
            {
                "id": "seg1",
                "start": 0.0,
                "end": 2.0,
                "text": "こんにちは",
                "words": [
                    {"text": "こ", "start": 0.0, "end": 0.4, "confidence": 0.9},
                    {"text": "ん", "start": 0.4, "end": 0.8, "confidence": 0.95},
                    {"text": "に", "start": 0.8, "end": 1.2, "confidence": 0.9},
                    {"text": "ち", "start": 1.2, "end": 1.6, "confidence": 0.9},
                    {"text": "は", "start": 1.6, "end": 2.0, "confidence": 0.9},
                ],
            },
            {
                "id": "seg2",
                "start": 2.0,
                "end": 3.5,
                "text": "元気です",
                "words": [
                    {"text": "元", "start": 2.0, "end": 2.5, "confidence": 0.85},
                    {"text": "気", "start": 2.5, "end": 3.0, "confidence": 0.9},
                    {"text": "で", "start": 3.0, "end": 3.2, "confidence": 0.9},
                    {"text": "す", "start": 3.2, "end": 3.5, "confidence": 0.95},
                ],
            },
        ]

    @pytest.fixture
    def sample_transcription_result(self):
        """TranscriptionResultオブジェクト"""
        segments = [
            TranscriptionSegment(
                id="seg1",
                start=0.0,
                end=2.0,
                text="こんにちは",
                words=[
                    Word(word="こ", start=0.0, end=0.4, confidence=0.9),
                    Word(word="ん", start=0.4, end=0.8, confidence=0.95),
                    Word(word="に", start=0.8, end=1.2, confidence=0.9),
                    Word(word="ち", start=1.2, end=1.6, confidence=0.9),
                    Word(word="は", start=1.6, end=2.0, confidence=0.9),
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

    def test_build_from_segments_with_words(self, builder, sample_segments_dict):
        """wordsフィールドがある場合の文字配列構築"""
        char_array, full_text = builder.build_from_segments(sample_segments_dict)

        # 文字数の確認
        assert len(char_array) == 9  # 5 + 4文字
        assert full_text == "こんにちは元気です"

        # 最初の文字の詳細確認
        first_char = char_array[0]
        assert first_char.char == "こ"
        assert first_char.start == 0.0
        assert first_char.end == 0.4
        assert first_char.segment_id == "seg1"
        assert first_char.word_index == 0
        assert first_char.original_position == 0
        assert first_char.confidence == 0.9

        # 最後の文字の詳細確認
        last_char = char_array[-1]
        assert last_char.char == "す"
        assert last_char.start == 3.2
        assert last_char.end == 3.5
        assert last_char.segment_id == "seg2"
        assert last_char.original_position == 8

    def test_build_from_segments_without_words(self, builder):
        """wordsフィールドがない場合のフォールバック"""
        segments = [{"id": "seg1", "start": 0.0, "end": 2.0, "text": "テスト"}]

        char_array, full_text = builder.build_from_segments(segments)

        assert len(char_array) == 3
        assert full_text == "テスト"

        # 時間が均等に配分されているか
        assert char_array[0].start == 0.0
        assert char_array[0].end == pytest.approx(2.0 / 3)
        assert char_array[1].start == pytest.approx(2.0 / 3)
        assert char_array[1].end == pytest.approx(4.0 / 3)
        assert char_array[2].start == pytest.approx(4.0 / 3)
        assert char_array[2].end == 2.0

        # 信頼度が低く設定されているか
        assert all(c.confidence == 0.5 for c in char_array)

    def test_build_from_transcription_result(self, builder, sample_transcription_result):
        """TranscriptionResultからの文字配列構築"""
        char_array, full_text = builder.build_from_transcription(sample_transcription_result)

        assert len(char_array) == 5
        assert full_text == "こんにちは"

        # 文字の順序確認
        chars = [c.char for c in char_array]
        assert chars == ["こ", "ん", "に", "ち", "は"]

    def test_validate_reconstruction_exact_match(self, builder):
        """再構築テキストの検証：完全一致"""
        assert builder.validate_reconstruction("テスト", "テスト") is True

    def test_validate_reconstruction_with_spaces(self, builder):
        """再構築テキストの検証：空白の正規化"""
        assert builder.validate_reconstruction("テ ス ト", "テスト") is True
        assert builder.validate_reconstruction("テ　ス　ト", "テスト") is True

    def test_validate_reconstruction_partial_match(self, builder):
        """再構築テキストの検証：部分一致"""
        assert builder.validate_reconstruction("テスト", "これはテストです") is True
        assert builder.validate_reconstruction("これはテストです", "テスト") is True

    def test_validate_reconstruction_no_match(self, builder):
        """再構築テキストの検証：不一致"""
        assert builder.validate_reconstruction("テスト", "試験") is False

    def test_empty_segments(self, builder):
        """空のセグメントリスト"""
        char_array, full_text = builder.build_from_segments([])

        assert len(char_array) == 0
        assert full_text == ""

    def test_character_timestamp_validation(self, builder):
        """CharacterWithTimestampのバリデーション"""
        # 不正な文字長
        with pytest.raises(ValueError, match="charは1文字である必要があります"):
            CharacterWithTimestamp(
                char="あい", start=0.0, end=1.0, segment_id="seg1", word_index=0, original_position=0  # 2文字
            )

        # 負の時間
        with pytest.raises(ValueError, match="時間は正の値である必要があります"):
            CharacterWithTimestamp(char="あ", start=-1.0, end=1.0, segment_id="seg1", word_index=0, original_position=0)

        # 開始時間 > 終了時間
        with pytest.raises(ValueError, match="開始時間は終了時間より前である必要があります"):
            CharacterWithTimestamp(char="あ", start=2.0, end=1.0, segment_id="seg1", word_index=0, original_position=0)

    def test_character_duration_calculation(self):
        """文字の継続時間計算"""
        char = CharacterWithTimestamp(
            char="あ", start=1.0, end=1.5, segment_id="seg1", word_index=0, original_position=0
        )

        assert char.duration == 0.5

    def test_character_overlap_detection(self):
        """文字の重なり検出"""
        char1 = CharacterWithTimestamp(
            char="あ", start=1.0, end=2.0, segment_id="seg1", word_index=0, original_position=0
        )

        char2 = CharacterWithTimestamp(
            char="い", start=1.5, end=2.5, segment_id="seg1", word_index=1, original_position=1
        )

        char3 = CharacterWithTimestamp(
            char="う", start=2.5, end=3.0, segment_id="seg1", word_index=2, original_position=2
        )

        assert char1.overlaps_with(char2) is True
        assert char1.overlaps_with(char3) is False
        assert char2.overlaps_with(char3) is False
