#!/usr/bin/env python3
"""Docker環境での機能テスト"""

import sys
import os
import time
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.transcription_subprocess import SubprocessTranscriber
from services.video_processing_service import VideoProcessingService
from services.export_service import ExportService


def test_transcription():
    """文字起こし機能のテスト"""
    print("\n=== 文字起こしテスト ===")
    
    config = Config()
    config.transcription.model_size = 'small'
    config.transcription.isolation_mode = 'subprocess'
    
    transcriber = SubprocessTranscriber(config)
    
    test_video = '/app/videos/test_short_30s.mp4'
    
    try:
        print(f"動画: {test_video}")
        start_time = time.time()
        
        result = transcriber.transcribe(test_video, model_size='small')
        
        elapsed = time.time() - start_time
        print(f"✓ 文字起こし成功: {len(result.segments)} セグメント ({elapsed:.1f}秒)")
        
        if result.segments:
            print(f"  最初のセグメント: {result.segments[0].text[:50]}...")
            
        return True
        
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        return False


def test_silence_removal():
    """無音削除機能のテスト"""
    print("\n=== 無音削除テスト ===")
    
    config = Config()
    video_service = VideoProcessingService(config)
    
    test_video = '/app/videos/test_short_30s.mp4'
    
    try:
        print(f"動画: {test_video}")
        
        # 時間範囲を指定（全体）
        time_ranges = [(0.0, 30.0)]
        
        result = video_service.remove_silence(
            video_path=test_video,
            time_ranges=time_ranges,
            threshold=-35,
            min_silence_duration=0.3,
            pad_start=0.1,
            pad_end=0.1,
            min_segment_duration=0.3
        )
        
        if result.success:
            keep_ranges = result.data
            print(f"✓ 無音削除成功: {len(keep_ranges)} セグメント")
            
            for i, range_obj in enumerate(keep_ranges[:3]):
                print(f"  セグメント {i+1}: {range_obj.start:.1f}s - {range_obj.end:.1f}s")
                
            # 統計情報
            metadata = result.metadata
            print(f"  削除時間: {metadata['silence_removed']:.1f}秒 ({metadata['removal_ratio']:.1%})")
            
            return True
        else:
            print(f"✗ エラー: {result.error}")
            return False
            
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_export():
    """エクスポート機能のテスト"""
    print("\n=== エクスポートテスト ===")
    
    config = Config()
    export_service = ExportService(config)
    
    test_video = '/app/videos/test_short_30s.mp4'
    output_dir = '/app/output'
    
    try:
        print(f"動画: {test_video}")
        
        # ダミーのセグメント
        segments = [(5.0, 10.0), (15.0, 20.0)]
        
        # FCPXMLエクスポート
        result = export_service.export_fcpxml(
            video_path=test_video,
            segments=segments,
            output_path=f"{output_dir}/test.fcpxml",
            project_name="Docker Test"
        )
        
        if result.success:
            print(f"✓ FCPXMLエクスポート成功: {result.data}")
            return True
        else:
            print(f"✗ エラー: {result.error}")
            return False
            
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        return False


def main():
    """メインテスト実行"""
    print("TextffCut Docker機能テスト")
    print("=" * 50)
    
    # 出力ディレクトリを作成
    os.makedirs('/app/output', exist_ok=True)
    
    results = {
        '文字起こし': test_transcription(),
        '無音削除': test_silence_removal(),
        'エクスポート': test_export()
    }
    
    print("\n=== テスト結果 ===")
    for name, success in results.items():
        status = "✓ 成功" if success else "✗ 失敗"
        print(f"{name}: {status}")
    
    # 全体の結果
    all_passed = all(results.values())
    print(f"\n全体結果: {'✓ すべて成功' if all_passed else '✗ 一部失敗'}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())