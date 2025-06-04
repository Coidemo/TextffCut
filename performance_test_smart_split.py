"""
SmartSplitTranscriberのパフォーマンステスト
"""
import time
import sys
from pathlib import Path
import argparse
from datetime import datetime
import json

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.transcription import Transcriber
from core.transcription_smart_split import SmartSplitTranscriber
from core.video import VideoInfo
from utils.logging import get_logger

logger = get_logger(__name__)


def measure_transcription(transcriber_class, video_path, config, label):
    """文字起こしの処理時間を計測"""
    print(f"\n{'='*60}")
    print(f" {label} のテスト")
    print(f"{'='*60}")
    
    # 動画情報を表示
    video_info = VideoInfo.from_file(video_path)
    print(f"動画: {Path(video_path).name}")
    print(f"時間: {video_info.duration/60:.1f}分")
    print(f"解像度: {video_info.width}x{video_info.height}")
    print(f"FPS: {video_info.fps:.1f}")
    
    # Transcriberをインスタンス化
    transcriber = transcriber_class(config)
    
    # プログレスコールバック
    def progress_callback(progress, status):
        print(f"\r進捗: {progress*100:.1f}% - {status}", end="", flush=True)
    
    # 処理時間を計測
    print("\n\n文字起こし開始...")
    start_time = time.time()
    
    try:
        result = transcriber.transcribe(
            video_path,
            model_size="base",
            progress_callback=progress_callback,
            use_cache=False,  # キャッシュを使わない
            save_cache=False  # キャッシュに保存しない
        )
        
        processing_time = time.time() - start_time
        
        print(f"\n\n処理完了!")
        print(f"処理時間: {processing_time:.1f}秒")
        print(f"リアルタイム比: {video_info.duration/processing_time:.1f}倍速")
        print(f"セグメント数: {len(result.segments)}")
        
        # 詳細情報
        if hasattr(result, 'processing_time'):
            print(f"内部処理時間: {result.processing_time:.1f}秒")
        
        return {
            "label": label,
            "video_duration": video_info.duration,
            "processing_time": processing_time,
            "realtime_factor": video_info.duration/processing_time,
            "segments_count": len(result.segments),
            "success": True
        }
        
    except Exception as e:
        print(f"\n\nエラー発生: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            "label": label,
            "video_duration": video_info.duration,
            "processing_time": None,
            "realtime_factor": None,
            "segments_count": None,
            "success": False,
            "error": str(e)
        }


def compare_performance(video_path):
    """従来版とスマート分割版のパフォーマンスを比較"""
    config = Config()
    
    # 両方のバージョンをテスト
    results = []
    
    # 1. 従来版（30秒チャンク）
    result1 = measure_transcription(
        Transcriber,
        video_path,
        config,
        "従来版（30秒チャンク）"
    )
    results.append(result1)
    
    # 少し待機（GPU/CPUのクールダウン）
    print("\n10秒待機中...")
    time.sleep(10)
    
    # 2. スマート分割版（20分分割）
    result2 = measure_transcription(
        SmartSplitTranscriber,
        video_path,
        config,
        "スマート分割版（20分分割）"
    )
    results.append(result2)
    
    # 結果を比較
    print(f"\n{'='*60}")
    print(" 比較結果")
    print(f"{'='*60}")
    
    if result1["success"] and result2["success"]:
        improvement = (result1["processing_time"] - result2["processing_time"]) / result1["processing_time"] * 100
        speedup = result2["realtime_factor"] / result1["realtime_factor"]
        
        print(f"処理時間の改善: {improvement:.1f}%")
        print(f"速度向上: {speedup:.1f}倍")
        
        # 詳細な比較表
        print("\n詳細比較:")
        print(f"{'項目':<20} {'従来版':>15} {'スマート分割版':>15}")
        print("-" * 52)
        print(f"{'処理時間':<20} {result1['processing_time']:>14.1f}秒 {result2['processing_time']:>14.1f}秒")
        print(f"{'リアルタイム比':<20} {result1['realtime_factor']:>14.1f}倍 {result2['realtime_factor']:>14.1f}倍")
        print(f"{'セグメント数':<20} {result1['segments_count']:>15d} {result2['segments_count']:>15d}")
    
    # 結果をJSON形式で保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"performance_test_result_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "test_time": timestamp,
            "video_path": str(video_path),
            "results": results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n結果を保存: {output_file}")


def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="SmartSplitTranscriberのパフォーマンステスト")
    parser.add_argument("video_path", help="テストする動画ファイルのパス")
    parser.add_argument("--mode", choices=["normal", "smart", "compare"], 
                      default="compare", help="テストモード")
    
    args = parser.parse_args()
    
    # 動画ファイルの存在確認
    if not Path(args.video_path).exists():
        print(f"エラー: 動画ファイルが見つかりません: {args.video_path}")
        sys.exit(1)
    
    config = Config()
    
    if args.mode == "normal":
        # 従来版のみテスト
        measure_transcription(Transcriber, args.video_path, config, "従来版")
    elif args.mode == "smart":
        # スマート分割版のみテスト
        measure_transcription(SmartSplitTranscriber, args.video_path, config, "スマート分割版")
    else:
        # 比較テスト
        compare_performance(args.video_path)


if __name__ == "__main__":
    # ログレベルを設定
    import logging
    logging.basicConfig(level=logging.INFO)
    
    main()