"""
TranscriptionConverterのテスト
"""

import pytest
from unittest.mock import Mock

from adapters.converters.transcription_converter import TranscriptionConverter
from domain.entities import TranscriptionResult


class TestTranscriptionConverter:
    """TranscriptionConverterのテスト"""
    
    @pytest.fixture
    def converter(self):
        """テスト用コンバーター"""
        return TranscriptionConverter()
    
    def test_convert_char_with_none_values(self, converter):
        """None値を含むchar変換のテスト"""
        # 辞書形式でNone値を含む場合
        char_dict = {
            "char": "あ",
            "start": None,  # Noneの場合
            "end": None,    # Noneの場合
            "confidence": 0.95
        }
        
        result = converter._convert_char(char_dict)
        
        assert result.char == "あ"
        assert result.start == 0.0  # Noneは0.0に変換される
        assert result.end == 0.0    # Noneは0.0に変換される
        assert result.confidence == 0.95
    
    def test_convert_word_with_none_values(self, converter):
        """None値を含むword変換のテスト"""
        # 辞書形式でNone値を含む場合
        word_dict = {
            "word": "テスト",
            "start": None,  # Noneの場合
            "end": None,    # Noneの場合
            "confidence": None
        }
        
        result = converter._convert_word(word_dict)
        
        assert result.word == "テスト"
        assert result.start == 0.0  # Noneは0.0に変換される
        assert result.end == 0.0    # Noneは0.0に変換される
        assert result.confidence is None
    
    def test_convert_segment_with_empty_words_and_chars(self, converter):
        """空のwordsとcharsを含むセグメント変換のテスト"""
        segment = Mock()
        segment.text = "テストセグメント"
        segment.start = 0.0
        segment.end = 1.0
        segment.words = []  # 空のリスト
        segment.chars = []  # 空のリスト
        
        result = converter._convert_segment(segment, "seg_001")
        
        assert result.text == "テストセグメント"
        assert result.start == 0.0
        assert result.end == 1.0
        assert result.words == []
        assert result.chars == []
    
    def test_legacy_to_domain_with_minimal_data(self, converter):
        """最小限のデータでのlegacy_to_domain変換テスト"""
        # 最小限の有効なデータ
        legacy_result = Mock()
        legacy_result.language = "ja"
        legacy_result.text = "テスト"
        legacy_result.processing_time = 1.0
        
        # セグメントを作成
        segment = Mock()
        segment.text = "テスト"
        segment.start = 0.0
        segment.end = 1.0
        segment.words = []
        segment.chars = []
        
        legacy_result.segments = [segment]
        
        # 変換実行
        result = converter.legacy_to_domain(legacy_result)
        
        assert isinstance(result, TranscriptionResult)
        assert result.language == "ja"
        assert result.text == "テスト"
        assert result.processing_time == 1.0
        assert len(result.segments) == 1
    
    def test_legacy_to_domain_with_real_cache_data(self, converter):
        """実際のキャッシュデータ形式での変換テスト"""
        # 実際のキャッシュファイルで発生する可能性のあるデータ
        legacy_result = Mock()
        legacy_result.language = "ja"
        legacy_result.text = "こんにちは"
        legacy_result.processing_time = 5.23
        
        # セグメント
        segment = Mock()
        segment.text = "こんにちは"
        segment.start = 0.0
        segment.end = 2.0
        
        # wordsがある場合
        word = Mock()
        word.word = "こんにちは"
        word.start = 0.0
        word.end = 2.0
        word.confidence = 0.95
        segment.words = [word]
        
        # charsがある場合（各文字にNone値が含まれる可能性）
        chars = []
        for i, char_text in enumerate("こんにちは"):
            char = {
                "char": char_text,
                "start": i * 0.4 if i > 0 else None,  # 最初の文字はNoneの可能性
                "end": (i + 1) * 0.4,
                "confidence": 0.9 + i * 0.01
            }
            chars.append(char)
        
        # charsは辞書形式で格納されることがある
        segment.chars = chars
        
        legacy_result.segments = [segment]
        
        # 変換実行
        result = converter.legacy_to_domain(legacy_result)
        
        assert isinstance(result, TranscriptionResult)
        assert len(result.segments) == 1
        assert len(result.segments[0].words) == 1
        assert len(result.segments[0].chars) == 5
        
        # 最初の文字のstartが0.0に変換されているか確認
        assert result.segments[0].chars[0].start == 0.0