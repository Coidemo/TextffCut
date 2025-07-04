"""
テキスト編集機能のE2Eテスト例

Selenium WebDriverを使用したE2Eテストのサンプル
"""

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from utils.test_helpers import UITestIds


class TestTextEditorE2E:
    """テキスト編集機能のE2Eテスト"""

    @pytest.fixture
    def driver(self):
        """WebDriverのセットアップ"""
        driver = webdriver.Chrome()  # ChromeDriverが必要
        driver.get("http://localhost:8501")
        yield driver
        driver.quit()

    def test_text_editor_display(self, driver):
        """文字起こし結果とテキストエディタが表示されることを確認"""
        # 文字起こし結果コンテナが表示されるまで待つ
        wait = WebDriverWait(driver, 10)
        transcription_container = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, UITestIds.get_selector(UITestIds.TRANSCRIPTION_RESULT_CONTAINER))
            )
        )
        assert transcription_container is not None

        # テキストエディタが存在することを確認
        text_editor = driver.find_element(
            By.CSS_SELECTOR, f"textarea{UITestIds.get_key_selector(UITestIds.TEXT_EDITOR_WIDGET)}"
        )
        assert text_editor is not None

    def test_update_button_click(self, driver):
        """更新ボタンのクリックテスト"""
        wait = WebDriverWait(driver, 10)

        # テキストエディタに文字を入力
        text_editor = wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, f"textarea{UITestIds.get_key_selector(UITestIds.TEXT_EDITOR_WIDGET)}")
            )
        )
        text_editor.clear()
        text_editor.send_keys("テストテキスト")

        # 更新ボタンをクリック
        update_button = driver.find_element(
            By.CSS_SELECTOR, f"button{UITestIds.get_key_selector(UITestIds.UPDATE_BUTTON)}"
        )
        update_button.click()

        # 処理が完了するまで待つ（Streamlitのリロードを考慮）
        wait.until(EC.staleness_of(update_button))

    def test_boundary_adjustment_mode(self, driver):
        """境界調整モードの切り替えテスト"""
        wait = WebDriverWait(driver, 10)

        # 境界調整モードチェックボックスを探す
        checkbox = wait.until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    f'input[type="checkbox"]{UITestIds.get_key_selector(UITestIds.BOUNDARY_ADJUSTMENT_CHECKBOX)}',
                )
            )
        )

        # チェックボックスの状態を確認
        initial_state = checkbox.is_selected()

        # クリックして状態を変更
        checkbox.click()

        # 状態が変わったことを確認
        assert checkbox.is_selected() != initial_state
