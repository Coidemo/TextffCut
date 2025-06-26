"""
Docker環境での自動最適化機能の統合テスト
"""

import json
import os
import subprocess
import sys
import unittest

# プロジェクトのルートをPythonパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestDockerOptimization(unittest.TestCase):
    """Docker環境での最適化機能テスト"""

    @classmethod
    def setUpClass(cls):
        """テストクラスの初期設定"""
        # Dockerコンテナが起動しているか確認
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=textffcut", "--format", "json"], capture_output=True, text=True
        )

        if result.returncode != 0 or not result.stdout.strip():
            cls.skipTest("Dockerコンテナが起動していません")

    def test_docker_container_memory_info(self):
        """Docker内でのメモリ情報取得テスト"""
        # Docker内でメモリ情報を取得するPythonスクリプトを実行
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
import psutil
import json
mem = psutil.virtual_memory()
info = {
    'total_gb': mem.total / (1024**3),
    'available_gb': mem.available / (1024**3),
    'percent': mem.percent
}
print(json.dumps(info))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"エラー: {result.stderr}")

        # メモリ情報を解析
        mem_info = json.loads(result.stdout)

        # 検証
        self.assertGreater(mem_info["total_gb"], 0)
        self.assertGreater(mem_info["available_gb"], 0)
        self.assertGreaterEqual(mem_info["percent"], 0)
        self.assertLessEqual(mem_info["percent"], 100)

        print("\nDocker環境のメモリ情報:")
        print(f"  総メモリ: {mem_info['total_gb']:.1f}GB")
        print(f"  利用可能: {mem_info['available_gb']:.1f}GB")
        print(f"  使用率: {mem_info['percent']:.1f}%")

    def test_auto_optimizer_initialization(self):
        """Docker内でのAutoOptimizer初期化テスト"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
from core.auto_optimizer import AutoOptimizer
import json

# 各モデルサイズで初期化をテスト
models = ['base', 'small', 'medium', 'large', 'large-v3']
results = {}

for model in models:
    try:
        optimizer = AutoOptimizer(model)
        results[model] = {
            'success': True,
            'initial_chunk': optimizer.current_params['chunk_seconds'],
            'initial_workers': optimizer.current_params['max_workers'],
            'initial_batch': optimizer.current_params['batch_size']
        }
    except Exception as e:
        results[model] = {'success': False, 'error': str(e)}

print(json.dumps(results, indent=2))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("コマンド実行エラー:")
            print(f"  標準出力: {result.stdout}")
            print(f"  標準エラー: {result.stderr}")
        self.assertEqual(result.returncode, 0, f"エラー: {result.stderr}")

        # 結果を解析
        if not result.stdout.strip():
            self.fail(f"出力が空です。stderr: {result.stderr}")
        results = json.loads(result.stdout)

        # 全モデルで初期化が成功していることを確認
        for model, info in results.items():
            self.assertTrue(info["success"], f"{model}の初期化に失敗: {info.get('error')}")

            # large-v3の初期パラメータが保守的であることを確認
            if model == "large-v3":
                self.assertLessEqual(info["initial_chunk"], 300)  # 5分以下
                self.assertEqual(info["initial_workers"], 1)
                self.assertLessEqual(info["initial_batch"], 2)

        print("\nモデル別初期パラメータ:")
        for model, info in results.items():
            if info["success"]:
                print(
                    f"  {model}: chunk={info['initial_chunk']}秒, "
                    f"workers={info['initial_workers']}, batch={info['initial_batch']}"
                )

    def test_diagnostic_phase_execution(self):
        """Docker内での診断フェーズ実行テスト"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
from core.auto_optimizer import AutoOptimizer
import json

# 診断フェーズをテスト
optimizer = AutoOptimizer('medium')

# 診断フェーズの実行
diagnostic_results = []
memory_values = [50.0, 52.0, 54.0]  # メモリが徐々に増加

for i, memory in enumerate(memory_values):
    params = optimizer.get_optimal_params(memory)
    diagnostic_results.append({
        'chunk': i + 1,
        'memory': memory,
        'diagnostic_mode': optimizer.diagnostic_mode,
        'chunk_seconds': params['chunk_seconds'],
        'diagnostic_chunks_processed': optimizer.diagnostic_chunks_processed
    })

# 診断完了後の状態
final_state = {
    'diagnostic_complete': not optimizer.diagnostic_mode,
    'memory_growth_rate': optimizer.diagnostic_data['memory_growth_rate'],
    'final_chunk_seconds': optimizer.current_params['chunk_seconds']
}

result = {
    'diagnostic_progress': diagnostic_results,
    'final_state': final_state
}

