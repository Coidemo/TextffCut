#!/usr/bin/env python3
"""
MVP版のビルドスクリプト（コンソール版）
デバッグ用にコンソール出力を有効化
"""

import subprocess
import sys
from pathlib import Path

def build_mvp_console():
    """MVP版をビルド（コンソール版）"""
    print("=== TextffCut MVP ビルド開始（コンソール版） ===")
    
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
        '--console',  # コンソール出力を有効化（デバッグ用）
        '--name', 'TextffCut_MVP_Console',
        '--add-data', f'{sys.prefix}/lib/python*/site-packages/streamlit:streamlit',
        '--hidden-import', 'streamlit',
        '--hidden-import', 'streamlit.runtime.scriptrunner.magic_funcs',
        '--hidden-import', 'altair',
        '--hidden-import', 'pandas',
        '--hidden-import', 'numpy',
        '--hidden-import', 'pyarrow',  # Streamlitが使用
        '--hidden-import', 'validators',
        '--hidden-import', 'toml',
        '--collect-all', 'streamlit',
        'textffcut_mvp.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ ビルド成功！")
        print("\n実行ファイル: dist/TextffCut_MVP_Console")
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_mvp_console()
    sys.exit(exit_code)