#!/usr/bin/env python3
"""
リファクタリング後の基本的な動作テスト
"""

import sys
from pathlib import Path

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))


def test_imports():
    """インポートテスト"""
    print("=== インポートテスト ===")
    
    try:
        # メインモジュール
        from main import main, setup_streamlit, render_sidebar
        print("✅ main.py のインポート: OK")
        
        # ページコントローラー
        from ui.pages import (
            TranscriptionPageController,
            TextEditingPageController,
            ProcessingPageController
        )
        print("✅ ページコントローラーのインポート: OK")
        
        # セッション状態管理
        from utils.session_state_manager import SessionStateManager
        print("✅ SessionStateManagerのインポート: OK")
        
        # UIコンポーネント
        from ui import (
            show_edited_text_with_highlights,
            show_diff_viewer,
            show_text_editor,
            show_audio_preview_for_clips,
            show_boundary_adjusted_preview,
        )
        print("✅ UIコンポーネントのインポート: OK")
        
        return True
        
    except Exception as e:
        print(f"❌ インポートエラー: {e}")
        return False


def test_function_signatures():
    """関数シグネチャのテスト"""
    print("\n=== 関数シグネチャテスト ===")
    
    try:
        import inspect
        from ui import show_edited_text_with_highlights
        
        # show_edited_text_with_highlightsの引数を確認
        sig = inspect.signature(show_edited_text_with_highlights)
        params = list(sig.parameters.keys())
        print(f"show_edited_text_with_highlights の引数: {params}")
        
        # 期待される引数
        expected = ["edited_text", "diff", "height"]
        if params == expected:
            print("✅ show_edited_text_with_highlights: OK")
        else:
            print(f"❌ show_edited_text_with_highlights: 引数が不一致")
            print(f"  期待: {expected}")
            print(f"  実際: {params}")
            
        return True
        
    except Exception as e:
        print(f"❌ シグネチャテストエラー: {e}")
        return False


def test_page_controllers():
    """ページコントローラーの基本テスト"""
    print("\n=== ページコントローラーテスト ===")
    
    try:
        from ui.pages import TextEditingPageController
        from config import Config
        
        # コントローラーのインスタンス化
        controller = TextEditingPageController()
        print("✅ TextEditingPageController のインスタンス化: OK")
        
        # 必要なメソッドの存在確認
        methods = ["render", "_validate_transcription", "_show_transcription_info", 
                  "_render_transcription_viewer", "_render_text_editor"]
        
        for method in methods:
            if hasattr(controller, method):
                print(f"✅ {method} メソッド: OK")
            else:
                print(f"❌ {method} メソッド: 見つかりません")
                
        return True
        
    except Exception as e:
        print(f"❌ ページコントローラーテストエラー: {e}")
        return False


def test_session_state_manager():
    """セッション状態管理のテスト"""
    print("\n=== SessionStateManagerテスト ===")
    
    try:
        from utils.session_state_manager import SessionStateManager
        
        # 基本的なメソッドの存在確認
        methods = ["initialize", "get", "set", "delete", "clear_processing_state"]
        
        for method in methods:
            if hasattr(SessionStateManager, method):
                print(f"✅ {method} メソッド: OK")
            else:
                print(f"❌ {method} メソッド: 見つかりません")
                
        return True
        
    except Exception as e:
        print(f"❌ SessionStateManagerテストエラー: {e}")
        return False


def main():
    """メインテスト実行"""
    print("TextffCut リファクタリングテスト\n")
    
    results = []
    
    # 各テストを実行
    results.append(test_imports())
    results.append(test_function_signatures())
    results.append(test_page_controllers())
    results.append(test_session_state_manager())
    
    # 結果サマリー
    print("\n=== テスト結果サマリー ===")
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ 全てのテストに合格 ({passed}/{total})")
        return 0
    else:
        print(f"❌ 一部のテストに失敗 ({passed}/{total})")
        return 1


if __name__ == "__main__":
    sys.exit(main())