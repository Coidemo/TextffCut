"""
SequenceMatcherのデバッグ
"""

import json
from types import SimpleNamespace
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway
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

# 編集テキスト
edited_text = """バイアスがかかってしまわない ために指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

print("【デバッグ情報】")
print(f"原文の長さ: {len(full_text)}文字")
print(f"編集テキストの長さ: {len(edited_text)}文字")

# ゲートウェイを初期化
gateway = SequenceMatcherTextProcessorGateway()

# 正規化
normalized_full = gateway.normalize_for_comparison(full_text)
normalized_edited = gateway.normalize_for_comparison(edited_text)

print(f"\n正規化後の原文: {len(normalized_full)}文字")
print(f"正規化後の編集: {len(normalized_edited)}文字")

# 検索対象のテキストを確認
search_text = "バイアスがかかってしまわないために"
print(f"\n検索するテキスト: \"{search_text}\"")

# 原文内で検索
position = full_text.find(search_text)
print(f"原文での位置: {position}")
if position != -1:
    print(f"見つかった部分: \"{full_text[position:position+50]}...\"")

# 正規化後で検索
normalized_search = gateway.normalize_for_comparison(search_text)
position_normalized = normalized_full.find(normalized_search)
print(f"\n正規化後での位置: {position_normalized}")
if position_normalized != -1:
    print(f"見つかった部分: \"{normalized_full[position_normalized:position_normalized+50]}...\"")

# 編集テキストの最初の部分を確認
print(f"\n編集テキストの最初の50文字: \"{edited_text[:50]}...\"")
print(f"正規化後の編集テキストの最初の50文字: \"{normalized_edited[:50]}...\"")

# 実際のテキストの該当部分を確認
print(f"\n原文の14300-14400の部分:")
print(f"\"{full_text[14300:14400]}\"")

# スペースを除去して比較
no_space_full = gateway.remove_spaces(normalized_full)
no_space_edited = gateway.remove_spaces(normalized_edited)
position_no_space = no_space_full.find(no_space_edited[:30])  # 最初の30文字で検索

print(f"\nスペース除去後で検索:")
print(f"検索文字列（最初の30文字）: \"{no_space_edited[:30]}\"")
print(f"位置: {position_no_space}")
if position_no_space != -1:
    print("見つかりました！")