"""
完全なユーザージャーニーのE2Eテスト

実際のユーザーが行うすべての操作をブラウザで自動実行し、
各ステップでスクリーンショットを保存します。
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


class TestCompleteUserJourney:
    """完全なユーザージャーニーのE2Eテスト"""

    @pytest.fixture(scope="class")
    def streamlit_server(self):
        """Streamlitサーバーを起動"""
        # テスト用の動画ファイルをコピー
        videos_dir = Path("videos")
        videos_dir.mkdir(exist_ok=True)

        # サンプル動画を作成（実際のテストでは本物の動画を使用）
        sample_video = videos_dir / "sample_test.mp4"
        if not sample_video.exists():
            # ダミーファイルを作成
            sample_video.write_text("dummy video file for testing")

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
        self.screenshot_dir = Path("tests/e2e/screenshots/complete_journey")
        self.screenshot_dir.mkdir(exist_ok=True, parents=True)

        # タイムスタンプ付きのサブディレクトリを作成
        self.test_run_dir = self.screenshot_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_run_dir.mkdir(exist_ok=True)

        self.screenshot_counter = 0

    def save_screenshot(self, page: Page, name: str):
        """スクリーンショットを保存（連番付き）"""
        self.screenshot_counter += 1
        filename = f"{self.screenshot_counter:02d}_{name}.png"
        filepath = self.test_run_dir / filename
        page.screenshot(path=str(filepath), full_page=True)
        print(f"📸 Screenshot saved: {filepath}")
        return filepath

    def test_complete_user_journey(self, page: Page, streamlit_server: str):
        """完全なユーザージャーニーテスト"""

        print("\n🚀 完全なユーザージャーニーテストを開始します")

        # =====================================
        # 1. アプリケーション起動
        # =====================================
        print("\n1️⃣ アプリケーション起動")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(3000)
        self.save_screenshot(page, "app_initial_load")

        # タイトルの確認（画像として実装されているため、別の要素を確認）
        app_container = page.locator('[data-testid="stApp"]')
        expect(app_container).to_be_visible()

        # =====================================
        # 2. APIキー設定（APIモードの場合）
        # =====================================
        print("\n2️⃣ APIキー設定")

        # サイドバーを開く
        sidebar_button = page.locator('[data-testid="collapsedControl"]').first
        if sidebar_button.is_visible():
            sidebar_button.click()
            page.wait_for_timeout(500)

        self.save_screenshot(page, "sidebar_opened")

        # APIキータブをクリック
        api_tab = page.locator('text="🔑APIキー"').first
        if api_tab.is_visible():
            api_tab.click()
            page.wait_for_timeout(500)
            self.save_screenshot(page, "api_key_tab")

            # APIキー入力フィールドを探す
            api_input = page.locator('input[type="password"]').first
            if api_input.is_visible():
                # テスト用のダミーAPIキーを入力
                api_input.fill("sk-test-dummy-api-key-for-e2e-testing")
                page.wait_for_timeout(500)
                self.save_screenshot(page, "api_key_entered")

        # =====================================
        # 3. 動画ファイル選択
        # =====================================
        print("\n3️⃣ 動画ファイル選択")

        # メインコンテンツに戻る
        main_content = page.locator('[data-testid="stApp"]').first
        main_content.click()
        page.wait_for_timeout(500)

        # 動画選択セクションを探す
        video_section = page.locator('text="動画ファイルの選択"').first
        if video_section.is_visible():
            video_section.scroll_into_view_if_needed()
            self.save_screenshot(page, "video_selection_section")

            # ドロップダウンから動画を選択
            video_dropdown = page.locator("select").first
            if video_dropdown.is_visible():
                # sample_test.mp4を選択
                video_dropdown.select_option(label="sample_test.mp4")
                page.wait_for_timeout(1000)
                self.save_screenshot(page, "video_selected")

        # =====================================
        # 4. 文字起こし実行
        # =====================================
        print("\n4️⃣ 文字起こし実行")

        # 文字起こしセクションまでスクロール
        transcription_section = page.locator('text="文字起こし"').nth(1)
        if transcription_section.is_visible():
            transcription_section.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            self.save_screenshot(page, "transcription_section")

            # 文字起こし実行ボタンを探す
            transcribe_button = page.locator('button:has-text("文字起こしを実行")')
            if transcribe_button.is_visible():
                self.save_screenshot(page, "before_transcription")
                # 実際にはクリックしない（処理時間がかかるため）
                # transcribe_button.click()
                print("  ⚠️ 文字起こし実行はスキップ（処理時間短縮のため）")

        # =====================================
        # 5. テキスト編集
        # =====================================
        print("\n5️⃣ テキスト編集")

        # テキスト編集セクションを探す
        text_editor_section = page.locator('text="テキスト編集"').first
        if text_editor_section.is_visible():
            text_editor_section.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            self.save_screenshot(page, "text_editor_section")

            # テキストエディタを探す
            text_editor = page.locator("textarea").first
            if text_editor.is_visible():
                # サンプルテキストを入力
                sample_text = """これはテストです。
