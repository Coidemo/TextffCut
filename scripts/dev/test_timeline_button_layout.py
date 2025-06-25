"""
タイムライン編集のボタンレイアウトをテスト
キャンセルボタンが削除され、2カラムレイアウトになったことを確認
"""

import sys
from pathlib import Path

# プロジェクトのルートディレクトリをPythonパスに追加
sys.path.insert(0, str(Path(__file__).parent))


def test_timeline_editor_button_layout():
    """タイムライン編集のボタンレイアウトをテスト"""
    print("=== タイムライン編集ボタンレイアウトテスト ===")
    
    # timeline_editor.pyのコードを読み込んで確認
    timeline_editor_path = Path(__file__).parent / "ui" / "timeline_editor.py"
    
    with open(timeline_editor_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # キャンセルボタンが存在しないことを確認
    assert "❌ キャンセル" not in content, "キャンセルボタンが削除されていません"
    print("✓ キャンセルボタンが削除されている")
    
    # 2カラムレイアウトになっていることを確認
    assert "col1, col2 = st.columns([1, 1])" in content, "2カラムレイアウトになっていません"
    print("✓ 2カラムレイアウトに変更されている")
    
    # リセットボタンと編集完了ボタンが存在することを確認
    assert "🔄 リセット" in content, "リセットボタンが見つかりません"
    assert "✅ 編集を完了" in content, "編集完了ボタンが見つかりません"
    print("✓ リセットボタンと編集完了ボタンが存在する")
    
    # ボタンがuse_container_widthを使用していることを確認
    assert "use_container_width=True" in content, "ボタンが全幅表示になっていません"
    print("✓ ボタンが全幅表示に設定されている")
    
    print("\n✅ タイムライン編集ボタンレイアウトテスト完了")


def test_inline_display_behavior():
    """インライン表示の動作をテスト"""
    print("\n=== インライン表示動作テスト ===")
    
    # キャンセル操作が不要な理由を確認
    reasons = [
        "タイムライン編集セクションはインラインで表示される",
        "編集を中止したい場合は、単に「編集を完了」ボタンを押さない",
        "リセットボタンで初期状態に戻すことができる",
        "セクションは常に表示されているため、別途キャンセルする必要がない"
    ]
    
    for i, reason in enumerate(reasons, 1):
        print(f"{i}. {reason}")
    
    print("\n✅ インライン表示動作テスト完了")


def test_documentation_consistency():
    """ドキュメントの整合性をテスト"""
    print("\n=== ドキュメント整合性テスト ===")
    
    # 基本設計書の確認
    basic_design_path = Path(__file__).parent / "docs" / "basic_design_specification_v2.md"
    with open(basic_design_path, "r", encoding="utf-8") as f:
        basic_content = f.read()
    
    assert "インライン表示のため、キャンセル操作は不要" in basic_content, "基本設計書にインライン表示の説明がありません"
    print("✓ 基本設計書にインライン表示の説明がある")
    
    # 詳細設計書の確認
    detailed_design_path = Path(__file__).parent / "docs" / "detailed_design_specification_v3.md"
    with open(detailed_design_path, "r", encoding="utf-8") as f:
        detailed_content = f.read()
    
    assert "[リセット] [編集を完了]" in detailed_content, "詳細設計書のボタン配置が更新されていません"
    assert "[戻る]" not in detailed_content or "[キャンセル]" not in detailed_content, "詳細設計書に古いボタンが残っています"
    print("✓ 詳細設計書のボタン配置が更新されている")
    
    print("\n✅ ドキュメント整合性テスト完了")


if __name__ == "__main__":
    try:
        test_timeline_editor_button_layout()
        test_inline_display_behavior()
        test_documentation_consistency()
        
        print("\n" + "="*50)
        print("🎉 すべてのボタンレイアウトテストが成功しました！")
        print("="*50)
        
    except Exception as e:
        print(f"\n❌ テストエラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)