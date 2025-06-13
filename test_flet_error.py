#!/usr/bin/env python3
"""
Fletのエラーを確認するテストスクリプト
"""

import flet as ft
import traceback

def main(page: ft.Page):
    try:
        page.title = "Flet Error Test"
        page.add(
            ft.Text("Fletが正常に動作しています", size=30),
            ft.ElevatedButton("テスト", on_click=lambda _: print("ボタンクリック"))
        )
        print("✅ Fletアプリが正常に起動しました")
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    try:
        print("Fletアプリを起動しています...")
        ft.app(target=main, port=8505, view=ft.AppView.WEB_BROWSER)
    except Exception as e:
        print(f"❌ 起動エラー: {e}")
        traceback.print_exc()