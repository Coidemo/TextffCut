"""
文字起こしエンティティのテスト
"""

import pytest

from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word


class TestWord:
    """Wordエンティティのテスト"""

    def test_create_valid_word(self):
        """正常なWordの作成"""
        word = Word(word="こんにちは", start=0.0, end=1.5, confidence=0.95)
        assert word.word == "こんにちは"
        assert word.start == 0.0
        assert word.end == 1.5
        assert word.confidence == 0.95
        assert word.duration == 1.5

    def test_invalid_start_time(self):
        """負の開始時間でエラー"""
        with pytest.raises(ValueError, match="Start time cannot be negative"):
            Word(word="test", start=-1.0, end=1.0)

    def test_invalid_end_time(self):
        """終了時間が開始時間より前でエラー"""
        with pytest.raises(ValueError, match="End time must be greater than start time"):
            Word(word="test", start=2.0, end=1.0)

    def test_invalid_confidence(self):
        """無効な信頼度でエラー"""
        with pytest.raises(ValueError, match="Confidence must be between 0 and 1"):
            Word(word="test", start=0.0, end=1.0, confidence=1.5)

    def test_from_dict(self):
        """辞書からの変換"""
        data = {"word": "テスト", "start": 0.5, "end": 1.0, "score": 0.88}
        word = Word.from_dict(data)
        assert word.word == "テスト"
        assert word.start == 0.5
        assert word.end == 1.0
        assert word.confidence == 0.88

    def test_to_dict(self):
        """辞書への変換"""
        word = Word(word="テスト", start=0.5, end=1.0, confidence=0.88)
        data = word.to_dict()
        assert data == {"word": "テスト", "start": 0.5, "end": 1.0, "confidence": 0.88}


class TestTranscriptionSegment:
    """TranscriptionSegmentエンティティのテスト"""

    def test_create_valid_segment(self):
        """正常なセグメントの作成"""
        segment = TranscriptionSegment(id="test-id", text="これはテストです", start=0.0, end=3.0)
        assert segment.id == "test-id"
        assert segment.text == "これはテストです"
        assert segment.start == 0.0
        assert segment.end == 3.0
        assert segment.duration == 3.0

    def test_segment_with_words(self):
        """単語付きセグメント"""
        words = [
            {"word": "これは", "start": 0.0, "end": 0.8, "confidence": 0.9},
            {"word": "テスト", "start": 0.8, "end": 1.5, "confidence": 0.85},
        ]
        segment = TranscriptionSegment(id="test-id", text="これはテスト", start=0.0, end=1.5, words=words)

        assert segment.has_word_level_timestamps
        assert len(segment.words) == 2
        assert all(isinstance(w, Word) for w in segment.words)

    def test_get_words_as_dicts(self):
        """wordsを辞書リストとして取得"""
        words = [Word(word="これは", start=0.0, end=0.8, confidence=0.9)]
        segment = TranscriptionSegment(id="test-id", text="これは", start=0.0, end=0.8, words=words)

        dicts = segment.get_words_as_dicts()
        assert isinstance(dicts, list)
        assert dicts[0]["word"] == "これは"

    def test_from_legacy_format(self):
        """レガシー形式からの変換"""
        legacy_data = {
            "text": "レガシーテキスト",
            "start": 1.0,
            "end": 2.5,
            "words": [{"word": "レガシー", "start": 1.0, "end": 1.8}],
        }
        segment = TranscriptionSegment.from_legacy_format(legacy_data)

        assert segment.text == "レガシーテキスト"
        assert segment.start == 1.0
        assert segment.end == 2.5
        assert len(segment.words) == 1


class TestTranscriptionResult:
    """TranscriptionResultエンティティのテスト"""

    def test_create_valid_result(self):
        """正常な結果の作成"""
        segments = [
            TranscriptionSegment(id="seg1", text="最初のセグメント", start=0.0, end=2.0),
            TranscriptionSegment(id="seg2", text="次のセグメント", start=2.0, end=4.0),
        ]

        result = TranscriptionResult(
            id="result-id",
            language="ja",
            segments=segments,
            original_audio_path="/path/to/audio.mp4",
            model_size="medium",
            processing_time=45.3,
        )

        assert result.id == "result-id"
        assert result.language == "ja"
        assert len(result.segments) == 2
        assert result.duration == 4.0
        assert result.text == "最初のセグメント 次のセグメント"

    def test_empty_segments_error(self):
        """セグメントが空の場合エラー"""
        with pytest.raises(ValueError, match="at least one segment"):
            TranscriptionResult(
                id="test",
                language="ja",
                segments=[],
                original_audio_path="/path/to/audio.mp4",
                model_size="medium",
                processing_time=10.0,
            )

    def test_get_segments_in_range(self):
        """指定範囲内のセグメントを取得"""
        segments = [
            TranscriptionSegment(id="1", text="A", start=0.0, end=2.0),
            TranscriptionSegment(id="2", text="B", start=2.0, end=4.0),
            TranscriptionSegment(id="3", text="C", start=4.0, end=6.0),
        ]

        result = TranscriptionResult(
            id="test",
            language="ja",
            segments=segments,
            original_audio_path="/path",
            model_size="medium",
            processing_time=10.0,
        )

        # 1.5から3.5の範囲を取得
        in_range = result.get_segments_in_range(1.5, 3.5)
        assert len(in_range) == 2
        assert in_range[0].text == "A"
        assert in_range[1].text == "B"

    def test_validate_for_text_search(self):
        """テキスト検索の検証"""
        # wordsなしのセグメント
        segments = [TranscriptionSegment(id="1", text="テスト", start=0.0, end=1.0)]
        result = TranscriptionResult(
            id="test",
            language="ja",
            segments=segments,
            original_audio_path="/path",
            model_size="medium",
            processing_time=10.0,
        )

        assert not result.validate_for_text_search()

        # wordsありのセグメント
        segments_with_words = [
            TranscriptionSegment(
                id="1", text="テスト", start=0.0, end=1.0, words=[{"word": "テスト", "start": 0.0, "end": 1.0}]
            )
        ]
        result_with_words = TranscriptionResult(
            id="test",
            language="ja",
            segments=segments_with_words,
            original_audio_path="/path",
            model_size="medium",
            processing_time=10.0,
        )

        assert result_with_words.validate_for_text_search()

    def test_from_legacy_format(self):
        """レガシー形式からの変換"""
        legacy_data = {
            "language": "ja",
            "segments": [
                {"text": "セグメント1", "start": 0.0, "end": 1.0},
                {"text": "セグメント2", "start": 1.0, "end": 2.0},
            ],
            "original_audio_path": "/path/to/audio.mp4",
            "model_size": "large",
            "processing_time": 30.5,
        }

        result = TranscriptionResult.from_legacy_format(legacy_data)

        assert result.language == "ja"
        assert len(result.segments) == 2
        assert result.model_size == "large"
        assert result.processing_time == 30.5
