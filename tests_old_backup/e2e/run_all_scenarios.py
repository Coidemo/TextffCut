"""
すべてのユーザーシナリオテストを実行

完全に網羅的なE2Eテストを実行し、詳細なレポートを生成します。
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_all_scenario_tests():
    """すべてのシナリオテストを実行"""
    print("🧪 すべてのユーザーシナリオテストを実行します...")
    print("=" * 60)

    # pytestでE2Eテストを実行
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/e2e/test_all_user_scenarios.py",
            "-v",
            "--browser",
            "chromium",
            "--headed",  # ブラウザを表示
            "-s",  # print文を表示
            "--tb=short",  # エラー時のトレースバックを短く
            "-x",  # 最初のエラーで停止（デバッグ用）
        ]
    )

    return result.returncode


def generate_comprehensive_report():
    """包括的なテストレポートを生成"""
    screenshot_dir = Path("tests/e2e/screenshots/all_scenarios")

    if not screenshot_dir.exists():
        print("スクリーンショットディレクトリが見つかりません")
        return

    # 最新のテスト実行ディレクトリを取得
    run_dirs = sorted([d for d in screenshot_dir.iterdir() if d.is_dir()], reverse=True)

    if not run_dirs:
        print("テスト実行結果が見つかりません")
        return

    latest_dir = run_dirs[0]
    screenshots = sorted(latest_dir.glob("*.png"))

    # HTMLレポートを生成
    report_path = latest_dir / "TEST_REPORT.html"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(
            """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>TextffCut E2E Test Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f4f4f4;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .header {
            background-color: #3498db;
            color: white;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .scenario {
            background-color: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .screenshot {
            margin: 10px 0;
            text-align: center;
        }
        .screenshot img {
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .screenshot-title {
            font-weight: bold;
            margin: 10px 0 5px 0;
            color: #2c3e50;
        }
        .stats {
            display: flex;
            justify-content: space-around;
            margin: 20px 0;
        }
        .stat-box {
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
        }
        .stat-number {
            font-size: 2em;
            font-weight: bold;
            color: #3498db;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🧪 TextffCut E2E テストレポート</h1>
        <p>実行日時: """
            + datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")
            + """</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <div class="stat-number">"""
            + str(len(screenshots))
            + """</div>
            <div>スクリーンショット数</div>
        </div>
        <div class="stat-box">
            <div class="stat-number">8</div>
            <div>テストシナリオ数</div>
        </div>
    </div>
"""
        )

        # シナリオごとにグループ化
        current_scenario = None
        scenario_screenshots = []

        for screenshot in screenshots:
            # ファイル名からシナリオを判定
            parts = screenshot.stem.split("_")
            if len(parts) > 1:
                scenario_num = int(parts[0])
                scenario_name = get_scenario_name(scenario_num)

                if scenario_name != current_scenario:
                    # 前のシナリオを出力
                    if current_scenario and scenario_screenshots:
                        f.write('<div class="scenario">\n')
                        f.write(f"<h2>{current_scenario}</h2>\n")
                        for ss in scenario_screenshots:
                            f.write('<div class="screenshot">\n')
                            f.write(f'<div class="screenshot-title">{ss.stem}</div>\n')
                            f.write(f'<img src="{ss.name}" alt="{ss.stem}">\n')
                            f.write("</div>\n")
                        f.write("</div>\n")

                    current_scenario = scenario_name
                    scenario_screenshots = [screenshot]
                else:
                    scenario_screenshots.append(screenshot)

        # 最後のシナリオを出力
        if current_scenario and scenario_screenshots:
            f.write('<div class="scenario">\n')
            f.write(f"<h2>{current_scenario}</h2>\n")
            for ss in scenario_screenshots:
                f.write('<div class="screenshot">\n')
                f.write(f'<div class="screenshot-title">{ss.stem}</div>\n')
                f.write(f'<img src="{ss.name}" alt="{ss.stem}">\n')
                f.write("</div>\n")
            f.write("</div>\n")

        f.write(
            """
</body>
</html>
"""
        )

    print(f"\n📝 HTMLレポートを生成しました: {report_path}")
    print(f"💾 スクリーンショットの保存場所: {latest_dir.absolute()}")

    # Markdownレポートも生成
    generate_markdown_report(latest_dir, screenshots)


def get_scenario_name(num):
    """シナリオ番号から名前を取得"""
    scenarios = {
        1: "シナリオ1: 基本的なワークフロー",
        2: "シナリオ2: APIモードでの操作",
        3: "シナリオ3: テキスト編集の詳細操作",
        4: "シナリオ4: タイムライン編集",
        5: "シナリオ5: エクスポート設定",
        6: "シナリオ6: エラーハンドリング",
        7: "シナリオ7: サイドバーの全機能",
        8: "シナリオ8: レスポンシブデザイン",
    }
    return scenarios.get(num // 100 + 1, f"シナリオ{num // 100 + 1}")


def generate_markdown_report(test_dir, screenshots):
    """Markdownレポートを生成"""
    report_path = test_dir / "TEST_REPORT.md"

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# TextffCut E2E テストレポート\n\n")
        f.write(f"実行日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}\n\n")
        f.write("## 📊 テスト結果サマリー\n\n")
        f.write(f"- **スクリーンショット総数**: {len(screenshots)}\n")
        f.write("- **テストシナリオ数**: 8\n")
        f.write("- **実行環境**: Chromium Browser\n\n")

        f.write("## 📸 スクリーンショット一覧\n\n")

        for i, screenshot in enumerate(screenshots, 1):
            f.write(f"{i}. [{screenshot.name}]({screenshot.name})\n")

        f.write("\n## 🔍 テストシナリオ詳細\n\n")
        f.write("1. **基本的なワークフロー**: アプリケーションの基本操作\n")
        f.write("2. **APIモードでの操作**: API設定と関連機能\n")
        f.write("3. **テキスト編集の詳細操作**: 編集機能と境界調整\n")
        f.write("4. **タイムライン編集**: タイムライン調整機能\n")
        f.write("5. **エクスポート設定**: 出力形式と設定\n")
        f.write("6. **エラーハンドリング**: エラー状態の確認\n")
        f.write("7. **サイドバーの全機能**: 各種設定タブ\n")
        f.write("8. **レスポンシブデザイン**: 様々な画面サイズ\n")

    print(f"📝 Markdownレポートを生成しました: {report_path}")


def show_summary():
    """テスト結果のサマリーを表示"""
    screenshot_dir = Path("tests/e2e/screenshots/all_scenarios")

    if screenshot_dir.exists():
        print("\n📊 テスト実行サマリー:")
        print("=" * 60)

        # すべてのテスト実行を表示
        run_dirs = sorted([d for d in screenshot_dir.iterdir() if d.is_dir()], reverse=True)

        for i, run_dir in enumerate(run_dirs[:5]):  # 最新5件まで表示
            screenshots = list(run_dir.glob("*.png"))
            print(f"\n{i+1}. {run_dir.name}")
            print(f"   スクリーンショット数: {len(screenshots)}")

            if i == 0:  # 最新の実行の詳細
                print(f"   保存場所: {run_dir.absolute()}")
                print("   レポート:")
                if (run_dir / "TEST_REPORT.html").exists():
                    print(f"   - HTML: {run_dir / 'TEST_REPORT.html'}")
                if (run_dir / "TEST_REPORT.md").exists():
                    print(f"   - Markdown: {run_dir / 'TEST_REPORT.md'}")


def main():
    """メイン処理"""
    print("🚀 TextffCut 完全網羅E2Eテスト")
    print("=" * 60)
    print("すべてのユーザーシナリオをブラウザで実行します")
    print()

    # テストの実行
    exit_code = run_all_scenario_tests()

    # レポートの生成
    generate_comprehensive_report()

    # サマリーの表示
    show_summary()

    if exit_code == 0:
        print("\n✅ すべてのシナリオテストが成功しました！")
    else:
        print("\n⚠️ 一部のテストが失敗しました")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
