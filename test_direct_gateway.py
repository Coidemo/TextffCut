"""
SequenceMatcherGatewayを直接テストする
"""

import json
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway

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

import logging
logging.basicConfig(level=logging.DEBUG)

print("=== SequenceMatcherGatewayの直接テスト ===\n")

# 編集テキスト
edited_text = """バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# ゲートウェイを作成
gateway = SequenceMatcherTextProcessorGateway()

# マーカーを除去
cleaned_text = gateway.remove_boundary_markers(edited_text)
print(f"編集テキスト: {edited_text}")
print(f"マーカー除去後: {cleaned_text}\n")

# 文字起こしデータを読み込む
try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
        
    converter = TranscriptionConverter()
    domain_result = converter.from_legacy(legacy_result)
    
    # 差分検出
    from domain.use_cases.character_array_builder import CharacterArrayBuilder
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(domain_result)
    
    print("差分検出を実行...")
    diff = gateway.find_differences(full_text, edited_text)
    
    print("時間範囲を計算...")
    time_ranges = gateway.get_time_ranges(diff, domain_result)
    
    print(f"\n時間範囲数: {len(time_ranges)}")
    for i, tr in enumerate(time_ranges):
        print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
    
    # 期待値と比較
    print("\n期待される調整:")
    print("  「指針となる考え方」を含む範囲の開始時間を1秒早める")
    
    # どの範囲に「指針」が含まれるか確認
    import logging
    logger = logging.getLogger('textffcut')
    
    # 差分の詳細を確認
    print("\n差分の詳細:")
    for i, (diff_type, text, positions) in enumerate(diff.differences):
        if diff_type.value == "unchanged":
            print(f"  差分{i}: {text[:30]}... (positions: {positions})")
        
except Exception as e:
    print(f"エラー: {e}")
    import traceback
    traceback.print_exc()