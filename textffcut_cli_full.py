#!/usr/bin/env python3
"""
TextffCut CLI版 - フル機能実装
実際のcore/モジュールを使用した本格的なCLIツール
"""

import sys
import os
import argparse
import json
from pathlib import Path
from datetime import datetime, timedelta
import tempfile
import shutil

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from core.video import VideoProcessor
    from core.export import FCPXMLExporter
    from core.text_processor import TextProcessor
    from utils.simple_logging import SimpleLogger
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    IMPORT_ERROR = str(e)

APP_NAME = "TextffCut CLI"
VERSION = "1.0.0-cli"

# ロガーの設定
logger = None
if CORE_AVAILABLE:
    logger = SimpleLogger()

def print_banner():
    """バナーを表示"""
    print(f"""
{'='*60}
🎬 {APP_NAME} v{VERSION}
   動画の文字起こしと切り抜きを効率化するツール
{'='*60}
    """)

def format_time(seconds):
    """秒を時間形式に変換"""
    return str(timedelta(seconds=int(seconds)))

def get_video_info_cli(video_path):
    """動画情報を取得して表示"""
    print(f"\n📹 動画情報を取得中: {video_path}")
    
    try:
        processor = VideoProcessor()
        info = processor.get_video_info(video_path)
        
        print(f"""
動画情報:
{'─'*50}
📁 ファイル: {os.path.basename(video_path)}
⏱️  長さ: {format_time(info.duration)} ({info.duration:.1f}秒)
📐 解像度: {info.width}x{info.height}
🎞️  FPS: {info.fps:.2f}
🎨 コーデック: {info.codec}
💾 サイズ: {os.path.getsize(video_path) / (1024*1024):.1f} MB
{'─'*50}
        """)
        return info
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None

def detect_silence_cli(video_path, threshold=-35, min_silence_duration=0.3, output_json=None):
    """無音部分を検出"""
    print(f"\n🔇 無音部分を検出中...")
    print(f"   閾値: {threshold} dB")
    print(f"   最小無音時間: {min_silence_duration} 秒")
    
    try:
        processor = VideoProcessor()
        
        # 動画情報を取得
        video_info = processor.get_video_info(video_path)
        duration = video_info.duration
        
        # 全体を範囲として無音検出
        time_ranges = [(0, duration)]
        
        # 無音検出
        keep_ranges = processor.remove_silence_new(
            video_path,
            time_ranges,
            threshold_db=threshold,
            min_silence_duration=min_silence_duration
        )
        
        # 無音部分を計算（全体から残す部分を引く）
        silence_ranges = []
        last_end = 0
        
        for start, end in keep_ranges:
            if start > last_end:
                silence_ranges.append((last_end, start))
            last_end = end
        
        if last_end < duration:
            silence_ranges.append((last_end, duration))
        
        # 結果を表示
        print(f"\n📊 検出結果:")
        print(f"   総時間: {format_time(duration)}")
        print(f"   残す部分: {len(keep_ranges)}セグメント")
        print(f"   無音部分: {len(silence_ranges)}箇所")
        
        total_kept = sum(end - start for start, end in keep_ranges)
        total_silence = sum(end - start for start, end in silence_ranges)
        
        print(f"   残す時間: {format_time(total_kept)} ({total_kept/duration*100:.1f}%)")
        print(f"   削除時間: {format_time(total_silence)} ({total_silence/duration*100:.1f}%)")
        
        # 詳細表示
        if len(silence_ranges) > 0:
            print(f"\n🔇 無音部分の詳細:")
            for i, (start, end) in enumerate(silence_ranges[:10]):  # 最初の10個まで
                duration_sec = end - start
                print(f"   {i+1:2d}. {format_time(start)} - {format_time(end)} ({duration_sec:.1f}秒)")
            if len(silence_ranges) > 10:
                print(f"   ... 他 {len(silence_ranges)-10} 箇所")
        
        # JSON出力
        if output_json:
            result = {
                "video_path": video_path,
                "duration": duration,
                "threshold_db": threshold,
                "min_silence_duration": min_silence_duration,
                "keep_ranges": keep_ranges,
                "silence_ranges": silence_ranges,
                "total_kept": total_kept,
                "total_silence": total_silence,
                "keep_percentage": total_kept/duration*100
            }
            
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n💾 結果をJSONに保存: {output_json}")
        
        return keep_ranges, silence_ranges
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None, None

