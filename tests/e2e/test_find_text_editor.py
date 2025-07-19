"""テキストエディタの要素を探すデバッグテスト"""
import pytest
from playwright.sync_api import Page
from utils.e2e_helpers import E2EHelper
from utils.test_ids import TestIds


def test_find_text_editor(page: Page):
    """テキストエディタの要素を探す"""
    e2e_helper = E2EHelper(page)
    
    # ページにアクセス
    page.goto("http://localhost:8502")
    e2e_helper.wait_for_streamlit_reload()
    
    # 動画を選択（前回と同じ手順）
    video_dropdown = e2e_helper.get_by_key(TestIds.VIDEO_SELECT_DROPDOWN)
    video_dropdown.locator('svg').locator('..').first.click()
    page.wait_for_timeout(1000)
    
    options = page.locator('[role="option"]:visible').all()
    for option in options:
        if "e2e_test_30s_speech_dense.mp4" in option.text_content():
            option.click()
            break
    
    e2e_helper.wait_for_streamlit_reload()
    
    # キャッシュを使用
    cache_header = page.locator('text=過去の文字起こし結果を利用する').first
    if cache_header.count() > 0:
        cache_select = page.locator(f'.st-key-{TestIds.TRANSCRIPTION_CACHE_SELECT}').first
        if cache_select.count() > 0:
            cache_dropdown_arrow = cache_select.locator('svg').first
            cache_dropdown_arrow.click(force=True)
            page.wait_for_timeout(1000)
            
            cache_options = page.locator('[role="option"]:visible').all()
            if len(cache_options) > 1:
                cache_options[1].click()
                e2e_helper.wait_for_streamlit_reload()
                
                use_cache_button = e2e_helper.get_by_key(TestIds.TRANSCRIPTION_USE_CACHE_BUTTON)
                use_cache_button.click()
                e2e_helper.wait_for_streamlit_reload()
    
    # 待機
    page.wait_for_timeout(3000)
    
    # すべてのtextareaを探す
    print("\n=== すべてのtextarea要素 ===")
    all_textareas = page.locator('textarea').all()
    print(f"textarea総数: {len(all_textareas)}")
    
    for i, textarea in enumerate(all_textareas):
        parent_div = textarea.locator('..')
        classes = parent_div.get_attribute('class') or ''
        value = textarea.input_value()[:50] if textarea.input_value() else '(空)'
        is_readonly = textarea.get_attribute('readonly') is not None
        
        print(f"\ntextarea[{i}]:")
        print(f"  親のクラス: {classes}")
        print(f"  値: {value}...")
        print(f"  読み取り専用: {is_readonly}")
        
        # st-key-*のクラスを探す
        import re
        key_match = re.search(r'st-key-(\S+)', classes)
        if key_match:
            print(f"  キー: {key_match.group(1)}")
    
    # 切り抜き箇所と思われるセクションを探す
    print("\n=== 切り抜き箇所セクション ===")
    cut_section = page.locator('text="✂️ 切り抜き箇所"').first
    if cut_section.count() > 0:
        print("切り抜き箇所セクションを発見")
        # その下のtextareaを探す
        parent = cut_section.locator('..').locator('..')
        textarea_in_section = parent.locator('textarea').first
        if textarea_in_section.count() > 0:
            print("切り抜き箇所のtextareaを発見")
            # その親のクラスを確認
            textarea_parent = textarea_in_section.locator('..')
            classes = textarea_parent.get_attribute('class') or ''
            print(f"親のクラス: {classes}")
    
    # スクリーンショット
    page.screenshot(path="tests/e2e/screenshots/text_editor_debug.png")
    print("\nスクリーンショット保存: text_editor_debug.png")