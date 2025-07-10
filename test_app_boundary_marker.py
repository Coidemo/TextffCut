"""
実際のアプリケーションで境界調整マーカーをテストするスクリプト
"""

import streamlit as st
from pathlib import Path

# DIコンテナの初期化
from di.containers import Container
container = Container()

# 文字起こし結果をモック
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

# 文字起こしデータを読み込む
with open('videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
    legacy_result = dict_to_obj(data)
    
converter = TranscriptionConverter()
domain_result = converter.from_legacy(legacy_result)

# セッション状態を初期化
if 'edited_text' not in st.session_state:
    st.session_state.edited_text = None

# テキスト編集PresenterとViewを作成
presenter = container.presentation.text_editor_presenter()
from presentation.views.text_editor import TextEditorView
view = TextEditorView(presenter)

# UIをレンダリング
st.title("境界調整マーカーテスト")

# 初期化
presenter.initialize(domain_result)

# マーカー付きテキストを設定
test_text = """バイアスがかかってしまわないために[<1.0]指針となる考え方などありますか指針となる考えを持つというよりかは考えをちゃんと言語化してアウトプットして自分の考えこうだよねって思ったものを レビューするっていうのがいいと思いますほとんどの人が自分の考えをちゃんとした文章で表現していないので バイアスに気づくどころか自分で何考えているかもわからないという状態になっているので 地説でもいいので文章化したほうがいいんじゃないかなと思ってます"""

st.text_area("テスト用テキスト（マーカー付き）", value=test_text, height=200)

if st.button("更新", type="primary"):
    # テキストを更新
    presenter.update_edited_text(test_text)
    
    # 時間範囲を取得
    if presenter.view_model.time_ranges:
        st.success(f"時間範囲が計算されました: {len(presenter.view_model.time_ranges)}個")
        for i, tr in enumerate(presenter.view_model.time_ranges):
            st.write(f"範囲{i+1}: {tr.start:.3f} - {tr.end:.3f}秒")
    else:
        st.error("時間範囲が計算されませんでした")
    
    # 境界調整マーカーの有無
    if presenter.view_model.has_boundary_markers:
        st.info("境界調整マーカーが検出されました")

# ログを表示
with st.expander("デバッグログ"):
    st.text("ログはコンソールに出力されます")