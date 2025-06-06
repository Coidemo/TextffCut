#!/usr/bin/env python
"""
テスト用動画ファイルを生成するスクリプト
"""

import os
import subprocess
from pathlib import Path

def create_test_video(duration_seconds: int, output_name: str, text: str):
    """
    指定された長さのテスト動画を作成
    
    Args:
        duration_seconds: 動画の長さ（秒）
        output_name: 出力ファイル名
        text: 動画に含めるテキスト（音声合成用）
    """
    videos_dir = Path("videos")
    videos_dir.mkdir(exist_ok=True)
    
    output_path = videos_dir / output_name
    
    # macOSの音声合成を使用してテスト音声を作成
    audio_path = videos_dir / f"{Path(output_name).stem}_audio.aiff"
    
    # 音声合成コマンド
    say_command = [
        "say",
        "-v", "Kyoko",  # 日本語音声
        "-o", str(audio_path),
        text
    ]
    
    try:
        print(f"音声を生成中: {audio_path}")
        subprocess.run(say_command, check=True)
        
        # FFmpegで動画を作成（黒い背景に白いテキスト）
        ffmpeg_command = [
            "ffmpeg",
            "-y",  # 上書き
            "-f", "lavfi",
            "-i", f"color=c=black:s=1280x720:d={duration_seconds}",
            "-i", str(audio_path),
            "-vf", f"drawtext=text='{text[:50]}...':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
            "-c:v", "libx264",
            "-c:a", "aac",
            "-shortest",
            str(output_path)
        ]
        
        print(f"動画を生成中: {output_path}")
        subprocess.run(ffmpeg_command, check=True)
        
        # 一時音声ファイルを削除
        audio_path.unlink()
        
        print(f"✅ テスト動画を作成しました: {output_path}")
        return output_path
        
    except subprocess.CalledProcessError as e:
        print(f"❌ エラー: {e}")
        return None
    except FileNotFoundError:
        print("❌ エラー: FFmpegまたはsayコマンドが見つかりません")
        print("FFmpegのインストール: brew install ffmpeg")
        return None


def main():
    """テスト用動画セットを作成"""
    
    test_videos = [
        {
            "duration": 30,
            "name": "test_short_30s.mp4",
            "text": "これは短いテスト動画です。30秒間の動画で、基本的な動作確認に使用します。文字起こしとアライメントのテストを行います。"
        },
        {
            "duration": 60,
            "name": "test_medium_1m.mp4",
            "text": "これは1分間のテスト動画です。中程度の長さで、通常の使用を想定しています。" * 3
        },
        {
            "duration": 300,
            "name": "test_long_5m.mp4",
            "text": "これは5分間のテスト動画です。長めの動画で、パフォーマンステストに使用します。" * 10
        }
    ]
    
    print("=== テスト用動画の生成 ===")
    
    created_videos = []
    for video_config in test_videos:
        path = create_test_video(
            video_config["duration"],
            video_config["name"],
            video_config["text"]
        )
        if path:
            created_videos.append(path)
    
    print(f"\n生成完了: {len(created_videos)}/{len(test_videos)} 本")
    
    # テスト用のメタデータファイルも作成
    metadata_path = Path("videos/test_metadata.json")
    import json
    metadata = {
        "test_videos": [
            {
                "file": str(p.name),
                "duration": d["duration"],
                "description": d["text"][:50] + "..."
            }
            for p, d in zip(created_videos, test_videos) if p
        ]
    }
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    print(f"メタデータを保存: {metadata_path}")


if __name__ == "__main__":
    main()