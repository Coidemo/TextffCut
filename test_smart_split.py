"""
SmartSplitTranscriberのテストケース
"""
import unittest
import tempfile
import os
import sys
from pathlib import Path
import shutil
import numpy as np

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.transcription_smart_split import SmartSplitTranscriber
from core.video import SilenceInfo
from utils.logging import get_logger

logger = get_logger(__name__)


class TestSmartSplitTranscriber(unittest.TestCase):
    """SmartSplitTranscriberのテストクラス"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = Config()
        self.transcriber = SmartSplitTranscriber(self.config)
        self.test_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """テストのクリーンアップ"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_calculate_split_points_short_video(self):
        """短い動画の分割点計算テスト"""
        # 20分の動画（分割不要）
        duration = 20 * 60
        silence_regions = []
        
        splits = self.transcriber._calculate_split_points(duration, silence_regions)
        
        # 分割されないことを確認
        self.assertEqual(len(splits), 1)
        self.assertEqual(splits[0], (0, duration))
    
    def test_calculate_split_points_medium_video(self):
        """中程度の動画の分割点計算テスト"""
        # 45分の動画（2分割想定）
        duration = 45 * 60
        
        # 22分付近に無音を配置
        silence_regions = [
            SilenceInfo(start=20*60, end=22*60),
            SilenceInfo(start=23*60, end=24*60),
        ]
        
        splits = self.transcriber._calculate_split_points(duration, silence_regions)
        
        # 2分割されることを確認
        self.assertEqual(len(splits), 2)
        
        # 最初の分割点が20-24分の間にあることを確認
        self.assertGreater(splits[0][1], 20*60)
        self.assertLess(splits[0][1], 24*60)
    
    def test_calculate_split_points_long_video(self):
        """長い動画の分割点計算テスト"""
        # 90分の動画（3-4分割想定）
        duration = 90 * 60
        
        # 20分ごとに無音を配置
        silence_regions = [
            SilenceInfo(start=19*60, end=20*60),
            SilenceInfo(start=39*60, end=40*60),
            SilenceInfo(start=59*60, end=60*60),
            SilenceInfo(start=79*60, end=80*60),
        ]
        
        splits = self.transcriber._calculate_split_points(duration, silence_regions)
        
        # 3-5分割されることを確認
        self.assertGreaterEqual(len(splits), 3)
        self.assertLessEqual(len(splits), 5)
        
        # 各セグメントが15-25分の範囲内であることを確認
        for start, end in splits:
            segment_duration = end - start
            self.assertGreaterEqual(segment_duration, 15*60)
            self.assertLessEqual(segment_duration, 25*60)
    
    def test_find_best_silence(self):
        """最適な無音検出テスト"""
        # 複数の無音候補
        silence_regions = [
            SilenceInfo(start=18*60, end=18.5*60),  # 18-18.5分
            SilenceInfo(start=19.5*60, end=20*60),  # 19.5-20分（最適）
            SilenceInfo(start=21*60, end=21.5*60),  # 21-21.5分
        ]
        
        # 20分を目標に検索（±3分）
        target = 20 * 60
        best = self.transcriber._find_best_silence(silence_regions, target, search_window=3*60)
        
        # 19.75分（19.5-20分の中心）が選ばれることを確認
        self.assertIsNotNone(best)
        self.assertAlmostEqual(best, 19.75*60, places=0)
    
    def test_api_mode_optimization(self):
        """APIモードの最適化テスト"""
        # APIモードを有効化
        self.config.transcription.use_api = True
        self.config.transcription.api_key = "test_key"
        
        # チャンクサイズが変更されることを確認
        original_chunk_seconds = self.config.transcription.chunk_seconds
        self.assertEqual(original_chunk_seconds, 30)  # デフォルトは30秒
        
        # TODO: APIモードのテストは実際のAPIを呼び出さないようにモックが必要
    
    def test_batch_size_selection(self):
        """バッチサイズ選択テスト"""
        # GPU環境をシミュレート
        self.transcriber.device = "cuda"
        
        # メモリに応じたバッチサイズを確認
        batch_size = self.transcriber._get_optimal_batch_size()
        self.assertIn(batch_size, [8, 16, 32])
        
        # CPU環境をシミュレート
        self.transcriber.device = "cpu"
        batch_size = self.transcriber._get_optimal_batch_size()
        self.assertEqual(batch_size, 4)


class TestIntegration(unittest.TestCase):
    """統合テスト"""
    
    def setUp(self):
        """テストのセットアップ"""
        self.config = Config()
        self.test_dir = Path(tempfile.mkdtemp())
        
    def tearDown(self):
        """テストのクリーンアップ"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
    
    def test_import_in_main(self):
        """main.pyでのインポートテスト"""
        try:
            from main import SmartSplitTranscriber
            # インポートが成功すればOK
            self.assertTrue(True)
        except ImportError as e:
            self.fail(f"SmartSplitTranscriberのインポートに失敗: {e}")
    
    def test_cache_separation(self):
        """キャッシュの分離テスト"""
        transcriber = SmartSplitTranscriber(self.config)
        
        # テスト用の動画パスを作成
        video_path = self.test_dir / "test_video.mp4"
        video_path.touch()  # ダミーファイルを作成
        
        # 通常のキャッシュパス
        normal_cache = transcriber.get_cache_path(str(video_path), "base")
        
        # スマート分割のキャッシュパス
        smart_cache = transcriber.get_cache_path(str(video_path), "base_smart")
        
        # パスが異なることを確認
        self.assertNotEqual(normal_cache, smart_cache)
        
        # ファイル名を確認
        self.assertEqual(normal_cache.name, "base.json")
        self.assertEqual(smart_cache.name, "base_smart.json")


if __name__ == "__main__":
    # ログレベルを設定
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # テストを実行
    unittest.main(verbosity=2)