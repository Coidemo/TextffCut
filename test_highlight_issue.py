#!/usr/bin/env python3
"""
赤ハイライト問題の調査
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment, Word
from domain.entities.text_difference import DifferenceType
from uuid import uuid4

def create_test_data():
    """テスト用のTranscriptionResult作成"""
    # ユーザーのスクリーンショットから推測されるテキスト
    segments = []
    
    full_text = "バイアスがかかってしまわないために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものをレビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないのでバイアスに気づくどころか自分で何考えているかもわからないという状態になっているので地説でもいいので文章化したほうがいいんじゃないかなと思ってます"
    
    words = []
    current_time = 0.0
    for char in full_text:
        words.append(Word(word=char, start=current_time, end=current_time + 0.1))
        current_time += 0.1
    
    segments.append(TranscriptionSegment(
        id=str(uuid4()),
        text=full_text,
        start=0.0,
        end=current_time,
        words=words
    ))
    
    return TranscriptionResult(
        id=str(uuid4()),
        video_id="test_video",
        language="ja",
        segments=segments,
        duration=current_time
    )

def main():
    print("=== 赤ハイライト問題の調査 ===\n")
    
    # テストデータ作成
    transcription_result = create_test_data()
    
    # CharacterArrayBuilderで構築
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(transcription_result)
    
    print(f"1. 元のテキスト:")
    print(f"   長さ: {len(full_text)}文字")
    print(f"   内容: {full_text[:50]}...")
    
    # ユーザーの編集テキスト（スクリーンショットから、少し変更）
    # 「の」や「で」が追加されているケース
    edited_text = """バイアスがかかってしまわないために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったもののをレビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないのでバイアスに気づくどころか自分で何考えているかもわからないという状態になっているので地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""
    
    print(f"\n2. 編集テキスト:")
    print(f"   長さ: {len(edited_text)}文字")
    
    # ゲートウェイで処理
    gateway = SequenceMatcherTextProcessorGateway()
    gateway.set_transcription_result(transcription_result)
    
    # 差分検出
    diff = gateway.find_differences("dummy", edited_text)
    
    print(f"\n3. 差分検出結果:")
    unchanged_count = 0
    deleted_count = 0
    added_count = 0
    
    for i, (diff_type, text, positions) in enumerate(diff.differences):
        if diff_type == DifferenceType.UNCHANGED:
            unchanged_count += len(text)
        elif diff_type == DifferenceType.DELETED:
            deleted_count += len(text)
        elif diff_type == DifferenceType.ADDED:
            added_count += len(text)
            print(f"   追加: '{text}' (長さ: {len(text)})")
    
    print(f"\n   統計:")
    print(f"   - 共通: {unchanged_count}文字")
    print(f"   - 削除: {deleted_count}文字")
    print(f"   - 追加: {added_count}文字")
    
    # 削除処理のシミュレーション
    print(f"\n4. 削除処理のシミュレーション:")
    
    # 現在の実装（UNCHANGEDのみ結合）
    cleaned_text = "".join(
        text for diff_type, text, _ in diff.differences if diff_type == DifferenceType.UNCHANGED
    )
    
    print(f"   現在の実装での結果: {len(cleaned_text)}文字")
    print(f"   元の編集テキスト: {len(edited_text)}文字")
    print(f"   差: {len(edited_text) - len(cleaned_text)}文字")
    
    # 詳細な差分表示
    print(f"\n   差分の詳細:")
    for i, (diff_type, text, positions) in enumerate(diff.differences):
        print(f"   {i+1}. {diff_type.value}: '{text[:20]}{'...' if len(text) > 20 else ''}' (長さ: {len(text)})")
    
    print(f"\n   削除後のテキスト比較:")
    print(f"   編集前: {edited_text[:50]}...")
    print(f"   削除後: {cleaned_text[:50]}...")
    
    # 問題の分析
    print(f"\n5. 問題の分析:")
    if added_count == 0 and len(edited_text) == len(full_text):
        print("   ⚠️ 追加文字が検出されていないのに、エラー表示される可能性があります")
        print("   原因: テキストは同じだが、文字の順序や位置が異なる可能性")
    
    # より良い判定方法の提案
    print(f"\n6. 改善案:")
    # 編集テキストに元のテキストにない文字が含まれているかチェック
    original_chars = set(full_text)
    edited_chars = set(edited_text)
    truly_added_chars = edited_chars - original_chars
    
    print(f"   本当に追加された文字（文字種）: {truly_added_chars}")
    print(f"   この方法なら誤検出を防げる可能性があります")

if __name__ == "__main__":
    main()