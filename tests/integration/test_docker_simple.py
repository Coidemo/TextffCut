"""
Docker環境での簡易統合テスト（最適化機能）
"""

import json
import subprocess
import unittest


class TestDockerSimple(unittest.TestCase):
    """Docker環境での簡易テスト"""

    @classmethod
    def setUpClass(cls):
        """Dockerコンテナの起動確認"""
        result = subprocess.run(["docker", "ps", "--filter", "name=textffcut", "-q"], capture_output=True, text=True)

        if not result.stdout.strip():
            cls.skipTest("Dockerコンテナが起動していません")

    def extract_json(self, output):
        """出力からJSON部分を抽出"""
        # 最後の行がJSONの可能性が高い
        lines = output.strip().split("\n")
        for line in reversed(lines):
            if line.strip().startswith("{") and line.strip().endswith("}"):
                return line.strip()
        return None

    def test_memory_info(self):
        """メモリ情報取得"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            "import psutil; import json; mem=psutil.virtual_memory(); print(json.dumps({'total_gb': mem.total/(1024**3), 'percent': mem.percent}))",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        data = json.loads(result.stdout)
        self.assertGreater(data["total_gb"], 0)
        print(f"\n✅ メモリ情報: {data['total_gb']:.1f}GB, 使用率 {data['percent']:.1f}%")

    def test_auto_optimizer_models(self):
        """各モデルのAutoOptimizer初期化"""
        models = ["base", "small", "medium", "large", "large-v3"]

        for model in models:
            cmd = [
                "docker",
                "exec",
                "textffcut_app",
                "python",
                "-c",
                f"from core.auto_optimizer import AutoOptimizer; opt=AutoOptimizer('{model}'); print('{{\"model\":\"{model}\",\"chunk\":' + str(opt.current_params['chunk_seconds']) + '}}')",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)

            # JSON部分を抽出
            json_str = self.extract_json(result.stdout)
            self.assertIsNotNone(json_str, f"{model}のJSON出力が見つかりません")

            data = json.loads(json_str)
            self.assertEqual(data["model"], model)

            # large-v3は保守的な初期値
            if model == "large-v3":
                self.assertLessEqual(data["chunk"], 300)

            print(f"✅ {model}: chunk={data['chunk']}秒")

    def test_diagnostic_phase(self):
        """診断フェーズの基本動作"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
import sys
sys.stdout = sys.stderr  # ログを標準エラーに出力
from core.auto_optimizer import AutoOptimizer
opt = AutoOptimizer('medium')

# 診断フェーズ実行
for i in range(3):
    params = opt.get_optimal_params(50.0 + i * 2)

# 結果を標準出力に
import json
sys.stdout = sys.__stdout__
result = {
    'diagnostic_complete': not opt.diagnostic_mode,
    'chunk_seconds': opt.current_params['chunk_seconds']
}
print(json.dumps(result))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        data = json.loads(result.stdout.strip())
        self.assertTrue(data["diagnostic_complete"])
        self.assertGreater(data["chunk_seconds"], 30)

        print(f"\n✅ 診断フェーズ完了: chunk={data['chunk_seconds']}秒")

    def test_memory_monitor(self):
        """MemoryMonitorのDocker環境検出"""
        cmd = [
            "docker",
            "exec",
            "textffcut_app",
            "python",
            "-c",
            """
import sys
sys.stdout = sys.stderr
from core.memory_monitor import MemoryMonitor
monitor = MemoryMonitor()
sys.stdout = sys.__stdout__
import json
print(json.dumps({'is_docker': monitor.is_docker, 'memory_usage': monitor.get_memory_usage()}))
""",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        data = json.loads(result.stdout.strip())
        self.assertTrue(data["is_docker"])
        self.assertGreater(data["memory_usage"], 0)

        print(f"✅ Docker環境検出: {data['is_docker']}, メモリ使用率: {data['memory_usage']:.1f}%")

    def test_worker_transcribe_import(self):
        """worker_transcribe.pyのインポート確認"""
        cmd = ["docker", "exec", "textffcut_app", "python", "-c", "import worker_transcribe; print('OK')"]

        result = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK", result.stdout)

        print("✅ worker_transcribe.pyのインポート成功")


if __name__ == "__main__":
    print("\n🐳 Docker環境での簡易統合テスト")
    print("=" * 60)
    unittest.main(verbosity=2)
