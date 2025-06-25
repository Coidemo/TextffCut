"""
波形表示機能のテスト
"""

import unittest

import numpy as np

from core.waveform_processor import WaveformData, WaveformProcessor
from ui.waveform_display import WaveformDisplay


class TestWaveformProcessor(unittest.TestCase):
    """波形処理のテスト"""

    def setUp(self):
        self.processor = WaveformProcessor()

    def test_cache_key_generation(self):
        """キャッシュキー生成のテスト"""
        key1 = self.processor.get_cache_key("video1.mp4", "seg001")
        key2 = self.processor.get_cache_key("video1.mp4", "seg002")
        key3 = self.processor.get_cache_key("video2.mp4", "seg001")

        # 同じ動画・セグメントは同じキー
        self.assertEqual(key1, self.processor.get_cache_key("video1.mp4", "seg001"))

        # 異なるセグメントは異なるキー
        self.assertNotEqual(key1, key2)

        # 異なる動画は異なるキー
        self.assertNotEqual(key1, key3)

    def test_downsample_waveform(self):
        """ダウンサンプリングのテスト"""
        # テスト用の波形データ（10000サンプル）
        original = np.sin(np.linspace(0, 10 * np.pi, 10000))

        # 1000サンプルにダウンサンプリング
        downsampled = self.processor._downsample_waveform(original, 1000)

        self.assertEqual(len(downsampled), 1000)
        # ピークが保持されているか確認
        self.assertAlmostEqual(np.max(np.abs(downsampled)), 1.0, places=2)

    def test_silence_detection(self):
        """無音検出のテスト"""
        # テスト用波形データ（無音部分を含む）
        samples = [0.8, 0.9, 0.001, 0.0001, 0.0, 0.0, 0.7, 0.8]
        waveform_data = WaveformData(
            segment_id="test", sample_rate=44100, samples=samples, duration=1.0, start_time=0.0, end_time=1.0
        )

        silence_regions = self.processor.detect_silence_regions(waveform_data)

        # 無音領域が検出されることを確認
        self.assertGreater(len(silence_regions), 0)

        # 無音領域のインデックスが正しいか確認
        for start, end in silence_regions:
            self.assertGreaterEqual(start, 0)
            self.assertLess(end, len(samples))
            self.assertLess(start, end)


class TestWaveformDisplay(unittest.TestCase):
    """波形表示のテスト"""

    def setUp(self):
        self.display = WaveformDisplay()

    def test_empty_waveform_handling(self):
        """空の波形データの処理"""
        waveform_data = WaveformData(
            segment_id="empty", sample_rate=44100, samples=[], duration=0.0, start_time=0.0, end_time=0.0
        )

        # エラーが発生しないことを確認
        fig = self.display.render_waveform(waveform_data)
        self.assertIsNotNone(fig)

    def test_waveform_rendering(self):
        """波形描画のテスト"""
        # テスト用波形データ
        samples = list(np.sin(np.linspace(0, 4 * np.pi, 100)))
        waveform_data = WaveformData(
            segment_id="test", sample_rate=44100, samples=samples, duration=2.0, start_time=0.0, end_time=2.0
        )

        fig = self.display.render_waveform(waveform_data)

        # フィギュアが正しく生成されることを確認
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.data), 2)  # 正と負の2つのトレース

    def test_timeline_overview_rendering(self):
        """タイムライン概要表示のテスト"""
        segments = [
            WaveformData("seg1", 44100, [], 2.0, 0.0, 2.0),
            WaveformData("seg2", 44100, [], 3.0, 5.0, 8.0),
            WaveformData("seg3", 44100, [], 2.5, 10.0, 12.5),
        ]

        fig = self.display.render_timeline_overview(segments, 15.0)

        # フィギュアが正しく生成されることを確認
        self.assertIsNotNone(fig)
        # 3つのセグメントが表示されることを確認
        self.assertEqual(len(fig.layout.shapes), 3)


if __name__ == "__main__":
    unittest.main()
