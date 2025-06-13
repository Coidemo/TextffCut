#!/usr/bin/env python3
"""
TextffCut Flet版 - モックアップ版
UIの動作確認用（実際の処理はモック）
"""

import flet as ft
import os
from pathlib import Path
from datetime import datetime, timedelta
import asyncio
import random

APP_NAME = "TextffCut"
VERSION = "1.0.0-flet"

# モッククラス
class MockVideoInfo:
    def __init__(self, path):
        self.path = path
        self.duration = 300.5  # 5分
        self.duration_str = str(timedelta(seconds=int(self.duration)))
        self.width = 1920
        self.height = 1080
        self.fps = 30.0
        self.codec = "h264"

class MockSegment:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text

class MockTranscriptionResult:
    def __init__(self):
        self.segments = [
            MockSegment(0, 5, "こんにちは、今日はTextffCutの使い方について説明します。"),
            MockSegment(5, 12, "このツールは動画の文字起こしと切り抜きを効率化するためのものです。"),
            MockSegment(12, 20, "まず最初に動画ファイルを選択してください。"),
            MockSegment(20, 28, "次に文字起こしボタンをクリックすると、自動的に文字起こしが始まります。"),
            MockSegment(28, 35, "文字起こしが完了したら、必要な部分だけを選択してエクスポートできます。"),
        ]

