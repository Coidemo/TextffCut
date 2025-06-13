#!/usr/bin/env python3
"""
最もシンプルなFletテスト - 動作確認用
"""

import flet as ft

def main(page: ft.Page):
    page.title = "TextffCut Test"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    
    # カウンター
    counter = ft.Text("0", size=50)
    
    def add_click(e):
        counter.value = str(int(counter.value) + 1)
        page.update()
    
    def minus_click(e):
        counter.value = str(int(counter.value) - 1)
        page.update()
    
    page.add(
        ft.Column(
            [
                ft.Text("TextffCut Flet Test", size=30),
                counter,
                ft.Row(
                    [
                        ft.ElevatedButton("-", on_click=minus_click),
                        ft.ElevatedButton("+", on_click=add_click),
                    ],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
    )

if __name__ == "__main__":
    ft.app(target=main, port=8506)