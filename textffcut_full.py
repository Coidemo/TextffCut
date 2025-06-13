#!/usr/bin/env python3
"""
TextffCut フル機能版 - WhisperXアライメント付き
文字起こし、アライメント、テキスト差分検出、無音削除を統合
"""

import sys
import os
import argparse
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from core.transcription import Transcriber, TranscriptionResult
    from core.video import VideoProcessor
    from core.export import FCPXMLExporter
    from core.text_processor import TextProcessor
    from utils.simple_logging import SimpleLogger
    CORE_AVAILABLE = True
except ImportError as e:
    CORE_AVAILABLE = False
    IMPORT_ERROR = str(e)

APP_NAME = "TextffCut Full"
VERSION = "2.0.0"

# ロガーの設定
logger = None
if CORE_AVAILABLE:
    logger = SimpleLogger()

def print_banner():
    """バナーを表示"""
    print(f"""
{'='*60}
🎬 {APP_NAME} v{VERSION}
   文字起こし・アライメント・切り抜きの統合ツール
{'='*60}
    """)

def format_time(seconds):
    """秒を時間形式に変換"""
    return str(timedelta(seconds=int(seconds)))

def transcribe_video(video_path, model_size="large", language="ja", 
                    device="cuda", compute_type="float16", 
                    progress_callback=None):
    """動画を文字起こし（WhisperX使用）"""
    print(f"\n🎤 文字起こしを開始...")
    print(f"   モデル: {model_size}")
    print(f"   言語: {language}")
    print(f"   デバイス: {device}")
    
    try:
        transcriber = Transcriber()
        
        # 文字起こし実行
        result = transcriber.transcribe(
            video_path,
            model_size=model_size,
            language=language,
            device=device,
            compute_type=compute_type,
            align=True,  # アライメントも実行
            progress_callback=progress_callback
        )
        
        print(f"\n✅ 文字起こし完了")
        print(f"   セグメント数: {len(result.segments)}")
        print(f"   処理時間: {result.processing_time:.1f}秒")
        
        # 最初の5セグメントを表示
        print(f"\n📝 文字起こし結果（最初の5セグメント）:")
        for i, seg in enumerate(result.segments[:5]):
            start_str = f"{int(seg.start//60):02d}:{seg.start%60:05.2f}"
            end_str = f"{int(seg.end//60):02d}:{seg.end%60:05.2f}"
            print(f"   {i+1}. [{start_str} → {end_str}] {seg.text}")
        
        if len(result.segments) > 5:
            print(f"   ... 他 {len(result.segments)-5} セグメント")
        
        return result
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None

def find_text_differences(transcription_result, original_text, target_text,
                         context_length=10):
    """テキストの差分を検出"""
    print(f"\n🔍 テキスト差分を検出中...")
    print(f"   コンテキスト長: {context_length}文字")
    
    try:
        processor = TextProcessor()
        
        # 差分検出
        differences = processor.find_differences(
            transcription_result,
            original_text,
            target_text,
            context_length=context_length
        )
        
        print(f"\n📊 差分検出結果:")
        print(f"   差分箇所: {len(differences)}箇所")
        
        # 時間範囲を計算
        time_ranges = []
        for diff in differences:
            time_ranges.extend(diff.time_ranges)
        
        # 重複を除去してソート
        merged_ranges = merge_time_ranges(time_ranges)
        
        total_duration = sum(end - start for start, end in merged_ranges)
        print(f"   対象時間: {format_time(total_duration)}")
        print(f"   セグメント数: {len(merged_ranges)}")
        
        return differences, merged_ranges
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None, None

def merge_time_ranges(ranges):
    """重複する時間範囲をマージ"""
    if not ranges:
        return []
    
    # ソート
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    
    # マージ
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            # 重複している場合はマージ
            merged[-1] = (last_start, max(last_end, end))
        else:
            # 重複していない場合は追加
            merged.append((start, end))
    
    return merged

