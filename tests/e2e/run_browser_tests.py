"""
ブラウザE2Eテストの実行スクリプト

Playwrightのインストールと設定を含む
"""

import subprocess
import sys
from pathlib import Path


def setup_playwright():
    """Playwrightのセットアップ"""
    print("🎭 Playwrightをセットアップしています...")

    # Playwrightのインストール
    subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], check=True)

    # ブラウザのインストール
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("✅ Playwrightのセットアップが完了しました")


def run_tests():
    """E2Eテストを実行"""
    print("\n🧪 ブラウザE2Eテストを実行します...")

    # pytestでE2Eテストを実行
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/test_text_editor_browser.py",
            "-v",
            "--browser",
            "chromium",
            "--headed",  # ヘッドレスモードを無効化（ブラウザを表示）
            "-s",  # print文を表示
        ]
    )

    return result.returncode


def show_results():
    """テスト結果を表示"""
    screenshot_dir = Path("tests/e2e/screenshots")

    if screenshot_dir.exists():
        print("\n📸 保存されたスクリーンショット:")

        # 最新のテスト実行ディレクトリを取得
        run_dirs = sorted([d for d in screenshot_dir.iterdir() if d.is_dir()], reverse=True)

        if run_dirs:
            latest_dir = run_dirs[0]
            print(f"\n最新のテスト実行: {latest_dir.name}")

            screenshots = sorted(latest_dir.glob("*.png"))
            for screenshot in screenshots:
                print(f"  - {screenshot.name}")

            print(f"\n💾 スクリーンショットの保存場所: {latest_dir.absolute()}")
        else:
            print("スクリーンショットが見つかりません")


def main():
    """メイン処理"""
    print("🚀 TextffCut ブラウザE2Eテスト")
    print("=" * 50)

    # Playwrightのセットアップ
    try:
        setup_playwright()
    except Exception as e:
        print(f"❌ Playwrightのセットアップに失敗しました: {e}")
        return 1

    # テストの実行
    exit_code = run_tests()

    # 結果の表示
    show_results()

    if exit_code == 0:
        print("\n✅ すべてのテストが成功しました！")
    else:
        print("\n❌ テストが失敗しました")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
