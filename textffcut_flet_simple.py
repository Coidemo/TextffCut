#!/usr/bin/env python3
"""
TextffCut Flet版 - シンプルテスト
最小限の機能で動作確認
"""

import flet as ft

def main(page: ft.Page):
    """シンプルなFletアプリ"""
    page.title = "TextffCut Flet Test"
    page.window_width = 600
    page.window_height = 400
    
    # タイトル
    title = ft.Text("🎬 TextffCut Flet版", size=30)
    
    # 入力フィールド
    file_input = ft.TextField(
        label="動画ファイルパス",
        hint_text="/path/to/video.mp4"
    )
    
    # 結果表示
    result_text = ft.Text("")
    
    # ボタンクリック時の処理
    def button_click(e):
        if file_input.value:
            result_text.value = f"選択されたファイル: {file_input.value}"
        else:
            result_text.value = "ファイルを入力してください"
        page.update()
    
    # ボタン
    check_button = ft.ElevatedButton(
        "確認",
        on_click=button_click
    )
    
    # レイアウト
    page.add(
        title,
        ft.Divider(),
        file_input,
        check_button,
        result_text
    )

# アプリ起動
if __name__ == "__main__":
    ft.app(target=main)