class TextffCutFletApp:
    def __init__(self):
        self.page = None
        self.video_path = None
        self.video_info = None
        self.transcription_result = None
        self.selected_segments = []
        
        # UI要素
        self.file_path_field = None
        self.video_info_card = None
        self.transcribe_button = None
        self.export_button = None
        self.progress_bar = None
        self.progress_text = None
        self.status_text = None
        self.segments_view = None
        
    def main(self, page: ft.Page):
        """メインアプリケーション"""
        self.page = page
        page.title = APP_NAME
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window_width = 1200
        page.window_height = 800
        page.window_resizable = True
        
        # ファイルピッカー
        file_picker = ft.FilePicker(on_result=self.on_file_picked)
        page.overlay.append(file_picker)
        
        # ヘッダー
        header = self.create_header()
        
        # メインコンテンツ
        main_content = ft.Row([
            # 左側：ファイル選択と情報
            ft.Container(
                content=self.create_left_panel(file_picker),
                width=400,
                padding=20,
                bgcolor=ft.Colors.GREY_100,
                border_radius=10,
            ),
            
            # 右側：文字起こし結果
            ft.Container(
                content=self.create_right_panel(),
                expand=True,
                padding=20,
            ),
        ], expand=True, spacing=20)
        
        # プログレスセクション
        progress_section = self.create_progress_section()
        
        # ページに追加
        page.add(
            header,
            ft.Divider(height=1),
            ft.Container(content=main_content, padding=20, expand=True),
            progress_section,
        )
        
    def create_header(self):
        """ヘッダーを作成"""
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.MOVIE_CREATION, size=40, color=ft.Colors.BLUE),
                ft.Text(APP_NAME, size=30, weight=ft.FontWeight.BOLD),
                ft.Text(f"v{VERSION}", size=14, color=ft.Colors.GREY),
                ft.Container(expand=True),  # スペーサー
                ft.IconButton(
                    icon=ft.Icons.SETTINGS,
                    tooltip="設定",
                    on_click=lambda _: self.show_settings_dialog()
                ),
            ]),
            padding=20,
            bgcolor=ft.Colors.BLUE_50,
        )
        
    def create_left_panel(self, file_picker):
        """左側パネル（ファイル選択と情報）"""
        # ファイル選択
        self.file_path_field = ft.TextField(
            label="動画ファイル",
            hint_text="クリックしてファイルを選択",
            read_only=True,
            expand=True,
        )
        
        select_button = ft.ElevatedButton(
            "選択",
            icon=ft.Icons.FOLDER_OPEN,
            on_click=lambda _: file_picker.pick_files(
                dialog_title="動画ファイルを選択",
                allowed_extensions=["mp4", "avi", "mov", "mkv", "webm"]
            ),
        )
        
        file_section = ft.Row([self.file_path_field, select_button])
        
        # 動画情報カード
        self.video_info_card = ft.Card(
            content=ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.VIDEO_FILE, size=50, color=ft.Colors.GREY_400),
                    ft.Text("動画ファイルを選択してください", size=14, color=ft.Colors.GREY_600),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=30,
                alignment=ft.alignment.center,
            ),
            elevation=2,
        )
        
        # アクションボタン
        self.transcribe_button = ft.FilledButton(
            "文字起こし開始",
            icon=ft.Icons.TRANSCRIBE,
            disabled=True,
            on_click=self.start_transcription,
            width=200,
            style=ft.ButtonStyle(
                color={
                    ft.MaterialState.DEFAULT: ft.Colors.WHITE,
                },
                bgcolor={
                    ft.MaterialState.DEFAULT: ft.Colors.BLUE,
                    ft.MaterialState.DISABLED: ft.Colors.GREY_400,
                },
            ),
        )
        
        self.export_button = ft.OutlinedButton(
            "FCPXMLエクスポート",
            icon=ft.Icons.DOWNLOAD,
            disabled=True,
            on_click=self.export_fcpxml,
            width=200,
        )
        
        # 設定セクション
        self.silence_removal_checkbox = ft.Checkbox(label="無音部分を削除", value=True)
        self.silence_threshold_slider = ft.Slider(
            label="無音閾値 (dB)",
            min=-60,
            max=-20,
            value=-35,
            divisions=40,
            on_change=self.on_threshold_change,
        )
        self.threshold_text = ft.Text("-35 dB", size=12)
        
        settings_section = ft.Container(
            content=ft.Column([
                ft.Text("⚙️ 設定", size=16, weight=ft.FontWeight.BOLD),
                self.silence_removal_checkbox,
                ft.Row([
                    ft.Text("無音閾値:", size=14),
                    self.threshold_text,
                ]),
                self.silence_threshold_slider,
            ], spacing=10),
            padding=20,
            bgcolor=ft.Colors.WHITE,
            border_radius=10,
        )
        
        return ft.Column([
            ft.Text("📁 ファイル選択", size=18, weight=ft.FontWeight.BOLD),
            file_section,
            self.video_info_card,
            ft.Divider(),
            ft.Text("🎬 アクション", size=18, weight=ft.FontWeight.BOLD),
            ft.Row([self.transcribe_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Row([self.export_button], alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            settings_section,
        ], spacing=15, scroll=ft.ScrollMode.AUTO)
        
    def create_right_panel(self):
        """右側パネル（文字起こし結果）"""
        # ヘッダー
        header = ft.Row([
            ft.Text("📝 文字起こし結果", size=20, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            ft.TextButton(
                "すべて選択",
                icon=ft.Icons.SELECT_ALL,
                on_click=self.select_all_segments,
            ),
            ft.TextButton(
                "選択解除",
                icon=ft.Icons.DESELECT,
                on_click=self.deselect_all_segments,
            ),
        ])
        
        # セグメントリスト
        self.segments_view = ft.ListView(
            expand=True,
            spacing=10,
            padding=ft.padding.all(10),
        )
        
        # 初期メッセージ
        self.segments_view.controls.append(
            ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.SUBTITLES_OFF, size=80, color=ft.Colors.GREY_300),
                    ft.Text(
                        "文字起こしを開始すると、ここに結果が表示されます",
                        size=16,
                        color=ft.Colors.GREY_600,
                        text_align=ft.TextAlign.CENTER,
                    ),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=60,
                alignment=ft.alignment.center,
            )
        )
        
        return ft.Column([
            header,
            ft.Divider(),
            ft.Container(
                content=self.segments_view,
                bgcolor=ft.Colors.GREY_50,
                border_radius=10,
                expand=True,
            ),
        ], expand=True)
        
    def create_progress_section(self):
        """プログレスセクション"""
        self.progress_bar = ft.ProgressBar(visible=False)
        self.progress_text = ft.Text("", size=12, visible=False)
        self.status_text = ft.Text("準備完了", size=14, color=ft.Colors.GREEN)
        
        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=20, color=ft.Colors.BLUE),
                    self.status_text,
                ]),
                self.progress_bar,
                self.progress_text,
            ], spacing=5),
            padding=20,
            bgcolor=ft.Colors.BLUE_50,
        )
        
    def on_file_picked(self, e: ft.FilePickerResultEvent):
        """ファイルが選択されたとき"""
        if e.files:
            self.video_path = e.files[0].path
            self.file_path_field.value = self.video_path
            self.update_video_info()
            self.page.update()
            
    def update_video_info(self):
        """動画情報を更新（モック）"""
        if not self.video_path:
            return
            
        # モックデータを使用
        self.video_info = MockVideoInfo(self.video_path)
        
        # 情報表示を更新
        info_content = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.VIDEO_FILE, size=40, color=ft.Colors.BLUE),
                ft.Text(os.path.basename(self.video_path), size=16, weight=ft.FontWeight.BOLD),
            ]),
            ft.Divider(),
            ft.Row([
                ft.Icon(ft.Icons.ACCESS_TIME, size=20),
                ft.Text(f"長さ: {self.video_info.duration_str}", size=14),
            ]),
            ft.Row([
                ft.Icon(ft.Icons.ASPECT_RATIO, size=20),
                ft.Text(f"解像度: {self.video_info.width}x{self.video_info.height}", size=14),
            ]),
            ft.Row([
                ft.Icon(ft.Icons.SPEED, size=20),
                ft.Text(f"FPS: {self.video_info.fps:.2f}", size=14),
            ]),
            ft.Row([
                ft.Icon(ft.Icons.STORAGE, size=20),
                ft.Text(f"サイズ: {random.randint(100, 500)} MB", size=14),
            ]),
        ], spacing=5)
        
        self.video_info_card.content = ft.Container(
            content=info_content,
            padding=20,
        )
        
        # ボタンを有効化
        self.transcribe_button.disabled = False
        
        self.status_text.value = "✅ 動画ファイルを読み込みました"
        self.page.update()
        
    async def start_transcription(self, e):
        """文字起こしを開始（モック）"""
        # プログレス表示
        self.progress_bar.visible = True
        self.progress_text.visible = True
        self.progress_bar.value = 0
        self.transcribe_button.disabled = True
        self.page.update()
        
        # モック処理（プログレスバーアニメーション）
        for i in range(101):
            self.progress_bar.value = i / 100
            self.progress_text.value = f"文字起こし中... {i}%"
            self.page.update()
            await asyncio.sleep(0.02)  # 2秒で完了
            
        # モック結果を設定
        self.transcription_result = MockTranscriptionResult()
        self.display_transcription_result()
        
        # 完了
        self.progress_bar.visible = False
        self.progress_text.visible = False
        self.status_text.value = "✅ 文字起こしが完了しました"
        self.export_button.disabled = False
        self.transcribe_button.disabled = False
        self.page.update()
        
    def display_transcription_result(self):
        """文字起こし結果を表示"""
        self.segments_view.controls.clear()
        self.selected_segments = []
        
        if not self.transcription_result or not self.transcription_result.segments:
            return
            
        # セグメントごとにカードを作成
        for i, segment in enumerate(self.transcription_result.segments):
            # チェックボックス
            checkbox = ft.Checkbox(
                value=True,
                data=i,
                on_change=self.on_segment_selected
            )
            self.selected_segments.append(i)
            
            # 時間表示
            start_time = f"{int(segment.start//60):02d}:{segment.start%60:05.2f}"
            end_time = f"{int(segment.end//60):02d}:{segment.end%60:05.2f}"
            
            # セグメントカード
            segment_card = ft.Card(
                content=ft.Container(
                    content=ft.Row([
                        checkbox,
                        ft.Container(width=10),  # スペーサー
                        ft.Column([
                            ft.Row([
                                ft.Icon(ft.Icons.SCHEDULE, size=16, color=ft.Colors.BLUE),
                                ft.Text(
                                    f"{start_time} → {end_time}",
                                    size=12,
                                    color=ft.Colors.BLUE,
                                    weight=ft.FontWeight.BOLD,
                                ),
                            ]),
                            ft.Text(segment.text, size=14),
                        ], expand=True),
                    ]),
                    padding=15,
                ),
                elevation=1,
            )
            
            self.segments_view.controls.append(segment_card)
            
    def on_segment_selected(self, e):
        """セグメントの選択状態が変更されたとき"""
        index = e.control.data
        if e.control.value:
            if index not in self.selected_segments:
                self.selected_segments.append(index)
        else:
            if index in self.selected_segments:
                self.selected_segments.remove(index)
                
    def select_all_segments(self, e):
        """すべてのセグメントを選択"""
        self.selected_segments = []
        for control in self.segments_view.controls:
            if isinstance(control, ft.Card):
                checkbox = control.content.content.controls[0]
                if isinstance(checkbox, ft.Checkbox):
                    checkbox.value = True
                    self.selected_segments.append(checkbox.data)
        self.page.update()
        
    def deselect_all_segments(self, e):
        """すべてのセグメントの選択を解除"""
        self.selected_segments = []
        for control in self.segments_view.controls:
            if isinstance(control, ft.Card):
                checkbox = control.content.content.controls[0]
                if isinstance(checkbox, ft.Checkbox):
                    checkbox.value = False
        self.page.update()
        
    def on_threshold_change(self, e):
        """閾値スライダーが変更されたとき"""
        self.threshold_text.value = f"{int(e.control.value)} dB"
        self.page.update()
        
    def show_settings_dialog(self):
        """設定ダイアログを表示"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()
            
        dialog = ft.AlertDialog(
            title=ft.Text("設定"),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("ここに詳細な設定が表示されます", size=14),
                    ft.Divider(),
                    ft.Text("• Whisperモデル選択", size=12),
                    ft.Text("• 出力形式設定", size=12),
                    ft.Text("• その他の詳細設定", size=12),
                ], spacing=10),
                width=400,
                height=200,
            ),
            actions=[
                ft.TextButton("閉じる", on_click=close_dialog),
            ],
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()
        
    def export_fcpxml(self, e):
        """FCPXMLをエクスポート（モック）"""
        if not self.selected_segments:
            self.status_text.value = "⚠️ エクスポートするセグメントを選択してください"
            self.status_text.color = ft.Colors.ORANGE
            self.page.update()
            return
            
        # モック処理
        output_name = "output_textffcut.fcpxml"
        self.status_text.value = f"✅ FCPXMLをエクスポートしました: {output_name}"
        self.status_text.color = ft.Colors.GREEN
        
        # 成功ダイアログ
        def close_dialog(e):
            dialog.open = False
            self.page.update()
            
        dialog = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN, size=30),
                ft.Text("エクスポート完了"),
            ]),
            content=ft.Container(
                content=ft.Column([
                    ft.Text(f"ファイル名: {output_name}", size=14),
                    ft.Text(f"選択セグメント数: {len(self.selected_segments)}", size=14),
                ], spacing=10),
                width=300,
            ),
            actions=[
                ft.TextButton("OK", on_click=close_dialog),
            ],
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

def main():
    """アプリケーションのエントリーポイント"""
    app = TextffCutFletApp()
    ft.app(
        target=app.main,
        port=8504,
        view=ft.AppView.WEB_BROWSER,
        assets_dir="assets"
    )

if __name__ == "__main__":
    main()