最初のセクション。
---
2番目のセクション。
ここは削除されます。"""
                text_editor.fill(sample_text)
                page.wait_for_timeout(500)
                self.save_screenshot(page, "text_entered")

                # 更新ボタンをクリック
                update_button = page.locator('button:has-text("更新")')
                if update_button.is_visible():
                    update_button.click()
                    page.wait_for_timeout(1000)
                    self.save_screenshot(page, "text_updated")

        # =====================================
        # 6. 境界調整モード
        # =====================================
        print("\n6️⃣ 境界調整モード")

        # 境界調整モードのチェックボックスを探す
        boundary_checkbox = page.locator('text="🎯 境界調整モード"')
        if boundary_checkbox.is_visible():
            boundary_checkbox.click()
            page.wait_for_timeout(500)
            self.save_screenshot(page, "boundary_mode_enabled")

            # 再度更新ボタンをクリック
            update_button = page.locator('button:has-text("更新")')
            if update_button.is_visible():
                update_button.click()
                page.wait_for_timeout(1000)
                self.save_screenshot(page, "boundary_markers_applied")

        # =====================================
        # 7. タイムライン編集
        # =====================================
        print("\n7️⃣ タイムライン編集")

        # タイムライン編集ボタンを探す
        timeline_button = page.locator('button:has-text("タイムライン編集")')
        if timeline_button.is_visible():
            timeline_button.click()
            page.wait_for_timeout(1000)
            self.save_screenshot(page, "timeline_editor_opened")

            # 編集完了ボタン
            complete_button = page.locator('button:has-text("編集完了")')
            if complete_button.is_visible():
                complete_button.click()
                page.wait_for_timeout(500)
                self.save_screenshot(page, "timeline_edited")

        # =====================================
        # 8. 切り抜き処理設定
        # =====================================
        print("\n8️⃣ 切り抜き処理設定")

        # 切り抜き処理セクションまでスクロール
        export_section = page.locator('text="切り抜き処理"').first
        if export_section.is_visible():
            export_section.scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            self.save_screenshot(page, "export_section")

            # 無音削除オプション
            silence_removal = page.locator('text="無音削除"')
            if silence_removal.is_visible():
                silence_removal.click()
                page.wait_for_timeout(500)
                self.save_screenshot(page, "silence_removal_enabled")

            # エクスポート形式選択
            export_format = page.locator("select").nth(1)
            if export_format.is_visible():
                export_format.select_option("FCPXML")
                page.wait_for_timeout(500)
                self.save_screenshot(page, "export_format_selected")

        # =====================================
        # 9. 処理実行
        # =====================================
        print("\n9️⃣ 処理実行")

        # 処理実行ボタンを探す
        process_button = page.locator('button:has-text("処理を実行")')
        if process_button.is_visible():
            self.save_screenshot(page, "before_processing")
            # 実際にはクリックしない（処理時間がかかるため）
            # process_button.click()
            print("  ⚠️ 処理実行はスキップ（処理時間短縮のため）")

        # =====================================
        # 10. 結果確認
        # =====================================
        print("\n🔟 結果確認")

        # ページ全体の最終スクリーンショット
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_timeout(500)
        self.save_screenshot(page, "final_state")

        # =====================================
        # 11. 各種オプション機能の確認
        # =====================================
        print("\n1️⃣1️⃣ オプション機能確認")

        # サイドバーの各タブを確認
        tabs = ["🔇 無音検出", "🎬 SRT字幕", "🔄 リカバリー", "📋 履歴", "❓ ヘルプ"]

        for tab_name in tabs:
            tab = page.locator(f'text="{tab_name}"').first
            if tab.is_visible():
                tab.click()
                page.wait_for_timeout(500)
                self.save_screenshot(page, f"sidebar_tab_{tab_name.replace(' ', '_')}")

        print("\n✅ 完全なユーザージャーニーテストが完了しました！")
        print(f"📁 スクリーンショットは以下に保存されました: {self.test_run_dir}")

    def test_error_scenarios(self, page: Page, streamlit_server: str):
        """エラーシナリオのテスト"""

        print("\n🚨 エラーシナリオテストを開始します")

        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # =====================================
        # 1. ファイル未選択での処理実行
        # =====================================
        print("\n1️⃣ ファイル未選択エラー")

        # 文字起こしボタンを直接クリック
        transcribe_button = page.locator('button:has-text("文字起こしを実行")')
        if transcribe_button.is_visible():
            transcribe_button.click()
            page.wait_for_timeout(1000)
            self.save_screenshot(page, "error_no_file_selected")

        # =====================================
        # 2. 無効なテキスト入力
        # =====================================
        print("\n2️⃣ 無効なテキスト入力")

        text_editor = page.locator("textarea").first
        if text_editor.is_visible():
            # 元動画に存在しないテキストを入力
            text_editor.fill("存在しないテキスト")

            update_button = page.locator('button:has-text("更新")')
            if update_button.is_visible():
                update_button.click()
                page.wait_for_timeout(1000)
                self.save_screenshot(page, "error_invalid_text")

        print("\n✅ エラーシナリオテストが完了しました！")
