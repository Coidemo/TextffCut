#!/usr/bin/env python3
"""
Fletアプリのテスト起動
ポート番号を明示的に指定
"""

import flet as ft
import sys

def main(page: ft.Page):
    """テスト用Fletアプリ"""
    page.title = "TextffCut Flet Test"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    # 大きなタイトル
    title = ft.Text(
        "🎬 TextffCut Flet版",
        size=40,
        weight=ft.FontWeight.BOLD
    )
    
    # 状態表示
    status = ft.Text(
        "✅ Fletが正常に動作しています！",
        size=20,
        color=ft.colors.GREEN
    )
    
    # アプリ情報
    info = ft.Text(
        f"Python {sys.version.split()[0]} | Flet {ft.version.VERSION}",
        size=14,
        color=ft.colors.GREY
    )
    
    # カウンター（動作確認用）
    counter_text = ft.Text("0", size=30)
    
    def increment(e):
        counter_text.value = str(int(counter_text.value) + 1)
        page.update()
    
    button = ft.FilledButton(
        "カウントアップ",
        on_click=increment,
        icon=ft.icons.ADD
    )
    
    # レイアウト
    page.add(
        ft.Column(
            [
                title,
                status,
                ft.Divider(),
                counter_text,
                button,
                ft.Divider(),
                info
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=20
        )
    )
    
    print("✅ Fletアプリが起動しました！")
    print(f"🌐 ブラウザで http://localhost:{page.port or 'auto'} を開いてください")

# 起動
if __name__ == "__main__":
    print("🚀 Fletアプリを起動しています...")
    # ポート8502で起動（Streamlitと重複しないように）
    ft.app(target=main, port=8502, view=ft.AppView.WEB_BROWSER)