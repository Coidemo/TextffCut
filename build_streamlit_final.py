#!/usr/bin/env python3
"""
Streamlit版のビルドスクリプト（最終版）
シンプルで確実な方法
"""

import subprocess
import sys
from pathlib import Path
import shutil

def build_streamlit():
    """Streamlit版をビルド（最終版）"""
    print("=== TextffCut Streamlit ビルド開始（最終版） ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            shutil.rmtree(dir_name)
    
    # PyInstallerコマンドを構築（シンプルに）
    cmd = [
        'pyinstaller',
        '--clean',
        '--onedir',
        '--name', 'TextffCut_Streamlit',
        '--collect-all', 'streamlit',
        '--copy-metadata', 'streamlit',
        '--add-data', '.streamlit:streamlit',
        '--add-data', 'textffcut_mvp.py:.',
        'run_subprocess.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ ビルド成功！")
        print("\n実行ファイル: dist/TextffCut_Streamlit/run_subprocess")
        
        # ディレクトリサイズを計算
        dist_path = Path('dist/TextffCut_Streamlit')
        if dist_path.exists():
            total_size = sum(f.stat().st_size for f in dist_path.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            print(f"合計サイズ: {size_mb:.2f} MB")
        
        print("\n使い方:")
        print("  cd dist/TextffCut_Streamlit")
        print("  ./run_subprocess")
        
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_streamlit()
    sys.exit(exit_code)