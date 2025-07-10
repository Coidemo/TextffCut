#!/usr/bin/env python3
"""
削除ハイライトのテスト
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
    print("=== 削除ハイライトのテスト ===\n")
    
    # テストデータ
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
    
    # ケース1: スペースが含まれている編集テキスト
    edited_text = "ほとんど の 人が自分 の 考えをちゃんとした文章 で 表現していない の で"
    print(f"編集テキスト: '{edited_text}'")
    print(f"長さ: {len(edited_text)}文字")
    
    # 差分検出
    diff = gateway.find_differences("dummy", edited_text)
    
    # 削除後のテキストを計算（現在の削除ボタンの動作）
    remaining_text = "".join(
        text for diff_type, text, _ in diff.differences if diff_type == DifferenceType.UNCHANGED
    )
    
    print(f"\n削除後のテキスト: '{remaining_text}'")
    print(f"長さ: {len(remaining_text)}文字")
    
    # 削除される文字を特定
    deleted_chars = []
    remaining_chars = list(remaining_text)
    remaining_index = 0
    
    for i, char in enumerate(edited_text):
        if remaining_index < len(remaining_chars) and char == remaining_chars[remaining_index]:
            # この文字は残る
            remaining_index += 1
        else:
            # この文字は削除される
            deleted_chars.append((i, char))
    
    print(f"\n削除される文字: {len(deleted_chars)}個")
    for pos, char in deleted_chars:
        print(f"  位置{pos}: '{char}'")
    
    # 検証
    print(f"\n検証:")
    print(f"  編集テキストの長さ: {len(edited_text)}")
    print(f"  削除後のテキストの長さ: {len(remaining_text)}")
    print(f"  削除される文字数: {len(deleted_chars)}")
    print(f"  計算が正しい？: {len(edited_text) - len(deleted_chars) == len(remaining_text)}")
    
    # ケース2: より複雑な例
    print(f"\n\n--- ケース2: 文字も追加されている場合 ---")
    edited_text2 = "ほとんどXの人が自分Yの考えをちゃんとした文章Zで表現していないAので"
    print(f"編集テキスト: '{edited_text2}'")
    
    diff2 = gateway.find_differences("dummy", edited_text2)
    
    remaining_text2 = "".join(
        text for diff_type, text, _ in diff2.differences if diff_type == DifferenceType.UNCHANGED
    )
    
    print(f"削除後のテキスト: '{remaining_text2}'")
    
    # 削除される文字を特定
    deleted_chars2 = []
    remaining_chars2 = list(remaining_text2)
    remaining_index2 = 0
    
    for i, char in enumerate(edited_text2):
        if remaining_index2 < len(remaining_chars2) and char == remaining_chars2[remaining_index2]:
            remaining_index2 += 1
        else:
            deleted_chars2.append(char)
    
    print(f"削除される文字: {''.join(deleted_chars2)}")

if __name__ == "__main__":
    main()