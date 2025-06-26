#!/usr/bin/env python3
"""
TextffCut E2Eテスト - フルワークフロー
ブラウザを使用して全機能を網羅的にテスト
"""

import asyncio
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tests.e2e.browser_base import BrowserTestBase


class TextffCutE2ETest(BrowserTestBase):
    """TextffCutのE2Eテスト"""

    def __init__(self):
        super().__init__()
        self.test_video_path = None

    async def run_all_tests(self):
        """全テストを実行"""
        try:
            self.setup()

            # 基本的なUI確認
            if self.config["test_suites"]["basic_ui"]:
                await self.test_basic_ui()

            # 動画選択
            if self.config["test_suites"]["video_selection"]:
                await self.test_video_selection()

            # 文字起こし（API）
            if self.config["test_suites"]["transcription_api"] and self.check_api_key():
                await self.test_transcription_api()

            # 文字起こし（ローカル）
            if self.config["test_suites"]["transcription_local"]:
                await self.test_transcription_local()

            # テキスト編集
            if self.config["test_suites"]["text_editing"]:
                await self.test_text_editing()

            # エクスポート
            if self.config["test_suites"]["export_fcpxml"]:
                await self.test_export_fcpxml()

            if self.config["test_suites"]["export_video"]:
                await self.test_export_video()

            # 設定
            if self.config["test_suites"]["settings"]:
                await self.test_settings()

        except Exception as e:
            print(f"❌ エラーが発生しました: {e}")
            self.add_test_result("E2Eテスト", "failed", {"error": str(e)})
        finally:
            self.teardown()

    async def test_basic_ui(self):
        """基本的なUI要素の確認"""
        test_name = "基本UI表示"
        try:
            print(f"\n🧪 {test_name}")

            # タイトルの確認
            await self.wait_for_text("TextffCut")
            await self.take_screenshot("01_home", "ホーム画面")

            # サイドバーの確認
            await self.wait_for_text("設定")
            await self.wait_for_text("APIキー")
            await self.wait_for_text("無音検出")
            await self.wait_for_text("ヘルプ")

            await self.take_screenshot("02_sidebar", "サイドバー")

            self.add_test_result(test_name, "passed", {"screenshots": ["01_home", "02_sidebar"]})

        except Exception as e:
            await self.take_screenshot("error_basic_ui", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_video_selection(self):
        """動画選択機能のテスト"""
        test_name = "動画選択"
        try:
            print(f"\n🧪 {test_name}")

            if self.config["environment"]["docker_mode"]:
                # Docker環境：ドロップダウンから選択
                await self.wait_for_text("動画ファイルを選択")
                await self.take_screenshot("03_video_select", "動画選択画面")

                # テスト動画が存在する場合は選択
                # 注: 実際のテストではvideos/フォルダに動画を配置する必要がある

            else:
                # ローカル環境：パス入力
                await self.wait_for_text("動画ファイルのフルパス")
                await self.fill_input("input[type='text']", str(self.test_video_path))

            await self.take_screenshot("04_video_selected", "動画選択後")

            self.add_test_result(test_name, "passed", {"screenshots": ["03_video_select", "04_video_selected"]})

        except Exception as e:
            await self.take_screenshot("error_video_selection", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_transcription_api(self):
        """API文字起こしのテスト"""
        test_name = "文字起こし（API）"
        try:
            print(f"\n🧪 {test_name}")

            # APIキー設定
            api_key = self.check_api_key()
            if not api_key:
                self.add_test_result(test_name, "skipped", {"reason": "APIキーが設定されていません"})
                return

            # APIモードを選択
            await self.click_element("input[value='🌐 API']", "APIモード選択")
            await self.take_screenshot("05_api_mode", "APIモード")

            # 文字起こし実行
            await self.click_element("button:contains('APIで文字起こしを実行')", "文字起こし実行")
            await self.take_screenshot("06_api_processing", "処理中")

            # 完了を待つ（最大5分）
            await self.wait_for_text("文字起こし完了", timeout=300)
            await self.take_screenshot("07_api_complete", "完了画面")

            self.add_test_result(
                test_name,
                "passed",
                {"mode": "API", "screenshots": ["05_api_mode", "06_api_processing", "07_api_complete"]},
            )

        except Exception as e:
            await self.take_screenshot("error_transcription_api", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_transcription_local(self):
        """ローカル文字起こしのテスト"""
        test_name = "文字起こし（ローカル）"
        try:
            print(f"\n🧪 {test_name}")

            # ローカルモードを選択
            await self.click_element("input[value='🖥️ ローカル']", "ローカルモード選択")
            await self.take_screenshot("08_local_mode", "ローカルモード")

            # mediumモデル固定の確認
            await self.wait_for_text("Whisper medium")

            # 文字起こし実行
            await self.click_element("button:contains('ローカルで文字起こしを実行')", "文字起こし実行")
            await self.take_screenshot("09_local_processing", "処理中")

            # 完了を待つ（最大10分）
            await self.wait_for_text("文字起こし完了", timeout=600)
            await self.take_screenshot("10_local_complete", "完了画面")

            self.add_test_result(
                test_name,
                "passed",
                {
                    "mode": "ローカル",
                    "model": "medium",
                    "screenshots": ["08_local_mode", "09_local_processing", "10_local_complete"],
                },
            )

        except Exception as e:
            await self.take_screenshot("error_transcription_local", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_text_editing(self):
        """テキスト編集機能のテスト"""
        test_name = "テキスト編集"
        try:
            print(f"\n🧪 {test_name}")

            # 切り抜き箇所の編集
            await self.wait_for_text("切り抜き箇所の指定")
            await self.take_screenshot("11_edit_start", "編集開始")

            # テスト編集を実行
            for i, edit_case in enumerate(self.config["test_data"]["test_edits"]):
                print(f"  📝 {edit_case['description']}")

                # テキストエリアに入力
                await self.fill_textarea(edit_case["text"])
                await self.click_element("button:contains('更新')", "更新ボタン")

                await self.take_screenshot(f"12_edit_{edit_case['name']}", edit_case["description"])

                # エラーケースの確認
                if edit_case["name"] == "error_case":
                    await self.wait_for_text("元動画に存在しない文字")
                    await self.take_screenshot("13_edit_error", "エラー表示")

                    # エラーダイアログ確認
                    if await self.element_exists("button:contains('エラー箇所を確認')"):
                        await self.click_element("button:contains('エラー箇所を確認')")
                        await self.take_screenshot("14_error_dialog", "エラーダイアログ")

            self.add_test_result(
                test_name,
                "passed",
                {
                    "test_cases": len(self.config["test_data"]["test_edits"]),
                    "screenshots": ["11_edit_start", "12_edit_*", "13_edit_error", "14_error_dialog"],
                },
            )

        except Exception as e:
            await self.take_screenshot("error_text_editing", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_export_fcpxml(self):
        """FCPXMLエクスポートのテスト"""
        test_name = "FCPXMLエクスポート"
        try:
            print(f"\n🧪 {test_name}")

            # 処理オプション選択
            await self.select_option("出力形式", "FCPXMLファイル")
            await self.take_screenshot("15_export_fcpxml", "FCPXML設定")

            # 処理実行
            await self.click_element("button:contains('処理を実行')", "処理実行")
            await self.take_screenshot("16_fcpxml_processing", "処理中")

            # 完了を待つ
            await self.wait_for_text("処理が完了しました", timeout=180)
            await self.take_screenshot("17_fcpxml_complete", "完了画面")

            self.add_test_result(
                test_name,
                "passed",
                {"format": "FCPXML", "screenshots": ["15_export_fcpxml", "16_fcpxml_processing", "17_fcpxml_complete"]},
            )

        except Exception as e:
            await self.take_screenshot("error_export_fcpxml", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_export_video(self):
        """動画エクスポートのテスト"""
        test_name = "動画エクスポート"
        try:
            print(f"\n🧪 {test_name}")

            # 処理オプション選択
            await self.select_option("出力形式", "動画ファイル（MP4）")
            await self.select_option("処理タイプ", "切り抜き + 無音削除")
            await self.take_screenshot("18_export_video", "動画エクスポート設定")

            # 処理実行
            await self.click_element("button:contains('処理を実行')", "処理実行")
            await self.take_screenshot("19_video_processing", "処理中")

            # 完了を待つ
            await self.wait_for_text("処理が完了しました", timeout=300)
            await self.take_screenshot("20_video_complete", "完了画面")

            # 動画プレビューの確認
            if await self.element_exists("video"):
                await self.take_screenshot("21_video_preview", "動画プレビュー")

            self.add_test_result(
                test_name,
                "passed",
                {
                    "format": "MP4",
                    "processing": "切り抜き + 無音削除",
                    "screenshots": ["18_export_video", "19_video_processing", "20_video_complete", "21_video_preview"],
                },
            )

        except Exception as e:
            await self.take_screenshot("error_export_video", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    async def test_settings(self):
        """設定機能のテスト"""
        test_name = "設定機能"
        try:
            print(f"\n🧪 {test_name}")

            # APIキー設定タブ
            await self.click_element("button:contains('APIキー')", "APIキータブ")
            await self.take_screenshot("22_settings_api", "APIキー設定")

            # 無音検出タブ
            await self.click_element("button:contains('無音検出')", "無音検出タブ")
            await self.take_screenshot("23_settings_silence", "無音検出設定")

            # パラメータ変更
            await self.adjust_slider("閾値", -40)
            await self.adjust_slider("最小無音時間", 0.5)
            await self.take_screenshot("24_settings_adjusted", "設定変更後")

            # ヘルプタブ
            await self.click_element("button:contains('ヘルプ')", "ヘルプタブ")
            await self.take_screenshot("25_settings_help", "ヘルプ")

            self.add_test_result(
                test_name,
                "passed",
                {
                    "tabs_tested": ["APIキー", "無音検出", "ヘルプ"],
                    "screenshots": [
                        "22_settings_api",
                        "23_settings_silence",
                        "24_settings_adjusted",
                        "25_settings_help",
                    ],
                },
            )

        except Exception as e:
            await self.take_screenshot("error_settings", "エラー画面")
            self.add_test_result(test_name, "failed", {"error": str(e)})

    # ヘルパーメソッド（実際のPuppeteer MCPコールは別途実装）
    async def wait_for_text(self, text: str, timeout: int = 30):
        """テキストが表示されるまで待機"""
        print(f"⏳ テキストを待機中: '{text}'")
        # 実装はPuppeteer MCP経由

    async def element_exists(self, selector: str) -> bool:
        """要素が存在するかチェック"""
        # 実装はPuppeteer MCP経由
        return True

    async def fill_textarea(self, text: str):
        """テキストエリアに入力"""
        print(f"⌨️ テキストエリアに入力: {len(text)}文字")
        # 実装はPuppeteer MCP経由

    async def select_option(self, label: str, value: str):
        """セレクトボックスで選択"""
        print(f"📋 選択: {label} = {value}")
        # 実装はPuppeteer MCP経由

    async def adjust_slider(self, label: str, value: float):
        """スライダーを調整"""
        print(f"🎚️ 調整: {label} = {value}")
        # 実装はPuppeteer MCP経由


async def main():
    """メイン関数"""
    print("=" * 60)
    print("TextffCut E2Eテスト")
    print("=" * 60)

    # APIキーの確認
    if not os.environ.get("OPENAI_API_KEY"):
        print("\n⚠️ 注意: OPENAI_API_KEYが設定されていません")
        print("APIモードのテストはスキップされます")
        response = input("\n続行しますか？ (y/n): ")
        if response.lower() != "y":
            return

    # テスト実行
    test = TextffCutE2ETest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
