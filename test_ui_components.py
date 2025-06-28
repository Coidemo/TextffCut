#!/usr/bin/env python3
"""
UIコンポーネントの詳細テスト
"""

import sys
import inspect
from pathlib import Path
from typing import get_type_hints

# プロジェクトルートをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))


def test_ui_component_signatures():
    """UIコンポーネントの関数シグネチャを詳細にテスト"""
    print("=== UIコンポーネント シグネチャテスト ===\n")
    
    # テスト対象の関数と期待されるシグネチャ
    test_cases = [
        {
            "module": "ui.components",
            "function": "show_edited_text_with_highlights",
            "expected_params": ["edited_text", "diff", "height"],
            "expected_defaults": {"diff": None, "height": 400}
        },
        {
            "module": "ui.components", 
            "function": "show_red_highlight_modal",
            "expected_params": ["edited_text", "diff"],
            "expected_defaults": {"diff": None}
        },
        {
            "module": "ui.components",
            "function": "show_diff_viewer",
            "check_manually": True  # 複雑なので手動チェック
        },
        {
            "module": "ui.components",
            "function": "show_text_editor",
            "check_manually": True
        },
        {
            "module": "ui.audio_preview",
            "function": "show_audio_preview_for_clips",
            "check_manually": True
        },
        {
            "module": "ui.audio_preview",
            "function": "show_boundary_adjusted_preview",
            "check_manually": True
        }
    ]
    
    results = []
    
    for test_case in test_cases:
        try:
            # モジュールと関数をインポート
            module = __import__(test_case["module"], fromlist=[test_case["function"]])
            func = getattr(module, test_case["function"])
            
            # シグネチャを取得
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            
            print(f"📌 {test_case['function']}:")
            print(f"   引数: {params}")
            
            # デフォルト値を確認
            defaults = {}
            for param_name, param in sig.parameters.items():
                if param.default != inspect.Parameter.empty:
                    defaults[param_name] = param.default
            if defaults:
                print(f"   デフォルト値: {defaults}")
            
            # 型ヒントを確認
            try:
                hints = get_type_hints(func)
                if hints:
                    print(f"   型ヒント: {hints}")
            except:
                pass
            
            # 手動チェックが必要な場合
            if test_case.get("check_manually"):
                print("   ⚠️  手動チェックが必要")
                results.append(True)
            else:
                # 期待される引数と比較
                expected = test_case["expected_params"]
                if params == expected:
                    # デフォルト値もチェック
                    expected_defaults = test_case.get("expected_defaults", {})
                    defaults_match = all(
                        defaults.get(k) == v for k, v in expected_defaults.items()
                    )
                    if defaults_match:
                        print("   ✅ OK")
                        results.append(True)
                    else:
                        print("   ❌ デフォルト値が不一致")
                        results.append(False)
                else:
                    print(f"   ❌ 引数が不一致 (期待: {expected})")
                    results.append(False)
            
            print()
            
        except Exception as e:
            print(f"❌ {test_case['function']}: エラー - {e}")
            results.append(False)
            print()
    
    return all(results)


def test_text_editing_page_usage():
    """text_editing_page.pyでのUI関数の使用方法をチェック"""
    print("\n=== text_editing_page.py での使用方法チェック ===\n")
    
    try:
        # ファイルを読み込んで使用箇所を確認
        text_editing_path = Path("ui/pages/text_editing_page.py")
        content = text_editing_path.read_text()
        
        # 関数呼び出しパターンを検索
        patterns = [
            ("show_edited_text_with_highlights", r"show_edited_text_with_highlights\([^)]+\)"),
            ("show_red_highlight_modal", r"show_red_highlight_modal\([^)]+\)"),
            ("show_diff_viewer", r"show_diff_viewer\([^)]+\)"),
            ("show_text_editor", r"show_text_editor\([^)]+\)"),
            ("show_audio_preview_for_clips", r"show_audio_preview_for_clips\([^)]+\)"),
            ("show_boundary_adjusted_preview", r"show_boundary_adjusted_preview\([^)]+\)")
        ]
        
        import re
        
        for func_name, pattern in patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            if matches:
                print(f"📌 {func_name} の使用箇所:")
                for i, match in enumerate(matches, 1):
                    # 改行を含む場合は整形
                    match_cleaned = match.replace('\n', ' ').strip()
                    # 長すぎる場合は省略
                    if len(match_cleaned) > 80:
                        match_cleaned = match_cleaned[:77] + "..."
                    print(f"   {i}. {match_cleaned}")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ エラー: {e}")
        return False


def generate_test_recommendations():
    """テスト推奨事項を生成"""
    print("\n=== テスト推奨事項 ===\n")
    
    recommendations = [
        "1. 型アノテーションを使用してmypyでの静的型チェックを実施",
        "2. 各UIコンポーネントに対するユニットテストを作成",
        "3. Streamlitのモック化によるUIテストの自動化",
        "4. 関数の引数にバリデーションを追加",
        "5. docstringに引数の詳細な説明を追加"
    ]
    
    for rec in recommendations:
        print(f"💡 {rec}")
    
    return True


def main():
    """メインテスト実行"""
    print("TextffCut UIコンポーネント詳細テスト\n")
    
    results = []
    
    # 各テストを実行
    results.append(test_ui_component_signatures())
    results.append(test_text_editing_page_usage())
    results.append(generate_test_recommendations())
    
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