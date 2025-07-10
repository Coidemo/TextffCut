"""
「指針」が音声プレビューに含まれない問題の調査
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

print("=== 「指針」が含まれない問題の調査 ===\n")

# 問題のテキスト
original_text = "バイアスがかかってしまわないために一定の指針となる考え方などありますか"
edited_text = "バイアスがかかってしまわないために指針となる考え方などありますか"

print(f"原文: \"{original_text}\"")
print(f"編集: \"{edited_text}\"")
print(f"削除された部分: \"一定の\"")
print()

# 文字位置を確認
print("【文字位置の確認】")
print("原文の文字位置:")
for i, char in enumerate(original_text):
    if char in "一定の指針":
        print(f"  位置{i}: '{char}' {'<-- 削除' if char in '一定の' else ''}")
    elif i in range(15, 21):  # 「一定の指針」周辺を表示
        print(f"  位置{i}: '{char}'")

print("\n編集テキストで「指針」の位置:")
shishin_pos = edited_text.find("指針")
print(f"  「指針」の位置: {shishin_pos}")

# 実際のデータを読み込む
try:
    with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        legacy_result = dict_to_obj(data)
        
    converter = TranscriptionConverter()
    domain_result = converter.from_legacy(legacy_result)
    
    builder = CharacterArrayBuilder()
    char_array, full_text = builder.build_from_transcription(domain_result)
    
    # 原文を探す
    pos = full_text.find(original_text)
    
    if pos != -1:
        print(f"\n原文が見つかりました（位置: {pos}）")
        
        # 「一定の指針」周辺の文字のタイムスタンプを表示
        print("\n【「一定の指針」周辺のタイムスタンプ】")
        print("文字 | 位置 | 開始時間 | 終了時間")
        print("-" * 50)
        
        # 「に」から「となる」まで表示
        start_idx = original_text.find("に一定の")
        end_idx = original_text.find("となる") + 3
        
        for i in range(start_idx, min(end_idx, len(original_text))):
            char_pos = pos + i
            if char_pos < len(char_array):
                char_info = char_array[char_pos]
                marker = ""
                if original_text[i] == "一":
                    marker = " <-- 「一定の」開始"
                elif original_text[i] == "の" and i < 20:
                    marker = " <-- 「一定の」終了"
                elif original_text[i] == "指":
                    marker = " <-- 「指針」開始"
                elif original_text[i] == "針":
                    marker = " <-- 「指針」終了"
                    
                print(f"{original_text[i]}    | {i:4d} | {char_info.start:9.3f} | {char_info.end:9.3f}{marker}")
        
        # 差分検出を実行
        print("\n" + "="*60)
        print("\n【差分検出の実行】")
        
        gateway = SequenceMatcherTextProcessorGateway()
        diff = gateway.find_differences(full_text, edited_text)
        
        # 差分の詳細を表示
        print("\n差分検出結果:")
        for i, (diff_type, text, positions) in enumerate(diff.differences):
            print(f"\n{i+1}. {diff_type.value}: \"{text[:30]}...\"" if len(text) > 30 else f"\n{i+1}. {diff_type.value}: \"{text}\"")
            if positions:
                for start, end in positions:
                    print(f"   位置: {start}-{end}")
                    # この範囲に「指針」が含まれているか確認
                    if start <= pos + 20 < end:  # 「指」の位置
                        print(f"   ✓ この範囲に「指針」が含まれています")
        
        # 時間範囲を計算
        time_ranges = gateway.get_time_ranges(diff, domain_result)
        
        print(f"\n【計算された時間範囲】")
        print(f"時間範囲数: {len(time_ranges)}")
        
        # 「指針」が含まれるべき時間範囲を特定
        shishin_char_pos = pos + 20  # 原文での「指」の位置
        shishin_start_time = char_array[shishin_char_pos].start if shishin_char_pos < len(char_array) else None
        shishin_end_time = char_array[shishin_char_pos + 1].end if shishin_char_pos + 1 < len(char_array) else None
        
        print(f"\n「指針」のタイムスタンプ:")
        print(f"  開始: {shishin_start_time:.3f}秒")
        print(f"  終了: {shishin_end_time:.3f}秒")
        
        # 各時間範囲を確認
        shishin_included = False
        for i, tr in enumerate(time_ranges):
            print(f"\n時間範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
            
            # この時間範囲に「指針」が含まれているか確認
            if shishin_start_time and shishin_end_time:
                if tr.start <= shishin_start_time and shishin_end_time <= tr.end:
                    print("  ✓ この時間範囲に「指針」が完全に含まれています")
                    shishin_included = True
                elif tr.start <= shishin_start_time < tr.end:
                    print("  ⚠️ この時間範囲に「指針」の開始部分のみ含まれています")
                    print(f"     時間範囲の終了: {tr.end:.3f}秒")
                    print(f"     「指針」の終了: {shishin_end_time:.3f}秒")
                    print(f"     不足: {shishin_end_time - tr.end:.3f}秒")
                elif tr.start < shishin_end_time <= tr.end:
                    print("  ⚠️ この時間範囲に「指針」の終了部分のみ含まれています")
                
        if not shishin_included:
            print("\n❌ 問題: 「指針」がどの時間範囲にも完全に含まれていません！")
        
        # 「一定の」の直前で時間範囲が切れている可能性を確認
        print("\n【境界の詳細確認】")
        itei_start_pos = pos + 17  # 「一」の位置
        if itei_start_pos < len(char_array):
            itei_start_time = char_array[itei_start_pos].start
            print(f"「一定の」の開始時間: {itei_start_time:.3f}秒")
            
            # 各時間範囲の終了時間と比較
            for i, tr in enumerate(time_ranges):
                if abs(tr.end - itei_start_time) < 0.001:
                    print(f"\n⚠️ 時間範囲{i+1}が「一定の」の直前で終了しています！")
                    print(f"   これにより「指針」が次の時間範囲に分割されている可能性があります")
                    
    else:
        print("\n原文が見つかりませんでした")
        
except FileNotFoundError:
    print("\n文字起こしファイルが見つかりません")