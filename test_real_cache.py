#!/usr/bin/env python3
"""
実際のキャッシュデータを使用した動作確認
"""

import sys
import os
import json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from domain.entities.text_difference import DifferenceType
from config import Config

def main():
    print("=== 実際のキャッシュデータでのテスト ===\n")
    
    # キャッシュファイルのパス
    cache_path = "/Users/naoki/myProject/TextffCut/videos/（朝ラジオ）習慣が続かないのはモチベーション次第で辞めるから_original_TextffCut/transcriptions/whisper-1_api.json"
    
    if not os.path.exists(cache_path):
        print(f"キャッシュファイルが見つかりません: {cache_path}")
        return
    
    # キャッシュを読み込み
    config = Config()
    gateway = TranscriptionGatewayAdapter(config)
    
    # キャッシュファイルから直接読み込み
    with open(cache_path, 'r', encoding='utf-8') as f:
        cache_data = json.load(f)
    
    # TranscriptionResultに変換
    from domain.entities.transcription import TranscriptionResult
    transcription_result = TranscriptionResult.from_legacy_format(cache_data)
    
    print(f"1. キャッシュデータの確認:")
    print(f"   セグメント数: {len(transcription_result.segments)}")
    print(f"   最初のセグメントのtext: {transcription_result.segments[0].text[:50]}...")
    print(f"   words数: {len(transcription_result.segments[0].words) if transcription_result.segments[0].words else 0}")
    
    # TranscriptionResult.textの確認
    print(f"\n2. TranscriptionResult.text:")
    full_text_with_spaces = transcription_result.text
    print(f"   長さ: {len(full_text_with_spaces)}文字")
    print(f"   最初の50文字: {full_text_with_spaces[:50]}")
    
    # CharacterArrayBuilderで構築
    builder = CharacterArrayBuilder()
    char_array, full_text_from_words = builder.build_from_transcription(transcription_result)
    
    print(f"\n3. CharacterArrayBuilderで構築したテキスト:")
    print(f"   長さ: {len(full_text_from_words)}文字")
    print(f"   最初の50文字: {full_text_from_words[:50]}")
    
    # 差分を確認
    print(f"\n4. 両者の差分:")
    print(f"   長さの差: {len(full_text_with_spaces) - len(full_text_from_words)}文字")
    
    # スペースの位置を特定
    space_positions = []
    for i, char in enumerate(full_text_with_spaces):
        if char == ' ':
            space_positions.append(i)
    
    print(f"   スペースの数: {len(space_positions)}")
    if space_positions:
        print(f"   最初の5個のスペース位置: {space_positions[:5]}")
        for pos in space_positions[:3]:
            start = max(0, pos - 10)
            end = min(len(full_text_with_spaces), pos + 10)
            print(f"     位置{pos}: ...{full_text_with_spaces[start:pos]}[SPACE]{full_text_with_spaces[pos+1:end]}...")
    
    # ユーザーが報告した問題のテキストで検証
    print(f"\n5. 実際の問題で検証:")
    
    # 問題の編集テキスト（ユーザーの例から）
    edited_text = "バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか"
    
    # ゲートウェイで処理
    gateway = SequenceMatcherTextProcessorGateway()
    
    # TranscriptionResultを設定
    gateway.set_transcription_result(transcription_result)
    
    # 差分検出
    diff = gateway.find_differences("dummy", edited_text)  # original_textは無視される
    
    print(f"\n   差分検出結果:")
    for i, (diff_type, text, positions) in enumerate(diff.differences):
        print(f"   {i+1}. {diff_type.value}: '{text}' (長さ: {len(text)})")
        if diff_type == DifferenceType.DELETED and text in ["の", "で"]:
            print(f"      ⚠️ 問題の文字が検出されました！")
    
    # 「の」と「で」の位置を確認
    print(f"\n6. 問題の文字の詳細調査:")
    for problem_char in ["の", "で"]:
        print(f"\n   '{problem_char}'の分析:")
        
        # wordsベースのテキストでの位置
        positions_in_words = []
        for i, char in enumerate(full_text_from_words):
            if char == problem_char:
                positions_in_words.append(i)
        
        print(f"     wordsテキストでの出現数: {len(positions_in_words)}")
        if positions_in_words:
            print(f"     最初の3個の位置: {positions_in_words[:3]}")
            
        # 編集テキストでの位置
        cleaned_edited = gateway.normalize_for_comparison(gateway.remove_boundary_markers(edited_text))
        positions_in_edited = []
        for i, char in enumerate(cleaned_edited):
            if char == problem_char:
                positions_in_edited.append(i)
        
        print(f"     編集テキストでの出現数: {len(positions_in_edited)}")
        if positions_in_edited:
            print(f"     位置: {positions_in_edited}")

if __name__ == "__main__":
    main()