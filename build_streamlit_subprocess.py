#!/usr/bin/env python3
"""
Streamlit版のビルドスクリプト（subprocess版）
より安定した方法
"""

import subprocess
import sys
from pathlib import Path
import shutil

def build_streamlit():
    """Streamlit版をビルド（subprocess版）"""
    print("=== TextffCut Streamlit ビルド開始（subprocess版） ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            shutil.rmtree(dir_name)
    
    # PyInstallerコマンドを構築
    cmd = [
        'pyinstaller',
        '--clean',
        '--onedir',  # onedirモードに変更（より安定）
        '--name', 'TextffCut_Streamlit_Sub',
        '--collect-all', 'streamlit',
        '--copy-metadata', 'streamlit',
        '--copy-metadata', 'streamlit-camera-input-live',
        '--copy-metadata', 'streamlit-webrtc',
        '--copy-metadata', 'streamlit-card',
        '--hidden-import', 'streamlit.web.cli',
        '--hidden-import', 'altair.vegalite.v5',
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
        print("\n実行ディレクトリ: dist/TextffCut_Streamlit_Sub/")
        print("\n使い方:")
        print("  ./dist/TextffCut_Streamlit_Sub/run_subprocess")
        
        # 起動スクリプトを作成
        launcher_content = """#!/bin/bash
cd "$(dirname "$0")"
./TextffCut_Streamlit_Sub/run_subprocess
"""
        launcher_path = Path('dist/start_streamlit.sh')
        launcher_path.write_text(launcher_content)
        launcher_path.chmod(0o755)
        print("\n起動スクリプト: ./dist/start_streamlit.sh")
        
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_streamlit()
    sys.exit(exit_code)