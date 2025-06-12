#!/usr/bin/env python3
"""
TextffCut Streamlit Embedded版
Streamlitを組み込みで起動（PyInstaller最適化版）
"""

import streamlit as st
import os
import sys
from pathlib import Path
import mimetypes
from datetime import datetime
import threading
import time
import webbrowser

# アプリ情報
APP_NAME = "TextffCut Streamlit"
VERSION = "0.3.0-streamlit"

def get_file_info(file_path):
    """ファイル情報を取得"""
    try:
        stat = os.stat(file_path)
        size_mb = stat.st_size / (1024 * 1024)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        mime_type, _ = mimetypes.guess_type(file_path)
        
        return {
            "サイズ": f"{size_mb:.2f} MB",
            "更新日時": modified,
            "MIMEタイプ": mime_type or "不明",
            "拡張子": Path(file_path).suffix
        }
    except Exception as e:
        return {"エラー": str(e)}

def run_app():
    """Streamlitアプリのメイン処理"""
    # ページ設定
    st.set_page_config(
        page_title=APP_NAME,
        page_icon="🎬",
        layout="wide"
    )
    
    # タイトル
    st.title(f"🎬 {APP_NAME}")
    st.caption(f"Version {VERSION} - PyInstaller最適化版")
    
    # サイドバー
    with st.sidebar:
        st.header("ℹ️ アプリ情報")
        st.info(f"""
        **バージョン**: {VERSION}
        **Python**: {sys.version.split()[0]}
        **Streamlit**: {st.__version__}
        **実行環境**: {'PyInstaller' if getattr(sys, 'frozen', False) else 'Python'}
        """)
    
    # メインエリア
    st.header("🎥 動画ファイル選択")
    
    # ファイルパス入力
    col1, col2 = st.columns([3, 1])
    with col1:
        file_path = st.text_input("動画ファイルのパス", placeholder="/path/to/video.mp4")
    with col2:
        st.write("")  # スペーサー
        check_button = st.button("🔍 確認", use_container_width=True)
    
    # ファイル情報表示
    if check_button and file_path:
        if os.path.exists(file_path):
            st.success("✅ ファイルが見つかりました")
            
            # ファイル情報を表示
            st.subheader("📊 ファイル情報")
            info = get_file_info(file_path)
            
            col1, col2 = st.columns(2)
            with col1:
                for key, value in list(info.items())[:2]:
                    st.metric(key, value)
            with col2:
                for key, value in list(info.items())[2:]:
                    st.metric(key, value)
            
            # 動画ファイルかチェック
            if info.get("MIMEタイプ", "").startswith("video/"):
                st.info("🎬 これは動画ファイルです")
            else:
                st.warning("⚠️ 動画ファイルではない可能性があります")
                
        else:
            st.error("❌ ファイルが見つかりません")
    
    # フッター
    st.divider()
    st.caption("TextffCut - 動画の文字起こしと切り抜きを効率化するツール")

def open_browser():
    """ブラウザを開く"""
    time.sleep(3)  # サーバー起動を待つ
    webbrowser.open('http://localhost:8501')

def main():
    """メインエントリーポイント"""
    print("🎬 TextffCut Streamlit版を起動しています...")
    print("ブラウザで http://localhost:8501 を開いています...")
    print("終了するには Ctrl+C を押してください\n")
    
    # ブラウザを別スレッドで開く
    if not os.environ.get('STREAMLIT_IN_DOCKER'):
        browser_thread = threading.Thread(target=open_browser, daemon=True)
        browser_thread.start()
    
    # Streamlitアプリを実行
    run_app()

if __name__ == "__main__":
    # Streamlitから直接実行された場合
    if 'streamlit' in sys.modules:
        run_app()
    else:
        # 通常実行の場合
        import streamlit.web.cli as stcli
        sys.argv = [
            'streamlit', 
            'run', 
            __file__,
            '--server.headless', 'true',
            '--server.port', '8501'
        ]
        sys.exit(stcli.main())