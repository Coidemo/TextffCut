"""セグメントの型を詳しく調査"""

import streamlit as st
import sys
import logging
from pathlib import Path

# ロギング設定
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# メインアプリケーションの処理を実行
def main():
    # セッション状態を確認
    if hasattr(st, "session_state") and st.session_state is not None:
        print("\n=== Session State Debug ===")
        
        # transcription_resultがあるか確認
        if "transcription_result" in st.session_state:
            tr = st.session_state.transcription_result
            print(f"transcription_result type: {type(tr)}")
            print(f"transcription_result class: {tr.__class__.__name__}")
            
            # TranscriptionResultAdapterの場合
            if hasattr(tr, "domain_result"):
                print(f"  - Has domain_result attribute")
                domain_result = tr.domain_result
                print(f"  - domain_result type: {type(domain_result)}")
                
                if domain_result and hasattr(domain_result, "segments"):
                    print(f"  - segments type: {type(domain_result.segments)}")
                    if domain_result.segments:
                        first_seg = domain_result.segments[0]
                        print(f"  - First segment type: {type(first_seg)}")
                        print(f"  - First segment is dict: {isinstance(first_seg, dict)}")
                        if isinstance(first_seg, dict):
                            print(f"  - First segment keys: {list(first_seg.keys())}")
                        else:
                            print(f"  - First segment attributes: {dir(first_seg)[:10]}...")
            else:
                # 直接のTranscriptionResult
                if hasattr(tr, "segments"):
                    print(f"  - segments type: {type(tr.segments)}")
                    if tr.segments:
                        first_seg = tr.segments[0]
                        print(f"  - First segment type: {type(first_seg)}")
                        print(f"  - First segment is dict: {isinstance(first_seg, dict)}")
        
        # text_editorの状態も確認
        if "text_editor" in st.session_state:
            te = st.session_state.text_editor
            print(f"\ntext_editor type: {type(te)}")
            if hasattr(te, "transcription_result"):
                tr2 = te.transcription_result
                print(f"  - transcription_result type: {type(tr2)}")
    
    # Presenterから直接取得を試みる
    try:
        from presentation.di_config import DIContainer
        container = DIContainer()
        
        # TextEditorPresenterを取得
        text_editor_presenter = container.get_text_editor_presenter()
        vm = text_editor_presenter.view_model
        
        print(f"\n=== ViewModel Debug ===")
        print(f"ViewModel type: {type(vm)}")
        if hasattr(vm, "transcription_result"):
            tr3 = vm.transcription_result
            print(f"transcription_result type: {type(tr3)}")
            if tr3 and hasattr(tr3, "segments"):
                print(f"  - segments type: {type(tr3.segments)}")
                if tr3.segments:
                    first_seg = tr3.segments[0]
                    print(f"  - First segment type: {type(first_seg)}")
                    print(f"  - First segment is dict: {isinstance(first_seg, dict)}")
    except Exception as e:
        print(f"Error accessing presenter: {e}")

if __name__ == "__main__":
    main()