def export_fcpxml_cli(video_path, output_path, time_ranges=None, project_name=None):
    """FCPXMLをエクスポート"""
    print(f"\n📝 FCPXMLをエクスポート中...")
    
    try:
        # プロジェクト名の設定
        if not project_name:
            project_name = Path(video_path).stem + "_edited"
        
        # 動画情報を取得
        processor = VideoProcessor()
        video_info = processor.get_video_info(video_path)
        
        # 時間範囲が指定されていない場合は全体
        if not time_ranges:
            time_ranges = [(0, video_info.duration)]
        
        # FCPXMLエクスポート
        exporter = FCPXMLExporter()
        exporter.export(
            video_path=video_path,
            time_ranges=time_ranges,
            output_path=output_path,
            project_name=project_name
        )
        
        print(f"✅ FCPXMLを出力しました: {output_path}")
        print(f"   プロジェクト名: {project_name}")
        print(f"   セグメント数: {len(time_ranges)}")
        
        total_duration = sum(end - start for start, end in time_ranges)
        print(f"   合計時間: {format_time(total_duration)}")
        
        return True
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return False

def process_video_cli(video_path, output_dir=None, remove_silence=True, 
                     threshold=-35, min_silence_duration=0.3, export_format="fcpxml"):
    """動画を処理（無音削除 + エクスポート）"""
    print_banner()
    
    # 出力ディレクトリの設定
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(video_path), "output")
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 動画情報を取得
    video_info = get_video_info_cli(video_path)
    if not video_info:
        return False
    
    # 無音検出
    keep_ranges = None
    if remove_silence:
        keep_ranges, silence_ranges = detect_silence_cli(
            video_path, 
            threshold=threshold,
            min_silence_duration=min_silence_duration
        )
        if not keep_ranges:
            return False
    else:
        # 無音削除しない場合は全体を保持
        keep_ranges = [(0, video_info.duration)]
    
    # エクスポート
    base_name = Path(video_path).stem
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if export_format == "fcpxml":
        output_path = os.path.join(output_dir, f"{base_name}_edited_{timestamp}.fcpxml")
        success = export_fcpxml_cli(video_path, output_path, keep_ranges, base_name)
    else:
        print(f"❌ 未対応のエクスポート形式: {export_format}")
        return False
    
    if success:
        print(f"\n✨ 処理が完了しました！")
        print(f"📁 出力フォルダ: {output_dir}")
    
    return success

def main():
    """メインエントリーポイント"""
    # core/モジュールが利用できない場合
    if not CORE_AVAILABLE:
        print(f"❌ 必要なモジュールが見つかりません: {IMPORT_ERROR}")
        print("core/モジュールが正しくインストールされているか確認してください。")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 動画の文字起こしと切り抜きを効率化するツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 動画情報を表示
  %(prog)s info video.mp4
  
  # 無音部分を検出
  %(prog)s silence video.mp4 --threshold -40
  
  # 無音を削除してFCPXMLをエクスポート
  %(prog)s process video.mp4 --remove-silence --export fcpxml
  
  # 結果をJSONに保存
  %(prog)s silence video.mp4 --output-json result.json
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
    parser_silence.add_argument("--output-json", help="結果をJSONファイルに保存")
    
    # process コマンド
    parser_process = subparsers.add_parser("process", help="動画を処理")
    parser_process.add_argument("video", help="動画ファイルのパス")
    parser_process.add_argument("--output-dir", help="出力ディレクトリ")
    parser_process.add_argument("--remove-silence", action="store_true", default=True,
                               help="無音部分を削除 (デフォルト: True)")
    parser_process.add_argument("--threshold", type=float, default=-35,
                               help="無音閾値 (dB) (デフォルト: -35)")
    parser_process.add_argument("--min-duration", type=float, default=0.3,
                               help="最小無音時間 (秒) (デフォルト: 0.3)")
    parser_process.add_argument("--export", choices=["fcpxml"], default="fcpxml",
                               help="エクスポート形式 (デフォルト: fcpxml)")
    
    args = parser.parse_args()
    
    # コマンドが指定されていない場合
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    # ファイルの存在確認
    if hasattr(args, "video") and not os.path.exists(args.video):
        print(f"❌ ファイルが見つかりません: {args.video}")
        sys.exit(1)
    
    # コマンドの実行
    try:
        if args.command == "info":
            get_video_info_cli(args.video)
        
        elif args.command == "silence":
            detect_silence_cli(
                args.video,
                threshold=args.threshold,
                min_silence_duration=args.min_duration,
                output_json=args.output_json
            )
        
        elif args.command == "process":
            success = process_video_cli(
                args.video,
                output_dir=args.output_dir,
                remove_silence=args.remove_silence,
                threshold=args.threshold,
                min_silence_duration=args.min_duration,
                export_format=args.export
            )
            if not success:
                sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\n👋 処理を中断しました。")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 予期しないエラー: {str(e)}")
        if logger:
            logger.error(f"Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()