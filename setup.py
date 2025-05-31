#!/usr/bin/env python3
"""
TextffCut セットアップヘルパー
Python環境の確認と必要なパッケージのインストールを支援
"""
import sys
import subprocess
import platform
import os
from pathlib import Path


def check_python_version():
    """Python バージョンの確認"""
    print("Pythonバージョンの確認...")
    version = sys.version_info
    print(f"  Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("  ❌ Python 3.8以上が必要です。")
        return False
    
    print("  ✅ Pythonバージョンは問題ありません。")
    return True


def check_ffmpeg():
    """FFmpegの確認"""
    print("\nFFmpegの確認...")
    try:
        result = subprocess.run(["ffmpeg", "-version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"  ✅ {version_line}")
            return True
    except FileNotFoundError:
        pass
    
    print("  ⚠️  FFmpegがインストールされていません。")
    print("  インストール方法:")
    
    system = platform.system()
    if system == "Darwin":  # macOS
        print("    brew install ffmpeg")
    elif system == "Windows":
        print("    1. https://ffmpeg.org/download.html からダウンロード")
        print("    2. 解凍してPATHに追加")
    else:  # Linux
        print("    sudo apt-get install ffmpeg  # Ubuntu/Debian")
        print("    sudo yum install ffmpeg      # CentOS/RHEL")
    
    return False


def check_cuda():
    """CUDA/GPUサポートの確認"""
    print("\nGPUサポートの確認...")
    
    # NVIDIA GPUの確認
    try:
        result = subprocess.run(["nvidia-smi"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("  ✅ NVIDIA GPUが検出されました。")
            return "cuda"
    except FileNotFoundError:
        pass
    
    # macOSの確認
    if platform.system() == "Darwin":
        # Apple Siliconの確認
        if platform.processor() == "arm" or "Apple" in platform.processor():
            print("  ✅ Apple Silicon (Metal Performance Shaders)が検出されました。")
            return "mps"
    
    print("  ℹ️  GPUが検出されませんでした。CPU版を使用します。")
    return "cpu"


def get_torch_install_command(device_type):
    """PyTorchインストールコマンドの取得"""
    if device_type == "cuda":
        return "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118"
    elif device_type == "mps":
        return "pip install torch torchaudio"
    else:
        return "pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu"


def main():
    """メイン処理"""
    print("=" * 50)
    print("   TextffCut セットアップヘルパー")
    print("=" * 50)
    print()
    
    # Pythonバージョン確認
    if not check_python_version():
        print("\n❌ セットアップを中止します。")
        sys.exit(1)
    
    # FFmpeg確認
    ffmpeg_ok = check_ffmpeg()
    
    # GPU確認
    device_type = check_cuda()
    
    # インストール推奨事項
    print("\n" + "=" * 50)
    print("インストール推奨事項:")
    print("=" * 50)
    
    print("\n1. 仮想環境の作成（推奨）:")
    print("   python -m venv venv")
    
    if platform.system() == "Windows":
        print("   venv\\Scripts\\activate")
    else:
        print("   source venv/bin/activate")
    
    print("\n2. PyTorchのインストール:")
    print(f"   {get_torch_install_command(device_type)}")
    
    print("\n3. その他の依存関係:")
    print("   pip install -r requirements.txt")
    
    print("\n4. 起動方法:")
    print("   streamlit run main.py")
    
    if not ffmpeg_ok:
        print("\n⚠️  注意: FFmpegのインストールを忘れずに！")
    
    print("\n✅ 上記のコマンドを順番に実行してください。")
    
    # 自動インストールの提案
    print("\n" + "-" * 50)
    response = input("自動インストールスクリプトを実行しますか？ (y/n): ")
    
    if response.lower() == 'y':
        if platform.system() == "Windows":
            print("\nWindowsの場合: install.bat を実行してください。")
        else:
            print("\nmacOS/Linuxの場合: ./install.sh を実行してください。")
    
    print("\n設定の詳細は README.md を参照してください。")


if __name__ == "__main__":
    main()