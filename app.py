"""
TextffCut - クリーンアーキテクチャ版エントリーポイント

移行期間中は、main.pyの動作を維持しながら段階的に移行する。
"""

import streamlit as st

from infrastructure.ui.router import Router


def main():
    """アプリケーションのエントリーポイント"""
    # 移行期間中の設定
    # Phase 1では既存のmain.pyの処理を呼び出す
    st.session_state["use_clean_architecture"] = st.session_state.get("use_clean_architecture", False)

    if st.session_state["use_clean_architecture"]:
        # クリーンアーキテクチャ版
        router = Router()
        router.route()
    else:
        # 既存のmain.pyを使用（デフォルト）
        from main import main as legacy_main

        legacy_main()


if __name__ == "__main__":
    main()