def process_with_silence_removal(video_path, time_ranges, output_path,
                               threshold=-35, min_silence_duration=0.3):
    """指定範囲から無音を削除して動画を出力"""
    print(f"\n🔇 無音削除処理を開始...")
    print(f"   閾値: {threshold} dB")
    print(f"   最小無音時間: {min_silence_duration} 秒")
    
    try:
        processor = VideoProcessor()
        
        # 無音削除
        keep_ranges = processor.remove_silence_new(
            video_path,
            time_ranges,
            threshold_db=threshold,
            min_silence_duration=min_silence_duration
        )
        
        total_kept = sum(end - start for start, end in keep_ranges)
        total_original = sum(end - start for start, end in time_ranges)
        
        print(f"\n📊 無音削除結果:")
        print(f"   元の長さ: {format_time(total_original)}")
        print(f"   削除後: {format_time(total_kept)} ({total_kept/total_original*100:.1f}%)")
        print(f"   セグメント数: {len(keep_ranges)}")
        
        # FCPXMLエクスポート
        exporter = FCPXMLExporter()
        exporter.export(
            video_path=video_path,
            time_ranges=keep_ranges,
            output_path=output_path,
            project_name=Path(video_path).stem + "_edited"
        )
        
        print(f"\n✅ FCPXMLを出力: {output_path}")
        
        return keep_ranges
        
    except Exception as e:
        print(f"❌ エラー: {str(e)}")
        return None

def save_transcription(result, output_path):
    """文字起こし結果を保存"""
    try:
        data = result.to_dict()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 文字起こし結果を保存: {output_path}")
    except Exception as e:
        print(f"❌ 保存エラー: {str(e)}")

def load_transcription(input_path):
    """文字起こし結果を読み込み"""
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        result = TranscriptionResult.from_dict(data)
        print(f"📂 文字起こし結果を読み込み: {input_path}")
        return result
    except Exception as e:
        print(f"❌ 読み込みエラー: {str(e)}")
        return None

