"""キャッシュ使用ボタンのクリックテスト"""
import pytest
from playwright.sync_api import Page
from utils.e2e_helpers import E2EHelper
from utils.test_ids import TestIds


def test_click_use_cache_button(page: Page):
    """キャッシュ使用ボタンをクリックできるか確認"""
    e2e_helper = E2EHelper(page)
    
    # ページにアクセス
    page.goto("http://localhost:8502")
    e2e_helper.wait_for_streamlit_reload()
    
    # 動画を選択
    video_dropdown = e2e_helper.get_by_key(TestIds.VIDEO_SELECT_DROPDOWN)
    video_dropdown.locator('svg').locator('..').first.click()
    page.wait_for_timeout(1000)
    
    options = page.locator('[role="option"]:visible').all()
    for option in options:
        if "e2e_test_30s_speech_dense.mp4" in option.text_content():
            option.click()
            break
    
    e2e_helper.wait_for_streamlit_reload()
    
    # キャッシュセクションを確認
    cache_header = page.locator('text=過去の文字起こし結果を利用する').first
    if cache_header.count() > 0:
        print("キャッシュセクションを発見")
        
        # キャッシュ選択
        cache_select = page.locator(f'.st-key-{TestIds.TRANSCRIPTION_CACHE_SELECT}').first
        cache_dropdown_arrow = cache_select.locator('svg').first
        cache_dropdown_arrow.click(force=True)
        page.wait_for_timeout(1000)
        
        cache_options = page.locator('[role="option"]:visible').all()
        print(f"キャッシュオプション数: {len(cache_options)}")
        
        if len(cache_options) > 1:
            print(f"キャッシュオプション[1]を選択: {cache_options[1].text_content()}")
            cache_options[1].click()
            e2e_helper.wait_for_streamlit_reload()
        else:
            print("キャッシュオプションが不足")
            
            # ボタンを探す - まずスクリーンショットを撮る
            page.wait_for_timeout(2000)
            page.screenshot(path="tests/e2e/screenshots/before_button_click.png")
            
            # 方法1: TestIds
            print("\n=== TestIdsでボタンを探す ===")
            use_cache_button = e2e_helper.get_by_key(TestIds.TRANSCRIPTION_USE_CACHE_BUTTON)
            print(f"ボタンが見つかった: {use_cache_button.is_visible()}")
            
            if use_cache_button.is_visible():
                print("TestIdsでボタンをクリック")
                use_cache_button.click()
                e2e_helper.wait_for_streamlit_reload()
                page.wait_for_timeout(3000)
                page.screenshot(path="tests/e2e/screenshots/after_button_click.png")
                print("クリック後のスクリーンショットを保存")
            else:
                # 方法2: テキストで探す
                print("\n=== テキストでボタンを探す ===")
                button_texts = ["選択した結果を使用", "📁選択した結果を使用", "使用"]
                for text in button_texts:
                    button = page.locator(f'button:has-text("{text}")').first
                    if button.count() > 0:
                        print(f"「{text}」ボタンを発見")
                        button.click()
                        e2e_helper.wait_for_streamlit_reload()
                        page.wait_for_timeout(3000)
                        page.screenshot(path="tests/e2e/screenshots/after_button_click.png")
                        print("クリック後のスクリーンショットを保存")
                        break
                
                # 方法3: すべてのボタンを確認
                print("\n=== すべてのボタンを確認 ===")
                all_buttons = page.locator('button').all()
                print(f"ボタン総数: {len(all_buttons)}")
                for i, button in enumerate(all_buttons):
                    text = button.text_content() or ""
                    print(f"ボタン[{i}]: {text}")