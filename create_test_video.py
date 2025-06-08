#\!/usr/bin/env python
"""
テスト用の短い動画を作成
"""

import subprocess
import os

def create_test_video():
    """5秒の無音テスト動画を作成"""
    output_path = "videos/test_short.mp4"
    
    # ffmpegコマンドで黒画面の動画を生成
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x480:r=30",  # 黒画面
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",  # 無音
        "-t", "5",  # 5秒
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac",
        output_path
    ]
    
    try:
        subprocess.run(cmd, check=True, capture_output=True)
        print(f"✅ テスト動画を作成しました: {output_path}")
        
        # ファイルサイズ確認
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"   サイズ: {size_mb:.2f} MB")
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 動画作成エラー: {e}")
        print(f"   stderr: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        print("❌ ffmpegがインストールされていません")
        print("   brew install ffmpeg でインストールしてください")
        return False

if __name__ == "__main__":
    create_test_video()
EOF < /dev/null