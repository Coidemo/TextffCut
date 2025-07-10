"""
実際のアプリケーションでの動作を確認するスクリプト
"""

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

with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    legacy_result = dict_to_obj(data)
    
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)

# 初期化
presenter.initialize(domain_result)

# マーカー付きテキストで更新
test_text = """バイアスがかかってしまわないために[<0.1]指針となる考え方などありますか"""

print("=== 実際のPresenterでテスト ===")
print(f"テスト用テキスト: {test_text}")

# 更新を実行
presenter.update_edited_text(test_text)

# 結果を確認
if presenter.view_model.time_ranges:
    print(f"\n時間範囲数: {len(presenter.view_model.time_ranges)}")
    for i, tr in enumerate(presenter.view_model.time_ranges):
        print(f"  範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
        
    print(f"\n境界調整マーカー検出: {presenter.view_model.has_boundary_markers}")
    print(f"文字数: {presenter.view_model.char_count}文字")
else:
    print("時間範囲が計算されませんでした")