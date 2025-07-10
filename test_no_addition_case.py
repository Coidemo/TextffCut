#!/usr/bin/env python3
"""
追加文字がないケースのテスト
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
    print("=== 追加文字がないケースのテスト ===\n")
    
    # テストケース1: 完全一致
    full_text = "バイアスがかかってしまわないために指針となる考え方などありますか"
    edited_text = "バイアスがかかってしまわないために指針となる考え方などありますか"
    
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
    
    # 処理
    gateway = SequenceMatcherTextProcessorGateway()
    gateway.set_transcription_result(transcription_result)
    diff = gateway.find_differences("dummy", edited_text)
    
    print("1. 完全一致のケース:")
    print(f"   元: {len(full_text)}文字")
    print(f"   編集: {len(edited_text)}文字")
    
    added_count = sum(1 for d in diff.differences if d[0] == DifferenceType.ADDED)
    print(f"   追加文字数: {added_count}")
    
    # テストケース2: スペースの問題をシミュレート
    print("\n2. スペース問題のシミュレーション:")
    
    # セグメントのtextにスペースを追加（APIの実際の動作）
    segments_with_space = [TranscriptionSegment(
        id=str(uuid4()),
        text=full_text[:10] + " " + full_text[10:],  # スペースを挿入
        start=0.0,
        end=current_time,
        words=words  # wordsは変更なし
    )]
    
    transcription_result_with_space = TranscriptionResult(
        id=str(uuid4()),
        video_id="test_video",
        language="ja",
        segments=segments_with_space,
        duration=current_time
    )
    
    # CharacterArrayBuilderで構築（修正前の動作をシミュレート）
    print(f"   セグメントtext: '{transcription_result_with_space.text}' ({len(transcription_result_with_space.text)}文字)")
    
    # 修正前の動作（TranscriptionResult.textを使用）
    gateway_old = SequenceMatcherTextProcessorGateway()
    diff_old = gateway_old.find_differences(transcription_result_with_space.text, edited_text)
    
    added_old = sum(len(t) for d, t, _ in diff_old.differences if d == DifferenceType.ADDED)
    deleted_old = sum(len(t) for d, t, _ in diff_old.differences if d == DifferenceType.DELETED)
    
    print(f"   修正前: 追加{added_old}文字, 削除{deleted_old}文字")
    
    # 修正後の動作（CharacterArrayBuilderを使用）
    gateway_new = SequenceMatcherTextProcessorGateway()
    gateway_new.set_transcription_result(transcription_result_with_space)
    diff_new = gateway_new.find_differences("dummy", edited_text)
    
    added_new = sum(len(t) for d, t, _ in diff_new.differences if d == DifferenceType.ADDED)
    deleted_new = sum(len(t) for d, t, _ in diff_new.differences if d == DifferenceType.DELETED)
    
    print(f"   修正後: 追加{added_new}文字, 削除{deleted_new}文字")
    
    print("\n3. 結論:")
    if added_old > 0 and added_new == 0:
        print("   ✅ 修正により、スペース問題による誤検出が解消されました！")
    else:
        print("   🤔 まだ問題が残っている可能性があります")

if __name__ == "__main__":
    main()