#!/usr/bin/env python3
"""
TextffCut Video版 - 動画処理機能付きCLI
Phase 2: ffmpeg-pythonを使った動画処理
"""

import sys
import os
import argparse
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
import subprocess
import json

APP_NAME = "TextffCut Video"
VERSION = "0.2.0-video"

class VideoProcessor:
    """動画処理クラス"""
    
    @staticmethod
    def get_video_info(file_path):
        """ffprobeを使って動画情報を取得"""
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                file_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return None
                
            data = json.loads(result.stdout)
            
            # 動画ストリームを探す
            video_stream = None
            audio_stream = None
            
            for stream in data.get('streams', []):
                if stream['codec_type'] == 'video' and not video_stream:
                    video_stream = stream
                elif stream['codec_type'] == 'audio' and not audio_stream:
                    audio_stream = stream
            
            if not video_stream:
                return None
                
            # 動画情報を整理
            duration = float(data['format'].get('duration', 0))
            
            return {
                'duration': duration,
                'duration_str': str(timedelta(seconds=int(duration))),
                'width': video_stream.get('width', 0),
                'height': video_stream.get('height', 0),
                'fps': eval(video_stream.get('r_frame_rate', '0/1')),
                'codec': video_stream.get('codec_name', 'unknown'),
                'audio_codec': audio_stream.get('codec_name', 'none') if audio_stream else 'none',
                'bitrate': int(data['format'].get('bit_rate', 0)) // 1000,  # kbps
                'format': data['format'].get('format_name', 'unknown')
            }
        except Exception as e:
            return {'error': str(e)}
    
    @staticmethod
    def extract_audio(video_path, output_path=None):
        """動画から音声を抽出"""
        if not output_path:
            output_path = video_path.rsplit('.', 1)[0] + '_audio.wav'
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',  # ビデオなし
            '-acodec', 'pcm_s16le',  # 16bit PCM
            '-ar', '44100',  # 44.1kHz
            '-ac', '2',  # ステレオ
            '-y',  # 上書き
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        return output_path if result.returncode == 0 else None

def get_file_info(file_path):
    """ファイル情報を取得（基本情報）"""
    try:
        stat = os.stat(file_path)
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return {
            "path": file_path,
            "name": os.path.basename(file_path),
            "size_mb": size_mb,
            "modified": modified,
            "mime_type": mime_type or "不明",
            "extension": Path(file_path).suffix,
            "is_video": mime_type and mime_type.startswith("video/")
        }
    except Exception as e:
        return {"error": str(e)}

def check_ffmpeg():
    """ffmpegがインストールされているか確認"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True)
        return result.returncode == 0
    except:
        return False

def print_banner():
    """バナーを表示"""
    print(f"""
{'='*60}
🎬 {APP_NAME} v{VERSION}
{'='*60}
    """)

def print_file_info(info, video_info=None):
    """ファイル情報を表示"""
    if "error" in info:
        print(f"❌ エラー: {info['error']}")
        return
    
    print(f"""
📁 基本情報:
{'─'*50}
ファイル名: {info['name']}
サイズ: {info['size_mb']:.2f} MB
更新日時: {info['modified']}
    """)
    
    if video_info and 'error' not in video_info:
        print(f"""🎥 動画情報:
{'─'*50}
時間: {video_info['duration_str']} ({video_info['duration']:.1f}秒)
解像度: {video_info['width']}x{video_info['height']}
FPS: {video_info['fps']:.2f}
ビデオコーデック: {video_info['codec']}
オーディオコーデック: {video_info['audio_codec']}
ビットレート: {video_info['bitrate']} kbps
フォーマット: {video_info['format']}
{'─'*50}
        """)

def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 動画処理機能付きCLI"
    )
    parser.add_argument("file", nargs="?", help="処理する動画ファイル")
    parser.add_argument("--extract-audio", action="store_true", help="音声を抽出")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    
    args = parser.parse_args()
    
    print_banner()
    
    # ffmpegチェック
    if not check_ffmpeg():
        print("❌ ffmpegがインストールされていません")
        print("インストール方法:")
        print("  Mac: brew install ffmpeg")
        print("  Windows: https://ffmpeg.org/download.html")
        sys.exit(1)
    
    if not args.file:
        # 対話モード
        print("対話モードで起動しました。")
        while True:
            file_path = input("\n動画ファイルのパスを入力 (quit で終了): ").strip()
            
            if file_path.lower() in ['quit', 'exit']:
                break
                
            if not os.path.exists(file_path):
                print(f"❌ ファイルが見つかりません: {file_path}")
                continue
            
            # 基本情報
            info = get_file_info(file_path)
            
            # 動画情報
            video_info = None
            if info.get('is_video'):
                print("🔍 動画情報を取得中...")
                video_info = VideoProcessor.get_video_info(file_path)
            
            print_file_info(info, video_info)
            
            if info.get('is_video'):
                extract = input("\n音声を抽出しますか？ (y/n): ").strip().lower()
                if extract == 'y':
                    print("🎵 音声を抽出中...")
                    audio_path = VideoProcessor.extract_audio(file_path)
                    if audio_path:
                        print(f"✅ 音声を抽出しました: {audio_path}")
                    else:
                        print("❌ 音声の抽出に失敗しました")
    else:
        # コマンドライン引数モード
        if not os.path.exists(args.file):
            print(f"❌ ファイルが見つかりません: {args.file}")
            sys.exit(1)
        
        info = get_file_info(args.file)
        video_info = None
        
        if info.get('is_video'):
            video_info = VideoProcessor.get_video_info(args.file)
        
        print_file_info(info, video_info)
        
        if args.extract_audio and info.get('is_video'):
            print("\n🎵 音声を抽出中...")
            audio_path = VideoProcessor.extract_audio(args.file)
            if audio_path:
                print(f"✅ 音声を抽出しました: {audio_path}")
            else:
                print("❌ 音声の抽出に失敗しました")

if __name__ == "__main__":
    main()