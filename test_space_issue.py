#!/usr/bin/env python3
"""
スペース問題の詳細な調査
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType
from uuid import uuid4

def main():
    print("=== スペース問題の調査 ===\n")
    
    # テストデータ（「の」「で」を含む）
    full_text = "ほとんどの人が自分の考えをちゃんとした文章で表現していないので"
    
    # TranscriptionResult作成
    words = []
    current_time = 0.0
    for char in full_text:
        words.append(Word(word=char, start=current_time, end=current_time + 0.1))
        current_time += 0.1
    
    segments = [TranscriptionSegment(
        id=str(uuid4()),
        text=full_text,
        start=0.0,
        end=current_time,
        words=words
    )]
    
    transcription_result = TranscriptionResult(
        id=str(uuid4()),
        video_id="test_video",
        language="ja",
        segments=segments,
        duration=current_time
    )
    
    # ゲートウェイ設定
    gateway = SequenceMatcherTextProcessorGateway()
    gateway.set_transcription_result(transcription_result)
    
    print(f"元のテキスト: '{full_text}'")
    print(f"長さ: {len(full_text)}文字\n")
    
    # ケース1: スペースなしの編集テキスト
    edited_text1 = "ほとんどの人が自分の考えをちゃんとした文章で表現していないので"
    print("ケース1: スペースなし")
    print(f"編集テキスト: '{edited_text1}'")
    
    # 正規化を確認
    normalized1 = gateway.normalize_for_comparison(edited_text1)
    print(f"正規化後: '{normalized1}'")
    print(f"元と同じ？: {full_text == normalized1}")
    
    diff1 = gateway.find_differences("dummy", edited_text1)
    added1 = sum(len(t) for d, t, _ in diff1.differences if d == DifferenceType.ADDED)
    print(f"追加文字数: {added1}\n")
    
    # ケース2: スペースありの編集テキスト
    edited_text2 = "ほとんど の 人が自分 の 考えをちゃんとした文章 で 表現していない の で"
    print("ケース2: スペースあり")
    print(f"編集テキスト: '{edited_text2}'")
    
    # 正規化を確認
    normalized2 = gateway.normalize_for_comparison(edited_text2)
    print(f"正規化後: '{normalized2}'")
    print(f"元と同じ？: {full_text == normalized2}")
    
    diff2 = gateway.find_differences("dummy", edited_text2)
    added2 = sum(len(t) for d, t, _ in diff2.differences if d == DifferenceType.ADDED)
    deleted2 = sum(len(t) for d, t, _ in diff2.differences if d == DifferenceType.DELETED)
    print(f"追加文字数: {added2}")
    print(f"削除文字数: {deleted2}")
    
    # 差分の詳細
    if diff2.differences:
        print("\n差分の詳細:")
        for i, (diff_type, text, pos) in enumerate(diff2.differences):
            print(f"  {i+1}. {diff_type.value}: '{text}' (位置: {pos})")
    
    # ケース3: 一部だけスペースあり
    edited_text3 = "ほとんどの人が自分の考えをちゃんとした文章で表現していないの で"
    print(f"\nケース3: 最後だけスペース")
    print(f"編集テキスト: '{edited_text3}'")
    
    normalized3 = gateway.normalize_for_comparison(edited_text3)
    print(f"正規化後: '{normalized3}'")
    
    diff3 = gateway.find_differences("dummy", edited_text3)
    added3 = sum(len(t) for d, t, _ in diff3.differences if d == DifferenceType.ADDED)
    print(f"追加文字数: {added3}")
    
    # 問題の特定
    print("\n問題の分析:")
    print("正規化処理が日本語文字間のスペースを除去しているが、")
    print("SequenceMatcherが文字位置を正確に追跡できていない可能性がある。")

if __name__ == "__main__":
    main()