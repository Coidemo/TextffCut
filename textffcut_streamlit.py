#!/usr/bin/env python3
"""
TextffCut Streamlit版 - 正しい起動方法を実装
Streamlitを内部から直接起動
"""

import sys
import os
from pathlib import Path

# PyInstallerでパッケージ化されているか確認
if getattr(sys, 'frozen', False):
    # パッケージ化されている場合
    bundle_dir = sys._MEIPASS
else:
    # 通常のPython環境
    bundle_dir = Path(__file__).parent

# Streamlitの設定
os.environ['STREAMLIT_SERVER_HEADLESS'] = 'true'
os.environ['STREAMLIT_SERVER_PORT'] = '8501'
os.environ['STREAMLIT_BROWSER_GATHER_USAGE_STATS'] = 'false'

def main():
    """Streamlitアプリを起動"""
    import streamlit.web.cli as stcli
    
    # アプリスクリプトのパス
    app_script = os.path.join(bundle_dir, 'textffcut_mvp.py')
    
    # Streamlitの引数を設定
    sys.argv = [
        'streamlit',
        'run',
        app_script,
        '--server.headless', 'true',
        '--server.port', '8501',
        '--browser.gatherUsageStats', 'false',
        '--logger.level', 'error'
    ]
    
    print("🎬 TextffCut Streamlit版を起動しています...")
    print("ブラウザで http://localhost:8501 を開いてください")
    print("終了するには Ctrl+C を押してください\n")
    
    try:
        # Streamlitを起動
        sys.exit(stcli.main())
    except KeyboardInterrupt:
        print("\n\n👋 終了しました")
        sys.exit(0)

if __name__ == '__main__':
    main()