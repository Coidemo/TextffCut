"""
ブラウザ操作の基底クラス
Puppeteer MCPを使用してブラウザを制御し、スクリーンショットを取得
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class BrowserTestBase:
    """ブラウザテストの基底クラス"""

    def __init__(self, config_path: str = None):
        """初期化

        Args:
            config_path: 設定ファイルのパス
        """
        # 設定読み込み
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "test_config.yaml"

        with open(config_path, encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

        # ディレクトリ設定
        self.test_dir = Path(__file__).parent.parent
        self.screenshot_dir = self.test_dir / "screenshots" / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

        # テスト結果
        self.results = {
            "start_time": datetime.now().isoformat(),
            "tests": [],
            "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
        }

        # Puppeteerの起動オプション
        self.launch_options = {
            "headless": self.config["environment"]["headless"],
            "args": ["--no-sandbox", "--disable-setuid-sandbox"],
        }

        self.base_url = self.config["environment"]["base_url"]
        self.timeout = self.config["environment"]["timeout"]

    def setup(self):
        """テストのセットアップ"""
        print("🚀 ブラウザテストを開始します")
        print(f"📸 スクリーンショット保存先: {self.screenshot_dir}")

        # 最初のページにアクセス
        self.navigate_to_home()

    def teardown(self):
        """テストのクリーンアップ"""
        # 結果を保存
        self.save_results()
        print("✅ テスト完了")
        print(f"📊 結果: {self.results['summary']}")

    def navigate_to_home(self):
        """ホームページにアクセス"""
        print(f"🌐 {self.base_url} にアクセス中...")
        # Puppeteer MCPを使用してナビゲート
        # 注: 実際のMCP呼び出しはテストランナーから行う

    def take_screenshot(self, name: str, description: str = ""):
        """スクリーンショットを撮影

        Args:
            name: スクリーンショット名
            description: 説明文
        """
        if not self.config["screenshots"]["enabled"]:
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.png"
        filepath = self.screenshot_dir / filename

        print(f"📸 スクリーンショット: {name}")

        # スクリーンショット情報を記録
        screenshot_info = {
            "name": name,
            "description": description,
            "filename": str(filepath),
            "timestamp": datetime.now().isoformat(),
        }

        return screenshot_info

    def wait_for_element(self, selector: str, timeout: int = 30):
        """要素が表示されるまで待機

        Args:
            selector: CSSセレクタ
            timeout: タイムアウト時間（秒）
        """
        print(f"⏳ 要素を待機中: {selector}")
        start_time = time.time()

        while time.time() - start_time < timeout:
            # 要素が存在するかチェック（実際の実装はMCP経由）
            time.sleep(0.5)

        raise TimeoutError(f"要素が見つかりません: {selector}")

    def click_element(self, selector: str, description: str = ""):
        """要素をクリック

        Args:
            selector: CSSセレクタ
            description: 操作の説明
        """
        print(f"🖱️ クリック: {description or selector}")

    def fill_input(self, selector: str, value: str, description: str = ""):
        """入力フィールドに値を入力

        Args:
            selector: CSSセレクタ
            value: 入力値
            description: 操作の説明
        """
        print(f"⌨️ 入力: {description or selector} = '{value}'")

    def add_test_result(self, name: str, status: str, details: dict[str, Any] = None):
        """テスト結果を追加

        Args:
            name: テスト名
            status: passed, failed, skipped
            details: 詳細情報
        """
        result = {"name": name, "status": status, "timestamp": datetime.now().isoformat(), "details": details or {}}

        self.results["tests"].append(result)
        self.results["summary"]["total"] += 1
        self.results["summary"][status] += 1

        # ステータスに応じたログ
        if status == "passed":
            print(f"✅ {name}")
        elif status == "failed":
            print(f"❌ {name}")
            if details and "error" in details:
                print(f"   エラー: {details['error']}")
        else:
            print(f"⏭️ {name} (スキップ)")

    def save_results(self):
        """テスト結果を保存"""
        self.results["end_time"] = datetime.now().isoformat()

        # JSON形式で保存
        report_path = self.test_dir / "reports" / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path.parent.mkdir(exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

        print(f"📄 レポート保存: {report_path}")

    def check_api_key(self) -> str | None:
        """APIキーの確認

        Returns:
            APIキー（設定されている場合）
        """
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key and self.config["api"]["api_key"]:
            api_key = os.path.expandvars(self.config["api"]["api_key"])

        if api_key and api_key.startswith("sk-"):
            return api_key
        return None
