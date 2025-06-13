#!/usr/bin/env python3
"""
TextffCut Flet版 - 修正版
エラーを修正したシンプルバージョン
"""

import flet as ft
import os
from datetime import timedelta
import asyncio

APP_NAME = "TextffCut"
VERSION = "1.0.0-flet"

class TextffCutApp:
    def __init__(self):
        self.page = None
        self.video_path = None
        self.file_path_field = None
        self.status_text = None
        self.progress_bar = None
        self.segments_view = None
        
    def main(self, page: ft.Page):
        """メインアプリケーション"""
        self.page = page
        page.title = APP_NAME
        page.window_width = 1000
        page.window_height = 700
        
        # ヘッダー
        header = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MOVIE, size=40),
                ft.Text(APP_NAME, size=30, weight=ft.FontWeight.BOLD),
                ft.Text(f"v{VERSION}", size=14),
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=20,
            bgcolor="#E3F2FD",  # 明るい青
        )
        
        # ファイル選択セクション
        self.file_path_field = ft.TextField(
            label="動画ファイル",
            hint_text="ファイルパスを入力",
            expand=True,
        )
        
        select_button = ft.ElevatedButton(
            "選択",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=self.select_file,
        )
        
        file_section = ft.Row([
            self.file_path_field,
            select_button,
        ])
        
        # アクションボタン
        transcribe_button = ft.FilledButton(
            "文字起こし開始",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.start_transcription,
        )
        
        export_button = ft.OutlinedButton(
            "FCPXMLエクスポート",
            icon=ft.Icons.DOWNLOAD,
            on_click=self.export_fcpxml,
        )
        
        buttons_row = ft.Row([
            transcribe_button,
            export_button,
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=20)
        
        # 結果表示エリア
        self.segments_view = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        
        results_container = ft.Container(
            content=self.segments_view,
            border=ft.border.all(1, "#E0E0E0"),
            border_radius=10,
            padding=20,
            expand=True,
            bgcolor="#FAFAFA",
        )
        
        # プログレスバー
        self.progress_bar = ft.ProgressBar(visible=False)
        
        # ステータステキスト
        self.status_text = ft.Text("準備完了", size=14)
        
        # レイアウト
        page.add(
            header,
            ft.Divider(height=1),
            ft.Container(
                content=ft.Column([
                    ft.Text("📁 動画ファイル選択", size=18, weight=ft.FontWeight.BOLD),
                    file_section,
                    ft.Divider(),
                    buttons_row,
                    ft.Divider(),
                    ft.Text("📝 文字起こし結果", size=18, weight=ft.FontWeight.BOLD),
                    results_container,
                    self.progress_bar,
                    self.status_text,
                ], spacing=15),
                padding=20,
                expand=True,
            )
        )
        
    def select_file(self, e):
        """ファイル選択（シンプル版）"""
        # 実際のファイル選択の代わりにサンプルパスを設定
        self.video_path = "/path/to/sample.mp4"
        self.file_path_field.value = self.video_path
        self.status_text.value = "✅ ファイルを選択しました"
        self.page.update()
        
    async def start_transcription(self, e):
        """文字起こし開始（モック）"""
        if not self.video_path:
            self.status_text.value = "❌ 動画ファイルを選択してください"
            self.page.update()
            return
            
        # プログレス表示
        self.progress_bar.visible = True
        self.progress_bar.value = 0
        self.status_text.value = "🎬 文字起こしを実行中..."
        self.page.update()
        
        # モックプログレス
        for i in range(11):
            self.progress_bar.value = i / 10
            await asyncio.sleep(0.2)
            self.page.update()
            
        # モック結果を表示
        self.display_mock_results()
        
        # 完了
        self.progress_bar.visible = False
        self.status_text.value = "✅ 文字起こしが完了しました"
        self.page.update()
        
    def display_mock_results(self):
        """モック結果を表示"""
        self.segments_view.controls.clear()
        
        # サンプルセグメント
        segments = [
            (0, 5, "こんにちは、TextffCutの使い方を説明します。"),
            (5, 12, "このツールは動画の文字起こしを効率化します。"),
            (12, 20, "まず動画ファイルを選択してください。"),
        ]
        
        for start, end, text in segments:
            # 時間フォーマット
            start_str = f"{int(start//60):02d}:{start%60:05.2f}"
            end_str = f"{int(end//60):02d}:{end%60:05.2f}"
            
            # セグメントカード
            segment_card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Checkbox(value=True),
                        ft.Text(f"{start_str} → {end_str}", weight=ft.FontWeight.BOLD),
                    ]),
                    ft.Text(text, size=14),
                ], spacing=5),
                bgcolor="#F5F5F5",
                padding=15,
                border_radius=8,
            )
            
            self.segments_view.controls.append(segment_card)
            
    def export_fcpxml(self, e):
        """FCPXMLエクスポート"""
        output_path = os.path.join(os.getcwd(), "output_textffcut.fcpxml")
        
        # 簡単なFCPXMLを生成
        fcpxml_content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.11">
    <resources>
        <format id="r1" name="FFVideoFormat1080p30"/>
        <asset id="r2" name="Sample Video" src="file:///path/to/sample.mp4"/>
    </resources>
    <library>
        <event name="TextffCut Export">
            <project name="TextffCut Project">
                <sequence format="r1">
                    <spine>
                        <clip name="Segment 1" duration="5s">
                            <video ref="r2" offset="0s" duration="5s"/>
                        </clip>
                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(fcpxml_content)
            self.status_text.value = f"✅ FCPXMLをエクスポートしました: {output_path}"
        except Exception as ex:
            self.status_text.value = f"❌ エクスポートエラー: {str(ex)}"
        
        self.page.update()

def main():
    """エントリーポイント"""
    app = TextffCutApp()
    ft.app(target=app.main, port=8507)

if __name__ == "__main__":
    main()