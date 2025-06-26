"""
パフォーマンスベンチマークテスト
実際の動画ファイルでのパフォーマンスを測定
"""

import json
import os
import sys
import time
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import Config
from core.transcription import Transcriber
from core.transcription_optimized import OptimizedTranscriber
from utils.logging import get_logger

logger = get_logger(__name__)


class PerformanceBenchmark:
    """パフォーマンスベンチマーククラス"""

    def __init__(self):
        self.config = Config()
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "system_info": self._get_system_info(),
            "benchmarks": [],
        }

    def _get_system_info(self):
        """システム情報を取得"""
        import platform

        import psutil

        return {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": psutil.cpu_count(),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
        }

    def run_benchmark(self, video_path: str, test_name: str):
        """ベンチマークを実行"""
        print(f"\n{'='*60}")
        print(f"ベンチマーク: {test_name}")
        print(f"動画ファイル: {video_path}")

        # 動画情報を取得
        from core.video import VideoInfo

        video_info = VideoInfo.from_file(video_path)
        print(f"動画時間: {video_info.duration:.1f}秒 ({video_info.duration/60:.1f}分)")
        print(f"{'='*60}")

        benchmark_result = {
            "test_name": test_name,
            "video_path": video_path,
            "video_duration_seconds": video_info.duration,
            "tests": [],
        }

        # 1. 従来版 (Transcriber) のテスト
        if video_info.duration <= 300:  # 5分以下の場合のみ従来版もテスト
            print("\n[1] 従来版 (Transcriber) のテスト")
            result = self._test_transcriber(Transcriber(self.config), video_path, "従来版")
            benchmark_result["tests"].append(result)
        else:
            print("\n[1] 従来版はスキップ（5分以上の動画のため）")

        # 2. 最適化版 (OptimizedTranscriber) のテスト - ローカルモード
        print("\n[2] 最適化版 (OptimizedTranscriber) - ローカルモード")
        self.config.transcription.use_api = False
        result = self._test_transcriber(OptimizedTranscriber(self.config), video_path, "最適化版（ローカル）")
        benchmark_result["tests"].append(result)

        # 3. 最適化版 (OptimizedTranscriber) - APIモード（APIキーがある場合）
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            print("\n[3] 最適化版 (OptimizedTranscriber) - APIモード")
            self.config.transcription.use_api = True
            self.config.transcription.api_key = api_key
            self.config.transcription.api_provider = "openai"

            result = self._test_transcriber(OptimizedTranscriber(self.config), video_path, "最適化版（API）")
            benchmark_result["tests"].append(result)

            # API料金の概算
            api_minutes = video_info.duration / 60
            api_cost = api_minutes * 0.006
            print(f"\nAPI料金概算: ${api_cost:.3f} (約{api_cost*150:.0f}円)")
        else:
            print("\n[3] APIモードはスキップ（OPENAI_API_KEYが未設定）")

        self.results["benchmarks"].append(benchmark_result)

        # 結果サマリーを表示
        self._print_summary(benchmark_result)

    def _test_transcriber(self, transcriber, video_path: str, label: str):
        """個別のトランスクライバーをテスト"""
        import gc

        import psutil

        # メモリ使用量（開始時）
        process = psutil.Process()
        memory_start = process.memory_info().rss / (1024**2)  # MB

        # プログレス表示用
        progress_info = {"last_update": time.time(), "last_progress": 0}

        def progress_callback(progress: float, status: str):
            current_time = time.time()
            # 1秒に1回または進捗が5%以上変化した場合のみ表示
            if current_time - progress_info["last_update"] > 1.0 or progress - progress_info["last_progress"] > 0.05:
                print(f"  [{label}] {progress*100:.1f}% - {status}")
                progress_info["last_update"] = current_time
                progress_info["last_progress"] = progress

        # 文字起こし実行
        start_time = time.time()
        try:
            result = transcriber.transcribe(
                video_path,
                model_size=(
                    "base"
                    if not hasattr(transcriber, "api_chunk_duration") or not transcriber.config.transcription.use_api
                    else "whisper-1"
                ),
                progress_callback=progress_callback,
                use_cache=False,
                save_cache=False,
            )
            success = True
            error_message = None
            segment_count = len(result.segments) if result else 0

        except Exception as e:
            success = False
            error_message = str(e)
            segment_count = 0
            logger.error(f"{label}でエラー: {e}")

        elapsed_time = time.time() - start_time

        # メモリ使用量（終了時）
        memory_end = process.memory_info().rss / (1024**2)  # MB
        memory_used = memory_end - memory_start

        # ガベージコレクション
        gc.collect()

        # 結果を記録
        test_result = {
            "label": label,
            "success": success,
            "elapsed_seconds": elapsed_time,
            "segments": segment_count,
            "memory_used_mb": memory_used,
            "error": error_message,
        }

        # 結果を表示
        if success:
            print("\n  ✅ 成功")
            print(f"  処理時間: {elapsed_time:.2f}秒")
            print(f"  セグメント数: {segment_count}")
            print(f"  メモリ使用量: {memory_used:.1f}MB")
        else:
            print(f"\n  ❌ 失敗: {error_message}")

        return test_result

    def _print_summary(self, benchmark_result):
        """ベンチマーク結果のサマリーを表示"""
        print(f"\n{'='*60}")
        print("📊 ベンチマーク結果サマリー")
        print(f"{'='*60}")

        video_duration = benchmark_result["video_duration_seconds"]
        print(f"動画時間: {video_duration:.1f}秒 ({video_duration/60:.1f}分)")
        print("")

        # 各テストの結果を表示
        for test in benchmark_result["tests"]:
            if test["success"]:
                speed_ratio = video_duration / test["elapsed_seconds"]
                print(f"{test['label']:20} : {test['elapsed_seconds']:6.1f}秒 (x{speed_ratio:.1f}速)")
            else:
                print(f"{test['label']:20} : エラー")

        # パフォーマンス比較（最適化版がある場合）
        traditional = next((t for t in benchmark_result["tests"] if "従来版" in t["label"]), None)
        optimized_local = next((t for t in benchmark_result["tests"] if "最適化版（ローカル）" in t["label"]), None)
        optimized_api = next((t for t in benchmark_result["tests"] if "最適化版（API）" in t["label"]), None)

        if traditional and optimized_local and traditional["success"] and optimized_local["success"]:
            improvement = (
                (traditional["elapsed_seconds"] - optimized_local["elapsed_seconds"])
                / traditional["elapsed_seconds"]
                * 100
            )
            print(f"\n最適化による改善率（ローカル）: {improvement:.1f}%")

        if optimized_local and optimized_api and optimized_local["success"] and optimized_api["success"]:
            api_speedup = optimized_local["elapsed_seconds"] / optimized_api["elapsed_seconds"]
            print(f"API使用による高速化: x{api_speedup:.1f}")

    def save_results(self, output_path: str = "benchmark_results.json"):
        """結果をJSONファイルに保存"""
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"\n📁 結果を保存しました: {output_path}")


