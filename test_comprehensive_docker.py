#!/usr/bin/env python3
"""Docker環境での包括的な機能テスト"""

import sys
import os
import time
import json
from pathlib import Path

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import Config
from core.transcription_subprocess import SubprocessTranscriber
from services.video_processing_service import VideoProcessingService
from services.export_service import ExportService
from services.text_editing_service import TextEditingService
from core import TranscriptionSegment, VideoSegment
from core.text_processor import TextProcessor


def print_section(title):
    """セクション区切りを表示"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def test_transcription():
    """1. 文字起こし機能のテスト"""
    print_section("1. 文字起こしテスト")
    
    config = Config()
    config.transcription.model_size = 'small'
    config.transcription.isolation_mode = 'subprocess'
    
    transcriber = SubprocessTranscriber(config)
    test_video = '/app/videos/test_short_chunk.mp4'
    
    try:
        print(f"動画: {test_video}")
        start_time = time.time()
        
        result = transcriber.transcribe(test_video, model_size='small')
        
        elapsed = time.time() - start_time
        print(f"✓ 文字起こし成功: {len(result.segments)} セグメント ({elapsed:.1f}秒)")
        
        if result.segments:
            print(f"  最初のセグメント: {result.segments[0].text[:50]}...")
            
        # 結果を保存（後のテストで使用）
        with open('/tmp/transcription_result.json', 'w') as f:
            json.dump({
                'segments': [
                    {
                        'start': seg.start,
                        'end': seg.end,
                        'text': seg.text
                    } for seg in result.segments
                ]
            }, f)
            
        return True, result
        
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_text_editing():
    """2. テキスト編集機能のテスト"""
    print_section("2. テキスト編集テスト")
    
    config = Config()
    service = TextEditingService(config)
    
    try:
        # ダミーのセグメント
        original_segments = [
            TranscriptionSegment(start=0.0, end=5.0, text="これは元のテキストです。", words=[]),
            TranscriptionSegment(start=5.0, end=10.0, text="変更されるテキストです。", words=[]),
            TranscriptionSegment(start=10.0, end=15.0, text="これも元のテキストです。", words=[])
        ]
        
        edited_segments = [
            TranscriptionSegment(start=0.0, end=5.0, text="これは元のテキストです。", words=[]),
            TranscriptionSegment(start=5.0, end=10.0, text="変更後のテキストです！", words=[]),  # 変更
            TranscriptionSegment(start=10.0, end=15.0, text="これも元のテキストです。", words=[])
        ]
        
        # 差分検出
        result = service.detect_changes(
            original_segments=original_segments,
            edited_segments=edited_segments
        )
        
        if result.success:
            changes = result.data
            print(f"✓ 差分検出成功: {len(changes)} 個の変更")
            for change in changes:
                print(f"  - セグメント {change['index']}: {change['type']}")
        else:
            print(f"✗ エラー: {result.error}")
            return False
            
        return True
        
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_silence_removal():
    """3. 無音削除機能のテスト"""
    print_section("3. 無音削除テスト")
    
    config = Config()
    video_service = VideoProcessingService(config)
    
    test_video = '/app/videos/test_short_chunk.mp4'
    
    try:
        print(f"動画: {test_video}")
        
        # 時間範囲を指定
        time_ranges = [(0.0, 10.0)]
        
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
            
            return True, keep_ranges
        else:
            print(f"✗ エラー: {result.error}")
            return False, None
            
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False, None


def test_video_export(keep_ranges=None):
    """4. 動画エクスポート機能のテスト"""
    print_section("4. 動画エクスポートテスト")
    
    config = Config()
    video_service = VideoProcessingService(config)
    
    test_video = '/app/videos/test_short_chunk.mp4'
    output_dir = '/app/output'
    
    try:
        print(f"動画: {test_video}")
        
        # VideoSegmentのリストを作成（textパラメータなし）
        segments = []
        if keep_ranges:
            for kr in keep_ranges:
                segments.append(VideoSegment(
                    start=kr.start,
                    end=kr.end
                ))
        else:
            # デフォルトセグメント
            segments = [
                VideoSegment(start=0.0, end=2.0),
                VideoSegment(start=3.0, end=5.0)
            ]
        
        # セグメントを切り出し
        result = video_service.extract_segments(
            video_path=test_video,
            segments=segments,
            output_dir=output_dir,
            format="mp4"
        )
        
        if result.success:
            extracted_files = result.data
            print(f"✓ セグメント切り出し成功: {len(extracted_files)} ファイル")
            
            # 結合
            if len(extracted_files) > 1:
                merge_result = video_service.merge_videos(
                    video_files=extracted_files,
                    output_path=f"{output_dir}/merged_test.mp4"
                )
                
                if merge_result.success:
                    print(f"✓ 動画結合成功: {merge_result.data}")
                    return True
                else:
                    print(f"✗ 結合エラー: {merge_result.error}")
                    return False
            
            return True
        else:
            print(f"✗ エラー: {result.error}")
            return False
            
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_xml_export():
    """5. FCPXML/EDLエクスポート機能のテスト"""
    print_section("5. XML/EDLエクスポートテスト")
    
    config = Config()
    export_service = ExportService(config)
    
    test_video = '/app/videos/test_short_chunk.mp4'
    output_dir = '/app/output'
    
    try:
        print(f"動画: {test_video}")
        
        # セグメント（タプル形式）
        segments = [(1.0, 3.0), (5.0, 8.0)]
        
        # FCPXMLエクスポート
        result = export_service.export_fcpxml(
            video_path=test_video,
            segments=segments,
            output_path=f"{output_dir}/test.fcpxml",
            project_name="Comprehensive Test"
        )
        
        if result.success:
            print(f"✓ FCPXMLエクスポート成功: {result.data}")
            
            # XMEMLエクスポート
            xmeml_result = export_service.export_xmeml(
                video_path=test_video,
                segments=segments,
                output_path=f"{output_dir}/test.xml",
                sequence_name="Test Sequence"
            )
            
            if xmeml_result.success:
                print(f"✓ XMEMLエクスポート成功: {xmeml_result.data}")
                return True
            else:
                print(f"✗ XMEMLエラー: {xmeml_result.error}")
                return False
        else:
            print(f"✗ FCPXMLエラー: {result.error}")
            return False
            
    except Exception as e:
        print(f"✗ エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration_workflow():
    """6. 統合ワークフローテスト（文字起こし→編集→無音削除→エクスポート）"""
    print_section("6. 統合ワークフローテスト")
    
    try:
        # 1. 文字起こし
        print("\n[Step 1] 文字起こし実行...")
        success, transcription = test_transcription()
        if not success:
            print("✗ 文字起こしで失敗")
            return False
        
        # 2. テキスト編集（差分検出）
        print("\n[Step 2] テキスト編集...")
        success = test_text_editing()
        if not success:
            print("✗ テキスト編集で失敗")
            return False
        
        # 3. 無音削除
        print("\n[Step 3] 無音削除...")
        success, keep_ranges = test_silence_removal()
        if not success:
            print("✗ 無音削除で失敗")
            return False
        
        # 4. 動画エクスポート
        print("\n[Step 4] 動画エクスポート...")
        success = test_video_export(keep_ranges)
        if not success:
            print("✗ 動画エクスポートで失敗")
            return False
        
        # 5. XMLエクスポート
        print("\n[Step 5] XMLエクスポート...")
        success = test_xml_export()
        if not success:
            print("✗ XMLエクスポートで失敗")
            return False
        
        print("\n✓ 統合ワークフロー成功！")
        return True
        
    except Exception as e:
        print(f"\n✗ 統合ワークフローエラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """メインテスト実行"""
    print("TextffCut Docker包括的機能テスト")
    print("=" * 60)
    
    # 出力ディレクトリを作成
    os.makedirs('/app/output', exist_ok=True)
    
    # 個別テスト
    results = {
        '文字起こし': test_transcription()[0],
        'テキスト編集': test_text_editing(),
        '無音削除': test_silence_removal()[0],
        '動画エクスポート': test_video_export(),
        'XMLエクスポート': test_xml_export(),
        '統合ワークフロー': test_integration_workflow()
    }
    
    print("\n" + "="*60)
    print("  テスト結果サマリー")
    print("="*60)
    
    for name, success in results.items():
        status = "✓ 成功" if success else "✗ 失敗"
        print(f"{name}: {status}")
    
    # 全体の結果
    all_passed = all(results.values())
    print(f"\n全体結果: {'✓ すべて成功' if all_passed else '✗ 一部失敗'}")
    
    if not all_passed:
        print("\n失敗したテスト:")
        for name, success in results.items():
            if not success:
                print(f"  - {name}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())