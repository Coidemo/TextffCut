#!/usr/bin/env python3
"""
全テストを実行してカバレッジレポートを生成するスクリプト

使用方法:
    python run_all_tests.py              # 全テストを実行
    python run_all_tests.py --unit       # 単体テストのみ
    python run_all_tests.py --integration # 統合テストのみ
    python run_all_tests.py --coverage   # カバレッジレポートを開く
"""

import argparse
import subprocess
import sys
import webbrowser
from pathlib import Path


def run_tests(test_type=None, verbose=False):
    """テストを実行"""
    cmd = ["pytest"]

    if test_type == "unit":
        cmd.extend(["-m", "unit"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])

    if verbose:
        cmd.append("-vv")

    print(f"実行コマンド: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def open_coverage_report():
    """カバレッジレポートをブラウザで開く"""
    coverage_file = Path("htmlcov/index.html")
    if coverage_file.exists():
        webbrowser.open(f"file://{coverage_file.absolute()}")
        print(f"カバレッジレポートを開きました: {coverage_file.absolute()}")
    else:
        print("カバレッジレポートが見つかりません。先にテストを実行してください。")


def main():
    parser = argparse.ArgumentParser(description="テストを実行してカバレッジレポートを生成")
    parser.add_argument("--unit", action="store_true", help="単体テストのみ実行")
    parser.add_argument("--integration", action="store_true", help="統合テストのみ実行")
    parser.add_argument("--coverage", action="store_true", help="カバレッジレポートを開く")
    parser.add_argument("-v", "--verbose", action="store_true", help="詳細な出力")

    args = parser.parse_args()

    if args.coverage:
        open_coverage_report()
        return 0

    test_type = None
    if args.unit:
        test_type = "unit"
    elif args.integration:
        test_type = "integration"

    return run_tests(test_type, args.verbose)


if __name__ == "__main__":
    sys.exit(main())
