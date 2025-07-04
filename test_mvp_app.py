"""
MVP版アプリケーションの動作テスト

各コンポーネントの動作を確認
"""

import streamlit as st

from di.bootstrap import bootstrap_di


def test_di_container():
    """DIコンテナの動作テスト"""
    try:
        # DIコンテナを初期化
        app_container = bootstrap_di()
        st.success("✅ DIコンテナの初期化成功")

        # Presentationコンテナを取得
        presentation_container = app_container.presentation()
        st.success("✅ Presentationコンテナの取得成功")

        # 各Presenterを取得
        main_presenter = presentation_container.main_presenter()
        st.success("✅ MainPresenterの取得成功")

        sidebar_presenter = presentation_container.sidebar_presenter()
        st.success("✅ SidebarPresenterの取得成功")

        # 初期化
        sidebar_presenter.initialize()
        st.success("✅ SidebarPresenterの初期化成功")

        # ViewModelの状態確認
        st.write("### MainViewModel状態")
        st.json(
            {
                "current_step": main_presenter.view_model.current_step,
                "is_initialized": main_presenter.view_model.is_initialized,
                "workflow_progress": main_presenter.view_model.workflow_progress,
            }
        )

        st.write("### SidebarViewModel状態")
        st.json(
            {
                "is_initialized": sidebar_presenter.view_model.is_initialized,
                "active_section": sidebar_presenter.view_model.active_section,
            }
        )

        return True

    except Exception as e:
        st.error(f"❌ エラー: {e}")
        st.exception(e)
        return False


def main():
    st.title("TextffCut MVP動作テスト")

    if st.button("DIコンテナテスト実行"):
        if test_di_container():
            st.balloons()
            st.success("すべてのテストが成功しました！")

            # 次のステップの提案
            st.info(
                """
            ### 次のステップ
            1. main_mvp.pyを実行してMVP版アプリケーションを起動
            2. 動画ファイルをアップロードして文字起こしをテスト
            3. エラーが発生した場合は、各Gatewayの実装を確認
            """
            )


if __name__ == "__main__":
    main()
