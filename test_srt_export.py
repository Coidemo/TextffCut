#!/usr/bin/env python3
"""
SRTエクスポート機能のテストスクリプト
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from core.export import SRTExporter
from core.transcription import TranscriptionResult
from config import Config

def create_test_transcription():
    """テスト用の文字起こし結果を作成"""
    segments = [
        {
            'start': 0.0,
            'end': 3.5,
            'text': 'こんにちは、今日は天気がいいですね。散歩に行きましょうか。'
        },
        {
            'start': 3.5,
            'end': 8.2,
            'text': 'This is a test of the subtitle generation system with English text that might be quite long.'
        },
        {
            'start': 8.2,
            'end': 15.0,
            'text': '長い日本語のテキストです。これは字幕生成システムのテストで、設定した文字数と行数に応じて適切に分割されることを確認します。句読点での分割も確認できます。'
        },
        {
            'start': 15.0,
            'end': 20.0,
            'text': '短いテキスト。'
        }
    ]
    
    # TranscriptionResultオブジェクトを作成
    result = type('TranscriptionResult', (), {
        'segments': segments,
        'text': ' '.join(seg['text'] for seg in segments),
        'language': 'ja',
        'model_size': 'test'
    })()
    
    return result

def test_srt_export():
    """SRTエクスポートのテスト"""
    print("=== SRTエクスポートテスト開始 ===\n")
    
    # テスト設定
    config = Config()
    exporter = SRTExporter(config)
    
    # テスト用文字起こし結果
    transcription = create_test_transcription()
    
    # テスト1: 基本的なエクスポート（デフォルト設定）
    print("テスト1: デフォルト設定（2行、40文字）")
    output_path = "test_output_default.srt"
    result = exporter.export(
        transcription_result=transcription,
        output_path=output_path
    )
    
    if result:
        print(f"✅ エクスポート成功: {output_path}")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("--- 出力内容 ---")
            print(content)
            print("--- 終了 ---\n")
        Path(output_path).unlink()  # テストファイルを削除
    else:
        print("❌ エクスポート失敗\n")
    
    # テスト2: カスタム設定（1行、20文字）
    print("テスト2: カスタム設定（1行、20文字）")
    output_path = "test_output_custom.srt"
    result = exporter.export(
        transcription_result=transcription,
        output_path=output_path,
        max_lines_per_subtitle=1,
        max_chars_per_line=20
    )
    
    if result:
        print(f"✅ エクスポート成功: {output_path}")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("--- 出力内容 ---")
            print(content)
            print("--- 終了 ---\n")
        Path(output_path).unlink()  # テストファイルを削除
    else:
        print("❌ エクスポート失敗\n")
    
    # テスト3: 時間範囲指定
    print("テスト3: 時間範囲指定（5-16秒のみ）")
    output_path = "test_output_range.srt"
    result = exporter.export(
        transcription_result=transcription,
        output_path=output_path,
        time_ranges=[(5.0, 16.0)],
        max_lines_per_subtitle=2,
        max_chars_per_line=30
    )
    
    if result:
        print(f"✅ エクスポート成功: {output_path}")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("--- 出力内容 ---")
            print(content)
            print("--- 終了 ---\n")
        Path(output_path).unlink()  # テストファイルを削除
    else:
        print("❌ エクスポート失敗\n")
    
    # テスト4: 複数の時間範囲
    print("テスト4: 複数の時間範囲（0-4秒、14-20秒）")
    output_path = "test_output_multi_range.srt"
    result = exporter.export(
        transcription_result=transcription,
        output_path=output_path,
        time_ranges=[(0.0, 4.0), (14.0, 20.0)],
        max_lines_per_subtitle=3,
        max_chars_per_line=50
    )
    
    if result:
        print(f"✅ エクスポート成功: {output_path}")
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            print("--- 出力内容 ---")
            print(content)
            print("--- 終了 ---\n")
        Path(output_path).unlink()  # テストファイルを削除
    else:
        print("❌ エクスポート失敗\n")
    
    print("=== テスト完了 ===")

if __name__ == '__main__':
    test_srt_export()