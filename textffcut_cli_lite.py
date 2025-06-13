#!/usr/bin/env python3
"""
TextffCut CLI版 - 軽量版（外部依存なし）
ffmpegのみを使用した基本機能実装
"""

import sys
import os
import argparse
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

APP_NAME = "TextffCut CLI Lite"
VERSION = "1.0.0-lite"

def print_banner():
    """バナーを表示"""
    print(f"""
{'='*60}
🎬 {APP_NAME} v{VERSION}
   動画の無音削除とFCPXMLエクスポート
{'='*60}
    """)

def check_ffmpeg():
    """ffmpegの存在確認"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], 
            capture_output=True, 
            text=True,
            check=False
        )
        if result.returncode == 0:
            return True
        return False
    except FileNotFoundError:
        return False

def format_time(seconds):
    """秒を時間形式に変換"""
    return str(timedelta(seconds=int(seconds)))

def get_video_duration(video_path):
    """動画の長さを取得（ffprobe使用）"""
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        # ストリームから取得できない場合はフォーマットから取得
        try:
            cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            duration = float(result.stdout.strip())
            return duration
        except:
            raise Exception(f"動画の長さを取得できません: {str(e)}")

def get_video_info(video_path):
    """動画情報を取得"""
    print(f"\n📹 動画情報を取得中: {video_path}")
    
    try:
        # 基本情報を取得
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-of", "json",
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        stream_data = json.loads(result.stdout)
        if not stream_data.get("streams"):
            raise Exception("動画ストリームが見つかりません")
        stream_info = stream_data["streams"][0]
        
        # FPSを計算
        fps_str = stream_info.get("r_frame_rate", "30/1")
        num, den = map(int, fps_str.split("/"))
        fps = num / den if den != 0 else 30.0
        
        # 長さを取得
        duration = get_video_duration(video_path)
        
        # ファイルサイズ
        file_size = os.path.getsize(video_path) / (1024*1024)
        
        print(f"""
