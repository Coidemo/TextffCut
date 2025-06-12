#!/usr/bin/env python3
"""
Streamlit実行用エントリーポイント
PyInstallerでのパッケージング用
"""

import sys
import os
from pathlib import Path

# PyInstallerでパッケージ化されているか確認
if getattr(sys, 'frozen', False):
    # パッケージ化されている場合
    bundle_dir = sys._MEIPASS
    # 必要なパスを追加
    sys.path.append(bundle_dir)
else:
    # 通常のPython環境
    bundle_dir = Path(__file__).parent

# 環境変数設定
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

def main():
    """Streamlitアプリを起動"""
    from streamlit.web import cli
    
    # アプリファイルのパス
    app_file = os.path.join(bundle_dir, 'textffcut_mvp.py')
    
    print("🎬 TextffCut Streamlit版を起動しています...")
    print("ブラウザで http://localhost:8501 を開いてください")
    print("終了するには Ctrl+C を押してください\n")
    
    # Streamlitを起動（内部APIを使用）
    try:
        # 新しいバージョンのStreamlit用
        if hasattr(cli, '_main_run_clExplicit'):
            cli._main_run_clExplicit(app_file, args=['run'])
        else:
            # 古いバージョンのStreamlit用
            sys.argv = ['streamlit', 'run', app_file, '--server.headless', 'true']
            cli.main()
    except KeyboardInterrupt:
        print("\n\n👋 終了しました")
        sys.exit(0)

if __name__ == '__main__':
    main()