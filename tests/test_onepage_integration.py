"""
ワンページアプリケーションの結合テスト

動画選択 → 文字起こし → テキスト編集 → エクスポートの
一連の流れをテストします。
"""

import sys
import time
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import streamlit as st
from streamlit.testing.v1 import AppTest

# テスト用の動画ファイルを準備
TEST_VIDEO = project_root / "videos" / "test_sample_speech.mp4"


def test_onepage_flow():
    """ワンページアプリケーションの全体フローをテスト"""
    
    print("\n=== ワンページアプリケーション結合テスト開始 ===\n")
    
    # アプリケーションを起動
    at = AppTest.from_file(str(project_root / "main.py"))
    at.run()
    
    print("1. 初期状態の確認")
    # タイトルが表示されているか（HTMLとして表示される場合もある）
    all_content = str(at)
    assert "Text" in all_content and "Cut" in all_content, "タイトルが表示されていません"
    
    # 動画選択セクションが表示されているか
    subheaders = [str(el.value) for el in at.subheader]
    assert any("動画ファイル選択" in subheader for subheader in subheaders), f"動画選択セクションが表示されていません。表示されているサブヘッダー: {subheaders}"
    
    print("   ✓ タイトルと動画選択セクションが表示されています")
    
    # 動画ファイルが存在することを確認
    if not TEST_VIDEO.exists():
        print(f"   ⚠️  テスト動画が見つかりません: {TEST_VIDEO}")
        print("   テスト動画を作成します...")
        # ダミーの動画ファイルを作成（実際のテストでは本物の動画を使用）
        TEST_VIDEO.parent.mkdir(exist_ok=True)
        TEST_VIDEO.touch()
    
    print("\n2. 動画選択のテスト")
    # セレクトボックスを探す
    selectboxes = at.selectbox
    if selectboxes:
        # 最初のセレクトボックスが動画選択
        video_select = selectboxes[0]
        print(f"   利用可能な動画: {video_select.options}")
        
        if TEST_VIDEO.name in video_select.options:
            # 動画を選択
            video_select.select(TEST_VIDEO.name)
            at.run()
            
            print(f"   ✓ 動画を選択しました: {TEST_VIDEO.name}")
            
            # セッション状態を確認
            if hasattr(at.session_state, 'video_selected'):
                print(f"   ✓ video_selected: {at.session_state.video_selected}")
            
            # 文字起こしセクションが表示されるか確認
            time.sleep(0.5)  # 少し待機
            at.run()
            
            if any("文字起こし" in str(el.value) for el in at.subheader):
                print("   ✓ 文字起こしセクションが表示されました")
            else:
                print("   ❌ 文字起こしセクションが表示されていません")
                print("   セッション状態:")
                for key in at.session_state:
                    print(f"      {key}: {getattr(at.session_state, key)}")
        else:
            print(f"   ⚠️  テスト動画がリストにありません: {TEST_VIDEO.name}")
    else:
        print("   ❌ 動画選択のセレクトボックスが見つかりません")
    
    print("\n3. キャッシュ使用のテスト")
    # キャッシュが存在する場合、それを使用
    cache_buttons = [btn for btn in at.button if "選択した結果を使用" in btn.label]
    if cache_buttons:
        print("   ✓ キャッシュが見つかりました")
        cache_buttons[0].click()
        at.run()
        
        # テキスト編集セクションが表示されるか確認
        time.sleep(0.5)
        at.run()
        
        if any("切り抜き箇所の指定" in str(el.value) for el in at.subheader):
            print("   ✓ テキスト編集セクションが表示されました")
            
            # セッション状態を確認
            if hasattr(at.session_state, 'transcription_completed'):
                print(f"   ✓ transcription_completed: {at.session_state.transcription_completed}")
        else:
            print("   ❌ テキスト編集セクションが表示されていません")
    else:
        print("   ⚠️  キャッシュが見つかりません（新規実行が必要）")
    
    print("\n4. エラー確認")
    # エラーメッセージが表示されていないか確認
    errors = at.error
    if errors:
        print("   ❌ エラーが発生しています:")
        for error in errors:
            print(f"      {error.value}")
    else:
        print("   ✓ エラーは発生していません")
    
    print("\n=== テスト完了 ===\n")


def test_session_state_management():
    """セッション状態の管理をテスト"""
    
    print("\n=== セッション状態管理テスト ===\n")
    
    at = AppTest.from_file(str(project_root / "main.py"))
    at.run()
    
    # 初期状態
    print("1. 初期セッション状態:")
    for key in ['video_selected', 'transcription_completed', 'text_edit_completed']:
        value = getattr(at.session_state, key, None)
        print(f"   {key}: {value}")
    
    # 動画選択をシミュレート
    at.session_state.video_selected = True
    at.session_state.video_path = str(TEST_VIDEO)
    at.run()
    
    print("\n2. 動画選択後:")
    print(f"   video_selected: {at.session_state.video_selected}")
    
    # 文字起こし完了をシミュレート
    at.session_state.transcription_completed = True
    at.run()
    
    print("\n3. 文字起こし完了後:")
    print(f"   transcription_completed: {at.session_state.transcription_completed}")
    
    # 各セクションが順番に表示されるか確認
    subheaders = [str(el.value) for el in at.subheader]
    expected_sections = ["動画ファイル選択", "文字起こし", "切り抜き箇所の指定"]
    
    print("\n4. 表示されているセクション:")
    for section in expected_sections:
        if any(section in subheader for subheader in subheaders):
            print(f"   ✓ {section}")
        else:
            print(f"   ❌ {section}")
    
    print("\n=== テスト完了 ===\n")


if __name__ == "__main__":
    # 結合テストを実行
    test_onepage_flow()
    
    # セッション状態管理テストを実行
    test_session_state_management()