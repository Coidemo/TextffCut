#!/usr/bin/env python3
"""エンドツーエンドテスト: テキスト処理の完全な流れ"""

import json
import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# DIコンテナのブートストラップ
from di.bootstrap import bootstrap_di, inject_streamlit_session
from di.config import DIConfig

# Streamlitのモック
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


def test_e2e_text_processing():
    """エンドツーエンドテスト"""
    print("=== エンドツーエンドテスト: テキスト処理 ===\n")
    
    # DIコンテナを初期化
    config = DIConfig()
    container = bootstrap_di(config=config)
    
    # SessionManagerを取得してテストデータを設定
    presentation_container = container.presentation()
    session_manager = presentation_container.session_manager()
    
    # テストデータの準備
    json_path = (
        project_root / "videos/合理性は人や国によって違うよねえ、という話_TextffCut/transcriptions/whisper-1_api.json"
    )
    
    with open(json_path) as f:
        data = json.load(f)
    
    # TranscriptionGatewayからTranscriptionResultを作成
    gateway_container = container.gateways()
    transcription_gateway = gateway_container.transcription_gateway()
    
    # TranscriptionResultAdapterを作成
    from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter
    from domain.entities.transcription import TranscriptionResult
    
    domain_result = TranscriptionResult.from_legacy_format(data)
    transcription_adapter = TranscriptionResultAdapter(domain_result)
    
    # TextEditorPresenterを作成してテスト
    text_editor_presenter = presentation_container.text_editor_presenter()
    
    # 初期化
    print("1. TextEditorPresenterを初期化")
    text_editor_presenter.initialize(transcription_adapter)
    print(f"   全文の長さ: {len(text_editor_presenter.view_model.full_text)}文字")
    
    # 編集テキストを設定
    edited_text = "お金持ちとか外国人とかお金に余裕のある高齢者とかからも平等に取れて社会福祉に使われる消費税は僕は上げてもいいとすら思っていますね。その代わり低所得の人とか生活困っているという人への財源にしていくというのをガンガンやった方がいいと思っています。"
    
    print("\n2. 編集テキストを設定")
    text_editor_presenter.update_edited_text(edited_text)
    print(f"   編集テキストの長さ: {len(edited_text)}文字")
    
    # 結果の確認
    print("\n3. 処理結果の確認")
    view_model = text_editor_presenter.view_model
    
    if view_model.has_added_chars:
        print(f"   ⚠️ 追加文字が検出されました: {view_model.added_chars_info}")
    else:
        print(f"   ✅ 追加文字なし")
    
    if view_model.has_time_ranges:
        print(f"   ✅ 時間範囲が計算されました: {len(view_model.time_ranges)}個")
        for i, tr in enumerate(view_model.time_ranges[:3]):
            print(f"      範囲{i+1}: {tr.start:.2f}秒 - {tr.end:.2f}秒")
    else:
        print("   ❌ 時間範囲が計算されていません")
    
    if view_model.error_message:
        print(f"   ❌ エラー: {view_model.error_message}")
    else:
        print("   ✅ エラーなし")
    
    # 処理データの取得
    print("\n4. 処理済みデータの取得")
    processed_data = text_editor_presenter.get_processed_data()
    print(f"   edited_text: {len(processed_data['edited_text'])}文字")
    print(f"   time_ranges: {len(processed_data['time_ranges'])}個")
    print(f"   total_duration: {processed_data['total_duration']:.2f}秒")
    
    print("\n✅ エンドツーエンドテストが完了しました")


if __name__ == "__main__":
    import streamlit as st
    
    # Streamlitのセッション状態をモック
    if not hasattr(st, "session_state"):
        st.session_state = MockSessionState()
    
    test_e2e_text_processing()