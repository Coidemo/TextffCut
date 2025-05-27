"""
Buzz Clip - 動画の文字起こしと切り抜きツール
"""

import streamlit as st
from config import config

# Streamlitの設定
st.set_page_config(
    page_title="Buzz Clip", 
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    """メイン関数"""
    st.title("🎙️ Buzz Clip")
    
    # TODO: 各モジュールの機能を段階的に移行
    st.info("リファクタリング中です。現在の機能は一時的に無効化されています。")

if __name__ == "__main__":
    main() 