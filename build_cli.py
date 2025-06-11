#!/usr/bin/env python3
"""
CLI版のビルドスクリプト
最小構成でPyInstallerの動作を確認
"""

import subprocess
import sys
from pathlib import Path

def build_cli():
    """CLI版をビルド"""
    print("=== TextffCut CLI ビルド開始 ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            subprocess.run(['rm', '-rf', dir_name])
    
    # PyInstallerコマンドを構築（最小構成）
    cmd = [
        'pyinstaller',
        '--clean',
        '--onefile',  # 単一実行ファイルにする
        '--name', 'TextffCut_CLI',
        'textffcut_cli.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ ビルド成功！")
        print("\n実行ファイル: dist/TextffCut_CLI")
        
        # ファイルサイズを確認
        if Path('dist/TextffCut_CLI').exists():
            size_mb = Path('dist/TextffCut_CLI').stat().st_size / (1024 * 1024)
            print(f"ファイルサイズ: {size_mb:.2f} MB")
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_cli()
    sys.exit(exit_code)