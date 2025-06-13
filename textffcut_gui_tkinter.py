#!/usr/bin/env python3
"""
TextffCut GUI版 - tkinterによるシンプルなGUI実装
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import subprocess
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta

APP_NAME = "TextffCut GUI"
VERSION = "1.0.0-gui"

class TextffCutGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("800x600")
        
        # 変数
        self.video_path = tk.StringVar()
        self.output_dir = tk.StringVar(value="./output")
        self.threshold = tk.DoubleVar(value=-35.0)
        self.min_duration = tk.DoubleVar(value=0.3)
        self.remove_silence = tk.BooleanVar(value=True)
        self.processing = False
        
        self.create_widgets()
        self.check_ffmpeg()
        
    def create_widgets(self):
        """ウィジェットを作成"""
        # メインフレーム
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # タイトル
        title_label = ttk.Label(main_frame, text=f"🎬 {APP_NAME}", font=("Arial", 20, "bold"))
        title_label.grid(row=0, column=0, columnspan=3, pady=10)
        
        # ファイル選択
        ttk.Label(main_frame, text="動画ファイル:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.video_path, width=50).grid(row=1, column=1, padx=5)
        ttk.Button(main_frame, text="選択", command=self.select_video).grid(row=1, column=2)
        
        # 出力ディレクトリ
        ttk.Label(main_frame, text="出力先:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_dir, width=50).grid(row=2, column=1, padx=5)
        ttk.Button(main_frame, text="選択", command=self.select_output_dir).grid(row=2, column=2)
        
        # 設定フレーム
        settings_frame = ttk.LabelFrame(main_frame, text="設定", padding="10")
        settings_frame.grid(row=3, column=0, columnspan=3, pady=10, sticky=(tk.W, tk.E))
        
        # 無音削除チェックボックス
        ttk.Checkbutton(settings_frame, text="無音部分を削除", 
                       variable=self.remove_silence).grid(row=0, column=0, columnspan=2, sticky=tk.W)
        
        # 閾値
        ttk.Label(settings_frame, text="無音閾値 (dB):").grid(row=1, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(settings_frame)
        threshold_frame.grid(row=1, column=1, sticky=tk.W)
        
        self.threshold_slider = ttk.Scale(threshold_frame, from_=-60, to=-20, 
                                         variable=self.threshold, orient=tk.HORIZONTAL, 
                                         length=200, command=self.update_threshold_label)
        self.threshold_slider.pack(side=tk.LEFT)
        
        self.threshold_label = ttk.Label(threshold_frame, text="-35.0 dB")
        self.threshold_label.pack(side=tk.LEFT, padx=10)
        
        # 最小無音時間
        ttk.Label(settings_frame, text="最小無音時間 (秒):").grid(row=2, column=0, sticky=tk.W, pady=5)
        duration_frame = ttk.Frame(settings_frame)
        duration_frame.grid(row=2, column=1, sticky=tk.W)
        
        self.duration_slider = ttk.Scale(duration_frame, from_=0.1, to=2.0, 
                                        variable=self.min_duration, orient=tk.HORIZONTAL, 
                                        length=200, command=self.update_duration_label)
        self.duration_slider.pack(side=tk.LEFT)
        
        self.duration_label = ttk.Label(duration_frame, text="0.3 秒")
        self.duration_label.pack(side=tk.LEFT, padx=10)
        
        # ボタンフレーム
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, columnspan=3, pady=10)
        
        self.info_button = ttk.Button(button_frame, text="動画情報", command=self.show_video_info)
        self.info_button.pack(side=tk.LEFT, padx=5)
        
        self.analyze_button = ttk.Button(button_frame, text="無音検出", command=self.analyze_silence)
        self.analyze_button.pack(side=tk.LEFT, padx=5)
        
        self.process_button = ttk.Button(button_frame, text="処理実行", command=self.process_video)
        self.process_button.pack(side=tk.LEFT, padx=5)
        
        # プログレスバー
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        
        # ログエリア
        log_frame = ttk.LabelFrame(main_frame, text="ログ", padding="5")
        log_frame.grid(row=6, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=70)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # グリッドの設定
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowgonfigure(6, weight=1)
        
    def update_threshold_label(self, value):
        """閾値ラベルを更新"""
        self.threshold_label.config(text=f"{float(value):.1f} dB")
        
    def update_duration_label(self, value):
        """最小無音時間ラベルを更新"""
        self.duration_label.config(text=f"{float(value):.1f} 秒")
        
    def check_ffmpeg(self):
        """ffmpegの存在確認"""
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                self.log("✅ ffmpegが正常に検出されました")
            else:
                self.log("❌ ffmpegが見つかりません")
                messagebox.showerror("エラー", "ffmpegがインストールされていません。\n"
                                            "ffmpegをインストールしてください。")
        except FileNotFoundError:
            self.log("❌ ffmpegが見つかりません")
            messagebox.showerror("エラー", "ffmpegがインストールされていません。\n"
                                        "ffmpegをインストールしてください。")
            
    def log(self, message):
        """ログにメッセージを追加"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.root.update()
        
    def select_video(self):
        """動画ファイルを選択"""
        filename = filedialog.askopenfilename(
            title="動画ファイルを選択",
            filetypes=[
                ("動画ファイル", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("すべてのファイル", "*.*")
            ]
        )
        if filename:
            self.video_path.set(filename)
            self.log(f"📁 ファイル選択: {os.path.basename(filename)}")
            
    def select_output_dir(self):
        """出力ディレクトリを選択"""
        directory = filedialog.askdirectory(title="出力先フォルダを選択")
        if directory:
            self.output_dir.set(directory)
            self.log(f"📁 出力先: {directory}")
            
    def set_processing(self, processing):
        """処理中状態を設定"""
        self.processing = processing
        if processing:
            self.progress.start()
            self.info_button.config(state='disabled')
            self.analyze_button.config(state='disabled')
            self.process_button.config(state='disabled')
        else:
            self.progress.stop()
            self.info_button.config(state='normal')
            self.analyze_button.config(state='normal')
            self.process_button.config(state='normal')
            
    def run_command(self, cmd, callback=None):
        """コマンドを別スレッドで実行"""
        def run():
            try:
                self.set_processing(True)
                result = subprocess.run(cmd, capture_output=True, text=True)
                if callback:
                    callback(result)
            except Exception as e:
                self.log(f"❌ エラー: {str(e)}")
            finally:
                self.set_processing(False)
                
        thread = threading.Thread(target=run)
        thread.start()
        
    def show_video_info(self):
        """動画情報を表示"""
        if not self.video_path.get():
            messagebox.showwarning("警告", "動画ファイルを選択してください")
            return
            
        self.log("📹 動画情報を取得中...")
        
        # textffcut_cli_liteのパスを取得
        if hasattr(sys, '_MEIPASS'):
            # PyInstallerでビルドされた場合
            cli_path = os.path.join(sys._MEIPASS, 'textffcut_cli_lite')
        else:
            # 開発環境
            cli_path = './dist/textffcut_cli_lite'
            if not os.path.exists(cli_path):
                cli_path = 'python textffcut_cli_lite.py'
        
        cmd = [cli_path, 'info', self.video_path.get()] if os.path.exists(cli_path) else \
              ['python', 'textffcut_cli_lite.py', 'info', self.video_path.get()]
        
        def callback(result):
            if result.returncode == 0:
                self.log(result.stdout)
            else:
                self.log(f"❌ エラー: {result.stderr}")
                
        self.run_command(cmd, callback)
        
    def analyze_silence(self):
        """無音部分を検出"""
        if not self.video_path.get():
            messagebox.showwarning("警告", "動画ファイルを選択してください")
            return
            
        self.log("🔇 無音部分を検出中...")
        
        # CLIコマンドを構築
        if hasattr(sys, '_MEIPASS'):
            cli_path = os.path.join(sys._MEIPASS, 'textffcut_cli_lite')
        else:
            cli_path = './dist/textffcut_cli_lite'
            if not os.path.exists(cli_path):
                cli_path = 'python'
                
        if cli_path == 'python':
            cmd = ['python', 'textffcut_cli_lite.py', 'silence', self.video_path.get()]
        else:
            cmd = [cli_path, 'silence', self.video_path.get()]
            
        cmd.extend(['--threshold', str(self.threshold.get())])
        cmd.extend(['--min-duration', str(self.min_duration.get())])
        
        def callback(result):
            if result.returncode == 0:
                self.log(result.stdout)
            else:
                self.log(f"❌ エラー: {result.stderr}")
                
        self.run_command(cmd, callback)
        
    def process_video(self):
        """動画を処理"""
        if not self.video_path.get():
            messagebox.showwarning("警告", "動画ファイルを選択してください")
            return
            
        self.log("🎬 動画を処理中...")
        
        # 出力ディレクトリを作成
        os.makedirs(self.output_dir.get(), exist_ok=True)
        
        # CLIコマンドを構築
        if hasattr(sys, '_MEIPASS'):
            cli_path = os.path.join(sys._MEIPASS, 'textffcut_cli_lite')
        else:
            cli_path = './dist/textffcut_cli_lite'
            if not os.path.exists(cli_path):
                cli_path = 'python'
                
        if cli_path == 'python':
            cmd = ['python', 'textffcut_cli_lite.py', 'process', self.video_path.get()]
        else:
            cmd = [cli_path, 'process', self.video_path.get()]
            
        cmd.extend(['--output-dir', self.output_dir.get()])
        
        if self.remove_silence.get():
            cmd.append('--remove-silence')
            cmd.extend(['--threshold', str(self.threshold.get())])
            cmd.extend(['--min-duration', str(self.min_duration.get())])
        
        def callback(result):
            if result.returncode == 0:
                self.log(result.stdout)
                self.log("✨ 処理が完了しました！")
                messagebox.showinfo("完了", "処理が完了しました！\n"
                                          f"出力先: {self.output_dir.get()}")
            else:
                self.log(f"❌ エラー: {result.stderr}")
                messagebox.showerror("エラー", "処理中にエラーが発生しました。\n"
                                            "ログを確認してください。")
                
        self.run_command(cmd, callback)
        
    def run(self):
        """アプリケーションを実行"""
        self.root.mainloop()

def main():
    app = TextffCutGUI()
    app.run()

if __name__ == "__main__":
    main()