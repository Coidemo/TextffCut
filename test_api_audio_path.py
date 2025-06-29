#!/usr/bin/env python3
"""
APIモードでの音声パス問題を調査
"""
import logging
import os
import sys

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.transcription_api import APITranscriber

# ログ設定
logging.basicConfig(level=logging.DEBUG)


def test_audio_path_issue() -> None:
    """APIモードでの音声パス問題をテスト"""
    print("=== APIモード音声パステスト ===")

    # 実際の動画ファイルへのパス（存在するものを使用）
    video_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original.mp4"

    if not os.path.exists(video_path):
        print(f"テスト動画が見つかりません: {video_path}")
        print("小さなテスト動画を作成してください:")
        print(
            "ffmpeg -f lavfi -i testsrc=duration=5:size=320x240:rate=30 -f lavfi -i sine=frequency=1000:duration=5 -c:v libx264 -c:a aac test_video.mp4"
        )
        return

    # 設定
    config = Config()
    config.transcription.use_api = True
    config.transcription.api_key = os.getenv("TEXTFFCUT_API_KEY", "")
    config.transcription.api_provider = "openai"
    config.transcription.language = "ja"
    config.transcription.api_align_in_subprocess = True

    # APITranscriberを初期化
    APITranscriber(config)

    # _transcribe_with_separated_alignmentメソッドの流れを追跡
    print("\n1. _transcribe_with_separated_alignment の流れを確認:")

    # audio_pathがどのように扱われるかを確認
    print(f"   - original_audio_path: {video_path}")
    print(f"   - ファイル存在確認: {os.path.exists(video_path)}")
    print(f"   - ファイルサイズ: {os.path.getsize(video_path) / 1024 / 1024:.1f}MB")

    # _align_in_subprocessに渡されるaudio_pathを確認
    print("\n2. _align_in_subprocess に渡される audio_path:")
    print("   - APIモードでは original_audio_path (動画ファイル) が渡される")
    print("   - worker_align.py はこのパスから音声を読み込む必要がある")

    # WhisperXのload_audio関数の動作を確認
    print("\n3. WhisperX load_audio の動作確認:")
    try:
        import whisperx

        print("   - WhisperXがインポートできました")

        # 動画ファイルから直接音声を読み込めるか確認
        try:
            audio = whisperx.load_audio(video_path)
            print(f"   ✅ 動画ファイルから音声を読み込み成功: shape={audio.shape}")
        except Exception as e:
            print(f"   ❌ 動画ファイルから音声読み込み失敗: {e}")

    except ImportError:
        print("   - WhisperXがインポートできません")


if __name__ == "__main__":
    test_audio_path_issue()
