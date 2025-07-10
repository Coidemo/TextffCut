#!/usr/bin/env python3
"""
CharacterArrayBuilder修正後の動作確認テスト
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType
from uuid import uuid4

# テストデータ作成
def create_test_transcription():
    """テスト用のTranscriptionResultを作成（実際のデータに近い形式）"""
    segments = []
    
    # セグメント1: バイアスがかかってしまわないために一定の指針となる考え方などありますか
    # 注：実際のAPIデータではセグメントのtextにスペースが含まれることがある
    segment1_text = "バイアスがかかってしまわないために一定の指針となる考え方などありますか"
    words1 = []
    current_time = 0.0
    for char in segment1_text:
        words1.append(Word(word=char, start=current_time, end=current_time + 0.1))
        current_time += 0.1
    
    segments.append(TranscriptionSegment(
        id=str(uuid4()),
        text=segment1_text,  # スペースなし
        start=0.0,
        end=current_time,
        words=words1
    ))
    
    # セグメント2のテキスト（スペース付き）
    segment2_text = "指針となる考えを持つというよりかは 考えをちゃんと言語化してアウトプットして"  # スペースあり
    segment2_words_text = "指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして"  # wordsはスペースなし
    words2 = []
    for char in segment2_words_text:
        words2.append(Word(word=char, start=current_time, end=current_time + 0.1))
        current_time += 0.1
    
    segments.append(TranscriptionSegment(
        id=str(uuid4()),
        text=segment2_text,  # スペース付き（APIの実際の動作を再現）
        start=words2[0].start,
        end=current_time,
        words=words2
    ))
    
    return TranscriptionResult(
        id=str(uuid4()),
        video_id="test_video",
        language="ja",
        segments=segments,
        duration=current_time
    )

# メイン処理
def main():
    print("=== CharacterArrayBuilder修正後の動作確認 ===\n")
    
    # TranscriptionResultを作成
    transcription_result = create_test_transcription()
    
    # TranscriptionResult.textの確認（セグメントのtextを結合）
    print(f"1. TranscriptionResult.text（セグメントtext結合）:")
    print(f"   内容: {transcription_result.text}")
    print(f"   長さ: {len(transcription_result.text)}文字")
    print(f"   スペース含む: {'はい' if ' ' in transcription_result.text else 'いいえ'}\n")
    
    # CharacterArrayBuilderで文字配列を構築
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(transcription_result)
    
    print(f"2. CharacterArrayBuilderで構築したテキスト:")
    print(f"   内容: {full_text}")
    print(f"   長さ: {len(full_text)}文字")
    print(f"   スペース含む: {'はい' if ' ' in full_text else 'いいえ'}\n")
    
    # ユーザーの編集テキスト
    edited_text = "バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか"
    
    # テキスト処理ゲートウェイで差分検出
    gateway = SequenceMatcherTextProcessorGateway()
    
    print("3. 修正前の動作（TranscriptionResult未設定）:")
    # TranscriptionResultを設定せずに実行（セグメントtextを使用）
    diff1 = gateway.find_differences(transcription_result.text, edited_text)
    
    deleted_count1 = sum(1 for d in diff1.differences if d[0] == DifferenceType.DELETED)
    print(f"   削除された文字数: {deleted_count1}")
    if deleted_count1 > 0:
        print("   削除された文字:")
        for diff_type, text, _ in diff1.differences:
            if diff_type == DifferenceType.DELETED:
                print(f"     '{text}'")
    
    print("\n4. 修正後の動作（TranscriptionResult設定）:")
    # TranscriptionResultを設定して実行（wordsから構築）
    gateway.set_transcription_result(transcription_result)
    diff2 = gateway.find_differences(transcription_result.text, edited_text)  # original_textは無視される
    
    deleted_count2 = sum(1 for d in diff2.differences if d[0] == DifferenceType.DELETED)
    print(f"   削除された文字数: {deleted_count2}")
    if deleted_count2 > 0:
        print("   削除された文字:")
        for diff_type, text, _ in diff2.differences:
            if diff_type == DifferenceType.DELETED:
                print(f"     '{text}'")
    
    # 共通部分の確認
    print("\n5. 共通部分の確認:")
    unchanged_text = ""
    for diff_type, text, _ in diff2.differences:
        if diff_type == DifferenceType.UNCHANGED:
            unchanged_text += text
    
    print(f"   共通部分: {unchanged_text}")
    print(f"   カバー率: {len(unchanged_text) / len(full_text) * 100:.1f}%")
    
    print("\n6. 結論:")
    if deleted_count2 == 0 or deleted_count2 < deleted_count1:
        print("   ✅ 修正により問題が改善されました！")
        print("   CharacterArrayBuilderのテキストを使用することで、")
        print("   セグメントtextのスペースによる不整合が解消されました。")
    else:
        print("   ❌ まだ問題が残っています。")

if __name__ == "__main__":
    main()