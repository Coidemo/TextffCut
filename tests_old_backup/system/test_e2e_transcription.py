"""
エンドツーエンド（E2E）文字起こしテスト
実際の動画ファイルを使用したシステムテスト
"""

import os
import subprocess
import sys
import tempfile
import time
import unittest

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from core.transcription import Transcriber
from core.transcription_optimized import OptimizedTranscriber


class TestE2ETranscription(unittest.TestCase):
    """E2E文字起こしテスト"""

    @classmethod
    def setUpClass(cls):
        """テストクラスの初期設定"""
        cls.test_dir = tempfile.mkdtemp()
        cls.test_video_path = cls._create_test_video()

    @classmethod
    def tearDownClass(cls):
        """テストクラスのクリーンアップ"""
        import shutil

        shutil.rmtree(cls.test_dir, ignore_errors=True)

    @classmethod
    def _create_test_video(cls):
        """テスト用動画ファイルを作成（音声のみ）"""
        video_path = os.path.join(cls.test_dir, "test_video.mp4")

        # FFmpegで10秒のテスト動画を生成
        # 音声: 1秒のビープ音 + 1秒の無音を5回繰り返し
        cmd = [
            "ffmpeg",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1,aevalsrc=0:duration=1[s0];"
            "sine=frequency=440:duration=1,aevalsrc=0:duration=1[s1];"
            "sine=frequency=440:duration=1,aevalsrc=0:duration=1[s2];"
            "sine=frequency=440:duration=1,aevalsrc=0:duration=1[s3];"
            "sine=frequency=440:duration=1,aevalsrc=0:duration=1[s4];"
            "[s0][s1][s2][s3][s4]concat=n=5:v=0:a=1",
            "-ar",
            "16000",
            "-ac",
            "1",
            "-t",
            "10",
            "-y",
            video_path,
        ]

        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            # 簡易版: 10秒の無音動画
            cmd_simple = ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "10", "-y", video_path]
            subprocess.run(cmd_simple, capture_output=True)

        return video_path

    def setUp(self):
        """各テストの初期設定"""
        self.config = Config()
        self.config.transcription.use_api = False  # デフォルトはローカルモード

    def test_local_mode_basic(self):
        """ローカルモードの基本動作テスト"""
        # パフォーマンス測定用
        start_time = time.time()

        # OptimizedTranscriberを使用
        transcriber = OptimizedTranscriber(self.config)

        # 文字起こし実行
        result = transcriber.transcribe(self.test_video_path, model_size="base", use_cache=False, save_cache=False)

        # 処理時間
        elapsed_time = time.time() - start_time

        # 検証
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "ja")
        self.assertIsInstance(result.segments, list)

        # パフォーマンス情報を出力
        print(f"\n[ローカルモード] 処理時間: {elapsed_time:.2f}秒")
        print(f"セグメント数: {len(result.segments)}")

        # 10秒の動画なので、処理は30秒以内に完了すべき
        self.assertLess(elapsed_time, 30.0)

    def test_api_mode_basic(self):
        """APIモードの基本動作テスト（APIキーが設定されている場合のみ）"""
        # 環境変数からAPIキーを取得
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            self.skipTest("OPENAI_API_KEYが設定されていません")

        # API設定
        self.config.transcription.use_api = True
        self.config.transcription.api_key = api_key
        self.config.transcription.api_provider = "openai"

        # パフォーマンス測定用
        start_time = time.time()

        # OptimizedTranscriberを使用
        transcriber = OptimizedTranscriber(self.config)

        # 文字起こし実行
        result = transcriber.transcribe(self.test_video_path, model_size="whisper-1", use_cache=False, save_cache=False)

        # 処理時間
        elapsed_time = time.time() - start_time

        # 検証
        self.assertIsNotNone(result)
        self.assertEqual(result.language, "ja")
        self.assertIsInstance(result.segments, list)

        # パフォーマンス情報を出力
        print(f"\n[APIモード] 処理時間: {elapsed_time:.2f}秒")
        print(f"セグメント数: {len(result.segments)}")

        # APIモードは通常より高速
        self.assertLess(elapsed_time, 20.0)

    def test_performance_comparison(self):
        """最適化前後のパフォーマンス比較"""
        # 30秒の長めのテスト動画を作成
        long_video_path = os.path.join(self.test_dir, "long_test_video.mp4")
        cmd = ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "30", "-y", long_video_path]
        subprocess.run(cmd, capture_output=True, check=True)

        results = {}

        # 1. 従来のTranscriberでテスト
        print("\n[パフォーマンス比較テスト]")

        start_time = time.time()
        traditional_transcriber = Transcriber(self.config)
        traditional_result = traditional_transcriber.transcribe(
            long_video_path, model_size="base", use_cache=False, save_cache=False
        )
        traditional_time = time.time() - start_time
        results["traditional"] = {"time": traditional_time, "segments": len(traditional_result.segments)}

        # 2. OptimizedTranscriberでテスト
        start_time = time.time()
        optimized_transcriber = OptimizedTranscriber(self.config)
        optimized_result = optimized_transcriber.transcribe(
            long_video_path, model_size="base", use_cache=False, save_cache=False
        )
        optimized_time = time.time() - start_time
        results["optimized"] = {"time": optimized_time, "segments": len(optimized_result.segments)}

        # 結果を表示
        print(f"\n従来版: {traditional_time:.2f}秒 ({results['traditional']['segments']}セグメント)")
        print(f"最適化版: {optimized_time:.2f}秒 ({results['optimized']['segments']}セグメント)")
        print(f"改善率: {(traditional_time - optimized_time) / traditional_time * 100:.1f}%")

        # 最適化版の方が遅くなっていないことを確認
        # （初回実行時はモデルロードの影響で遅い場合があるため、1.2倍まで許容）
        self.assertLess(optimized_time, traditional_time * 1.2)

    def test_cache_functionality(self):
        """キャッシュ機能のテスト"""
        transcriber = OptimizedTranscriber(self.config)

        # 1回目: キャッシュに保存
        start_time = time.time()
        result1 = transcriber.transcribe(
            self.test_video_path,
            model_size="base",
            use_cache=False,  # キャッシュを使わない
            save_cache=True,  # キャッシュに保存
        )
        first_time = time.time() - start_time

        # 2回目: キャッシュから読み込み
        start_time = time.time()
        result2 = transcriber.transcribe(
            self.test_video_path, model_size="base", use_cache=True, save_cache=False  # キャッシュを使う
        )
        cache_time = time.time() - start_time

        # 検証
        self.assertEqual(len(result1.segments), len(result2.segments))
        self.assertLess(cache_time, first_time * 0.1)  # キャッシュは10倍以上高速

        print("\n[キャッシュテスト]")
        print(f"初回実行: {first_time:.2f}秒")
        print(f"キャッシュ読み込み: {cache_time:.2f}秒")
        print(f"高速化: {first_time / cache_time:.1f}倍")

    def test_error_handling(self):
        """エラーハンドリングのテスト"""
        transcriber = OptimizedTranscriber(self.config)

        # 存在しないファイル
        with self.assertRaises(Exception):
            transcriber.transcribe("/non/existent/file.mp4", use_cache=False)

        # 無効なAPIキー（APIモード）
        self.config.transcription.use_api = True
        self.config.transcription.api_key = "invalid-key"

        with self.assertRaises(Exception):
            transcriber.transcribe(self.test_video_path, use_cache=False)


if __name__ == "__main__":
    # 詳細な出力を有効化
    unittest.main(verbosity=2)
