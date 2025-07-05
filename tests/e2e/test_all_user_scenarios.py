"""
すべてのユーザーシナリオを網羅したE2Eテスト

実際のユーザーが遭遇するあらゆるシナリオをテストし、
各操作の詳細なスクリーンショットを保存します。
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path

import pytest
from playwright.sync_api import Page


class TestAllUserScenarios:
    """すべてのユーザーシナリオのE2Eテスト"""

    @pytest.fixture(scope="class")
    def streamlit_server(self):
        """Streamlitサーバーを起動"""
        # テスト用の動画ファイルをコピー
        videos_dir = Path("videos")
        videos_dir.mkdir(exist_ok=True)

        # 文字起こし済みの動画が存在することを確認
        # 実際のテストでは既存の文字起こし済み動画を使用

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
        self.screenshot_dir = Path("tests/e2e/screenshots/all_scenarios")
        self.screenshot_dir.mkdir(exist_ok=True, parents=True)

        # タイムスタンプ付きのサブディレクトリを作成
        self.test_run_dir = self.screenshot_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
        self.test_run_dir.mkdir(exist_ok=True)

        self.screenshot_counter = 0

    def save_screenshot(self, page: Page, name: str):
        """スクリーンショットを保存（連番付き）"""
        self.screenshot_counter += 1
        filename = f"{self.screenshot_counter:03d}_{name}.png"
        filepath = self.test_run_dir / filename
        page.screenshot(path=str(filepath), full_page=True)
        print(f"📸 {filename}")
        return filepath

    def wait_and_screenshot(self, page: Page, name: str, wait_time: int = 1000):
        """待機してからスクリーンショット"""
        page.wait_for_timeout(wait_time)
        return self.save_screenshot(page, name)

    def scroll_and_screenshot(self, page: Page, name: str, pixels: int = 500):
        """スクロールしてからスクリーンショット"""
        page.evaluate(f"window.scrollBy(0, {pixels})")
        page.wait_for_timeout(500)
        return self.save_screenshot(page, name)

    def test_scenario_1_basic_workflow(self, page: Page, streamlit_server: str):
        """シナリオ1: 基本的なワークフロー（APIキー無し）"""
        print("\n\n🎬 シナリオ1: 基本的なワークフロー")

        # 1. アプリケーション起動
        print("📍 アプリケーション起動")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        self.wait_and_screenshot(page, "01_basic_app_start", 3000)

        # 2. 動画選択
        print("📍 動画ファイル選択")
        # ドロップダウンを探す
        selects = page.locator("select").all()
        if selects:
            self.save_screenshot(page, "02_basic_before_video_selection")
            selects[0].select_option(index=1)  # 最初のファイルを選択
            self.wait_and_screenshot(page, "03_basic_video_selected")

        # 3. 文字起こしセクションの確認
        print("📍 文字起こしセクション")
        # 下にスクロール
        self.scroll_and_screenshot(page, "04_basic_transcription_section")

        # 4. テキスト編集セクションの確認
        print("📍 テキスト編集セクション")
        self.scroll_and_screenshot(page, "05_basic_text_editor_section")

        # 5. 切り抜き処理セクションの確認
        print("📍 切り抜き処理セクション")
        self.scroll_and_screenshot(page, "06_basic_export_section")

    def test_scenario_2_api_mode(self, page: Page, streamlit_server: str):
        """シナリオ2: APIモードでの操作"""
        print("\n\n🎬 シナリオ2: APIモードでの操作")

        # 1. アプリケーション起動
        print("📍 アプリケーション起動")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        self.wait_and_screenshot(page, "01_api_app_start", 2000)

        # 2. サイドバーを開く
        print("📍 サイドバーを開く")
        sidebar_button = page.locator('[data-testid="collapsedControl"]').first
        if sidebar_button.is_visible():
            sidebar_button.click()
            self.wait_and_screenshot(page, "02_api_sidebar_open")
        else:
            # すでに開いている場合
            self.save_screenshot(page, "02_api_sidebar_already_open")

        # 3. APIキータブをクリック
        print("📍 APIキー設定")
        api_tab = page.locator('text="🔑APIキー"').first
        if api_tab.is_visible():
            api_tab.click()
            self.wait_and_screenshot(page, "03_api_key_tab")

            # APIキー入力
            api_inputs = page.locator('input[type="password"]').all()
            if api_inputs:
                api_inputs[0].fill("sk-test-api-key-12345")
                self.wait_and_screenshot(page, "04_api_key_entered")
        else:
            print("  ⚠️ APIキータブが見つかりません")

        # 4. 無音検出タブ
        print("📍 無音検出設定")
        silence_tab = page.locator('text="🔇 無音検出"').first
        if silence_tab.is_visible():
            silence_tab.click()
            self.wait_and_screenshot(page, "05_api_silence_detection")

        # 5. SRT字幕タブ
        print("📍 SRT字幕設定")
        srt_tab = page.locator('text="🎬 SRT字幕"').first
        if srt_tab.is_visible():
            srt_tab.click()
            self.wait_and_screenshot(page, "06_api_srt_settings")

    def test_scenario_3_text_editing(self, page: Page, streamlit_server: str):
        """シナリオ3: テキスト編集の詳細操作"""
        print("\n\n🎬 シナリオ3: テキスト編集の詳細操作")

        # 1. 初期設定
        print("📍 初期設定")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 動画ファイルを選択（文字起こし済みの動画を選択）
        print("📍 動画ファイルを選択")
        selects = page.locator("select").all()
        if selects:
            # 文字起こし済みの動画を探して選択
            options = selects[0].locator("option").all()
            selected = False
            for i, option in enumerate(options):
                text = option.inner_text()
                print(f"    オプション{i}: {text}")
                if "習慣が続かない" in text or "誰しも主人公" in text or "港区おじさん" in text:
                    print(f"    ✅ 文字起こし済み動画を選択: {text}")
                    selects[0].select_option(index=i)
                    self.wait_and_screenshot(page, "00_video_selected_with_transcription", 2000)
                    selected = True
                    break
            if not selected:
                # 文字起こし済み動画が見つからない場合は最初のファイルを選択
                print("    ⚠️ 文字起こし済み動画が見つかりません。最初のファイルを選択します。")
                selects[0].select_option(index=1)
                self.wait_and_screenshot(page, "00_video_selected", 1000)

        # 文字起こし結果が読み込まれるまで待機
        print("📍 文字起こし結果の読み込みを待機")
        page.wait_for_timeout(3000)

        # キャッシュ選択ボタンを探す
        use_cache_buttons = page.locator('button:has-text("選択した結果を使用")').all()
        if use_cache_buttons:
            print("  ✅ キャッシュ使用ボタンを発見")
            # セレクトボックスで最初のキャッシュを選択
            cache_selects = page.locator("select").all()
            if len(cache_selects) > 1:  # 動画選択以外のセレクトボックス
                cache_selects[1].select_option(index=0)
                self.wait_and_screenshot(page, "00_cache_selected", 1000)

            use_cache_buttons[0].click()
            print("  📝 文字起こし結果を読み込み中...")
            page.wait_for_timeout(3000)
            self.wait_and_screenshot(page, "01_after_cache_load", 1000)

        # 2. テキストエディタまでスクロール
        print("📍 テキストエディタを探す")
        # 初期画面をキャプチャ
        self.save_screenshot(page, "01_text_initial_state")

        # 文字起こし結果が表示されているか確認
        transcription_result = page.locator('text="文字起こし結果"').first
        if transcription_result.is_visible():
            print("  ✅ 文字起こし結果が表示されています")
            self.save_screenshot(page, "02_transcription_result_found")

        # ページの下の方までスクロール
        found_textarea = False
        for i in range(5):
            self.scroll_and_screenshot(page, f"03_text_scroll_{i+1}")

            # テキストエリアを探す
            textareas = page.locator("textarea").all()
            if textareas and not found_textarea:
                print(f"  ✅ テキストエリアを発見（{len(textareas)}個）")
                textarea = textareas[0]
                textarea.scroll_into_view_if_needed()
                self.wait_and_screenshot(page, "04_text_editor_found")

                # テキストを入力
                print("📍 テキスト入力")
                sample_text = """本日の会議について
