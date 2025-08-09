"""
wordsベースの検索ロジックのテストケース
"""

import unittest

from core.text_processor import TextProcessor, TranscriptionResult, TranscriptionSegment


class TestWordsBasedSearch(unittest.TestCase):
    """wordsベースの検索機能のテスト"""

    def setUp(self):
        """テストの初期設定"""
        self.processor = TextProcessor()

    def test_japanese_with_spaces(self):
        """日本語テキスト（空白あり）の検索テスト"""
        # WhisperXの実際の出力を模擬
        segments = [
            TranscriptionSegment(
                start=10.0,
                end=15.0,
                text="こんにちは　世界です",  # 元のテキスト（空白あり）
                words=[
                    {"word": "こ", "start": 10.0, "end": 10.2},
                    {"word": "ん", "start": 10.2, "end": 10.4},
                    {"word": "に", "start": 10.4, "end": 10.6},
                    {"word": "ち", "start": 10.6, "end": 10.8},
                    {"word": "は", "start": 10.8, "end": 11.0},
                    # 空白部分はwordsに含まれない
                    {"word": "世", "start": 11.5, "end": 11.7},
                    {"word": "界", "start": 11.7, "end": 11.9},
                    {"word": "で", "start": 11.9, "end": 12.1},
                    {"word": "す", "start": 12.1, "end": 12.3},
                ],
            )
        ]

        transcription = TranscriptionResult(
            language="ja", segments=segments, original_audio_path="test.mp4", model_size="base", processing_time=10.0
        )

        # wordsベースのテキスト（空白なし）
        full_text = transcription.get_full_text()
        self.assertEqual(full_text, "こんにちは世界です")

        # 「世界」を検索
        diff = self.processor.find_differences(full_text, "世界")
        time_ranges = diff.get_time_ranges(transcription)

        # 「世界」の時間範囲が正しく取得できるか
        self.assertEqual(len(time_ranges), 1)
        start_time, end_time = time_ranges[0]
        self.assertAlmostEqual(start_time, 11.5, places=1)
        self.assertAlmostEqual(end_time, 11.9, places=1)

    def test_single_character_precision(self):
        """1文字単位の精度テスト"""
        segments = [
            TranscriptionSegment(
                start=0.0,
                end=3.0,
                text="日本語テスト",
                words=[
                    {"word": "日", "start": 0.0, "end": 0.5},
                    {"word": "本", "start": 0.5, "end": 1.0},
                    {"word": "語", "start": 1.0, "end": 1.5},
                    {"word": "テ", "start": 1.5, "end": 2.0},
                    {"word": "ス", "start": 2.0, "end": 2.5},
                    {"word": "ト", "start": 2.5, "end": 3.0},
                ],
            )
        ]

        transcription = TranscriptionResult(
            language="ja", segments=segments, original_audio_path="test.mp4", model_size="base", processing_time=10.0
        )

        # 「本」だけを検索（1文字）
        full_text = transcription.get_full_text()
        diff = self.processor.find_differences(full_text, "本")
        time_ranges = diff.get_time_ranges(transcription)

        self.assertEqual(len(time_ranges), 1)
        start_time, end_time = time_ranges[0]
        self.assertAlmostEqual(start_time, 0.5, places=1)
        self.assertAlmostEqual(end_time, 1.0, places=1)

    def test_missing_words_error(self):
        """wordsがない場合のエラーテスト"""
        segments = [TranscriptionSegment(start=0.0, end=3.0, text="テスト", words=None)]  # wordsがない

        # get_text()を呼ぶとエラーになるはず
        with self.assertRaises(ValueError) as context:
            segments[0].get_text()

        self.assertIn("wordsが存在しません", str(context.exception))

    def test_multiple_segments(self):
        """複数セグメントにまたがる検索テスト"""
        segments = [
            TranscriptionSegment(
                start=0.0,
                end=2.0,
                text="今日は",
                words=[
                    {"word": "今", "start": 0.0, "end": 0.5},
                    {"word": "日", "start": 0.5, "end": 1.0},
                    {"word": "は", "start": 1.0, "end": 1.5},
                ],
            ),
            TranscriptionSegment(
                start=2.0,
                end=4.0,
                text="良い天気",
                words=[
                    {"word": "良", "start": 2.0, "end": 2.5},
                    {"word": "い", "start": 2.5, "end": 3.0},
                    {"word": "天", "start": 3.0, "end": 3.5},
                    {"word": "気", "start": 3.5, "end": 4.0},
                ],
            ),
        ]

        transcription = TranscriptionResult(
            language="ja", segments=segments, original_audio_path="test.mp4", model_size="base", processing_time=10.0
        )

        # 複数セグメントにまたがる「今日は良い」を検索
        full_text = transcription.get_full_text()
        self.assertEqual(full_text, "今日は良い天気")

        diff = self.processor.find_differences(full_text, "今日は良い")
        time_ranges = diff.get_time_ranges(transcription)

        self.assertEqual(len(time_ranges), 1)
        start_time, end_time = time_ranges[0]
        self.assertAlmostEqual(start_time, 0.0, places=1)
        self.assertAlmostEqual(end_time, 3.0, places=1)


if __name__ == "__main__":
    unittest.main()
