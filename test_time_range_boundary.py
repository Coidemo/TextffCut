"""
時間範囲の境界問題を詳細に調査
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

print("=== 時間範囲の境界問題調査 ===\n")

try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
        
    converter = TranscriptionConverter()
    domain_result = converter.from_legacy(legacy_result)
    
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(domain_result)
    
    # 「ちゃんとした文章とかで表現していない」を探す
    search_text = "ちゃんとした文章とかで表現していない"
    pos = full_text.find(search_text)
    
    if pos != -1:
        print(f"テキストが見つかりました（位置: {pos}）")
        
        # 各文字の詳細を表示
        print("\n【文字ごとの詳細】")
        print("文字 | 位置 | 開始時間 | 終了時間")
        print("-" * 50)
        
        for i, char in enumerate(search_text):
            char_pos = pos + i
            if char_pos < len(char_array):
                char_info = char_array[char_pos]
                print(f"{char}    | {i:4d} | {char_info.start:9.3f} | {char_info.end:9.3f}")
                
                # 重要な境界をマーク
                if i == 7:  # 「章」
                    print("     ^--- 「ちゃんとした文章」の終了")
                elif i == 8:  # 「と」
                    print("     ^--- 「とか」の開始")
                elif i == 9:  # 「か」
                    print("     ^--- 「とか」の終了")
                elif i == 10:  # 「で」
                    print("     ^--- 「で表現していない」の開始")
        
        # 時間範囲の計算をシミュレート
        print("\n" + "="*60)
        print("\n【時間範囲の計算】")
        
        # 位置情報から時間を取得
        # 1. 「ちゃんとした文章」（位置0-8）
        start1 = char_array[pos + 0].start
        end1 = char_array[pos + 7].end  # 「章」の終了時間
        print(f"\n1. 「ちゃんとした文章」:")
        print(f"   文字位置: 0-8")
        print(f"   時間範囲: {start1:.3f} - {end1:.3f}秒")
        
        # 2. 「とか」（位置8-10）
        start2 = char_array[pos + 8].start  # 「と」の開始時間
        end2 = char_array[pos + 9].end      # 「か」の終了時間
        print(f"\n2. 「とか」（削除される部分）:")
        print(f"   文字位置: 8-10")
        print(f"   時間範囲: {start2:.3f} - {end2:.3f}秒")
        
        # 3. 「で表現していない」（位置10-18）
        start3 = char_array[pos + 10].start  # 「で」の開始時間
        end3 = char_array[pos + 17].end      # 最後の「い」の終了時間
        print(f"\n3. 「で表現していない」:")
        print(f"   文字位置: 10-18")
        print(f"   時間範囲: {start3:.3f} - {end3:.3f}秒")
        
        # ギャップを確認
        print(f"\n【ギャップの確認】")
        gap1 = start2 - end1
        gap2 = start3 - end2
        print(f"「章」と「と」の間のギャップ: {gap1:.3f}秒")
        print(f"「か」と「で」の間のギャップ: {gap2:.3f}秒")
        
        # 問題の診断
        print(f"\n【診断】")
        if gap1 < 0:
            print(f"⚠️ 問題: 「章」の終了時間({end1:.3f})が「と」の開始時間({start2:.3f})より後です！")
            print(f"   これにより、最初の時間範囲に「と」が含まれてしまいます。")
        else:
            print(f"✅ 「章」と「と」の間に{gap1:.3f}秒のギャップがあります。")
            
except FileNotFoundError:
    print("文字起こしファイルが見つかりません")