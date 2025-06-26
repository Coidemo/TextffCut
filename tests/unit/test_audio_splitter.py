"""
AudioSplitterの単体テスト
"""

import os
import sys
import unittest
from unittest.mock import Mock, patch

import numpy as np

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.audio_splitter import AudioSplitter
from core.video import SilenceInfo


class TestAudioSplitter(unittest.TestCase):
    """AudioSplitterのテストクラス"""

    def setUp(self):
        """テストの初期設定"""
        self.config = Mock()
        self.splitter = AudioSplitter(self.config)

    def test_calculate_split_points_basic(self):
        """基本的な分割ポイント計算のテスト"""
        # 無音情報のモック（5分ごとに10秒の無音）
        silences = [
            SilenceInfo(start=295, end=305),  # 5分前後
            SilenceInfo(start=595, end=605),  # 10分前後
            SilenceInfo(start=895, end=905),  # 15分前後
        ]

        total_duration = 1200  # 20分
        target_duration = 300  # 5分

        # 分割ポイントを計算
        points = self.splitter._calculate_split_points(silences, total_duration, target_duration)

        # 検証
        self.assertEqual(points[0], 0.0)  # 開始点
        self.assertEqual(points[-1], 1200.0)  # 終了点

        # 各分割ポイントが無音の中央付近にあることを確認
        self.assertAlmostEqual(points[1], 300.0, delta=10)
        self.assertAlmostEqual(points[2], 600.0, delta=10)
        self.assertAlmostEqual(points[3], 900.0, delta=10)

    def test_calculate_split_points_min_chunk_duration(self):
        """最小チャンク時間の保証テスト"""
        # 最後に短い無音がある場合
        silences = [
            SilenceInfo(start=295, end=305),
            SilenceInfo(start=599, end=600),  # 600秒（10分）の位置に短い無音
        ]

        total_duration = 600.5  # 10分0.5秒
        target_duration = 300  # 5分

        points = self.splitter._calculate_split_points(silences, total_duration, target_duration)

        # 1秒未満のチャンクが作られないことを確認
        for i in range(len(points) - 1):
            chunk_duration = points[i + 1] - points[i]
            self.assertGreaterEqual(chunk_duration, 1.0)

    def test_calculate_split_points_no_silence(self):
        """無音がない場合の分割テスト"""
        silences = []
        total_duration = 1200  # 20分
        target_duration = 300  # 5分

        points = self.splitter._calculate_split_points(silences, total_duration, target_duration)

        # 機械的に5分ごとに分割されることを確認
        expected_points = [0.0, 300.0, 600.0, 900.0, 1200.0]
        self.assertEqual(points, expected_points)

    def test_calculate_split_points_edge_case(self):
        """エッジケースのテスト"""
        # 短い音声（1分）
        silences = []
        total_duration = 60  # 1分
        target_duration = 300  # 5分

        points = self.splitter._calculate_split_points(silences, total_duration, target_duration)

        # 全体が1つのチャンクになることを確認
        self.assertEqual(points, [0.0, 60.0])

    @patch("subprocess.run")
    @patch("core.video.VideoInfo")
    def test_find_natural_split_points(self, mock_video_info, mock_run):
        """find_natural_split_pointsメソッドのテスト"""
        # VideoInfoのモック
        mock_video_info.from_file.return_value.duration = 600.0

        # FFmpegのモック
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        # detect_silence_from_wavのモック
        self.splitter.video_processor.detect_silence_from_wav = Mock(
            return_value=[
                SilenceInfo(start=295, end=305),
                SilenceInfo(start=595, end=605),
            ]
        )

        # テスト実行
        ranges = self.splitter.find_natural_split_points("test.mp4", target_duration=300.0)

        # 検証
        self.assertEqual(len(ranges), 2)  # 2つのチャンク
        self.assertEqual(ranges[0][0], 0.0)  # 最初のチャンクの開始
        self.assertAlmostEqual(ranges[0][1], 300.0, delta=10)  # 最初のチャンクの終了
        self.assertAlmostEqual(ranges[1][0], 300.0, delta=10)  # 2番目のチャンクの開始
        self.assertEqual(ranges[1][1], 600.0)  # 2番目のチャンクの終了

    def test_split_audio_array_basic(self):
        """split_audio_arrayメソッドの基本テスト"""
        # 10秒の音声データをモック
        sample_rate = 16000
        duration = 10.0
        audio = np.zeros(int(sample_rate * duration))

        # find_natural_split_pointsのモック
        self.splitter.find_natural_split_points = Mock(return_value=[(0.0, 5.0), (5.0, 10.0)])

        # テスト実行
        chunks = self.splitter.split_audio_array(audio, sample_rate, target_duration=5.0)

        # 検証
        self.assertEqual(len(chunks), 2)

        # 各チャンクの検証
        chunk1_audio, start1, end1 = chunks[0]
        self.assertEqual(start1, 0.0)
        self.assertEqual(end1, 5.0)
        self.assertEqual(len(chunk1_audio), int(sample_rate * 5))

        chunk2_audio, start2, end2 = chunks[1]
        self.assertEqual(start2, 5.0)
        self.assertEqual(end2, 10.0)
        self.assertEqual(len(chunk2_audio), int(sample_rate * 5))


if __name__ == "__main__":
    unittest.main()
