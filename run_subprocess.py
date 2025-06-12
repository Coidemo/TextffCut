#!/usr/bin/env python3
"""
Streamlit実行用ラッパー（subprocess版）
PyInstallerで確実に動作する方法
"""

import sys
import os
import subprocess
from pathlib import Path
import signal
import time

def signal_handler(sig, frame):
    """Ctrl+Cのハンドリング"""
    print("\n\n👋 終了しました")
    sys.exit(0)

def main():
    """Streamlitアプリを起動"""
    signal.signal(signal.SIGINT, signal_handler)
    
    # PyInstallerでパッケージ化されているか確認
    if getattr(sys, 'frozen', False):
        # パッケージ化されている場合
        bundle_dir = sys._MEIPASS
        python_path = sys.executable
    else:
        # 通常のPython環境
        bundle_dir = Path(__file__).parent
        python_path = sys.executable
    
    # アプリファイルのパス
    app_file = os.path.join(bundle_dir, 'textffcut_mvp.py')
    
    print("🎬 TextffCut Streamlit版を起動しています...")
    print("ブラウザで http://localhost:8501 を開いてください")
    print("終了するには Ctrl+C を押してください\n")
    
    # Streamlitをsubprocessで起動
    cmd = [
        python_path,
        '-m', 'streamlit',
        'run',
        app_file,
        '--server.headless', 'true',
        '--server.port', '8501',
        '--browser.gatherUsageStats', 'false'
    ]
    
    try:
        # プロセスを起動
        process = subprocess.Popen(cmd)
        
        # プロセスが終了するまで待機
        process.wait()
        
    except KeyboardInterrupt:
        print("\n\n👋 終了しました")
        process.terminate()
        time.sleep(1)
        if process.poll() is None:
            process.kill()
        sys.exit(0)
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()