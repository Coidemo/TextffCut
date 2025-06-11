#!/usr/bin/env python3
"""
MVP版のビルドスクリプト
PyInstallerのコマンドを直接実行
"""

import subprocess
import sys
import os
from pathlib import Path

def build_mvp():
    """MVP版をビルド"""
    print("=== TextffCut MVP ビルド開始 ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            subprocess.run(['rm', '-rf', dir_name])
    
    # PyInstallerコマンドを構築
    cmd = [
        'pyinstaller',
        '--clean',
        '--onefile',  # 単一実行ファイルにする
        '--windowed',  # コンソールウィンドウを表示しない
        '--name', 'TextffCut_MVP',
        '--add-data', f'{sys.prefix}/lib/python*/site-packages/streamlit:streamlit',
        '--hidden-import', 'streamlit',
        '--hidden-import', 'streamlit.runtime.scriptrunner.magic_funcs',
        '--hidden-import', 'altair',
        '--hidden-import', 'pandas',
        '--hidden-import', 'numpy',
        '--collect-all', 'streamlit',
        'textffcut_mvp.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("✅ ビルド成功！")
        print("\n実行ファイル:")
        if Path('dist/TextffCut_MVP').exists():
            print("  - dist/TextffCut_MVP (Mac/Linux)")
        if Path('dist/TextffCut_MVP.exe').exists():
            print("  - dist/TextffCut_MVP.exe (Windows)")
    else:
        print("❌ ビルド失敗")
        print("\nエラー出力:")
        print(result.stderr)
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_mvp()
    sys.exit(exit_code)