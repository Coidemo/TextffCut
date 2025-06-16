#!/usr/bin/env python3
"""
SRTエクスポート機能のテストスクリプト
"""
import sys
from pathlib import Path
from config import config
from core import TranscriptionResult, TranscriptionSegment, SRTExporter

def test_srt_export():
    """SRTエクスポートの基本的なテスト"""
    
    # テスト用の文字起こし結果を作成
    segments = [
        TranscriptionSegment(
            start=0.0,
            end=2.5,
            text="こんにちは、今日は良い天気ですね。",
            words=None
        ),
        TranscriptionSegment(
            start=3.0,
            end=5.8,
            text="明日も晴れるといいですね。",
            words=None
        ),
        TranscriptionSegment(
            start=6.2,
            end=9.1,
            text="週末は公園に行きたいです。",
            words=None
        ),
        TranscriptionSegment(
            start=10.0,
            end=13.5,
            text="桜が咲いているかもしれません。",
            words=None
        )
    ]
    
    transcription_result = TranscriptionResult(
        language="ja",
        segments=segments,
        original_audio_path="test_video.mp4",
        model_size="medium",
        processing_time=10.0
    )
    
    # SRTエクスポーターを作成
    exporter = SRTExporter(config)
    
    # テスト1: 全セグメントをエクスポート
    print("テスト1: 全セグメントのエクスポート")
    output_path_full = Path("test_output_full.srt")
    try:
        success = exporter.export(
            transcription_result=transcription_result,
            output_path=str(output_path_full),
            time_ranges=None
        )
        if success:
            print(f"✅ 成功: {output_path_full}")
            with open(output_path_full, 'r', encoding='utf-8') as f:
                print("--- 出力内容 ---")
                print(f.read())
                print("--- 終了 ---")
            output_path_full.unlink()  # クリーンアップ
        else:
            print("❌ 失敗")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    
    # テスト2: 時間範囲を指定してエクスポート
    print("\nテスト2: 時間範囲指定のエクスポート（2-8秒）")
    output_path_range = Path("test_output_range.srt")
    time_ranges = [(2.0, 8.0)]
    try:
        success = exporter.export(
            transcription_result=transcription_result,
            output_path=str(output_path_range),
            time_ranges=time_ranges
        )
        if success:
            print(f"✅ 成功: {output_path_range}")
            with open(output_path_range, 'r', encoding='utf-8') as f:
                print("--- 出力内容 ---")
                print(f.read())
                print("--- 終了 ---")
            output_path_range.unlink()  # クリーンアップ
        else:
            print("❌ 失敗")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    
    # テスト3: 複数の時間範囲
    print("\nテスト3: 複数時間範囲のエクスポート")
    output_path_multi = Path("test_output_multi.srt")
    time_ranges_multi = [(0.0, 3.0), (6.0, 14.0)]
    try:
        success = exporter.export(
            transcription_result=transcription_result,
            output_path=str(output_path_multi),
            time_ranges=time_ranges_multi
        )
        if success:
            print(f"✅ 成功: {output_path_multi}")
            with open(output_path_multi, 'r', encoding='utf-8') as f:
                print("--- 出力内容 ---")
                print(f.read())
                print("--- 終了 ---")
            output_path_multi.unlink()  # クリーンアップ
        else:
            print("❌ 失敗")
    except Exception as e:
        print(f"❌ エラー: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nテスト完了！")

if __name__ == "__main__":
    test_srt_export()