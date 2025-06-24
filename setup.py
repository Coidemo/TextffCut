#!/usr/bin/env python3
"""
TextffCut セットアップヘルパー
macOS専用 - Python環境の確認と必要なパッケージのインストールを支援
"""
import platform
import subprocess
import sys


def check_macos():
    """macOSの確認"""
    if platform.system() != "Darwin":
        print("❌ このツールはmacOS専用です。")
        print(f"  検出されたOS: {platform.system()}")
        return False

    # macOSバージョンの取得
    mac_version = platform.mac_ver()[0]
    print(f"✅ macOS {mac_version} を検出しました。")

    # Apple Siliconの確認
    processor = platform.processor()
    if processor == "arm" or "Apple" in processor:
        print("✅ Apple Silicon (M1/M2/M3) を検出しました。")
    else:
        print("✅ Intel Mac を検出しました。")

    return True


def check_python_version():
    """Python バージョンの確認"""
    print("\nPythonバージョンの確認...")
    version = sys.version_info
    print(f"  Python {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("  ❌ Python 3.8以上が必要です。")
        return False

    print("  ✅ Pythonバージョンは問題ありません。")
    return True


def check_homebrew():
    """Homebrewの確認"""
    print("\nHomebrewの確認...")
    try:
        result = subprocess.run(["brew", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            print(f"  ✅ {version_line}")
            return True
    except FileNotFoundError:
        pass

    print("  ⚠️  Homebrewがインストールされていません。")
    print("  インストール方法:")
    print('    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
    return False


def check_ffmpeg():
    """FFmpegの確認"""
    print("\nFFmpegの確認...")
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            print(f"  ✅ {version_line}")
            return True
    except FileNotFoundError:
        pass

    print("  ⚠️  FFmpegがインストールされていません。")
    print("  インストール方法:")
    print("    brew install ffmpeg")
    return False


def check_gpu_support():
    """GPUサポートの確認（macOS専用）"""
    print("\nGPUサポートの確認...")

    # Apple Siliconの確認
    processor = platform.processor()
    if processor == "arm" or "Apple" in processor:
        print("  ✅ Apple Silicon (Metal Performance Shaders)対応")
        return "mps"
    else:
        print("  ℹ️  Intel Mac (CPU処理)")
        return "cpu"


def main():
    """メイン処理"""
    print("=" * 50)
    print("   TextffCut セットアップヘルパー")
    print("         macOS専用版")
    print("=" * 50)
    print()

    # macOS確認
    if not check_macos():
        print("\n❌ セットアップを中止します。")
        sys.exit(1)

    # Pythonバージョン確認
    if not check_python_version():
        print("\n❌ セットアップを中止します。")
        sys.exit(1)

    # Homebrew確認
    homebrew_ok = check_homebrew()

    # FFmpeg確認
    ffmpeg_ok = check_ffmpeg()

    # GPU確認
    device_type = check_gpu_support()

    # インストール推奨事項
    print("\n" + "=" * 50)
    print("インストール推奨事項:")
    print("=" * 50)

    if not homebrew_ok:
        print("\n0. Homebrewのインストール（必須）:")
        print('   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')

    if not ffmpeg_ok:
        print("\n0. FFmpegのインストール（必須）:")
        print("   brew install ffmpeg")

    print("\n1. 仮想環境の作成（推奨）:")
    print("   python3 -m venv venv")
    print("   source venv/bin/activate")

    print("\n2. 依存関係のインストール:")
    print("   pip install -r requirements.txt")

    print("\n3. 起動方法:")
    print("   streamlit run main.py")

    if device_type == "mps":
        print("\n💡 ヒント: Apple Siliconでは自動的にMetal Performance Shadersが使用されます。")

    print("\n✅ 上記のコマンドを順番に実行してください。")

    # 自動インストールの提案
    print("\n" + "-" * 50)
    response = input("自動インストールスクリプトを実行しますか？ (y/n): ")

    if response.lower() == "y":
        print("\n以下のコマンドを実行してください:")
        print("  ./install.sh")

    print("\n詳細は README.md を参照してください。")


if __name__ == "__main__":
    main()