動画情報:
{'─'*50}
📁 ファイル: {os.path.basename(video_path)}
⏱️  長さ: {format_time(duration)} ({duration:.1f}秒)
📐 解像度: {stream_info.get('width', '?')}x{stream_info.get('height', '?')}
🎞️  FPS: {fps:.2f}
🎨 コーデック: {stream_info.get('codec_name', '不明')}
💾 サイズ: {file_size:.1f} MB
{'─'*50}
        """)
        
        return {
            "duration": duration,
            "width": stream_info.get('width', 0),
            "height": stream_info.get('height', 0),
            "fps": fps,
            "codec": stream_info.get('codec_name', ''),
            "size_mb": file_size
        }
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None

def detect_silence(video_path, threshold=-35, min_duration=0.3):
    """無音部分を検出（ffmpeg使用）"""
    print(f"\n🔇 無音部分を検出中...")
    print(f"   閾値: {threshold} dB")
    print(f"   最小無音時間: {min_duration} 秒")
    
    try:
        # 一時ファイルで無音検出結果を保存
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
            temp_path = temp_file.name
        
        # ffmpegで無音検出
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-af", f"silencedetect=noise={threshold}dB:d={min_duration}",
            "-f", "null",
            "-"
        ]
        
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True
        )
        
        # 結果を解析（stderrに出力される）
        lines = result.stderr.split('\n') if result.stderr else []
        silence_ranges = []
        silence_start = None
        
        for line in lines:
            if "silence_start:" in line:
                parts = line.split("silence_start:")
                if len(parts) > 1:
                    try:
                        silence_start = float(parts[1].strip().split()[0])
                    except:
                        pass
            elif "silence_end:" in line and silence_start is not None:
                parts = line.split("silence_end:")
                if len(parts) > 1:
                    try:
                        silence_end = float(parts[1].strip().split()[0])
                        silence_ranges.append((silence_start, silence_end))
                        silence_start = None
                    except:
                        pass
        
        # 動画の長さを取得
        duration = get_video_duration(video_path)
        
        # 最後まで無音の場合
        if silence_start is not None:
            silence_ranges.append((silence_start, duration))
        
        # 残す部分を計算
        keep_ranges = []
        last_end = 0
        
        for start, end in silence_ranges:
            if start > last_end:
                keep_ranges.append((last_end, start))
            last_end = end
        
        if last_end < duration:
            keep_ranges.append((last_end, duration))
        
        # 結果を表示
        print(f"\n📊 検出結果:")
        print(f"   総時間: {format_time(duration)}")
        print(f"   無音部分: {len(silence_ranges)}箇所")
        print(f"   残す部分: {len(keep_ranges)}セグメント")
        
        total_silence = sum(end - start for start, end in silence_ranges)
        total_kept = sum(end - start for start, end in keep_ranges)
        
        print(f"   残す時間: {format_time(total_kept)} ({total_kept/duration*100:.1f}%)")
        print(f"   削除時間: {format_time(total_silence)} ({total_silence/duration*100:.1f}%)")
        
        # 詳細表示
        if len(silence_ranges) > 0:
            print(f"\n🔇 無音部分の詳細（最初の10個）:")
            for i, (start, end) in enumerate(silence_ranges[:10]):
                duration_sec = end - start
                print(f"   {i+1:2d}. {format_time(start)} - {format_time(end)} ({duration_sec:.1f}秒)")
            if len(silence_ranges) > 10:
                print(f"   ... 他 {len(silence_ranges)-10} 箇所")
        
        # 一時ファイルを削除
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        
        return keep_ranges, silence_ranges
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None, None

def export_fcpxml(video_path, output_path, time_ranges=None, project_name=None):
    """FCPXMLをエクスポート"""
    print(f"\n📝 FCPXMLをエクスポート中...")
    
    try:
        # プロジェクト名の設定
        if not project_name:
            project_name = Path(video_path).stem + "_edited"
        
        # 動画情報を取得
        info = get_video_info(video_path)
        if not info:
            return False
        
        duration = info["duration"]
        fps = info["fps"]
        
        # 時間範囲が指定されていない場合は全体
        if not time_ranges:
            time_ranges = [(0, duration)]
        
        # FCPXMLを生成
        fcpxml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.11">
    <resources>
        <format id="r1" name="FFVideoFormat{info['width']}p{int(fps)}" frameDuration="1/{int(fps)}s" width="{info['width']}" height="{info['height']}"/>
        <asset id="r2" name="{os.path.basename(video_path)}" src="file://{os.path.abspath(video_path)}" start="0s" duration="{duration}s" hasVideo="1" hasAudio="1"/>
    </resources>
    <library>
        <event name="TextffCut Export">
            <project name="{project_name}">
                <sequence format="r1">
                    <spine>"""
        
        # 各セグメントを追加
        for i, (start, end) in enumerate(time_ranges):
            segment_duration = end - start
            fcpxml_content += f"""
                        <clip name="Segment {i+1}" offset="0s" duration="{segment_duration}s">
                            <video ref="r2" offset="{start}s" duration="{segment_duration}s"/>
                            <audio ref="r2" offset="{start}s" duration="{segment_duration}s"/>
                        </clip>"""
        
        fcpxml_content += """
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""
        
        # ファイルに書き込み
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(fcpxml_content)
        
        print(f"✅ FCPXMLを出力しました: {output_path}")
        print(f"   プロジェクト名: {project_name}")
        print(f"   セグメント数: {len(time_ranges)}")
        
        total_duration = sum(end - start for start, end in time_ranges)
        print(f"   合計時間: {format_time(total_duration)}")
        
        return True
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

def process_video(video_path, output_dir=None, remove_silence=True, 
                 threshold=-35, min_silence_duration=0.3):
    """動画を処理（無音削除 + FCPXMLエクスポート）"""
    print_banner()
    
    # ffmpegの確認
    if not check_ffmpeg():
        print("❌ ffmpegが見つかりません。ffmpegをインストールしてください。")
        print("   macOS: brew install ffmpeg")
        print("   Windows: https://ffmpeg.org/download.html")
        return False
    
    # ファイルの存在確認
    if not os.path.exists(video_path):
        print(f"❌ ファイルが見つかりません: {video_path}")
        return False
    
    # 出力ディレクトリの設定
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(video_path), "output")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 動画情報を取得
    video_info = get_video_info(video_path)
    if not video_info:
        return False
    
    # 無音検出
    keep_ranges = None
    if remove_silence:
        keep_ranges, silence_ranges = detect_silence(
            video_path, 
            threshold=threshold,
            min_duration=min_silence_duration
        )
        if not keep_ranges:
            return False
    else:
        # 無音削除しない場合は全体を保持
        keep_ranges = [(0, video_info["duration"])]
    
    # FCPXMLエクスポート
    base_name = Path(video_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"{base_name}_edited_{timestamp}.fcpxml")
    
    success = export_fcpxml(video_path, output_path, keep_ranges, base_name)
    
    if success:
        print(f"\n✨ 処理が完了しました！")
        print(f"📁 出力フォルダ: {output_dir}")
    
    return success

def main():
    """メインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 動画の無音削除とFCPXMLエクスポート",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 動画情報を表示
  %(prog)s info video.mp4
  
  # 無音部分を検出
  %(prog)s silence video.mp4 --threshold -40
  
  # 無音を削除してFCPXMLをエクスポート
  %(prog)s process video.mp4 --remove-silence
  
  # 出力先を指定
  %(prog)s process video.mp4 --output-dir ./exports
        """
    )
    
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    
    # サブコマンド
    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")
    
    # info コマンド
    parser_info = subparsers.add_parser("info", help="動画情報を表示")
    parser_info.add_argument("video", help="動画ファイルのパス")
    
    # silence コマンド
    parser_silence = subparsers.add_parser("silence", help="無音部分を検出")
    parser_silence.add_argument("video", help="動画ファイルのパス")
    parser_silence.add_argument("--threshold", type=float, default=-35, 
                               help="無音閾値 (dB) (デフォルト: -35)")
    parser_silence.add_argument("--min-duration", type=float, default=0.3,
                               help="最小無音時間 (秒) (デフォルト: 0.3)")
    
    # process コマンド
    parser_process = subparsers.add_parser("process", help="動画を処理してFCPXMLを出力")
    parser_process.add_argument("video", help="動画ファイルのパス")
    parser_process.add_argument("--output-dir", help="出力ディレクトリ")
    parser_process.add_argument("--remove-silence", action="store_true", default=True,
                               help="無音部分を削除 (デフォルト: True)")
    parser_process.add_argument("--threshold", type=float, default=-35,
                               help="無音閾値 (dB) (デフォルト: -35)")
    parser_process.add_argument("--min-duration", type=float, default=0.3,
                               help="最小無音時間 (秒) (デフォルト: 0.3)")
    
    args = parser.parse_args()
    
    # コマンドが指定されていない場合
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # コマンドの実行
    try:
        if args.command == "info":
            get_video_info(args.video)
        
        elif args.command == "silence":
            detect_silence(
                args.video,
                threshold=args.threshold,
                min_duration=args.min_duration
            )
        
        elif args.command == "process":
            success = process_video(
                args.video,
                output_dir=args.output_dir,
                remove_silence=args.remove_silence,
                threshold=args.threshold,
                min_silence_duration=args.min_duration
            )
            if not success:
                sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n👋 処理を中断しました。")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()