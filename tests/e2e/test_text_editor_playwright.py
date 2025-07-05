"""
Playwrightを使用したE2Eテスト例

より現代的なE2Eテストフレームワーク
"""

import pytest
from playwright.sync_api import Page, expect

from utils.test_helpers import UITestIds


class TestTextEditorPlaywright:
    """Playwrightを使用したテキスト編集機能のE2Eテスト"""

    @pytest.fixture
    def page(self, browser):
        """ページのセットアップ"""
        page = browser.new_page()
        page.goto("http://localhost:8501")
        yield page
        page.close()

    def test_text_editor_workflow(self, page: Page):
        """テキスト編集の一連のワークフローをテスト"""
        # 文字起こし結果の表示を確認
        transcription_container = page.locator(UITestIds.get_selector(UITestIds.TRANSCRIPTION_RESULT_CONTAINER))
        expect(transcription_container).to_be_visible()

        # テキストエディタにテキストを入力
        text_editor = page.locator(f"textarea{UITestIds.get_key_selector(UITestIds.TEXT_EDITOR_WIDGET)}")
        text_editor.fill("これはテストテキストです")

        # 更新ボタンをクリック
        update_button = page.locator(f"button{UITestIds.get_key_selector(UITestIds.UPDATE_BUTTON)}")
        update_button.click()

        # Streamlitのリロードを待つ
        page.wait_for_timeout(1000)

        # 結果が反映されていることを確認
        # （実際のテストでは、具体的な期待値を設定）

    def test_boundary_adjustment_markers(self, page: Page):
        """境界調整マーカーの動作テスト"""
        # 境界調整モードを有効にする
        boundary_checkbox = page.locator(
            f'input[type="checkbox"]{UITestIds.get_key_selector(UITestIds.BOUNDARY_ADJUSTMENT_CHECKBOX)}'
        )
        boundary_checkbox.check()

        # テキストエディタにマーカー付きテキストを入力
        text_editor = page.locator(f"textarea{UITestIds.get_key_selector(UITestIds.TEXT_EDITOR_WIDGET)}")
        text_editor.fill("[<0.5]テストテキスト[0.3>]")

        # 更新ボタンをクリック
        update_button = page.locator(f"button{UITestIds.get_key_selector(UITestIds.UPDATE_BUTTON)}")
        update_button.click()

        # マーカーが処理されることを確認
        # （実際のテストでは、処理結果を検証）

    async def test_audio_preview_generation(self, page: Page):
        """音声プレビューの生成テスト"""
        # テキストを入力して更新
        text_editor = page.locator(f"textarea{UITestIds.get_key_selector(UITestIds.TEXT_EDITOR_WIDGET)}")
        text_editor.fill("音声プレビューテスト")

        update_button = page.locator(f"button{UITestIds.get_key_selector(UITestIds.UPDATE_BUTTON)}")
        update_button.click()

        # 音声プレビューが生成されるまで待つ
        audio_element = page.locator("audio")
        await expect(audio_element).to_be_visible(timeout=5000)
