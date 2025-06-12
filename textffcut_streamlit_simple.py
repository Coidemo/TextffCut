#!/usr/bin/env python3
"""
TextffCut Streamlit Simple版
最もシンプルなStreamlitアプリで動作確認
"""

import streamlit as st

def main():
    st.title("🎬 TextffCut Streamlit Simple")
    st.write("PyInstallerでの動作確認用")
    
    file_path = st.text_input("ファイルパス")
    
    if st.button("確認"):
        st.write(f"入力されたパス: {file_path}")

# エントリーポイント
if __name__ == "__main__":
    # Streamlitから実行されている場合
    if "streamlit" in dir():
        main()
    else:
        # 直接実行されている場合
        import sys
        from streamlit.web import cli as stcli
        sys.argv = ["streamlit", "run", __file__]
        sys.exit(stcli.main())