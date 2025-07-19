"""エクスポートセクションのデバッグ"""
import pytest
from playwright.sync_api import Page


def test_debug_export_section(page: Page):
    """エクスポートセクションの要素を確認"""
    page.goto("http://localhost:8502")
    page.wait_for_timeout(5000)
    
    # 全要素のキーをデバッグ
    elements = page.locator('[class*="st-key-"]').all()
    print(f"\n見つかった要素数: {len(elements)}")
    
    for elem in elements:
        classes = elem.get_attribute("class")
        # st-key-xxx の部分を抽出
        import re
        key_match = re.search(r'st-key-(\S+)', classes)
        if key_match:
            key = key_match.group(1)
            print(f"Key: {key}")
    
    # エクスポート関連の要素を探す
    print("\n---- エクスポート関連の要素 ----")
    
    # ラジオボタンを探す
    radios = page.locator('input[type="radio"]').all()
    print(f"ラジオボタン数: {len(radios)}")
    
    # エクスポート形式のラジオボタンを探す
    export_section = page.locator('text="エクスポート形式"')
    if export_section.count() > 0:
        print("エクスポート形式セクションを発見")
        # 親要素を探して、その中のラジオボタンを探す
        parent = export_section.locator('..').locator('..')
        radio_containers = parent.locator('[data-baseweb="radio"]').all()
        print(f"ラジオボタンコンテナ数: {len(radio_containers)}")
    
    # スクリーンショット
    page.screenshot(path="tests/e2e/screenshots/debug_export_section.png")
    print("\nスクリーンショット保存: debug_export_section.png")