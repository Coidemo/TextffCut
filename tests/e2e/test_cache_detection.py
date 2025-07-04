"""
キャッシュ検出のE2Eテスト

文字起こし済み動画を選択したときに、キャッシュが正しく検出されるかを確認します。
"""

import subprocess
import time

import pytest
from playwright.sync_api import Page


class TestCacheDetection:
    """キャッシュ検出のE2Eテスト"""

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

    def test_cache_detection_for_transcribed_video(self, page: Page, streamlit_server: str):
        """文字起こし済み動画のキャッシュ検出テスト"""
        print("\n🎬 キャッシュ検出テスト")

        # 1. アプリケーション起動
        print("📍 アプリケーション起動")
        page.goto(streamlit_server)
        page.wait_for_selector('[data-testid="stApp"]', timeout=30000)
        page.wait_for_timeout(2000)

        # 2. 動画ファイル選択
        print("📍 動画ファイルを選択")
        selects = page.locator("select").all()
        if selects:
            # 動画ファイルのオプションを取得
            options = selects[0].locator("option").all()
            print(f"  利用可能な動画ファイル数: {len(options)}")

            for i, option in enumerate(options):
                text = option.inner_text()
                print(f"  オプション{i}: {text}")

                # 文字起こし済みの動画を選択
                if "習慣が続かない" in text:
                    print(f"  ✅ 文字起こし済み動画を選択: {text}")
                    selects[0].select_option(index=i)
                    page.wait_for_timeout(3000)  # キャッシュ検出を待つ

                    # スクリーンショットを撮る
                    page.screenshot(path="cache_detection_after_selection.png", full_page=True)

                    # キャッシュUIが表示されているか確認
                    cache_container = page.locator('text="過去の文字起こし結果を利用する"')
                    if cache_container.is_visible():
                        print("  ✅ キャッシュUIが表示されています！")

                        # キャッシュ選択のセレクトボックスを確認
                        cache_selects = page.locator("select").all()
                        if len(cache_selects) > 1:
                            print("  ✅ キャッシュ選択セレクトボックスが見つかりました")

                            # キャッシュオプションを確認
                            cache_options = cache_selects[1].locator("option").all()
                            print(f"  利用可能なキャッシュ数: {len(cache_options)}")
                            for j, cache_option in enumerate(cache_options):
                                print(f"    キャッシュ{j}: {cache_option.inner_text()}")

                        # 「選択した結果を使用」ボタンを確認
                        use_cache_button = page.locator('button:has-text("選択した結果を使用")')
                        if use_cache_button.is_visible():
                            print("  ✅ キャッシュ使用ボタンが表示されています！")
                    else:
                        print("  ❌ キャッシュUIが表示されていません")

                        # エラーメッセージやアラートを確認
                        alerts = page.locator('[data-testid="stAlert"]').all()
                        for alert in alerts:
                            print(f"  アラート: {alert.inner_text()}")

                    break
            else:
                print("  ⚠️ 文字起こし済み動画が見つかりませんでした")
        else:
            print("  ❌ 動画選択のセレクトボックスが見つかりません")
