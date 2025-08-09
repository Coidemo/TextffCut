import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import soundfile as sf

from core.waveform_processor import LIBROSA_AVAILABLE, ClipWaveformData, WaveformProcessor


# テスト用のダミー動画ファイルを作成するヘルパー関数
def create_dummy_audio_file(path: Path, sr=22050, duration=10, channels=1):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, float(duration), int(sr * duration))
    amplitude = np.iinfo(np.int16).max * 0.5
    data = amplitude * np.sin(2.0 * np.pi * 440.0 * t)
    sf.write(str(path), data.astype(np.int16), sr)


class TestWaveformProcessor(unittest.TestCase):

    def setUp(self):
        self.processor = WaveformProcessor()
        self.test_dir = Path("./test_output")
        self.test_dir.mkdir(exist_ok=True)
        self.dummy_video_path = self.test_dir / "dummy_audio.wav"
        create_dummy_audio_file(self.dummy_video_path, duration=20)

    def tearDown(self):
        import shutil

        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @unittest.skipIf(not LIBROSA_AVAILABLE, "librosa is not installed")
    def test_extract_waveforms_for_clips_success(self):
        """extract_waveforms_for_clipsが正常に動作するかのテスト"""
        time_ranges = [(1.0, 3.0), (5.5, 8.0), (10.0, 10.5)]
        samples_per_clip = 100

        result = self.processor.extract_waveforms_for_clips(str(self.dummy_video_path), time_ranges, samples_per_clip)

        self.assertIsNotNone(result)
        self.assertEqual(len(result), len(time_ranges))

        for i, clip_data in enumerate(result):
            self.assertIsInstance(clip_data, ClipWaveformData)
            self.assertEqual(clip_data.id, f"clip-{i}")
            self.assertAlmostEqual(clip_data.start_time, time_ranges[i][0], places=2)
            self.assertAlmostEqual(clip_data.end_time, time_ranges[i][1], places=2)
            self.assertEqual(len(clip_data.samples), samples_per_clip)
            self.assertTrue(all(-1.0 <= s <= 1.0 for s in clip_data.samples))

    @unittest.skipIf(not LIBROSA_AVAILABLE, "librosa is not installed")
    def test_extract_waveforms_empty_input(self):
        """空の入力に対する挙動のテスト"""
        result = self.processor.extract_waveforms_for_clips(str(self.dummy_video_path), [])
        self.assertEqual(result, [])

    @patch("core.waveform_processor.librosa.load")
    def test_librosa_error_handling(self, mock_librosa_load):
        """librosaでのエラーハンドリングのテスト"""
        mock_librosa_load.side_effect = Exception("Test librosa error")

        result = self.processor.extract_waveforms_for_clips(str(self.dummy_video_path), [(1.0, 2.0)])
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