def main():
    """メインエントリーポイント"""
    # core/モジュールが利用できない場合
    if not CORE_AVAILABLE:
        print(f"❌ 必要なモジュールが見つかりません: {IMPORT_ERROR}")
        print("WhisperXとcore/モジュールがインストールされているか確認してください。")
        sys.exit(1)
    
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 文字起こし・アライメント・切り抜きの統合ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # 文字起こしのみ
  %(prog)s transcribe video.mp4 --model large --language ja
  
  # テキスト差分検出
  %(prog)s diff video.mp4 --original orig.txt --target edited.txt
  
  # 完全なワークフロー（文字起こし＋差分検出＋無音削除）
  %(prog)s full video.mp4 --original orig.txt --target edited.txt
  
  # 保存済み文字起こしを使用
  %(prog)s diff video.mp4 --transcription result.json --original orig.txt --target edited.txt
        """
    )
    
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {VERSION}")
    
    # サブコマンド
    subparsers = parser.add_subparsers(dest="command", help="実行するコマンド")
    
    # transcribe コマンド
    parser_transcribe = subparsers.add_parser("transcribe", help="動画を文字起こし")
    parser_transcribe.add_argument("video", help="動画ファイルのパス")
    parser_transcribe.add_argument("--model", default="large", 
                                  choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
                                  help="Whisperモデルサイズ")
    parser_transcribe.add_argument("--language", default="ja", help="言語コード")
    parser_transcribe.add_argument("--device", default="cuda", 
                                  choices=["cuda", "cpu"], help="処理デバイス")
    parser_transcribe.add_argument("--output", help="文字起こし結果の保存先")
    
    # diff コマンド
    parser_diff = subparsers.add_parser("diff", help="テキスト差分を検出")
    parser_diff.add_argument("video", help="動画ファイルのパス")
    parser_diff.add_argument("--transcription", help="保存済み文字起こし結果")
    parser_diff.add_argument("--original", required=True, help="オリジナルテキストファイル")
    parser_diff.add_argument("--target", required=True, help="編集後テキストファイル")
    parser_diff.add_argument("--context", type=int, default=10, help="コンテキスト長")
    parser_diff.add_argument("--output", help="FCPXMLの出力先")
    parser_diff.add_argument("--remove-silence", action="store_true", help="無音を削除")
    parser_diff.add_argument("--threshold", type=float, default=-35, help="無音閾値")
    
    # full コマンド
    parser_full = subparsers.add_parser("full", help="完全なワークフロー")
    parser_full.add_argument("video", help="動画ファイルのパス")
    parser_full.add_argument("--original", required=True, help="オリジナルテキストファイル")
    parser_full.add_argument("--target", required=True, help="編集後テキストファイル")
    parser_full.add_argument("--model", default="large", help="Whisperモデル")
    parser_full.add_argument("--language", default="ja", help="言語コード")
    parser_full.add_argument("--output-dir", help="出力ディレクトリ")
    parser_full.add_argument("--remove-silence", action="store_true", help="無音を削除")
    
    args = parser.parse_args()
    
    # コマンドが指定されていない場合
    if not args.command:
        parser.print_help()
        sys.exit(0)
    
    print_banner()
    
    try:
        if args.command == "transcribe":
            # 文字起こし実行
            result = transcribe_video(
                args.video,
                model_size=args.model,
                language=args.language,
                device=args.device
            )
            
            if result and args.output:
                save_transcription(result, args.output)
        
        elif args.command == "diff":
            # 文字起こし結果を取得
            if args.transcription:
                result = load_transcription(args.transcription)
            else:
                result = transcribe_video(args.video)
            
            if not result:
                sys.exit(1)
            
            # テキストファイルを読み込み
            with open(args.original, 'r', encoding='utf-8') as f:
                original_text = f.read()
            with open(args.target, 'r', encoding='utf-8') as f:
                target_text = f.read()
            
            # 差分検出
            differences, time_ranges = find_text_differences(
                result, original_text, target_text,
                context_length=args.context
            )
            
            if not time_ranges:
                print("差分が見つかりませんでした。")
                sys.exit(0)
            
            # 出力先設定
            if not args.output:
                base_name = Path(args.video).stem
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                args.output = f"{base_name}_diff_{timestamp}.fcpxml"
            
            # 無音削除またはそのままエクスポート
            if args.remove_silence:
                process_with_silence_removal(
                    args.video, time_ranges, args.output,
                    threshold=args.threshold
                )
            else:
                exporter = FCPXMLExporter()
                exporter.export(
                    video_path=args.video,
                    time_ranges=time_ranges,
                    output_path=args.output
                )
                print(f"✅ FCPXMLを出力: {args.output}")
        
        elif args.command == "full":
            # 完全なワークフロー
            # 1. 文字起こし
            result = transcribe_video(
                args.video,
                model_size=args.model,
                language=args.language
            )
            
            if not result:
                sys.exit(1)
            
            # 2. テキスト読み込み
            with open(args.original, 'r', encoding='utf-8') as f:
                original_text = f.read()
            with open(args.target, 'r', encoding='utf-8') as f:
                target_text = f.read()
            
            # 3. 差分検出
            differences, time_ranges = find_text_differences(
                result, original_text, target_text
            )
            
            if not time_ranges:
                print("差分が見つかりませんでした。")
                sys.exit(0)
            
            # 4. 出力
            output_dir = args.output_dir or "output"
            Path(output_dir).mkdir(exist_ok=True)
            
            base_name = Path(args.video).stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 文字起こし結果を保存
            transcription_path = os.path.join(output_dir, f"{base_name}_transcription.json")
            save_transcription(result, transcription_path)
            
            # FCPXMLエクスポート
            fcpxml_path = os.path.join(output_dir, f"{base_name}_edited_{timestamp}.fcpxml")
            
            if args.remove_silence:
                process_with_silence_removal(
                    args.video, time_ranges, fcpxml_path
                )
            else:
                exporter = FCPXMLExporter()
                exporter.export(
                    video_path=args.video,
                    time_ranges=time_ranges,
                    output_path=fcpxml_path
                )
                print(f"✅ FCPXMLを出力: {fcpxml_path}")
            
            print(f"\n✨ 処理完了！")
            print(f"📁 出力フォルダ: {output_dir}")
    
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