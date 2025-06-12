#!/usr/bin/env python3
"""
TextffCut Flet版サンプル
Fletフレームワークを使ったモダンUI実装例
"""

import flet as ft
import os
from datetime import datetime
from pathlib import Path
import mimetypes

APP_NAME = "TextffCut Flet"
VERSION = "0.4.0-flet"

class TextffCutApp:
    def __init__(self):
        self.file_path = None
        self.file_info_text = None
        self.progress_bar = None
        self.status_text = None
        
    def main(self, page: ft.Page):
        """メインアプリケーション"""
        page.title = APP_NAME
        page.theme_mode = ft.ThemeMode.LIGHT
        page.window_width = 800
        page.window_height = 600
        
        # ファイルピッカー
        def pick_files_result(e: ft.FilePickerResultEvent):
            if e.files:
                self.file_path = e.files[0].path
                file_path_field.value = self.file_path
                self.update_file_info()
                page.update()
        
        file_picker = ft.FilePicker(on_result=pick_files_result)
        page.overlay.append(file_picker)
        
        # ヘッダー
        header = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.icons.MOVIE_CREATION, size=40, color=ft.colors.BLUE),
                    ft.Text(APP_NAME, size=30, weight=ft.FontWeight.BOLD),
                ], alignment=ft.MainAxisAlignment.CENTER),
                ft.Text(f"Version {VERSION}", size=12, color=ft.colors.GREY),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            bgcolor=ft.colors.BLUE_50,
            border_radius=10,
        )
        
        # ファイル選択セクション
        file_path_field = ft.TextField(
            label="動画ファイル",
            hint_text="ファイルを選択してください",
            read_only=True,
            expand=True,
        )
        
        select_button = ft.ElevatedButton(
            "ファイルを選択",
            icon=ft.icons.FOLDER_OPEN,
            on_click=lambda _: file_picker.pick_files(
                dialog_title="動画ファイルを選択",
                allowed_extensions=["mp4", "avi", "mov", "mkv", "webm"]
            ),
        )
        
        file_section = ft.Container(
            content=ft.Row([file_path_field, select_button]),
            padding=10,
        )
        
        # ファイル情報表示
        self.file_info_text = ft.Text("ファイルが選択されていません", size=14)
        file_info_card = ft.Card(
            content=ft.Container(
                content=self.file_info_text,
                padding=20,
            ),
            elevation=2,
        )
        
        # アクションボタン
        transcribe_button = ft.FilledButton(
            "文字起こし開始",
            icon=ft.icons.TRANSCRIBE,
            disabled=True,
            on_click=self.start_transcription,
        )
        
        extract_audio_button = ft.OutlinedButton(
            "音声抽出",
            icon=ft.icons.AUDIOTRACK,
            disabled=True,
            on_click=self.extract_audio,
        )
        
        actions_row = ft.Row([
            transcribe_button,
            extract_audio_button,
        ], alignment=ft.MainAxisAlignment.CENTER)
        
        # プログレスバー
        self.progress_bar = ft.ProgressBar(visible=False)
        self.status_text = ft.Text("", size=12, color=ft.colors.GREY)
        
        # フッター
        footer = ft.Container(
            content=ft.Column([
                ft.Divider(),
                ft.Text(
                    "TextffCut - 動画の文字起こしと切り抜きを効率化",
                    size=12,
                    color=ft.colors.GREY,
                ),
            ]),
            padding=10,
        )
        
        # コンポーネントを保存
        self.transcribe_button = transcribe_button
        self.extract_audio_button = extract_audio_button
        self.page = page
        
        # ページに追加
        page.add(
            header,
            file_section,
            file_info_card,
            actions_row,
            self.progress_bar,
            self.status_text,
            footer,
        )
    
    def update_file_info(self):
        """ファイル情報を更新"""
        if not self.file_path or not os.path.exists(self.file_path):
            self.file_info_text.value = "ファイルが見つかりません"
            self.transcribe_button.disabled = True
            self.extract_audio_button.disabled = True
            return
        
        try:
            stat = os.stat(self.file_path)
            size_mb = stat.st_size / (1024 * 1024)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            mime_type, _ = mimetypes.guess_type(self.file_path)
            
            info_text = f"""📁 ファイル情報
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 ファイル名: {os.path.basename(self.file_path)}
💾 サイズ: {size_mb:.2f} MB
📅 更新日時: {modified}
🔍 MIMEタイプ: {mime_type or '不明'}
📌 拡張子: {Path(self.file_path).suffix}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            
            self.file_info_text.value = info_text
            
            # 動画ファイルの場合はボタンを有効化
            if mime_type and mime_type.startswith("video/"):
                self.transcribe_button.disabled = False
                self.extract_audio_button.disabled = False
            
        except Exception as e:
            self.file_info_text.value = f"エラー: {str(e)}"
    
    def start_transcription(self, e):
        """文字起こしを開始（デモ）"""
        self.progress_bar.visible = True
        self.status_text.value = "🎬 文字起こしを開始しています..."
        self.page.update()
        
        # 実際の実装では、ここでcore/モジュールを呼び出す
        import time
        time.sleep(2)  # デモ用
        
        self.progress_bar.visible = False
        self.status_text.value = "✅ 文字起こしが完了しました！"
        self.page.update()
    
    def extract_audio(self, e):
        """音声抽出（デモ）"""
        self.progress_bar.visible = True
        self.status_text.value = "🎵 音声を抽出しています..."
        self.page.update()
        
        # 実際の実装では、ここでffmpegを呼び出す
        import time
        time.sleep(1)  # デモ用
        
        self.progress_bar.visible = False
        self.status_text.value = "✅ 音声抽出が完了しました！"
        self.page.update()

def main():
    """アプリケーションのエントリーポイント"""
    app = TextffCutApp()
    ft.app(target=app.main)

if __name__ == "__main__":
    main()