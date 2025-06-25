#!/usr/bin/env python3
"""
TextffCut スモークテスト
最小限の動作確認を行う
"""

import os
import sys


def test_imports():
    """必要なモジュールがインポートできるか確認"""
    print("1. インポートテスト...")

    try:
        # メインモジュール
        import main

        print("  ✅ main.py")

        # 設定
        from config import Config

        print("  ✅ config.py")

        # コアモジュール
        from core import FCPXMLExporter, TextProcessor, Transcriber, VideoProcessor

        print("  ✅ core modules")

        # UIモジュール
        from ui import show_video_input

        print("  ✅ ui modules")

        # ユーティリティ
        from utils.logging import get_logger

        print("  ✅ utils modules")

        return True

    except ImportError as e:
        print(f"  ❌ インポートエラー: {e}")
        return False


def test_config():
    """設定が正しく初期化できるか確認"""
    print("\n2. 設定初期化テスト...")

    try:
        from config import Config

        config = Config()

        # 基本的な設定値の確認
        assert hasattr(config, "transcription")
        print("  ✅ transcription設定")

        assert hasattr(config, "ui")
        print("  ✅ UI設定")

        assert hasattr(config.transcription, "language")
        assert config.transcription.language == "ja"
        print("  ✅ 言語設定: ja")

        return True

    except Exception as e:
        print(f"  ❌ 設定エラー: {e}")
        return False


def test_transcriber_init():
    """Transcriberが初期化できるか確認"""
    print("\n3. Transcriber初期化テスト...")

    try:
        from config import Config
        from core import Transcriber

        config = Config()

        # ローカルモード
        config.transcription.use_api = False
        transcriber = Transcriber(config)
        print("  ✅ ローカルモードTranscriber")

        # APIモード（初期化のみ）
        config.transcription.use_api = True
        config.transcription.api_provider = "openai"
        transcriber_api = Transcriber(config)
        print("  ✅ APIモードTranscriber")

        return True

    except Exception as e:
        print(f"  ❌ Transcriberエラー: {e}")
        return False


def test_video_processor():
    """VideoProcessorが初期化できるか確認"""
    print("\n4. VideoProcessor初期化テスト...")

    try:
        from config import Config
        from core import VideoProcessor

        config = Config()
        processor = VideoProcessor(config)
        print("  ✅ VideoProcessor")

        # メソッドの存在確認
        assert hasattr(processor, "extract_segment")
        assert hasattr(processor, "remove_silence_new")
        print("  ✅ 必要なメソッドが存在")

        return True

    except Exception as e:
        print(f"  ❌ VideoProcessorエラー: {e}")
        return False


def test_ffmpeg():
    """FFmpegが利用可能か確認"""
    print("\n5. FFmpeg確認テスト...")

    try:
        import subprocess

        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)

        if result.returncode == 0:
            version_line = result.stdout.split("\n")[0]
            print(f"  ✅ {version_line}")
            return True
        else:
            print("  ❌ FFmpegが見つかりません")
            return False

    except Exception as e:
        print(f"  ❌ FFmpegエラー: {e}")
        return False


def test_worker_scripts():
    """ワーカースクリプトが存在するか確認"""
    print("\n6. ワーカースクリプト確認...")

    scripts = ["worker_transcribe.py", "worker_align.py"]

    all_exist = True
    for script in scripts:
        if os.path.exists(script):
            print(f"  ✅ {script}")
        else:
            print(f"  ❌ {script} が見つかりません")
            all_exist = False

    return all_exist


def main():
    """すべてのテストを実行"""
    print("=== TextffCut スモークテスト ===\n")

    # 各テストの実行
    results = {
        "インポート": test_imports(),
        "設定": test_config(),
        "Transcriber": test_transcriber_init(),
        "VideoProcessor": test_video_processor(),
        "FFmpeg": test_ffmpeg(),
        "ワーカースクリプト": test_worker_scripts(),
    }

    # 結果のサマリー
    print("\n=== テスト結果 ===")
    passed = 0
    failed = 0

    for test_name, result in results.items():
        if result:
            print(f"✅ {test_name}: PASS")
            passed += 1
        else:
            print(f"❌ {test_name}: FAIL")
            failed += 1

    print(f"\n合計: {passed} 成功, {failed} 失敗")

    # 終了コード
    if failed == 0:
        print("\n🎉 すべてのテストが成功しました！")
        sys.exit(0)
    else:
        print(f"\n⚠️  {failed}個のテストが失敗しました")
        sys.exit(1)


if __name__ == "__main__":
    main()
