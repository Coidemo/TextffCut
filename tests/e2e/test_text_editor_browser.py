"""
TextEditor機能のブラウザE2Eテスト

Playwrightを使用して実際のブラウザを操作し、スクリーンショットを保存します。
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


class TestTextEditorBrowserE2E:
    """TextEditor機能のブラウザE2Eテスト"""

    @pytest.fixture(scope="class")
    def streamlit_server(self):
        """Streamlitサーバーを起動"""
        # サーバープロセスを起動
        process = subprocess.Popen(
            ["streamlit", "run", "main.py", "--server.headless=true"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # サーバーの起動を待つ
        time.sleep(5)

        yield "http://localhost:8501"

        # サーバーを終了
        process.terminate()
        process.wait()

    @pytest.fixture(autouse=True)
    def setup_screenshots(self):
        """スクリーンショット保存の設定"""
        self.screenshot_dir = Path("tests/e2e/screenshots")
        self.screenshot_dir.mkdir(exist_ok=True, parents=True)

        # タイムスタンプ付きのサブディレクトリを作成
        self.test_run_dir = self.screenshot_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_run_dir.mkdir(exist_ok=True)

    def save_screenshot(self, page: Page, name: str):
        """スクリーンショットを保存"""
        filename = f"{name}_{datetime.now().strftime('%H%M%S')}.png"
        filepath = self.test_run_dir / filename
        page.screenshot(path=str(filepath), full_page=True)
        print(f"Screenshot saved: {filepath}")
        return filepath

    def test_initial_page_load(self, page: Page, streamlit_server: str):
        """初期ページ読み込みテスト"""
        # ページを開く
        page.goto(streamlit_server)

        # Streamlitが完全に読み込まれるまで待つ
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # さらに初期コンテンツが表示されるまで待つ
        page.wait_for_timeout(3000)  # 3秒待つ

        # スクリーンショットを保存
        self.save_screenshot(page, "01_initial_load")

        # タイトルが表示されていることを確認
        # h1, h2, h3など様々なヘッダータグを探す
        header = page.locator("h1, h2, h3").filter(has_text="TextffCut").first
        if header.is_visible():
            expect(header).to_contain_text("TextffCut")
        else:
            # またはタイトルがコンテナ内にある場合
            expect(page.locator('[data-testid="stMarkdown"]')).to_contain_text("TextffCut")

    def test_video_upload_flow(self, page: Page, streamlit_server: str):
        """動画アップロードフローのテスト"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 初期状態のスクリーンショット
        self.save_screenshot(page, "02_before_upload")

        # ファイル選択セクションを探す
        try:
            video_section = page.locator('text="動画ファイルの選択"').first
            if video_section.is_visible():
                video_section.scroll_into_view_if_needed()
                self.save_screenshot(page, "03_video_selection_found")
            else:
                # 別の表記を試す
                video_section = page.locator('text="動画"').first
                if video_section.is_visible():
                    video_section.scroll_into_view_if_needed()
                    self.save_screenshot(page, "03_video_section_alternative")
        except Exception as e:
            print(f"Video section not found: {e}")
            self.save_screenshot(page, "03_video_section_not_found")

    def test_transcription_section(self, page: Page, streamlit_server: str):
        """文字起こしセクションのテスト"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # 文字起こしセクションまでスクロール
        transcription_section = page.locator('text="文字起こし"').first
        if transcription_section.is_visible():
            transcription_section.scroll_into_view_if_needed()
            self.save_screenshot(page, "04_transcription_section")

    def test_text_editor_ui_elements(self, page: Page, streamlit_server: str):
        """テキストエディタUI要素のテスト"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # テキスト編集セクションを探す
        try:
            # テキスト編集セクションまでスクロール
            editor_section = page.locator('text="テキスト編集"').first
            if editor_section.is_visible():
                editor_section.scroll_into_view_if_needed()
                time.sleep(1)  # スクロールアニメーションを待つ
                self.save_screenshot(page, "05_text_editor_section")

                # 境界調整モードのチェックボックスを探す
                boundary_checkbox = page.locator('[data-testid="boundary_adjustment_checkbox"]')
                if boundary_checkbox.is_visible():
                    self.save_screenshot(page, "06_boundary_adjustment_checkbox")

                    # チェックボックスをクリック
                    boundary_checkbox.click()
                    time.sleep(0.5)
                    self.save_screenshot(page, "07_boundary_adjustment_enabled")
        except Exception as e:
            print(f"Text editor section not found: {e}")
            self.save_screenshot(page, "05_text_editor_not_found")

    def test_responsive_layout(self, page: Page, streamlit_server: str):
        """レスポンシブレイアウトのテスト"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # デスクトップサイズ
        page.set_viewport_size({"width": 1920, "height": 1080})
        self.save_screenshot(page, "08_desktop_view")

        # タブレットサイズ
        page.set_viewport_size({"width": 768, "height": 1024})
        self.save_screenshot(page, "09_tablet_view")

        # モバイルサイズ
        page.set_viewport_size({"width": 375, "height": 667})
        self.save_screenshot(page, "10_mobile_view")

    def test_error_states(self, page: Page, streamlit_server: str):
        """エラー状態のテスト"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # エラー表示を探す
        error_elements = page.locator('[data-testid="stAlert"]')
        if error_elements.count() > 0:
            self.save_screenshot(page, "11_error_states")

    def test_full_workflow_simulation(self, page: Page, streamlit_server: str):
        """完全なワークフローのシミュレーション"""
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)

        # 1. 初期状態
        self.save_screenshot(page, "12_workflow_start")

        # 2. 各セクションをスクロールして表示
        sections = ["動画ファイルの選択", "文字起こし", "テキスト編集", "切り抜き処理"]

        for i, section_text in enumerate(sections):
            try:
                section = page.locator(f'text="{section_text}"').first
                if section.is_visible():
                    section.scroll_into_view_if_needed()
                    time.sleep(0.5)
                    self.save_screenshot(page, f"13_workflow_section_{i+1}_{section_text.replace(' ', '_')}")
            except Exception as e:
                print(f"Section '{section_text}' not found: {e}")

        # 最終状態
        self.save_screenshot(page, "14_workflow_end")


@pytest.fixture(scope="module")
def browser_context_args(browser_context_args):
    """ブラウザコンテキストの設定"""
    return {
        **browser_context_args,
        "locale": "ja-JP",
        "timezone_id": "Asia/Tokyo",
    }


@pytest.fixture(scope="function")
def page(page: Page):
    """ページの基本設定"""
    # 日本語フォントの読み込みを待つ
    page.wait_for_load_state("networkidle")
    return page
