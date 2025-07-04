"""
MVP版の簡易テスト
"""

import os

# MVP版を使用
os.environ["TEXTFFCUT_USE_MVP"] = "true"

# main.pyをインポートして実行
from main import main

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback

        traceback.print_exc()
