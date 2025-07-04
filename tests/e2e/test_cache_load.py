"""
キャッシュ読み込みのE2Eテスト

文字起こし済み動画を選択して、キャッシュから結果を読み込むテスト
"""

import subprocess
import time

import pytest
from playwright.sync_api import Page


class TestCacheLoad:
    """キャッシュ読み込みのE2Eテスト"""

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

    def test_cache_load_flow(self, page: Page, streamlit_server: str):
        """キャッシュ読み込みフローのテスト"""
        print("\n🎬 キャッシュ読み込みフローテスト")

        # 1. アプリケーション起動
        print("📍 アプリケーション起動")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 初期画面をキャプチャ
        page.screenshot(path="cache_load_01_initial.png", full_page=True)

        # 2. 動画ファイル選択
        print("📍 動画ファイルを選択")
        selects = page.locator("select").all()
        print(f"  セレクトボックス数: {len(selects)}")

        if selects:
            # 動画ファイルのオプションを確認
            options = selects[0].locator("option").all()
            print(f"  利用可能な動画ファイル数: {len(options)}")

            # 文字起こし済みの動画を選択（実際のファイル名を使用）
            try:
                # 具体的なファイル名で選択を試みる
                selects[0].select_option("（朝ラジオ）習慣が続かないのはモチベーション次第で辞めるから_original.mp4")
                print("  ✅ '習慣が続かない' を選択しました")
            except:
                # または最初の実際のファイルを選択
                if len(options) > 1:
                    selects[0].select_option(index=1)
                    print("  ✅ 最初のファイルを選択しました")

            page.wait_for_timeout(3000)
            page.screenshot(path="cache_load_02_video_selected.png", full_page=True)

        # 3. キャッシュUIを探す
        print("📍 キャッシュUIを探す")

        # 文字起こしセクションまでスクロール
        page.evaluate("window.scrollBy(0, 400)")
        page.wait_for_timeout(1000)
        page.screenshot(path="cache_load_03_scroll_to_transcription.png", full_page=True)

        # キャッシュUIの要素を探す
        cache_text = page.locator('text="過去の文字起こし結果を利用する"')
        if cache_text.is_visible():
            print("  ✅ キャッシュUIが表示されています！")

            # キャッシュ選択セレクトボックスを確認
            all_selects = page.locator("select").all()
            print(f"  全セレクトボックス数: {len(all_selects)}")

            if len(all_selects) > 1:
                # 2番目のセレクトボックスがキャッシュ選択
                cache_select = all_selects[1]
                cache_options = cache_select.locator("option").all()
                print(f"  利用可能なキャッシュ数: {len(cache_options)}")

                if cache_options:
                    # 最初のキャッシュを選択
                    cache_select.select_option(index=0)
                    page.wait_for_timeout(1000)
                    page.screenshot(path="cache_load_04_cache_selected.png", full_page=True)

            # 「選択した結果を使用」ボタンを探す
            use_button = page.locator('button:has-text("選択した結果を使用")')
            if use_button.is_visible():
                print("  ✅ キャッシュ使用ボタンが表示されています！")

                # ボタンをクリック
                use_button.click()
                print("  📝 キャッシュから読み込み中...")
                page.wait_for_timeout(5000)  # 再描画を待つ

                # 読み込み後の画面をキャプチャ
                page.screenshot(path="cache_load_05_after_load.png", full_page=True)

                # 文字起こし結果が表示されているか確認
                result_text = page.locator('text="文字起こし結果"')
                if result_text.is_visible():
                    print("  ✅ 文字起こし結果が表示されました！")

                    # テキストエディタまでスクロール
                    page.evaluate("window.scrollBy(0, 500)")
                    page.wait_for_timeout(1000)
                    page.screenshot(path="cache_load_06_text_editor.png", full_page=True)

                    # テキストエリアを確認
                    textareas = page.locator("textarea").all()
                    if textareas:
                        print(f"  ✅ テキストエディタが表示されています（{len(textareas)}個）")

                        # テキスト内容を確認
                        text_content = textareas[0].input_value()
                        print(f"  テキスト内容の長さ: {len(text_content)}文字")
                else:
                    print("  ❌ 文字起こし結果が表示されていません")
            else:
                print("  ❌ キャッシュ使用ボタンが見つかりません")
        else:
            print("  ❌ キャッシュUIが表示されていません")

            # エラーメッセージを確認
            alerts = page.locator('[data-testid="stAlert"]').all()
            for alert in alerts:
                print(f"  アラート: {alert.inner_text()}")