print(json.dumps(result, indent=2))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("コマンド実行エラー:")
            print(f"  標準出力: {result.stdout}")
            print(f"  標準エラー: {result.stderr}")
        self.assertEqual(result.returncode, 0, f"エラー: {result.stderr}")

        # 結果を解析
        if not result.stdout.strip():
            self.fail(f"出力が空です。stderr: {result.stderr}")
        data = json.loads(result.stdout)

        # 診断フェーズの進行を確認
        progress = data["diagnostic_progress"]
        self.assertEqual(len(progress), 3)

        # 最初の2チャンクは診断モード
        for i in range(2):
            self.assertTrue(progress[i]["diagnostic_mode"])
            self.assertEqual(progress[i]["chunk_seconds"], 30)  # 診断チャンクは30秒

        # 3チャンク目で診断完了
        self.assertFalse(progress[2]["diagnostic_mode"])

        # 最終状態を確認
        final = data["final_state"]
        self.assertTrue(final["diagnostic_complete"])
        self.assertGreater(final["memory_growth_rate"], 0)
        self.assertGreater(final["final_chunk_seconds"], 30)

        print("\n診断フェーズの実行結果:")
        print(f"  メモリ増加率: {final['memory_growth_rate']:.2f}%/チャンク")
        print(f"  最適化後のチャンクサイズ: {final['final_chunk_seconds']}秒")

    def test_memory_monitor_in_docker(self):
        """Docker内でのMemoryMonitor動作テスト"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
from core.memory_monitor import MemoryMonitor
import psutil
import json

monitor = MemoryMonitor()

# Docker環境の検出
is_docker = monitor.is_docker

# メモリ使用率の取得
memory_usage = monitor.get_memory_usage()

# 利用可能メモリの取得（psutil経由）
mem = psutil.virtual_memory()
available_gb = mem.available / (1024**3)

result = {
    'is_docker': is_docker,
    'memory_usage_percent': memory_usage,
    'available_gb': available_gb
}

print(json.dumps(result))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"標準エラー出力: {result.stderr}")
        self.assertEqual(result.returncode, 0, f"エラー: {result.stderr}")

        # 結果を解析
        data = json.loads(result.stdout)

        # Docker環境として認識されていることを確認
        self.assertTrue(data["is_docker"])

        # メモリ情報が正常に取得できていることを確認
        self.assertGreater(data["memory_usage_percent"], 0)
        self.assertLess(data["memory_usage_percent"], 100)
        self.assertGreater(data["available_gb"], 0)

        print("\nDocker内でのMemoryMonitor:")
        print(f"  Docker環境検出: {data['is_docker']}")
        print(f"  メモリ使用率: {data['memory_usage_percent']:.1f}%")
        print(f"  利用可能メモリ: {data['available_gb']:.1f}GB")

    def test_profile_persistence_in_docker(self):
        """Docker内でのプロファイル永続化テスト"""
        # プロファイルの保存
        cmd_save = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
from core.auto_optimizer import AutoOptimizer
import json

optimizer = AutoOptimizer('small')

# テスト用のパラメータとメトリクス
test_params = {
    'chunk_seconds': 999,
    'max_workers': 3,
    'batch_size': 16,
    'align_chunk_seconds': 1200
}

test_metrics = {
    'completed': True,
    'avg_memory': 60.0,
    'processing_time': 300.0,
    'segments_count': 50,
    'successful_runs': 1
}

# プロファイルを保存
optimizer.save_successful_run(test_params, test_metrics)

print(json.dumps({'saved': True}))
""",
        ]

        result = subprocess.run(cmd_save, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        # プロファイルの読み込み
        cmd_load = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
from core.auto_optimizer import AutoOptimizer
import json

# 新しいインスタンスで読み込み
optimizer = AutoOptimizer('small')

# 保存されたパラメータが読み込まれているか確認
result = {
    'chunk_seconds': optimizer.current_params['chunk_seconds'],
    'max_workers': optimizer.current_params['max_workers'],
    'batch_size': optimizer.current_params['batch_size']
}

print(json.dumps(result))
""",
        ]

        result = subprocess.run(cmd_load, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        # 結果を確認
        data = json.loads(result.stdout)
        self.assertEqual(data["chunk_seconds"], 999)
        self.assertEqual(data["max_workers"], 3)
        self.assertEqual(data["batch_size"], 16)

        print("\nプロファイル永続化テスト:")
        print("  ✅ プロファイルの保存と読み込みが正常に動作")

    def test_large_v3_memory_warning(self):
        """large-v3選択時のメモリ警告テスト"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
import psutil
from core.auto_optimizer import AutoOptimizer
import json

# 現在のメモリ状況
mem = psutil.virtual_memory()
available_gb = mem.available / (1024**3)

# large-v3での初期化
optimizer = AutoOptimizer('large-v3')

# 低メモリ環境での警告判定
should_warn = available_gb < 8

result = {
    'available_gb': available_gb,
    'should_warn': should_warn,
    'initial_chunk': optimizer.current_params['chunk_seconds'],
    'initial_batch': optimizer.current_params['batch_size']
}

print(json.dumps(result))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        data = json.loads(result.stdout)

        # large-v3の保守的なパラメータを確認
        self.assertLessEqual(data["initial_chunk"], 300)
        self.assertLessEqual(data["initial_batch"], 2)

        print("\nlarge-v3メモリチェック:")
        print(f"  利用可能メモリ: {data['available_gb']:.1f}GB")
        print(f"  警告が必要: {data['should_warn']}")
        print(f"  初期チャンクサイズ: {data['initial_chunk']}秒")
        print(f"  初期バッチサイズ: {data['initial_batch']}")


if __name__ == "__main__":
    # Dockerコンテナが起動していることを前提とする
    print("\n🐳 Docker環境での自動最適化機能テスト")
    print("=" * 60)
    unittest.main(verbosity=2)
