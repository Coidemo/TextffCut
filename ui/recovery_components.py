"""
リカバリーUI コンポーネント

処理中断時の状態復旧用のUIコンポーネント集。
"""

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# プロジェクトルートをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator.processing_state_manager import ProcessingStateManager, TranscriptionRecovery
from utils.logging import get_logger

logger = get_logger(__name__)


def show_recovery_check(video_path: str | Path | None = None) -> dict[str, Any] | None:
    """リカバリーチェックUI

    Args:
        video_path: チェック対象の動画ファイルパス

    Returns:
        リカバリー情報または None
    """
    if not video_path:
        return None

    state_manager = ProcessingStateManager()
    recovery = TranscriptionRecovery(state_manager)

    # リカバリー情報をチェック
    recovery_info = recovery.check_recovery(str(video_path))

    if recovery_info and recovery_info.get("can_resume"):
        # リカバリー可能な場合、確認UIを表示
        with st.container(border=True):
            st.warning("⚠️ 前回の処理が中断されています")

            col1, col2 = st.columns([3, 1])

            with col1:
                st.markdown(f"**{recovery_info['message']}**")

                # 進捗バーを表示
                progress = recovery_info.get("progress", 0)
                st.progress(progress, text=f"進捗: {progress:.0%}")

                # 詳細情報
                with st.expander("詳細情報を表示"):
                    st.text(f"状態: {recovery_info['state']}")

                    # タイムスタンプ情報を取得
                    state_data = state_manager.load_state(str(video_path))
                    if state_data and "timestamp" in state_data:
                        timestamp = datetime.fromisoformat(state_data["timestamp"])
                        elapsed = datetime.now() - timestamp
                        hours = int(elapsed.total_seconds() // 3600)
                        minutes = int((elapsed.total_seconds() % 3600) // 60)
                        st.text(f"中断時刻: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                        st.text(f"経過時間: {hours}時間{minutes}分前")

                    # データ情報
                    if "data" in recovery_info:
                        data = recovery_info["data"]
                        if "chunks" in data:
                            completed_chunks = sum(1 for chunk in data["chunks"] if chunk is not None)
                            total_chunks = data.get("total_chunks", 0)
                            st.text(f"処理済みチャンク: {completed_chunks}/{total_chunks}")

            with col2:
                # アクションボタン
                if st.button("続きから再開", type="primary", use_container_width=True):
                    st.session_state["recovery_action"] = "resume"
                    st.session_state["recovery_info"] = recovery_info
                    return recovery_info

                if st.button("最初から実行", use_container_width=True):
                    st.session_state["recovery_action"] = "restart"
                    # 状態をクリア
                    state_manager.clear_state(str(video_path))
                    return None

        # ユーザーが選択するまで待機
        if "recovery_action" not in st.session_state:
            st.stop()

    return recovery_info if recovery_info else None


def show_startup_recovery() -> list[dict[str, Any]]:
    """起動時のリカバリーチェックUI

    Returns:
        リカバリー可能な処理のリスト
    """
    from orchestrator.processing_state_manager import check_and_recover_on_startup

    # リカバリー可能な処理をチェック
    recoverable = check_and_recover_on_startup()

    if recoverable:
        st.info(f"🔄 {len(recoverable)}件の中断された処理が見つかりました")

        # リカバリー可能な処理を表示
        for i, rec in enumerate(recoverable):
            with st.container(border=True):
                col1, col2, col3 = st.columns([4, 1, 1])

                with col1:
                    video_name = Path(rec["video_path"]).name
                    st.markdown(f"**{video_name}**")
                    st.caption(rec["message"])

                    # 進捗バー
                    progress = rec.get("progress", 0)
                    st.progress(progress, text=f"{progress:.0%}")

                with col2:
                    if st.button("再開", key=f"resume_{i}", use_container_width=True):
                        st.session_state[f"resume_{video_name}"] = True
                        return [rec]

                with col3:
                    if st.button("削除", key=f"delete_{i}", use_container_width=True):
                        state_manager = ProcessingStateManager()
                        state_manager.clear_state(rec["video_path"])
                        st.rerun()

    return recoverable


def show_recovery_status(video_path: str | Path, current_state: str, progress: float = 0.0) -> None:
    """処理中の状態表示UI

    Args:
        video_path: 動画ファイルパス
        current_state: 現在の処理状態
        progress: 進捗率（0.0-1.0）
    """
    # 状態に応じたアイコンとメッセージ
    state_config = {
        "transcribing": ("🎤", "文字起こし中", "primary"),
        "processing": ("⚙️", "処理中", "secondary"),
        "exporting": ("📤", "エクスポート中", "info"),
        "error": ("❌", "エラー", "error"),
        "completed": ("✅", "完了", "success"),
    }

    icon, message, status = state_config.get(current_state, ("❓", "不明", "secondary"))

    # 進捗状況を表示
    container = st.container()
    with container:
        col1, col2 = st.columns([5, 1])

        with col1:
            st.markdown(f"{icon} **{message}**")

            # 進捗バー
            if 0 <= progress <= 1:
                st.progress(progress, text=f"{progress:.0%} 完了")

            # 自動保存インジケーター
            if current_state in ["transcribing", "processing"]:
                st.caption("💾 進捗は自動的に保存されています")

        with col2:
            # 中断ボタン
            if current_state in ["transcribing", "processing"]:
                if st.button("⏸️ 中断", use_container_width=True):
                    st.session_state["interrupt_requested"] = True
                    st.warning("処理を中断しています...")


def show_recovery_settings() -> None:
    """リカバリー設定UI（サイドバー用）"""
    st.markdown("#### 🔄 リカバリー設定")

    # 自動リカバリーの有効/無効
    auto_recovery = st.checkbox(
        "自動リカバリーを有効にする",
        value=st.session_state.get("auto_recovery", True),
        help="処理が中断された場合、次回起動時に自動的に再開します",
    )
    st.session_state["auto_recovery"] = auto_recovery

    # 状態保存間隔
    if auto_recovery:
        save_interval = st.select_slider(
            "状態保存間隔",
            options=[1, 5, 10, 30, 60],
            value=st.session_state.get("save_interval", 10),
            format_func=lambda x: f"{x}秒",
            help="処理状態を保存する間隔を設定します",
        )
        st.session_state["save_interval"] = save_interval

    # 保存期間
    retention_hours = st.number_input(
        "状態ファイルの保存期間（時間）",
        min_value=1,
        max_value=168,  # 1週間
        value=st.session_state.get("retention_hours", 24),
        help="古い状態ファイルは自動的に削除されます",
    )
    st.session_state["retention_hours"] = retention_hours

    # 手動クリーンアップ
    if st.button("🗑️ 古い状態ファイルを削除", use_container_width=True):
        state_manager = ProcessingStateManager()
        deleted = state_manager.cleanup_old_states(hours=retention_hours)
        st.success(f"{deleted}個の古い状態ファイルを削除しました")


def show_recovery_history() -> None:
    """リカバリー履歴UI"""
    st.markdown("### 📋 処理履歴")

    state_manager = ProcessingStateManager()
    states = state_manager.list_states()

    if not states:
        st.info("処理履歴はありません")
        return

    # 履歴を表形式で表示
    for state in states:
        with st.container(border=True):
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

            with col1:
                video_name = Path(state["video_path"]).name
                st.markdown(f"**{video_name}**")

                # タイムスタンプ
                timestamp = datetime.fromisoformat(state["timestamp"])
                st.caption(timestamp.strftime("%Y-%m-%d %H:%M:%S"))

            with col2:
                # 状態アイコン
                state_icon = {
                    "transcribing": "🎤",
                    "processing": "⚙️",
                    "exporting": "📤",
                    "error": "❌",
                    "completed": "✅",
                    "interrupted": "⏸️",
                }.get(state["state"], "❓")
                st.markdown(f"{state_icon} {state['state']}")

            with col3:
                # 進捗
                progress = state.get("progress", 0)
                if progress >= 0:  # -1は中断を示す
                    st.metric("進捗", f"{progress:.0%}")
                else:
                    st.metric("進捗", "中断")

            with col4:
                # アクション
                if state["state"] in ["transcribing", "processing", "interrupted"]:
                    if st.button("再開", key=f"hist_resume_{state['video_path']}", use_container_width=True):
                        st.session_state[f"resume_history_{video_name}"] = state
                        st.rerun()

                if st.button("削除", key=f"hist_delete_{state['video_path']}", use_container_width=True):
                    state_manager.clear_state(state["video_path"])
                    st.rerun()


# テスト用関数
def test_recovery_ui() -> None:
    """リカバリーUIのテスト"""
    st.set_page_config(page_title="Recovery UI Test", layout="wide")

    st.title("🔄 リカバリーUI テスト")

    # サイドバー
    with st.sidebar:
        show_recovery_settings()

    # メインコンテンツ
    tab1, tab2, tab3 = st.tabs(["リカバリーチェック", "処理状態", "履歴"])

    with tab1:
        st.markdown("### リカバリーチェック")

        # テスト用の動画パス
        test_video = st.text_input("動画ファイルパス", value="/test/videos/sample.mp4")

        if st.button("チェック実行"):
            recovery_info = show_recovery_check(test_video)
            if recovery_info:
                st.success("リカバリー情報が見つかりました")
                st.json(recovery_info)
            else:
                st.info("リカバリー可能な情報はありません")

    with tab2:
        st.markdown("### 処理状態表示")

        # テスト用の状態表示
        test_states = [
            ("transcribing", 0.3),
            ("processing", 0.7),
            ("exporting", 0.9),
            ("completed", 1.0),
            ("error", 0.5),
        ]

        for state, progress in test_states:
            st.markdown(f"#### {state}")
            show_recovery_status("/test/video.mp4", state, progress)
            st.divider()

    with tab3:
        show_recovery_history()


if __name__ == "__main__":
    test_recovery_ui()
