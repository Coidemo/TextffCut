#!/usr/bin/env python3
"""
異常なタイムスタンプ処理のテスト
"""
import json
import pytest
from pathlib import Path
from core.text_processor import TextProcessor
from core.transcription import TranscriptionResult, TranscriptionSegment


class TestAbnormalTimestamp:
    """異常なタイムスタンプ処理のテストクラス"""
    
    def setup_method(self):
        """テストメソッドごとの初期化"""
        self.text_processor = TextProcessor()
    
    def create_test_transcription(self, segments_data, language='ja'):
        """テスト用のTranscriptionResultを作成"""
        segments = []
        for seg_data in segments_data:
            segments.append(TranscriptionSegment(
                start=seg_data['start'],
                end=seg_data['end'],
                text=seg_data['text'],
                words=seg_data.get('words', [])
            ))
        
        return TranscriptionResult(
            language=language,
            segments=segments,
            original_audio_path='test.wav',
            model_size='medium',
            processing_time=0.0
        )
    
    def test_abnormal_last_word_japanese(self):
        """日本語での最後の単語が異常に長い場合"""
        segments_data = [{
            'start': 0.0,
            'end': 3.0,
            'text': 'テストです。',
            'words': [
                {'word': 'テ', 'start': 0.0, 'end': 0.1},
                {'word': 'ス', 'start': 0.1, 'end': 0.2},
                {'word': 'ト', 'start': 0.2, 'end': 0.3},
                {'word': 'で', 'start': 0.3, 'end': 0.4},
                {'word': 'す', 'start': 0.4, 'end': 1.5},  # 異常に長い
                {'word': '。', 'start': None, 'end': None}
            ]
        }]
        
        transcription = self.create_test_transcription(segments_data, 'ja')
        diff = self.text_processor.find_differences('テストです。', 'テストです。')
        time_ranges = diff.get_time_ranges(transcription)
        
        # 「す」の終了時刻が前の単語「で」の終了時刻（0.4秒）になるはず
        assert len(time_ranges) == 1
        assert time_ranges[0][0] == 0.0
        assert time_ranges[0][1] == 0.4  # 1.5ではなく0.4
    
    def test_abnormal_last_word_english(self):
        """英語では補正が適用されないことを確認"""
        segments_data = [{
            'start': 0.0,
            'end': 3.0,
            'text': 'Test it.',
            'words': [
                {'word': 'Test', 'start': 0.0, 'end': 0.3},
                {'word': ' ', 'start': 0.3, 'end': 0.35},
                {'word': 'it', 'start': 0.35, 'end': 1.5},  # 異常に長い
                {'word': '.', 'start': None, 'end': None}
            ]
        }]
        
        transcription = self.create_test_transcription(segments_data, 'en')
        diff = self.text_processor.find_differences('Test it.', 'Test it.')
        time_ranges = diff.get_time_ranges(transcription)
        
        # 英語では補正されず、元の終了時刻が使われる
        # ただし句読点「.」のタイムスタンプが推定される
        assert len(time_ranges) == 1
        assert time_ranges[0][0] == 0.0
        # 「it」の終了時刻1.5秒は補正されないが、「.」の推定時刻が使われる
        assert time_ranges[0][1] > 1.5  # 句読点の推定により1.5より大きくなる
    
    def test_first_word_abnormal(self):
        """最初の単語が異常に長い場合（補正されない）"""
        segments_data = [{
            'start': 0.0,
            'end': 3.0,
            'text': 'あいうえお',
            'words': [
                {'word': 'あ', 'start': 0.0, 'end': 1.5},  # 異常に長い
                {'word': 'い', 'start': 1.5, 'end': 1.6},
                {'word': 'う', 'start': 1.6, 'end': 1.7},
                {'word': 'え', 'start': 1.7, 'end': 1.8},
                {'word': 'お', 'start': 1.8, 'end': 1.9}
            ]
        }]
        
        transcription = self.create_test_transcription(segments_data, 'ja')
        diff = self.text_processor.find_differences('あいうえお', 'あ')
        time_ranges = diff.get_time_ranges(transcription)
        
        # 最初の単語なので前の単語がなく、補正されない
        assert len(time_ranges) == 1
        assert time_ranges[0][0] == 0.0
        assert time_ranges[0][1] == 1.5
    
    def test_multiple_abnormal_words(self):
        """連続して複数の単語が異常に長い場合"""
        segments_data = [{
            'start': 0.0,
            'end': 5.0,
            'text': 'これはテストです。',
            'words': [
                {'word': 'こ', 'start': 0.0, 'end': 0.1},
                {'word': 'れ', 'start': 0.1, 'end': 0.2},
                {'word': 'は', 'start': 0.2, 'end': 0.3},
                {'word': 'テ', 'start': 0.3, 'end': 0.4},
                {'word': 'ス', 'start': 0.4, 'end': 0.5},
                {'word': 'ト', 'start': 0.5, 'end': 1.6},  # 異常に長い
                {'word': 'で', 'start': 1.6, 'end': 2.7},  # 異常に長い
                {'word': 'す', 'start': 2.7, 'end': 3.8},  # 異常に長い
                {'word': '。', 'start': None, 'end': None}
            ]
        }]
        
        transcription = self.create_test_transcription(segments_data, 'ja')
        diff = self.text_processor.find_differences('これはテストです。', 'これはテストです。')
        time_ranges = diff.get_time_ranges(transcription)
        
        # 最後の実質的な単語「す」のみが補正される
        assert len(time_ranges) == 1
        assert time_ranges[0][0] == 0.0
        assert time_ranges[0][1] == 2.7  # 「で」の終了時刻
    
    def test_various_punctuation_patterns(self):
        """様々な句読点パターンでのテスト"""
        test_patterns = [
            ('こんにちは！', '！'),
            ('質問ですか？', '？'),
            ('はい、わかりました。', '。'),
            ('そう、ですね。', '。'),
        ]
        
        for text, punctuation in test_patterns:
            segments_data = [{
                'start': 0.0,
                'end': 3.0,
                'text': text,
                'words': []
            }]
            
            # wordsを動的に生成
            current_time = 0.0
            for i, char in enumerate(text[:-1]):  # 句読点以外
                if i == len(text) - 2:  # 最後の文字
                    segments_data[0]['words'].append({
                        'word': char,
                        'start': current_time,
                        'end': current_time + 1.5  # 異常に長い
                    })
                else:
                    segments_data[0]['words'].append({
                        'word': char,
                        'start': current_time,
                        'end': current_time + 0.1
                    })
                    current_time += 0.1
            
            # 句読点を追加
            segments_data[0]['words'].append({
                'word': punctuation,
                'start': None,
                'end': None
            })
            
            transcription = self.create_test_transcription(segments_data, 'ja')
            diff = self.text_processor.find_differences(text, text)
            time_ranges = diff.get_time_ranges(transcription)
            
            assert len(time_ranges) == 1
            # 最後の文字が異常に長いので、その前の文字の終了時刻が使われる
            expected_end = (len(text) - 3) * 0.1 + 0.1  # 最後から2番目の文字の終了時刻
            assert time_ranges[0][1] == pytest.approx(expected_end, 0.01)
    
    def test_long_word_threshold(self):
        """3文字以上の単語は補正されないことを確認"""
        segments_data = [{
            'start': 0.0,
            'end': 3.0,
            'text': 'これはテストです。',
            'words': [
                {'word': 'これは', 'start': 0.0, 'end': 0.3},
                {'word': 'テスト', 'start': 0.3, 'end': 2.0},  # 長いが3文字以上
                {'word': 'です', 'start': 2.0, 'end': 2.2},
                {'word': '。', 'start': None, 'end': None}
            ]
        }]
        
        transcription = self.create_test_transcription(segments_data, 'ja')
        diff = self.text_processor.find_differences('これはテストです。', 'これはテスト')
        time_ranges = diff.get_time_ranges(transcription)
        
        # 「テスト」は3文字以上なので補正されない
        assert len(time_ranges) == 1
        assert time_ranges[0][0] == 0.0
        assert time_ranges[0][1] == 2.0  # 補正されない


if __name__ == '__main__':
    pytest.main([__file__, '-v'])