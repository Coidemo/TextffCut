"""
処理時間を計測するスクリプト
"""

import time
import logging
logging.basicConfig(level=logging.INFO)

# セッション状態のモック
class MockSessionState:
    def __init__(self):
        self.data = {}
        
    def get(self, key, default=None):
        return self.data.get(key, default)
        
    def __setitem__(self, key, value):
        self.data[key] = value
        
    def __getitem__(self, key):
        return self.data[key]
        
    def __contains__(self, key):
        return key in self.data

import streamlit as st
st.session_state = MockSessionState()

# DIコンテナを初期化
from di.containers import ApplicationContainer
container = ApplicationContainer()

# Presenterを作成
presenter = container.presentation.text_editor_presenter()

# 文字起こし結果をロード
import json
from types import SimpleNamespace
from adapters.converters.transcription_converter import TranscriptionConverter

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

print("=== 処理時間計測 ===\n")

# 文字起こしデータの読み込み
start_time = time.time()
with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    legacy_result = dict_to_obj(data)
print(f"JSONロード: {time.time() - start_time:.3f}秒")

# 変換処理
start_time = time.time()
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)
print(f"ドメインエンティティ変換: {time.time() - start_time:.3f}秒")

# 初期化
start_time = time.time()
presenter.initialize(domain_result)
print(f"Presenter初期化: {time.time() - start_time:.3f}秒")

# テスト用テキスト（長めのテキストで試す）
test_text = """バイアスがかかってしまわないために[<0.1]指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

# 更新処理の計測
print("\n--- 更新処理 ---")
start_time = time.time()
presenter.update_edited_text(test_text)
total_time = time.time() - start_time
print(f"update_edited_text 合計: {total_time:.3f}秒")

# 個別処理の計測（ゲートウェイを直接呼び出して計測）
print("\n--- 個別処理の計測 ---")

# 1. find_differences
gateway = container.gateways.text_processor_gateway()
start_time = time.time()
diff_result = gateway.find_differences(presenter.view_model.full_text, test_text, skip_normalization=True)
print(f"find_differences: {time.time() - start_time:.3f}秒")

# 2. get_time_ranges
start_time = time.time()
time_ranges = gateway.get_time_ranges(diff_result, domain_result)
print(f"get_time_ranges: {time.time() - start_time:.3f}秒")

# 3. CharacterArrayBuilder（get_time_ranges内で呼ばれる）
from domain.use_cases.character_array_builder import CharacterArrayBuilder
builder = CharacterArrayBuilder()
start_time = time.time()
char_array, full_text = builder.build_from_transcription(domain_result)
print(f"CharacterArrayBuilder.build_from_transcription: {time.time() - start_time:.3f}秒")

print(f"\n文字数: {len(full_text)}文字")
print(f"セグメント数: {len(domain_result.segments)}")
if hasattr(domain_result.segments[0], 'words') and domain_result.segments[0].words:
    total_words = sum(len(seg.words) for seg in domain_result.segments if hasattr(seg, 'words') and seg.words)
    print(f"総単語数: {total_words}")