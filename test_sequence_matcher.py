"""
SequenceMatcherとLCSアルゴリズムの比較テスト
"""

import json
from types import SimpleNamespace
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
from adapters.gateways.text_processing.search_based_lcs_gateway import SearchBasedLCSTextProcessorGateway
from domain.entities.transcription import TranscriptionResult
from adapters.converters.transcription_converter import TranscriptionConverter
from domain.use_cases.character_array_builder import CharacterArrayBuilder

# JSON to object converter
def dict_to_obj(d):
    if isinstance(d, dict):
        obj = SimpleNamespace()
        for k, v in d.items():
            setattr(obj, k, dict_to_obj(v))
        return obj
    elif isinstance(d, list):
        return [dict_to_obj(item) for item in d]
    else:
        return d

# 文字起こし結果を読み込む
with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    legacy_result = dict_to_obj(data)

# ドメイン形式に変換
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)

# CharacterArrayBuilderで再構築
builder = CharacterArrayBuilder()
char_array, full_text = builder.build_from_transcription(domain_result)

# 編集テキスト（スペースと改行を含む）
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

print("="*80)
print("SequenceMatcherとLCSの比較テスト")
print("="*80)
print(f"原文の長さ: {len(full_text)}文字")
print(f"編集テキストの長さ: {len(edited_text)}文字")
print()

# SequenceMatcherでテスト
print("【SequenceMatcherの結果】")
sm_gateway = SequenceMatcherTextProcessorGateway()
sm_diff = sm_gateway.find_differences(full_text, edited_text)

if sm_diff.differences:
    from domain.entities.text_difference import DifferenceType
    
    total_matched = 0
    match_count = 0
    
    print("\nマッチしたブロック:")
    for diff_type, text, positions in sm_diff.differences:
        if diff_type == DifferenceType.UNCHANGED:
            match_count += 1
            matched_len = len(text)
            total_matched += matched_len
            
            if positions and positions[0]:
                pos_start = positions[0][0]
                print(f"  ブロック{match_count}: 位置{pos_start}, 長さ{matched_len}文字")
                print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
    
    normalized_edited = sm_gateway.normalize_for_comparison(edited_text)
    coverage = (total_matched / len(normalized_edited)) * 100 if normalized_edited else 0
    print(f"\n合計マッチブロック数: {match_count}個")
    print(f"合計マッチ文字数: {total_matched}文字")
    print(f"カバー率: {coverage:.1f}%")

print("\n" + "-"*40 + "\n")

# LCS（SearchBasedLCS）でテスト
print("【LCS（SearchBasedLCS）の結果】")
lcs_gateway = SearchBasedLCSTextProcessorGateway()
lcs_diff = lcs_gateway.find_differences(full_text, edited_text)

if lcs_diff.differences:
    from domain.entities.text_difference import DifferenceType
    
    total_matched = 0
    match_count = 0
    
    print("\nマッチしたブロック:")
    for diff_type, text, positions in lcs_diff.differences:
        if diff_type == DifferenceType.UNCHANGED:
            match_count += 1
            matched_len = len(text)
            total_matched += matched_len
            
            if positions and positions[0]:
                pos_start = positions[0][0]
                print(f"  ブロック{match_count}: 位置{pos_start}, 長さ{matched_len}文字")
                print(f"    内容: \"{text[:50]}...\"" if len(text) > 50 else f"    内容: \"{text}\"")
    
    normalized_edited = lcs_gateway.normalize_for_comparison(edited_text)
    coverage = (total_matched / len(normalized_edited)) * 100 if normalized_edited else 0
    print(f"\n合計マッチブロック数: {match_count}個")
    print(f"合計マッチ文字数: {total_matched}文字")
    print(f"カバー率: {coverage:.1f}%")

print("\n" + "="*80)