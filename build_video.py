#!/usr/bin/env python3
"""
Video版のビルドスクリプト
ffmpeg連携機能を含むバージョン
"""

import subprocess
import sys
from pathlib import Path

def build_video():
    """Video版をビルド"""
    print("=== TextffCut Video ビルド開始 ===")
    
    # ビルドディレクトリをクリーンアップ
    for dir_name in ['build', 'dist']:
        if Path(dir_name).exists():
            print(f"既存の{dir_name}ディレクトリを削除...")
            subprocess.run(['rm', '-rf', dir_name])
    
    # PyInstallerコマンドを構築
    cmd = [
        'pyinstaller',
        '--clean',
        '--onefile',
        '--name', 'TextffCut_Video',
        'textffcut_video.py'
    ]
    
    print("実行コマンド:")
    print(" ".join(cmd))
    print()
    
    # ビルド実行
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ ビルド成功！")
        print("\n実行ファイル: dist/TextffCut_Video")
        
        # ファイルサイズを確認
        if Path('dist/TextffCut_Video').exists():
            size_mb = Path('dist/TextffCut_Video').stat().st_size / (1024 * 1024)
            print(f"ファイルサイズ: {size_mb:.2f} MB")
            
        print("\n注意: ffmpegは別途インストールが必要です")
    else:
        print("\n❌ ビルド失敗")
        
    return result.returncode

if __name__ == "__main__":
    exit_code = build_video()
    sys.exit(exit_code)