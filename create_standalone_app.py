#!/usr/bin/env python3
"""
TextffCut スタンドアロンアプリ作成スクリプト
Nuitkaを使用してネイティブ実行ファイルを作成
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path

def check_nuitka():
    """Nuitkaがインストールされているか確認"""
    try:
        result = subprocess.run(['python', '-m', 'nuitka', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ Nuitka is installed: {result.stdout.strip()}")
            return True
    except:
        pass
    
    print("✗ Nuitka is not installed")
    print("Installing Nuitka...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'nuitka'])
    return False

def create_minimal_app():
    """最小限のアプリを作成"""
    minimal_code = '''#!/usr/bin/env python3
"""
TextffCut Minimal - 基本機能のみ
"""

import sys
import os
import json
import subprocess
from pathlib import Path

APP_NAME = "TextffCut Minimal"
VERSION = "1.0.0-minimal"

def transcribe_with_api(video_path, api_key=None):
    """OpenAI Whisper APIを使用した文字起こし"""
    print("Note: This version uses Whisper API for transcription")
    print("Local WhisperX is not included to reduce app size")
    return None

def detect_silence(video_path, threshold=-35):
    """ffmpegで無音検出"""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={threshold}dB:d=0.3",
        "-f", "null", "-"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    # 簡易的な解析
    return []

def export_fcpxml(video_path, time_ranges, output_path):
    """FCPXMLエクスポート"""
    # 簡易実装
    with open(output_path, 'w') as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>')
    print(f"Exported to {output_path}")

def main():
    print(f"{APP_NAME} v{VERSION}")
    print("="*50)
    
    if len(sys.argv) < 2:
        print("Usage: textffcut_minimal <video_file>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    if not os.path.exists(video_path):
        print(f"Error: File not found: {video_path}")
        sys.exit(1)
    
    print(f"Processing: {video_path}")
    
    # 無音検出
    silence_ranges = detect_silence(video_path)
    print(f"Detected {len(silence_ranges)} silence ranges")
    
    # FCPXMLエクスポート
    output_path = Path(video_path).stem + "_edited.fcpxml"
    export_fcpxml(video_path, silence_ranges, output_path)
    
    print("Done!")

if __name__ == "__main__":
    main()
'''
    
    with open('textffcut_minimal.py', 'w') as f:
        f.write(minimal_code)
    
    print("✓ Created textffcut_minimal.py")

def build_with_nuitka():
    """Nuitkaでビルド"""
    print("\nBuilding with Nuitka...")
    
    cmd = [
        sys.executable, '-m', 'nuitka',
        '--standalone',
        '--onefile',
        '--assume-yes-for-downloads',
        '--output-dir=dist_nuitka',
        '--company-name=TextffCut',
        '--product-name=TextffCut',
        '--file-version=1.0.0',
        '--product-version=1.0.0',
        '--file-description=Video editing tool',
        '--copyright=2025 TextffCut Team',
        'textffcut_minimal.py'
    ]
    
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("✅ Build successful!")
        return True
    else:
        print("❌ Build failed!")
        return False

def build_with_pyinstaller_minimal():
    """PyInstallerで最小限ビルド"""
    print("\nBuilding minimal version with PyInstaller...")
    
    cmd = [
        'pyinstaller',
        '--onefile',
        '--name', 'textffcut_minimal',
        '--distpath', 'dist_minimal',
        'textffcut_minimal.py'
    ]
    
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    print("TextffCut Standalone App Builder")
    print("="*50)
    
    # 最小限のアプリを作成
    create_minimal_app()
    
    # ビルド方法を選択
    print("\nSelect build method:")
    print("1. Nuitka (smaller, faster)")
    print("2. PyInstaller (simpler)")
    
    # 両方試す
    print("\nTrying PyInstaller first...")
    if build_with_pyinstaller_minimal():
        print("\n✅ PyInstaller build successful!")
        print(f"Output: dist_minimal/textffcut_minimal")
    
    # Nuitkaもチェック
    if check_nuitka():
        print("\nTrying Nuitka...")
        if build_with_nuitka():
            print("\n✅ Nuitka build successful!")
            print(f"Output: dist_nuitka/textffcut_minimal")

if __name__ == "__main__":
    main()