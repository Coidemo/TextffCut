#!/usr/bin/env python3
"""
Streamlit版のビルドスクリプト
実績のある方法を使用
"""

import subprocess
import sys
from pathlib import Path
import shutil

def build_streamlit():
    """Streamlit版をビルド"""
    print("=== TextffCut Streamlit ビルド開始 ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            shutil.rmtree(dir_name)
    
    # PyInstallerコマンドを構築（実績のある設定）
    cmd = [
        'pyinstaller',
        '--clean',
        '--onefile',
        '--name', 'TextffCut_Streamlit',
        '--additional-hooks-dir', './hooks',
        '--collect-all', 'streamlit',
        '--copy-metadata', 'streamlit',
        '--collect-data', 'streamlit',
        '--hidden-import', 'streamlit.runtime.scriptrunner.magic_funcs',
        '--hidden-import', 'streamlit.web.cli',
        '--hidden-import', 'altair',
        '--hidden-import', 'pandas',
        '--hidden-import', 'numpy',
        '--hidden-import', 'pyarrow',
        '--hidden-import', 'validators',
        '--hidden-import', 'toml',
        '--hidden-import', 'gitpython',
        '--hidden-import', 'pydeck',
        '--hidden-import', 'pympler',
        '--hidden-import', 'tzlocal',
        '--add-data', '.streamlit:streamlit',
        '--add-data', 'textffcut_mvp.py:.',
        'run_streamlit.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ ビルド成功！")
        print("\n実行ファイル: dist/TextffCut_Streamlit")
        
        # ファイルサイズを確認
        if Path('dist/TextffCut_Streamlit').exists():
            size_mb = Path('dist/TextffCut_Streamlit').stat().st_size / (1024 * 1024)
            print(f"ファイルサイズ: {size_mb:.2f} MB")
            
        print("\n使い方:")
        print("  ./dist/TextffCut_Streamlit")
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_streamlit()
    sys.exit(exit_code)