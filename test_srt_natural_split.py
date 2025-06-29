#!/usr/bin/env python3
"""
自然なSRTエントリ分割のテストスクリプト
"""

import sys
from pathlib import Path

# プロジェクトのルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.srt_diff_exporter import SRTDiffExporter


def test_distribute_by_semantics() -> None:
    """意味的な分割のテスト"""
    print("=== 意味的な分割のテスト ===")

    exporter = SRTDiffExporter(Config())

    # テストケース1: 木曜日の例
    text = "6月5日の木曜日かな木曜日はい8時でございます"
    result = exporter._distribute_by_semantics(text, 3)

    print(f"\n入力: '{text}'")
    print("分割数: 3")
    print("結果:")
    for i, segment in enumerate(result, 1):
        print(f"  {i}: '{segment}' ({len(segment)}文字)")

    # 期待される結果
    expected = ["6月5日の木曜日かな", "木曜日", "はい8時でございます"]
    if result == expected:
        print("✅ 期待通りの分割です！")
    else:
        print("❌ 期待と異なる分割です")
        print(f"期待: {expected}")

    # テストケース2: 2分割の場合
    print("\n--- 2分割の場合 ---")
    result2 = exporter._distribute_by_semantics(text, 2)
    print("結果:")
    for i, segment in enumerate(result2, 1):
        print(f"  {i}: '{segment}' ({len(segment)}文字)")

    # テストケース3: 別のテキスト
    print("\n--- 別のテキストのテスト ---")
    text2 = "今日は月曜日かな火曜日かな水曜日だったかな"
    result3 = exporter._distribute_by_semantics(text2, 3)
    print(f"\n入力: '{text2}'")
    print("結果:")
    for i, segment in enumerate(result3, 1):
        print(f"  {i}: '{segment}' ({len(segment)}文字)")


def test_mock_silence_removal() -> None:
    """無音削除シミュレーションのテスト"""
    print("\n\n=== 無音削除シミュレーション ===")

    exporter = SRTDiffExporter(Config())
    # 設定を適用（11文字×2行）
    exporter.max_line_length = 11
    exporter.max_lines = 2

    # モックデータ
    text = "6月5日の木曜日かな木曜日はい8時でございます"
    original_range = (35.5, 40.8)  # 5.3秒

    # 無音削除後の3つのセグメント（合計4.3秒）
    mapped_ranges = [(0.0, 1.5), (1.6, 2.5), (2.6, 4.3)]  # 1.5秒  # 0.9秒  # 1.7秒

    # 単語タイミング情報（簡易版）
    words_with_timing = [
        {"text": "6月", "start": 35.5, "end": 35.8},
        {"text": "5日", "start": 35.8, "end": 36.1},
        {"text": "の", "start": 36.1, "end": 36.2},
        {"text": "木曜日", "start": 36.2, "end": 36.6},
        {"text": "かな", "start": 36.6, "end": 36.9},
        {"text": "木曜日", "start": 37.2, "end": 37.6},  # 無音後
        {"text": "はい", "start": 38.0, "end": 38.2},  # 無音後
        {"text": "8時", "start": 38.2, "end": 38.5},
        {"text": "で", "start": 38.5, "end": 38.6},
        {"text": "ございます", "start": 38.6, "end": 39.2},
    ]

    print(f"入力テキスト: '{text}'")
    print(f"元の時間範囲: {original_range}")
    print(f"無音削除後の範囲: {mapped_ranges}")

    # テキスト分配
    segments = exporter._distribute_text_to_segments(text, original_range, mapped_ranges, words_with_timing)

    print("\n分配結果:")
    for i, (segment, time_range) in enumerate(zip(segments, mapped_ranges, strict=False), 1):
        print(f"  セグメント{i}: '{segment}' [{time_range[0]:.1f}-{time_range[1]:.1f}秒]")

    # セグメントエントリを作成
    segment_entries = []
    for text_seg, (start_time, end_time) in zip(segments, mapped_ranges, strict=False):
        if text_seg.strip():
            segment_entries.append({"text": text_seg.strip(), "start_time": start_time, "end_time": end_time})

    print("\n結合前のエントリ:")
    for i, entry in enumerate(segment_entries, 1):
        print(f"  エントリ{i}: '{entry['text']}' [{entry['start_time']:.1f}-{entry['end_time']:.1f}秒]")

    # 結合処理をテスト
    merged_entries = exporter._smart_segment_merge(segment_entries)

    print("\n結合後のエントリ:")
    for i, entry in enumerate(merged_entries, 1):
        print(f"  エントリ{i}: '{entry['text']}' [{entry['start_time']:.1f}-{entry['end_time']:.1f}秒]")

    # 改行処理も確認
    print("\n改行処理後:")
    for i, entry in enumerate(merged_entries, 1):
        processed = exporter._apply_natural_line_breaks(entry["text"])
        print(f"  エントリ{i}: '{processed}'")


if __name__ == "__main__":
    test_distribute_by_semantics()
    test_mock_silence_removal()

    print("\n\n=== テスト完了 ===")
