"""
境界調整マーカー[<1.0]が音声プレビューに反映されない問題の調査
"""

import json
import logging
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter
from domain.use_cases.character_array_builder import CharacterArrayBuilder
from adapters.gateways.text_processing.sequence_matcher_gateway import SequenceMatcherTextProcessorGateway

# デバッグログを有効化
logging.basicConfig(level=logging.DEBUG)

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

print("=== 境界調整マーカー[<1.0]の処理問題調査 ===\n")

# ユーザーが指定したテキスト
edited_text = """バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

print(f"編集テキスト（マーカー付き）:\n{edited_text}\n")

# マーカーの位置を確認
marker_pos = edited_text.find("[<1.0]")
print(f"マーカー[<1.0]の位置: {marker_pos}")
print(f"マーカー前のテキスト: '{edited_text[:marker_pos]}'")
print(f"マーカー後のテキスト: '{edited_text[marker_pos+6:marker_pos+10]}...'\n")

# 実際のデータを読み込む
try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
        
    converter = TranscriptionConverter()
    domain_result = converter.from_legacy(legacy_result)
    
    gateway = SequenceMatcherTextProcessorGateway()
    
    # 境界調整マーカーを除去
    cleaned_text = gateway.remove_boundary_markers(edited_text)
    print(f"マーカー除去後のテキスト:\n{cleaned_text}\n")
    
    # 差分検出を実行（マーカー除去後のテキストで）
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(domain_result)
    
    diff = gateway.find_differences(full_text, cleaned_text)
    time_ranges = gateway.get_time_ranges(diff, domain_result)
    
    print(f"時間範囲数: {len(time_ranges)}")
    for i, tr in enumerate(time_ranges):
        print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
    
    # apply_boundary_adjustmentsメソッドを呼び出す
    print("\n=== 境界調整の適用 ===")
    
    # デバッグ：各時間範囲に対応するテキストを表示
    print("\n【時間範囲と対応テキスト】")
    for i, tr in enumerate(time_ranges):
        # この時間範囲に対応する文字を探す
        start_char = None
        end_char = None
        for j, char in enumerate(char_array):
            if char.start >= tr.start and start_char is None:
                start_char = j
            if char.end <= tr.end:
                end_char = j
        
        if start_char is not None and end_char is not None:
            text_snippet = full_text[start_char:end_char+1]
            print(f"範囲{i+1}: {text_snippet[:20]}...")
    
    adjusted_text, adjusted_ranges = gateway.apply_boundary_adjustments(edited_text, time_ranges)
    
    print(f"\n調整後の時間範囲数: {len(adjusted_ranges)}")
    for i, tr in enumerate(adjusted_ranges):
        print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
    
    # 差分を確認
    if len(time_ranges) == len(adjusted_ranges):
        print("\n【時間範囲の変化】")
        for i, (orig, adj) in enumerate(zip(time_ranges, adjusted_ranges)):
            if orig.start != adj.start or orig.end != adj.end:
                print(f"範囲{i+1}:")
                print(f"  変更前: {orig.start:.3f} - {orig.end:.3f}秒")
                print(f"  変更後: {adj.start:.3f} - {adj.end:.3f}秒")
                print(f"  差分: 開始 {adj.start - orig.start:+.3f}秒, 終了 {adj.end - orig.end:+.3f}秒")
    
    # マーカーの効果を確認
    print("\n【マーカー[<1.0]の効果】")
    print("期待される動作: 「指針」を含む時間範囲の開始を1秒早める")
    
    # 「指針」がどの時間範囲に含まれているか確認
    shishin_pos = cleaned_text.find("指針")
    if shishin_pos != -1:
        print(f"\n「指針」の位置: {shishin_pos}")
        # 原文での位置を探す
        original_pos = full_text.find("指針")
        if original_pos != -1 and original_pos < len(char_array):
            shishin_time = char_array[original_pos].start
            print(f"「指針」の開始時間: {shishin_time:.3f}秒")
            
            # どの時間範囲に含まれるか確認
            for i, tr in enumerate(time_ranges):
                if tr.start <= shishin_time <= tr.end:
                    print(f"「指針」は範囲{i+1}に含まれています")
                    if i < len(adjusted_ranges):
                        adj = adjusted_ranges[i]
                        print(f"  調整前: {tr.start:.3f}秒から")
                        print(f"  調整後: {adj.start:.3f}秒から")
                        if adj.start == tr.start:
                            print("  ⚠️ マーカーが適用されていません！")
                        elif adj.start == tr.start - 1.0:
                            print("  ✅ マーカーが正しく適用されました")
    
except FileNotFoundError:
    print("文字起こしファイルが見つかりません")
except Exception as e:
    print(f"エラー: {e}")
    import traceback
    traceback.print_exc()