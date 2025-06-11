#!/usr/bin/env python3
"""
TextffCut CLI版 - コマンドラインインターフェース
PyInstallerでの動作確認用（最小構成）
"""

import sys
import os
import argparse
import mimetypes
from pathlib import Path
from datetime import datetime

APP_NAME = "TextffCut CLI"
VERSION = "0.1.0-cli"

def get_file_info(file_path):
    """ファイル情報を取得"""
    try:
        stat = os.stat(file_path)
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return {
            "path": file_path,
            "name": os.path.basename(file_path),
            "size_mb": size_mb,
            "modified": modified,
            "mime_type": mime_type or "不明",
            "extension": Path(file_path).suffix,
            "is_video": mime_type and mime_type.startswith("video/")
        }
    except Exception as e:
        return {"error": str(e)}

def print_banner():
    """バナーを表示"""
    print(f"""
{'='*50}
🎬 {APP_NAME} v{VERSION}
{'='*50}
    """)

def print_file_info(info):
    """ファイル情報を表示"""
    if "error" in info:
        print(f"❌ エラー: {info['error']}")
        return
    
    print(f"""
ファイル情報:
{'─'*40}
📁 パス: {info['path']}
📄 ファイル名: {info['name']}
💾 サイズ: {info['size_mb']:.2f} MB
📅 更新日時: {info['modified']}
🔍 MIMEタイプ: {info['mime_type']}
📌 拡張子: {info['extension']}
{'─'*40}
{'✅ 動画ファイルです' if info['is_video'] else '⚠️  動画ファイルではない可能性があります'}
    """)

def interactive_mode():
    """対話モード"""
    print_banner()
    print("対話モードで起動しました。")
    print("'quit'または'exit'で終了します。\n")
    
    while True:
        file_path = input("動画ファイルのパスを入力してください: ").strip()
        
        if file_path.lower() in ['quit', 'exit']:
            print("👋 終了します。")
            break
        
        if not file_path:
            print("⚠️  ファイルパスを入力してください。\n")
            continue
        
        if not os.path.exists(file_path):
            print(f"❌ ファイルが見つかりません: {file_path}\n")
            continue
        
        info = get_file_info(file_path)
        print_file_info(info)

def main():
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} - 動画ファイル情報確認ツール"
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="確認する動画ファイルのパス"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{APP_NAME} {VERSION}"
    )
    
    args = parser.parse_args()
    
    if args.file:
        # ファイルが指定された場合
        if not os.path.exists(args.file):
            print(f"❌ ファイルが見つかりません: {args.file}")
            sys.exit(1)
        
        print_banner()
        info = get_file_info(args.file)
        print_file_info(info)
    else:
        # 対話モード
        interactive_mode()

if __name__ == "__main__":
    main()