#!/usr/bin/env python3
"""
_detect_excerpt_differences メソッドのデバッグ
"""

from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.entities.text_difference import DifferenceType

# テストデータ
original_text = """おはようございます。今日は良い天気ですね。
明日の予定について話しましょう。
会議は午後2時からです。
上司からのフィードバック"""

edited_text = """上司からのフィードバック"""

# TextDifferenceDetectorを使用
detector = TextDifferenceDetector()

# デバッグ情報を追加しながら実行
print("=== _detect_excerpt_differences のデバッグ ===")
print(f"元のテキスト長: {len(original_text)}文字")
print(f"編集テキスト長: {len(edited_text)}文字")
print(f"編集/元の比率: {len(edited_text) / len(original_text) * 100:.1f}%")
print(f"0.8閾値: {len(original_text) * 0.8}文字")
print(f"抜粋として処理されるか: {len(edited_text) < len(original_text) * 0.8}")
print("")

# 句読点を除去
edited_no_punct = detector._remove_punctuation(edited_text)
print(f"句読点除去後: '{edited_no_punct}'")

# 位置を検索
position = original_text.find(edited_no_punct)
print(f"検索結果（句読点除去後）: {position}")
position_direct = original_text.find(edited_text)
print(f"検索結果（直接）: {position_direct}")
print("")

# 抜粋範囲
if position != -1:
    excerpt_end = position + len(edited_no_punct)
    original_excerpt = original_text[position:excerpt_end]
    print(f"抜粋範囲: {position} - {excerpt_end}")
    print(f"元の抜粋部分: '{original_excerpt}'")
    print(f"編集テキスト: '{edited_text}'")
    print(f"一致するか: {original_excerpt == edited_text}")
    print("")

# 差分検出を実行
differences = detector.detect_differences(original_text, edited_text, None)

print("=== 差分検出結果 ===")
for i, (diff_type, text, _) in enumerate(differences.differences):
    print(f"差分{i+1}: {diff_type.value}")
    print(f"  内容: '{text}'")
print("")

# _compare_texts メソッドをテスト
print("=== _compare_texts のテスト ===")
compare_result = detector._compare_texts(edited_text, edited_text, 0)
print(f"同じテキストを比較した結果: {compare_result}")
print("")

# 問題の根本原因を特定
print("=== 問題の分析 ===")
print("62行目で句読点を除去したテキストで検索しているが、")
print("82行目では句読点を除去する前の長さでスライスしている")
print(f"len(edited_no_punct) = {len(edited_no_punct)}")
print(f"len(edited_text) = {len(edited_text)}")
print("これが原因で正しい範囲が取得できていない可能性がある")