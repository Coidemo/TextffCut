#!/usr/bin/env python3
"""
TextffCut MVP版 - ランチャースクリプト
PyInstallerでパッケージ化したStreamlitアプリを起動
"""

import sys
import os
from pathlib import Path
import subprocess

def launch_streamlit():
    """Streamlitアプリを起動"""
    # PyInstallerでパッケージ化されているか確認
    if getattr(sys, 'frozen', False):
        # パッケージ化されている場合
        base_path = sys._MEIPASS
        app_script = os.path.join(base_path, 'textffcut_mvp.py')
    else:
        # 通常のPython環境
        base_path = Path(__file__).parent
        app_script = base_path / 'textffcut_mvp.py'
    
    # Streamlitコマンドを構築
    cmd = [
        sys.executable,
        '-m', 'streamlit',
        'run',
        str(app_script),
        '--server.headless', 'true',
        '--server.port', '8501',
        '--browser.gatherUsageStats', 'false'
    ]
    
    print("TextffCut MVP を起動しています...")
    print(f"ブラウザで http://localhost:8501 を開いてください")
    
    try:
        # Streamlitを起動
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n終了しました")
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    launch_streamlit()