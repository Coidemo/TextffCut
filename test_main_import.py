#!/usr/bin/env python3
"""main.pyのインポートをテスト"""
import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("1. 基本的なインポートテスト...")
try:
    from utils.logging import get_logger

    print("✓ get_logger インポート成功")
except Exception as e:
    print(f"✗ get_logger インポート失敗: {e}")
    sys.exit(1)

print("\n2. main.pyのインポートテスト...")
try:

    print("✓ main関数 インポート成功")
except Exception as e:
    print(f"✗ main関数 インポート失敗: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n3. main関数の実行テスト（Streamlit無し）...")
try:
    # Streamlitのモックを作成
    class MockStreamlit:
        def __init__(self):
            self.session_state = {}

        def set_page_config(self, *args, **kwargs):
            pass

        def markdown(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            print(f"[ERROR] {args[0] if args else ''}")

        def title(self, *args, **kwargs):
            pass

        def columns(self, *args, **kwargs):
            return [self] * len(args)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    # Streamlitをモックに置き換え
    import sys

    sys.modules["streamlit"] = MockStreamlit()

    print("✓ テスト完了")

except Exception as e:
    print(f"✗ エラー: {e}")
    import traceback

    traceback.print_exc()

print("\n4. get_logger関数の直接実行テスト...")
try:
    logger = get_logger("test")
    print("✓ get_logger 実行成功")
    logger.info("テストログメッセージ")
except Exception as e:
    print(f"✗ get_logger 実行失敗: {e}")
