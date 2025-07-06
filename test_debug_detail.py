#!/usr/bin/env python3
"""
_detect_excerpt_differences メソッドの詳細デバッグ
"""

from domain.entities import TranscriptionResult, TranscriptionSegment
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.entities.text_difference import DifferenceType

# 実際のシナリオ
original_text = """上司からのフィードバック。まず自分ができてから言えよという気持ちになってしまうことがあります。"""
edited_text = """上司からのフィードバック。まず自分ができてから言えよという気持ちになってしまうことがあります。"""

# TextDifferenceDetectorを使用
detector = TextDifferenceDetector()

print("=== テストケース1: 完全一致（句読点あり） ===")
print(f"元: {original_text}")
print(f"編: {edited_text}")
print(f"一致: {original_text == edited_text}")

# 句読点を除去
edited_no_punct = detector._remove_punctuation(edited_text)
original_no_punct = detector._remove_punctuation(original_text)
print(f"\n句読点除去後:")
print(f"元: {original_no_punct}")
print(f"編: {edited_no_punct}")
print(f"一致: {original_no_punct == edited_no_punct}")

# 位置検索
position = original_text.find(edited_no_punct)
print(f"\n位置検索（句読点除去後）: {position}")

# 問題の核心
print("\n=== 問題の核心 ===")
print("line 81 の excerpt_end 計算:")
print(f"position = {position}")
print(f"len(edited_no_punct) = {len(edited_no_punct)}")
print(f"excerpt_end = {position + len(edited_no_punct)}")

if position != -1:
    excerpt_end = position + len(edited_no_punct)
    original_excerpt = original_text[position:excerpt_end]
    print(f"\n抽出された部分: '{original_excerpt}'")
    print(f"編集テキスト: '{edited_text}'")
    print(f"一致するか: {original_excerpt == edited_text}")
    
print("\n=== 修正案 ===")
print("問題: 句読点を除去したテキストで検索しているが、")
print("      句読点を除去した長さで切り出している")
print("解決: 元のテキストで検索するか、")
print("      または正しい終了位置を計算する必要がある")