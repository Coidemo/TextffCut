#!/usr/bin/env python3
"""
テスト用動画作成スクリプト
短い動画ファイルを生成して、テストで使用
"""

import os
import subprocess
from pathlib import Path


def create_test_video(output_path: str, duration: int = 30, text: str = "これはテストサンプル動画です"):
    """テスト用動画を作成

    Args:
        output_path: 出力パス
        duration: 動画の長さ（秒）
        text: 表示するテキスト
    """
    print(f"🎬 テスト動画を作成中: {output_path}")
    print(f"  時間: {duration}秒")
    print(f"  テキスト: {text}")

    # FFmpegコマンドを構築
    # 黒背景に白文字でテキストを表示する動画を作成
    cmd = [
        "ffmpeg",
        "-y",  # 上書き確認なし
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1280x720:d={duration}",  # 黒背景
        "-vf",
        f"drawtext=text='{text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",  # テキスト
        "-c:v",
        "libx264",  # H.264エンコード
        "-pix_fmt",
        "yuv420p",  # 互換性のあるピクセルフォーマット
        "-t",
        str(duration),  # 動画の長さ
        output_path,
    ]

    # 無音の音声トラックを追加（文字起こしテスト用）
    cmd_with_audio = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s=1280x720:d={duration}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=44100:cl=stereo:d={duration}",  # 無音
        "-vf",
        f"drawtext=text='{text}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",  # 音声コーデック
        "-pix_fmt",
        "yuv420p",
        "-shortest",  # 短い方に合わせる
        output_path,
    ]

    try:
        # FFmpegが利用可能か確認
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)

        # 動画を作成
        result = subprocess.run(cmd_with_audio, capture_output=True, text=True)

        if result.returncode == 0:
            print(f"✅ テスト動画を作成しました: {output_path}")

            # ファイルサイズ確認
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  サイズ: {size_mb:.1f}MB")

            return True
        else:
            print(f"❌ エラー: {result.stderr}")
            return False

    except FileNotFoundError:
        print("❌ エラー: FFmpegがインストールされていません")
        print("  インストール方法:")
        print("  - Mac: brew install ffmpeg")
        print("  - Ubuntu: sudo apt install ffmpeg")
        print("  - Windows: https://ffmpeg.org/download.html")
        return False
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False


def create_test_video_with_speech(output_path: str, duration: int = 30):
    """音声付きテスト動画を作成（TTS使用）"""
    print(f"🎤 音声付きテスト動画を作成中: {output_path}")

    # macOSのsayコマンドを使用（他のOSでは要調整）
    import platform

    if platform.system() != "Darwin":
        print("⚠️ 音声生成はmacOSのみ対応しています")
        return create_test_video(output_path, duration)

    try:
        # 音声ファイルを生成
        audio_path = output_path.replace(".mp4", "_audio.aiff")
        text = "これはテストサンプル動画です。TextffCutの機能テストに使用します。"

        # 日本語音声を生成
        subprocess.run(["say", "-v", "Kyoko", "-o", audio_path, text], check=True)  # 日本語音声

        # 音声の長さを取得
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                audio_path,
            ],
            capture_output=True,
            text=True,
        )

        audio_duration = float(result.stdout.strip())

        # 動画と音声を結合
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1280x720:d={max(duration, audio_duration)}",
            "-i",
            audio_path,
            "-vf",
            f"drawtext=text='{text}':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-pix_fmt",
            "yuv420p",
            "-shortest",
            output_path,
        ]

        subprocess.run(cmd, check=True)

        # 一時ファイルを削除
        os.remove(audio_path)

        print(f"✅ 音声付きテスト動画を作成しました: {output_path}")
        return True

    except Exception as e:
        print(f"❌ 音声生成エラー: {e}")
        print("  無音動画を作成します")
        return create_test_video(output_path, duration)


def main():
    """メイン関数"""
    # 出力先ディレクトリ
    output_dir = Path(__file__).parent
    output_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("TextffCut テスト動画作成")
    print("=" * 60)

    # 基本的なテスト動画
    videos = [
        {"name": "test_sample.mp4", "duration": 30, "text": "これはテストサンプル動画です", "with_speech": False},
        {"name": "test_sample_speech.mp4", "duration": 30, "text": "音声付きテスト動画", "with_speech": True},
        {"name": "test_short.mp4", "duration": 10, "text": "短いテスト動画", "with_speech": False},
    ]

    success_count = 0

    for video_config in videos:
        output_path = output_dir / video_config["name"]

        if video_config["with_speech"]:
            success = create_test_video_with_speech(str(output_path), video_config["duration"])
        else:
            success = create_test_video(str(output_path), video_config["duration"], video_config["text"])

        if success:
            success_count += 1

    print(f"\n✅ {success_count}/{len(videos)} 個の動画を作成しました")
    print(f"📁 保存先: {output_dir}")

    # Docker環境の場合はvideosフォルダにコピー
    if os.path.exists("/.dockerenv"):
        videos_dir = Path("/app/videos")
        if videos_dir.exists():
            print("\n📋 Docker環境: videosフォルダにコピー中...")
            for video_config in videos:
                src = output_dir / video_config["name"]
                dst = videos_dir / video_config["name"]
                if src.exists():
                    import shutil

                    shutil.copy2(src, dst)
                    print(f"  ✓ {video_config['name']}")


if __name__ == "__main__":
    main()