def main():
    """メイン実行関数"""
    import argparse

    parser = argparse.ArgumentParser(description="TextffCut パフォーマンスベンチマーク")
    parser.add_argument("video_path", help="テストする動画ファイルのパス")
    parser.add_argument("--name", default="ベンチマークテスト", help="テスト名")
    parser.add_argument("--output", default="benchmark_results.json", help="結果の出力先")

    args = parser.parse_args()

    # ファイルの存在確認
    if not os.path.exists(args.video_path):
        print(f"エラー: 動画ファイルが見つかりません: {args.video_path}")
        sys.exit(1)

    # ベンチマーク実行
    benchmark = PerformanceBenchmark()
    benchmark.run_benchmark(args.video_path, args.name)
    benchmark.save_results(args.output)


if __name__ == "__main__":
    # テスト実行時
    if len(sys.argv) > 1:
        main()
    else:
        # 引数なしで実行された場合は使用方法を表示
        print("使用方法:")
        print("  python test_performance_benchmark.py <動画ファイルパス> [--name テスト名] [--output 出力ファイル]")
        print("")
        print("例:")
        print("  python test_performance_benchmark.py /path/to/video.mp4 --name '60分動画テスト'")
        print("")
        print("環境変数:")
        print("  OPENAI_API_KEY : OpenAI APIキー（APIモードのテスト用）")
