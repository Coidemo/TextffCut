"""
実際の文字起こしデータでのタイムスタンプ確認
"""

import json
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter
from domain.use_cases.character_array_builder import CharacterArrayBuilder
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

# 文字起こし結果を読み込む
print("=== 実際のタイムスタンプ確認 ===\n")

try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
        
    # ドメイン形式に変換
    converter = TranscriptionConverter()
    domain_result = converter.from_legacy(legacy_result)
    
    # CharacterArrayBuilderで文字配列を構築
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(domain_result)
    
    # 「ちゃんとした文章とかで表現していない」を探す
    search_text = "ちゃんとした文章とかで表現していない"
    pos = full_text.find(search_text)
    
    if pos != -1:
        print(f"テキストが見つかりました！")
        print(f"位置: {pos}")
        print(f"該当部分: \"{full_text[pos:pos+len(search_text)]}\"")
        
        # 各文字のタイムスタンプを表示
        print("\n文字ごとのタイムスタンプ:")
        print("文字 | 開始時間 | 終了時間")
        print("-" * 40)
        
        for i in range(len(search_text)):
            if pos + i < len(char_array):
                char_info = char_array[pos + i]
                print(f"{char_info.char}    | {char_info.start:8.3f} | {char_info.end:8.3f}")
                
                # 「とか」の部分を特別にマーク
                if char_info.char in "とか":
                    print(f"     ^ 「とか」の文字です！")
        
        # 編集後のテキストで時間範囲を計算
        print("\n" + "="*60)
        print("\n編集後のテキストで時間範囲を計算:")
        
        edited_text = "ちゃんとした文章で表現していない"
        
        # SequenceMatcherで差分検出
        gateway = SequenceMatcherTextProcessorGateway()
        diff = gateway.find_differences(full_text, edited_text)
        
        # 時間範囲を計算
        time_ranges = gateway.get_time_ranges(diff, domain_result)
        
        print(f"\n計算された時間範囲: {len(time_ranges)}個")
        
        # 「ちゃんとした文章」と「で表現していない」の時間範囲を探す
        for tr in time_ranges:
            # この時間範囲に対応する文字を特定
            start_chars = []
            end_chars = []
            
            for i, char_info in enumerate(char_array):
                # 開始時間付近の文字
                if abs(char_info.start - tr.start) < 0.1:
                    start_chars.append((i, char_info.char, char_info.start))
                # 終了時間付近の文字
                if abs(char_info.end - tr.end) < 0.1:
                    end_chars.append((i, char_info.char, char_info.end))
            
            print(f"\n時間範囲: {tr.start:.3f} - {tr.end:.3f}秒")
            if start_chars:
                print(f"  開始付近の文字: {start_chars}")
            if end_chars:
                print(f"  終了付近の文字: {end_chars}")
            
            # この時間範囲の音声に「とか」が含まれているか確認
            contains_toka = False
            for char_info in char_array:
                if tr.start <= char_info.start < tr.end and char_info.char in "とか":
                    contains_toka = True
                    print(f"  ⚠️ この時間範囲に「{char_info.char}」が含まれています！（{char_info.start:.3f}秒）")
            
            if not contains_toka:
                print("  ✅ この時間範囲に「とか」は含まれていません")
                
    else:
        print("テキストが見つかりませんでした")
        
except FileNotFoundError:
    print("文字起こしファイルが見つかりません")