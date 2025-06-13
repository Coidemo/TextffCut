#!/usr/bin/env python3
"""
TextffCut Flet版 - 本格実装
既存のcore/モジュールを統合したフル機能版
"""

import flet as ft
import os
import sys
from pathlib import Path
from datetime import datetime
import asyncio
import json
import traceback

# 既存のcoreモジュールをインポート
try:
    from core import VideoProcessor, VideoInfo
    from core import Transcriber, TranscriptionResult
    from core import TextProcessor
    from core import FCPXMLExporter
    from utils import ProgressCallback
except ImportError:
    # 開発時のパス調整
    sys.path.append(str(Path(__file__).parent))
    from core import VideoProcessor, VideoInfo
    from core import Transcriber, TranscriptionResult  
    from core import TextProcessor
    from core import FCPXMLExporter
    from utils import ProgressCallback

APP_NAME = "TextffCut"
VERSION = "1.0.0-flet"

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
            ),
            
            # 右側：文字起こし結果
            ft.Container(
                content=self.create_right_panel(),
                expand=True,
                padding=20,
            ),
        ], expand=True)
        
        # プログレスセクション
        progress_section = self.create_progress_section()
        
        # ページに追加
        page.add(
            header,
            ft.Divider(),
            main_content,
            progress_section,
        )
        
    def create_header(self):
        """ヘッダーを作成"""
        return ft.Container(
            content=ft.Row([
                ft.Icon(ft.icons.MOVIE_CREATION, size=40, color=ft.colors.BLUE),
                ft.Text(APP_NAME, size=30, weight=ft.FontWeight.BOLD),
                ft.Text(f"v{VERSION}", size=14, color=ft.colors.GREY),
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=20,
            bgcolor=ft.colors.BLUE_50,
            border_radius=10,
        )
        
    def create_left_panel(self, file_picker):
        """左側パネル（ファイル選択と情報）"""
        # ファイル選択
        self.file_path_field = ft.TextField(
            label="動画ファイル",
            hint_text="ファイルを選択してください",
            read_only=True,
            expand=True,
        )
        
        select_button = ft.ElevatedButton(
            "選択",
            icon=ft.icons.FOLDER_OPEN,
            on_click=lambda _: file_picker.pick_files(
                dialog_title="動画ファイルを選択",
                allowed_extensions=["mp4", "avi", "mov", "mkk", "webm"]
            ),
        )
        
        file_section = ft.Row([self.file_path_field, select_button])
        
        # 動画情報カード
        self.video_info_card = ft.Card(
            content=ft.Container(
                content=ft.Text("動画ファイルを選択してください", size=14),
                padding=20,
            ),
            elevation=2,
        )
        
        # アクションボタン
        self.transcribe_button = ft.FilledButton(
            "文字起こし開始",
            icon=ft.icons.TRANSCRIBE,
            disabled=True,
            on_click=self.start_transcription,
            width=200,
        )
        
        self.export_button = ft.OutlinedButton(
            "FCPXMLエクスポート",
            icon=ft.icons.DOWNLOAD,
            disabled=True,
            on_click=self.export_fcpxml,
            width=200,
        )
        
        # 設定セクション
        settings_section = ft.Column([
            ft.Text("設定", size=16, weight=ft.FontWeight.BOLD),
            ft.Checkbox(label="無音部分を削除", value=True),
            ft.Slider(
                label="無音閾値 (dB)",
                min=-60,
                max=-20,
                value=-35,
                divisions=40,
            ),
        ])
        
        return ft.Column([
            file_section,
            self.video_info_card,
            ft.Divider(),
            self.transcribe_button,
            self.export_button,
            ft.Divider(),
            settings_section,
        ], spacing=20)
        
    def create_right_panel(self):
        """右側パネル（文字起こし結果）"""
        # セグメントリスト
        self.segments_view = ft.ListView(
            expand=True,
            spacing=10,
            padding=ft.padding.all(10),
        )
        
        # 初期メッセージ
        self.segments_view.controls.append(
            ft.Card(
                content=ft.Container(
                    content=ft.Text(
                        "文字起こしを開始すると、ここに結果が表示されます",
                        size=16,
                        color=ft.colors.GREY,
                    ),
                    padding=40,
                    alignment=ft.alignment.center,
                ),
                elevation=1,
            )
        )
        
        return ft.Column([
            ft.Text("文字起こし結果", size=20, weight=ft.FontWeight.BOLD),
            ft.Divider(),
            self.segments_view,
        ], expand=True)
        
    def create_progress_section(self):
        """プログレスセクション"""
        self.progress_bar = ft.ProgressBar(visible=False)
        self.progress_text = ft.Text("", size=12, visible=False)
        self.status_text = ft.Text("", size=14, color=ft.colors.GREEN)
        
        return ft.Container(
            content=ft.Column([
                self.progress_bar,
                self.progress_text,
                self.status_text,
            ]),
            padding=20,
        )
        
    def on_file_picked(self, e: ft.FilePickerResultEvent):
        """ファイルが選択されたとき"""
        if e.files:
            self.video_path = e.files[0].path
            self.file_path_field.value = self.video_path
            self.update_video_info()
            self.page.update()
            
    def update_video_info(self):
        """動画情報を更新"""
        if not self.video_path or not os.path.exists(self.video_path):
            return
            
        try:
            # VideoProcessorを使って動画情報を取得
            processor = VideoProcessor()
            self.video_info = processor.get_video_info(self.video_path)
            
            # 情報表示を更新
            info_text = f"""📹 動画情報
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📄 ファイル名: {os.path.basename(self.video_path)}
⏱️ 長さ: {self.video_info.duration_str}
📐 解像度: {self.video_info.width}x{self.video_info.height}
🎯 FPS: {self.video_info.fps:.2f}
💾 サイズ: {os.path.getsize(self.video_path) / (1024*1024):.2f} MB
━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
            
            self.video_info_card.content = ft.Container(
                content=ft.Text(info_text, size=14),
                padding=20,
            )
            
            # ボタンを有効化
            self.transcribe_button.disabled = False
            
            self.status_text.value = "✅ 動画ファイルを読み込みました"
            
        except Exception as e:
            self.status_text.value = f"❌ エラー: {str(e)}"
            self.status_text.color = ft.colors.RED
            
    async def start_transcription_async(self):
        """文字起こしを非同期で実行"""
        try:
            # プログレス表示
            self.progress_bar.visible = True
            self.progress_text.visible = True
            self.progress_text.value = "文字起こしを開始しています..."
            self.transcribe_button.disabled = True
            self.page.update()
            
            # Transcriberを使って文字起こし
            def progress_callback(progress, message):
                self.progress_bar.value = progress / 100
                self.progress_text.value = message
                self.page.update()
                
            transcriber = Transcriber(progress_callback=progress_callback)
            self.transcription_result = await asyncio.to_thread(
                transcriber.transcribe,
                self.video_path
            )
            
            # 結果を表示
            self.display_transcription_result()
            
            # 完了
            self.progress_bar.visible = False
            self.progress_text.visible = False
            self.status_text.value = "✅ 文字起こしが完了しました"
            self.export_button.disabled = False
            
        except Exception as e:
            self.status_text.value = f"❌ エラー: {str(e)}"
            self.status_text.color = ft.colors.RED
            traceback.print_exc()
            
        finally:
            self.transcribe_button.disabled = False
            self.page.update()
            
    def start_transcription(self, e):
        """文字起こしを開始"""
        asyncio.run(self.start_transcription_async())
        
    def display_transcription_result(self):
        """文字起こし結果を表示"""
        self.segments_view.controls.clear()
        
        if not self.transcription_result or not self.transcription_result.segments:
            self.segments_view.controls.append(
                ft.Text("文字起こし結果がありません", color=ft.colors.GREY)
            )
            return
            
        # セグメントごとにカードを作成
        for i, segment in enumerate(self.transcription_result.segments):
            # チェックボックス付きカード
            checkbox = ft.Checkbox(
                value=True,
                data=i,
                on_change=self.on_segment_selected
            )
            
            # 時間表示
            start_time = f"{int(segment.start//60):02d}:{segment.start%60:05.2f}"
            end_time = f"{int(segment.end//60):02d}:{segment.end%60:05.2f}"
            
            segment_card = ft.Card(
                content=ft.Container(
                    content=ft.Row([
                        checkbox,
                        ft.Column([
                            ft.Text(
                                f"{start_time} → {end_time}",
                                size=12,
                                color=ft.colors.BLUE,
                            ),
                            ft.Text(segment.text, size=14),
                        ], expand=True),
                    ]),
                    padding=10,
                ),
                elevation=1,
            )
            
            self.segments_view.controls.append(segment_card)
            self.selected_segments.append(i)
            
    def on_segment_selected(self, e):
        """セグメントの選択状態が変更されたとき"""
        index = e.control.data
        if e.control.value:
            if index not in self.selected_segments:
                self.selected_segments.append(index)
        else:
            if index in self.selected_segments:
                self.selected_segments.remove(index)
                
    def export_fcpxml(self, e):
        """FCPXMLをエクスポート"""
        if not self.transcription_result or not self.selected_segments:
            self.status_text.value = "❌ エクスポートするセグメントがありません"
            self.status_text.color = ft.colors.RED
            self.page.update()
            return
            
        try:
            # 選択されたセグメントを取得
            selected = [
                self.transcription_result.segments[i]
                for i in sorted(self.selected_segments)
            ]
            
            # FCPXMLエクスポート
            output_path = self.video_path.rsplit('.', 1)[0] + '_textffcut.fcpxml'
            exporter = FCPXMLExporter()
            exporter.export(
                video_path=self.video_path,
                segments=selected,
                output_path=output_path,
                video_info=self.video_info
            )
            
            self.status_text.value = f"✅ FCPXMLをエクスポートしました: {os.path.basename(output_path)}"
            self.status_text.color = ft.colors.GREEN
            
        except Exception as e:
            self.status_text.value = f"❌ エラー: {str(e)}"
            self.status_text.color = ft.colors.RED
            traceback.print_exc()
            
        self.page.update()

def main():
    """アプリケーションのエントリーポイント"""
    app = TextffCutFletApp()
    ft.app(target=app.main, port=8503)

if __name__ == "__main__":
    main()