重要な議題がありました
---
次回の予定
来週月曜日に再度議論します"""
                textarea.fill(sample_text)
                self.wait_and_screenshot(page, "05_text_entered")

                # 更新ボタンを探す
                print("📍 更新ボタンをクリック")
                update_buttons = page.locator('button:has-text("更新")').all()
                if update_buttons:
                    self.save_screenshot(page, "06_text_before_update")
                    update_buttons[0].click()
                    self.wait_and_screenshot(page, "07_text_updated", 2000)

                # 境界調整モード
                print("📍 境界調整モードを有効化")
                boundary_checkbox = page.locator('text="🎯 境界調整モード"').first
                if boundary_checkbox.is_visible():
                    self.save_screenshot(page, "08_boundary_mode_before")
                    boundary_checkbox.click()
                    self.wait_and_screenshot(page, "09_boundary_mode_on")

                    # 再度更新
                    if update_buttons:
                        update_buttons[0].click()
                        self.wait_and_screenshot(page, "10_boundary_markers", 2000)

                found_textarea = True
                break

        if not found_textarea:
            print("  ⚠️ テキストエディタが見つかりませんでした")
            self.save_screenshot(page, "11_text_editor_not_found")

    def test_scenario_4_timeline_editing(self, page: Page, streamlit_server: str):
        """シナリオ4: タイムライン編集"""
        print("\n\n🎬 シナリオ4: タイムライン編集")

        # 1. 初期設定
        print("📍 初期設定")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 動画ファイルを選択（文字起こし済みの動画を選択）
        print("📍 動画ファイルを選択")
        selects = page.locator("select").all()
        if selects:
            # 文字起こし済みの動画を探して選択
            options = selects[0].locator("option").all()
            selected = False
            for i, option in enumerate(options):
                text = option.inner_text()
                print(f"    オプション{i}: {text}")
                if "習慣が続かない" in text or "誰しも主人公" in text or "港区おじさん" in text:
                    print(f"    ✅ 文字起こし済み動画を選択: {text}")
                    selects[0].select_option(index=i)
                    self.wait_and_screenshot(page, "00_video_selected_with_transcription", 2000)
                    selected = True
                    break
            if not selected:
                # 文字起こし済み動画が見つからない場合は最初のファイルを選択
                print("    ⚠️ 文字起こし済み動画が見つかりません。最初のファイルを選択します。")
                selects[0].select_option(index=1)
                self.wait_and_screenshot(page, "00_video_selected", 1000)

        # 2. タイムライン編集ボタンを探す
        print("📍 タイムライン編集ボタンを探す")
        self.save_screenshot(page, "01_timeline_initial")

        found_timeline = False
        for i in range(5):
            self.scroll_and_screenshot(page, f"02_timeline_scroll_{i+1}")

            timeline_buttons = page.locator('button:has-text("タイムライン編集")').all()
            if timeline_buttons and not found_timeline:
                print("  ✅ タイムライン編集ボタンを発見")
                timeline_buttons[0].scroll_into_view_if_needed()
                self.wait_and_screenshot(page, "03_timeline_button_found")

                timeline_buttons[0].click()
                self.wait_and_screenshot(page, "04_timeline_editor_opened", 2000)

                # 時間調整コントロールを探す
                number_inputs = page.locator('input[type="number"]').all()
                if number_inputs:
                    print(f"  ✅ 時間調整入力フィールドを発見（{len(number_inputs)}個）")
                    self.wait_and_screenshot(page, "05_timeline_controls")

                # 編集完了ボタン
                complete_buttons = page.locator('button:has-text("編集完了")').all()
                if complete_buttons:
                    self.save_screenshot(page, "06_timeline_before_complete")
                    complete_buttons[0].click()
                    self.wait_and_screenshot(page, "07_timeline_completed")

                found_timeline = True
                break

        if not found_timeline:
            print("  ⚠️ タイムライン編集ボタンが見つかりませんでした")
            self.save_screenshot(page, "08_timeline_not_found")

    def test_scenario_5_export_settings(self, page: Page, streamlit_server: str):
        """シナリオ5: エクスポート設定の詳細"""
        print("\n\n🎬 シナリオ5: エクスポート設定")

        # 1. 初期設定
        print("📍 初期設定")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 動画ファイルを選択（文字起こし済みの動画を選択）
        print("📍 動画ファイルを選択")
        selects = page.locator("select").all()
        if selects:
            # 文字起こし済みの動画を探して選択
            options = selects[0].locator("option").all()
            selected = False
            for i, option in enumerate(options):
                text = option.inner_text()
                print(f"    オプション{i}: {text}")
                if "習慣が続かない" in text or "誰しも主人公" in text or "港区おじさん" in text:
                    print(f"    ✅ 文字起こし済み動画を選択: {text}")
                    selects[0].select_option(index=i)
                    self.wait_and_screenshot(page, "00_video_selected_with_transcription", 2000)
                    selected = True
                    break
            if not selected:
                # 文字起こし済み動画が見つからない場合は最初のファイルを選択
                print("    ⚠️ 文字起こし済み動画が見つかりません。最初のファイルを選択します。")
                selects[0].select_option(index=1)
                self.wait_and_screenshot(page, "00_video_selected", 1000)

        # 2. 切り抜き処理セクションまでスクロール
        print("📍 切り抜き処理セクションを探す")
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.wait_and_screenshot(page, "01_scrolled_to_bottom")

        # 3. 無音削除チェックボックス
        print("📍 無音削除オプション")
        silence_checkboxes = page.locator('input[type="checkbox"]').all()
        for i, checkbox in enumerate(silence_checkboxes):
            label = checkbox.locator("xpath=..").inner_text()
            if "無音" in label:
                checkbox.click()
                self.wait_and_screenshot(page, "02_silence_removal_checked")
                break

        # 4. エクスポート形式
        print("📍 エクスポート形式選択")
        # 最後のselectを探す（エクスポート形式の可能性が高い）
        selects = page.locator("select").all()
        if len(selects) > 1:
            export_select = selects[-1]
            export_select.scroll_into_view_if_needed()

            # FCPXMLを選択
            try:
                export_select.select_option("FCPXML")
                self.wait_and_screenshot(page, "03_export_fcpxml")
            except:
                pass

            # EDLを選択
            try:
                export_select.select_option("EDL")
                self.wait_and_screenshot(page, "04_export_edl")
            except:
                pass

        # 5. 処理実行ボタン
        print("📍 処理実行ボタン")
        process_buttons = page.locator('button:has-text("処理を実行")').all()
        if process_buttons:
            process_buttons[0].scroll_into_view_if_needed()
            self.wait_and_screenshot(page, "05_process_button_ready")

    def test_scenario_6_error_handling(self, page: Page, streamlit_server: str):
        """シナリオ6: エラーハンドリング"""
        print("\n\n🎬 シナリオ6: エラーハンドリング")

        # 1. 初期設定
        print("📍 初期設定")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 2. ファイル未選択で文字起こし実行
        print("📍 ファイル未選択エラー")
        transcribe_buttons = page.locator('button:has-text("文字起こし")').all()
        if transcribe_buttons:
            transcribe_buttons[0].click()
            self.wait_and_screenshot(page, "01_error_no_file", 2000)

        # 3. 無効なテキスト
        print("📍 無効なテキストエラー")
        textareas = page.locator("textarea").all()
        if textareas:
            textareas[0].fill("これは存在しないテキストです！@#$%")
            update_buttons = page.locator('button:has-text("更新")').all()
            if update_buttons:
                update_buttons[0].click()
                self.wait_and_screenshot(page, "02_error_invalid_text", 2000)

        # 4. エラーメッセージの確認
        print("📍 エラーメッセージ")
        error_elements = page.locator('[data-testid="stAlert"]').all()
        if error_elements:
            self.wait_and_screenshot(page, "03_error_messages")

    def test_scenario_7_sidebar_features(self, page: Page, streamlit_server: str):
        """シナリオ7: サイドバーの全機能"""
        print("\n\n🎬 シナリオ7: サイドバーの全機能")

        # 1. 初期設定
        print("📍 初期設定")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 2. サイドバーを開く
        print("📍 サイドバーを開く")
        sidebar_button = page.locator('[data-testid="collapsedControl"]').first
        if sidebar_button.is_visible():
            sidebar_button.click()
            self.wait_and_screenshot(page, "01_sidebar_opened")

        # 3. 各タブを順番にクリック
        tabs = [
            ("🔑APIキー", "api_key"),
            ("🔇 無音検出", "silence_detection"),
            ("🎬 SRT字幕", "srt_subtitles"),
            ("🔄 リカバリー", "recovery"),
            ("📋 履歴", "history"),
            ("❓ ヘルプ", "help"),
        ]

        for tab_text, tab_id in tabs:
            print(f"📍 {tab_text}タブ")
            tab = page.locator(f'text="{tab_text}"').first
            if tab.is_visible():
                tab.click()
                self.wait_and_screenshot(page, f"02_sidebar_{tab_id}")

                # タブ内のコントロールを操作
                if tab_id == "silence_detection":
                    # スライダーを操作
                    sliders = page.locator('input[type="range"]').all()
                    if sliders:
                        self.wait_and_screenshot(page, f"03_sidebar_{tab_id}_controls")

                elif tab_id == "srt_subtitles":
                    # チェックボックスをクリック
                    checkboxes = page.locator('input[type="checkbox"]').all()
                    if checkboxes:
                        try:
                            # 可視のチェックボックスを探す
                            for cb in checkboxes:
                                if cb.is_visible():
                                    cb.click()
                                    self.wait_and_screenshot(page, f"03_sidebar_{tab_id}_enabled")
                                    break
                        except:
                            # エラーの場合でもスクリーンショットを撮る
                            self.save_screenshot(page, f"03_sidebar_{tab_id}_error")

    def test_scenario_8_responsive_design(self, page: Page, streamlit_server: str):
        """シナリオ8: レスポンシブデザイン"""
        print("\n\n🎬 シナリオ8: レスポンシブデザイン")

        # 1. デスクトップサイズ
        print("📍 デスクトップビュー (1920x1080)")
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        self.wait_and_screenshot(page, "01_desktop_1920x1080", 2000)

        # 2. ラップトップサイズ
        print("📍 ラップトップビュー (1366x768)")
        page.set_viewport_size({"width": 1366, "height": 768})
        self.wait_and_screenshot(page, "02_laptop_1366x768")

        # 3. タブレット横向き
        print("📍 タブレット横向き (1024x768)")
        page.set_viewport_size({"width": 1024, "height": 768})
        self.wait_and_screenshot(page, "03_tablet_landscape_1024x768")

        # 4. タブレット縦向き
        print("📍 タブレット縦向き (768x1024)")
        page.set_viewport_size({"width": 768, "height": 1024})
        self.wait_and_screenshot(page, "04_tablet_portrait_768x1024")

        # 5. モバイル
        print("📍 モバイルビュー (375x667)")
        page.set_viewport_size({"width": 375, "height": 667})
        self.wait_and_screenshot(page, "05_mobile_375x667")

        # 6. 大型モバイル
        print("📍 大型モバイルビュー (414x896)")
        page.set_viewport_size({"width": 414, "height": 896})
        self.wait_and_screenshot(page, "06_mobile_large_414x896")
