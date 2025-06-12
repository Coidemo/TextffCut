#!/usr/bin/env python3
"""
TextffCut Simple版 - Streamlitを使わない純粋なPythonアプリ
PyInstallerでの動作確認用
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import os
import mimetypes
from datetime import datetime
from pathlib import Path

APP_NAME = "TextffCut Simple"
VERSION = "0.1.0-simple"

class TextffCutApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{VERSION}")
        self.root.geometry("600x400")
        
        # ヘッダー
        header = tk.Label(root, text=f"🎬 {APP_NAME}", font=("Arial", 20, "bold"))
        header.pack(pady=10)
        
        version_label = tk.Label(root, text=f"Version {VERSION} - PyInstaller動作確認用", font=("Arial", 10))
        version_label.pack()
        
        # ファイル選択フレーム
        file_frame = tk.Frame(root)
        file_frame.pack(pady=20, padx=20, fill="x")
        
        tk.Label(file_frame, text="動画ファイル:").pack(side="left")
        
        self.file_path_var = tk.StringVar()
        self.file_entry = tk.Entry(file_frame, textvariable=self.file_path_var, width=40)
        self.file_entry.pack(side="left", padx=10, fill="x", expand=True)
        
        tk.Button(file_frame, text="選択", command=self.select_file).pack(side="left")
        
        # 情報表示エリア
        self.info_text = tk.Text(root, height=10, width=70)
        self.info_text.pack(pady=10, padx=20, fill="both", expand=True)
        
        # ボタンフレーム
        button_frame = tk.Frame(root)
        button_frame.pack(pady=10)
        
        tk.Button(button_frame, text="ファイル情報を確認", command=self.check_file, bg="blue", fg="white").pack(side="left", padx=5)
        tk.Button(button_frame, text="終了", command=root.quit).pack(side="left", padx=5)
        
        # ステータスバー
        self.status_label = tk.Label(root, text="準備完了", bd=1, relief="sunken", anchor="w")
        self.status_label.pack(side="bottom", fill="x")
    
    def select_file(self):
        """ファイル選択ダイアログ"""
        filename = filedialog.askopenfilename(
            title="動画ファイルを選択",
            filetypes=[
                ("動画ファイル", "*.mp4 *.avi *.mov *.mkv *.webm"),
                ("すべてのファイル", "*.*")
            ]
        )
        if filename:
            self.file_path_var.set(filename)
            self.status_label.config(text=f"ファイルを選択しました: {os.path.basename(filename)}")
    
    def check_file(self):
        """ファイル情報を確認"""
        file_path = self.file_path_var.get()
        
        if not file_path:
            messagebox.showwarning("警告", "ファイルを選択してください")
            return
        
        if not os.path.exists(file_path):
            messagebox.showerror("エラー", "ファイルが見つかりません")
            return
        
        # ファイル情報を取得
        try:
            stat = os.stat(file_path)
            size_mb = stat.st_size / (1024 * 1024)
            modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            mime_type, _ = mimetypes.guess_type(file_path)
            
            info = f"""ファイル情報:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
パス: {file_path}
ファイル名: {os.path.basename(file_path)}
サイズ: {size_mb:.2f} MB
更新日時: {modified}
MIMEタイプ: {mime_type or '不明'}
拡張子: {Path(file_path).suffix}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{"✅ 動画ファイルです" if mime_type and mime_type.startswith("video/") else "⚠️ 動画ファイルではない可能性があります"}
"""
            
            self.info_text.delete(1.0, tk.END)
            self.info_text.insert(1.0, info)
            self.status_label.config(text="ファイル情報を表示しました")
            
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル情報の取得に失敗しました:\n{str(e)}")

def main():
    root = tk.Tk()
    app = TextffCutApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()