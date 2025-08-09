#!/usr/bin/env python3
"""
エッジケースの分析と最適化ポイントの特定
"""
import json

# サンプルデータでエッジケースを確認
json_path = "videos/（朝ラジオ）誰しも主人公になりたい時代は「あやかる」を重視した方がいい_original_TextffCut/transcriptions/whisper-1_api.json"

with open(json_path, encoding="utf-8") as f:
    data = json.load(f)

print("=== エッジケース分析 ===")

# 1. 全てのwordがタイムスタンプを持たないセグメント
print("\n1. タイムスタンプ欠落率の高いセグメント:")
for i, seg in enumerate(data["segments"]):
    if "words" in seg and seg["words"]:
        null_count = sum(1 for w in seg["words"] if w.get("start") is None or w.get("end") is None)
        null_ratio = null_count / len(seg["words"])
        if null_ratio > 0.5:
            print(f"   セグメント{i}: {null_ratio:.1%} ({null_count}/{len(seg['words'])}) - {seg['text'][:30]}...")

# 2. 非常に短いセグメント
print("\n2. 非常に短いセグメント（1秒未満）:")
for i, seg in enumerate(data["segments"]):
    duration = seg["end"] - seg["start"]
    if duration < 1.0:
        print(f"   セグメント{i}: {duration:.2f}秒 - {seg['text'][:30]}...")

# 3. 非常に長いセグメント
print("\n3. 非常に長いセグメント（30秒以上）:")
for i, seg in enumerate(data["segments"]):
    duration = seg["end"] - seg["start"]
    if duration > 30:
        print(f"   セグメント{i}: {duration:.2f}秒 - {seg['text'][:30]}...")

# 4. 連続するnullタイムスタンプ
print("\n4. 連続するnullタイムスタンプの最大数:")
max_consecutive_nulls = 0
current_consecutive_nulls = 0

for seg in data["segments"]:
    if "words" in seg and seg["words"]:
        for word in seg["words"]:
            if word.get("start") is None:
                current_consecutive_nulls += 1
                max_consecutive_nulls = max(max_consecutive_nulls, current_consecutive_nulls)
            else:
                current_consecutive_nulls = 0

print(f"   最大連続nullタイムスタンプ数: {max_consecutive_nulls}")

# 5. パフォーマンステスト用のシミュレーション
print("\n5. パフォーマンス最適化ポイント:")

# 現在の実装の問題点
print("\n   a) TextProcessorインスタンスの重複作成")
print("      - 問題: _get_timestamp_for_position内で毎回新しいインスタンスを作成")
print("      - 影響: メモリ使用量の増加、処理速度の低下")
print("      - 解決策: self参照を正しく使用する")

print("\n   b) 重複した検索処理")
print("      - 問題: 同じセグメントを複数回検索")
print("      - 影響: O(n*m)の計算量")
print("      - 解決策: キャッシュ機構の導入")

print("\n   c) 大量のログ出力")
print("      - 問題: 各word推定でINFO/WARNINGログを出力")
print("      - 影響: I/O負荷、ログファイルの肥大化")
print("      - 解決策: ログレベルの調整、バッチログ出力")

# 6. メモリ最適化の提案
print("\n6. メモリ最適化の提案:")
print("   - 音声プレビュー用の一時ファイル管理")
print("   - 大規模な文字起こし結果のストリーミング処理")
print("   - 不要なデータ構造のガベージコレクション")
