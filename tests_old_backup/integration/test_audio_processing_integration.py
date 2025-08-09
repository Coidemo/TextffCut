"""
音声処理の結合テスト
AudioSplitter + VideoProcessor + OptimizedTranscriberの統合動作を確認
"""

import os
import sys
import tempfile
import unittest

import numpy as np

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from core.audio_splitter import AudioSplitter
from core.transcription_optimized import OptimizedTranscriber
from core.video import VideoProcessor


class TestAudioProcessingIntegration(unittest.TestCase):
    """音声処理統合テスト"""

    def setUp(self):
        """テストの初期設定"""
        self.config = Config()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """テスト後のクリーンアップ"""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def create_test_audio(self, duration_seconds=10, sample_rate=16000):
        """テスト用音声ファイルを作成"""
        import soundfile as sf

        # 簡単な音声信号を生成（サイン波 + 無音部分）
        samples = int(duration_seconds * sample_rate)
        audio = np.zeros(samples)

        # 最初の3秒: 440Hzのサイン波（duration_secondsが3秒未満の場合は調整）
        end1 = min(3, duration_seconds)
        if end1 > 0:
            t1 = np.linspace(0, end1, int(end1 * sample_rate))
            audio[: int(end1 * sample_rate)] = 0.3 * np.sin(2 * np.pi * 440 * t1)

        # 3-4秒: 無音
        # (既にゼロで初期化されている)

        # 4-7秒: 880Hzのサイン波
        start2 = min(4, duration_seconds)
        end2 = min(7, duration_seconds)
        if end2 > start2:
            duration2 = end2 - start2
            t2 = np.linspace(0, duration2, int(duration2 * sample_rate))
            audio[int(start2 * sample_rate) : int(end2 * sample_rate)] = 0.3 * np.sin(2 * np.pi * 880 * t2)

        # 7-8秒: 無音

        # 8秒以降: 220Hzのサイン波
        start3 = min(8, duration_seconds)
        if start3 < duration_seconds:
            duration3 = duration_seconds - start3
            t3 = np.linspace(0, duration3, int(duration3 * sample_rate))
            audio[int(start3 * sample_rate) :] = 0.3 * np.sin(2 * np.pi * 220 * t3)

        # WAVファイルとして保存
        audio_path = os.path.join(self.temp_dir, "test_audio.wav")
        sf.write(audio_path, audio, sample_rate)

        return audio_path, audio

    def test_silence_detection_integration(self):
        """無音検出の統合テスト"""
        # テスト音声を作成
        audio_path, _ = self.create_test_audio(duration_seconds=10)

        # VideoProcessorで無音検出
        video_processor = VideoProcessor(self.config)
        silences = video_processor.detect_silence_from_wav(audio_path, noise_threshold=-30, min_silence_duration=0.5)

        # 検証: 2つの無音部分が検出されるはず
        self.assertEqual(len(silences), 2)

        # 最初の無音（3-4秒付近）
        self.assertAlmostEqual(silences[0].start, 3.0, delta=0.2)
        self.assertAlmostEqual(silences[0].end, 4.0, delta=0.2)

        # 2番目の無音（7-8秒付近）
        self.assertAlmostEqual(silences[1].start, 7.0, delta=0.2)
        self.assertAlmostEqual(silences[1].end, 8.0, delta=0.2)

    def test_audio_splitter_with_real_audio(self):
        """実際の音声ファイルでのAudioSplitterテスト"""
        # 30秒のテスト音声を作成（10秒パターンを3回繰り返し）
        audio_path, audio_data = self.create_test_audio(duration_seconds=30)

        # 10秒ごとに無音を追加
        import soundfile as sf

        sample_rate = 16000
        extended_audio = np.zeros(30 * sample_rate)

        # 0-9秒: 最初の10秒をコピー（サイズを確認してからコピー）
        segment_size = min(10 * sample_rate, len(audio_data))
        extended_audio[:segment_size] = audio_data[:segment_size]
        # 9-10秒: 無音（既にゼロ）
        # 10-19秒: 最初の10秒をコピー
        if len(audio_data) >= 10 * sample_rate:
            extended_audio[10 * sample_rate : 20 * sample_rate] = audio_data[: 10 * sample_rate]
            # 19-20秒: 無音
            # 20-29秒: 最初の9秒をコピー
            extended_audio[20 * sample_rate : 29 * sample_rate] = audio_data[: 9 * sample_rate]

        # 保存
        extended_path = os.path.join(self.temp_dir, "extended_audio.wav")
        sf.write(extended_path, extended_audio, sample_rate)

        # AudioSplitterで分割
        splitter = AudioSplitter(self.config)
        ranges = splitter.find_natural_split_points(
            extended_path, target_duration=15.0, min_silence_len=0.5, silence_thresh=-30  # 15秒チャンク
        )

        # 検証: 2つのチャンクに分割されるはず
        self.assertEqual(len(ranges), 2)

        # 各チャンクが1秒以上であることを確認
        for start, end in ranges:
            self.assertGreaterEqual(end - start, 1.0)

    def test_optimized_transcriber_with_audio_splitter(self):
        """OptimizedTranscriberとAudioSplitterの統合テスト"""
        from unittest.mock import Mock, patch

        # 10秒のテスト音声
        audio_path, _ = self.create_test_audio(duration_seconds=10)

        # 設定
        self.config.transcription.use_api = False
        transcriber = OptimizedTranscriber(self.config)

        # WhisperXのモック
        with (
            patch("whisperx.load_audio") as mock_load_audio,
            patch("whisperx.load_model") as mock_load_model,
            patch("whisperx.load_align_model") as mock_load_align,
            patch("whisperx.align") as mock_align,
        ):

            # 音声データを返す
            mock_load_audio.return_value = np.zeros(16000 * 10)

            # モデルのモック
            mock_model = Mock()
            mock_model.transcribe.return_value = {
                "segments": [
                    {"start": 0.0, "end": 5.0, "text": "最初の部分"},
                    {"start": 5.0, "end": 10.0, "text": "次の部分"},
                ]
            }
            mock_load_model.return_value = mock_model

            # アライメントモデルのモック
            mock_load_align.return_value = (Mock(), Mock())
            mock_align.return_value = {
                "segments": [
                    {"start": 0.0, "end": 5.0, "text": "最初の部分", "words": []},
                    {"start": 5.0, "end": 10.0, "text": "次の部分", "words": []},
                ]
            }

            # 実行
            result = transcriber.transcribe(audio_path, use_cache=False, save_cache=False)

            # 検証
            self.assertIsNotNone(result)
            self.assertEqual(len(result.segments), 2)
            self.assertEqual(result.segments[0].text, "最初の部分")
            self.assertEqual(result.segments[1].text, "次の部分")

    def test_api_mode_chunk_size_validation(self):
        """APIモードでのチャンクサイズ検証テスト"""
        # 2秒の短い音声を作成
        audio_path, _ = self.create_test_audio(duration_seconds=2)

        splitter = AudioSplitter(self.config)
        ranges = splitter.find_natural_split_points(
            audio_path, target_duration=5.0, min_silence_len=0.1  # 5秒チャンクを要求
        )

        # 検証: 1つのチャンクになるはず
        self.assertEqual(len(ranges), 1)
        self.assertEqual(ranges[0], (0.0, 2.0))

        # 各チャンクが1秒以上であることを確認
        for start, end in ranges:
            self.assertGreaterEqual(end - start, 1.0)

    def test_memory_cleanup_during_processing(self):
        """処理中のメモリクリーンアップテスト"""
        from unittest.mock import patch

        # メモリ使用量を記録
        gc_collect_calls = []

        def mock_collect(generation=2):
            gc_collect_calls.append(generation)
            return 0

        with patch("gc.collect", side_effect=mock_collect):
            # 10秒の音声
            audio_path, _ = self.create_test_audio(duration_seconds=10)

            # APIモードでテスト
            self.config.transcription.use_api = True
            self.config.transcription.api_key = "dummy-key"

            transcriber = OptimizedTranscriber(self.config)

            # _cleanup_memoryを直接呼び出してテスト
            transcriber._cleanup_memory(force=False)
            transcriber._cleanup_memory(force=True)

            # gc.collectが呼ばれたことを確認
            self.assertIn(1, gc_collect_calls)  # ソフトクリーンアップ
            self.assertIn(2, gc_collect_calls)  # 強制クリーンアップ


if __name__ == "__main__":
    unittest.main()
