"""
プログレス管理ユーティリティ
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

try:
    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator
except ImportError:
    st = None
    DeltaGenerator = None


@dataclass
class ProgressStep:
    """プログレスのステップ情報"""

    name: str
    weight: float = 1.0
    completed: bool = False
    start_time: float | None = None
    end_time: float | None = None

    @property
    def duration(self) -> float:
        """実行時間を取得"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0


class ProgressTracker:
    """詳細なプログレス追跡クラス"""

    def __init__(self, steps: list[str], weights: list[float] | None = None) -> None:
        """
        Args:
            steps: ステップ名のリスト
            weights: 各ステップの重み（Noneの場合は均等）
        """
        if weights is None:
            weights = [1.0] * len(steps)
        elif len(weights) != len(steps):
            raise ValueError("ステップ数と重みの数が一致しません")

        self.steps = [ProgressStep(name=name, weight=weight) for name, weight in zip(steps, weights, strict=False)]
        self.current_step_index = 0
        self.total_weight = sum(s.weight for s in self.steps)
        self.start_time = time.time()

        # Streamlit要素
        self.progress_bar: DeltaGenerator | None = None
        self.status_text: DeltaGenerator | None = None
        self.time_text: DeltaGenerator | None = None
        self.details_container: DeltaGenerator | None = None

    def initialize_ui(self) -> None:
        """Streamlit UIを初期化"""
        self.progress_bar = st.progress(0.0)
        col1, col2 = st.columns([3, 1])
        with col1:
            self.status_text = st.empty()
        with col2:
            self.time_text = st.empty()
        self.details_container = st.container()

    def start_step(self, step_index: int | None = None) -> None:
        """ステップを開始"""
        if step_index is not None:
            self.current_step_index = step_index

        if 0 <= self.current_step_index < len(self.steps):
            step = self.steps[self.current_step_index]
            step.start_time = time.time()
            step.completed = False
            self._update_display()

    def complete_step(self) -> None:
        """現在のステップを完了"""
        if 0 <= self.current_step_index < len(self.steps):
            step = self.steps[self.current_step_index]
            step.end_time = time.time()
            step.completed = True
            self.current_step_index += 1
            self._update_display()

    def update_progress(self, step_progress: float, message: str | None = None) -> None:
        """現在のステップ内の進捗を更新"""
        if message:
            self._update_display(step_progress, message)
        else:
            self._update_display(step_progress)

    def _update_display(self, step_progress: float = 0.0, custom_message: str | None = None) -> None:
        """表示を更新"""
        if not self.progress_bar:
            return

        # 全体の進捗を計算
        completed_weight = sum(s.weight for s in self.steps if s.completed)

        current_step_weight = 0.0
        if 0 <= self.current_step_index < len(self.steps):
            current_step = self.steps[self.current_step_index]
            current_step_weight = current_step.weight * step_progress

        total_progress = (completed_weight + current_step_weight) / self.total_weight

        # プログレスバーを更新
        if self.progress_bar is not None:
            self.progress_bar.progress(total_progress)

        # ステータステキストを更新
        if custom_message:
            status_message = custom_message
        elif 0 <= self.current_step_index < len(self.steps):
            current_step = self.steps[self.current_step_index]
            status_message = f"{current_step.name} ({self.current_step_index + 1}/{len(self.steps)})"
        else:
            status_message = "完了"

        if self.status_text is not None:
            self.status_text.text(status_message)

        # 時間情報を更新
        if self.time_text is not None:
            elapsed_time = time.time() - self.start_time
            if total_progress > 0 and total_progress < 1.0:
                estimated_total = elapsed_time / total_progress
                remaining = estimated_total - elapsed_time
                self.time_text.text(f"残り: {self._format_time(remaining)}")
            else:
                self.time_text.text(f"経過: {self._format_time(elapsed_time)}")

    def show_summary(self) -> None:
        """処理のサマリーを表示"""
        if self.details_container is not None:
            with self.details_container:
                total_time = time.time() - self.start_time
                st.success(f"✅ 処理完了（合計時間: {self._format_time(total_time)}）")

                # 各ステップの詳細
                with st.expander("処理の詳細", expanded=False):
                    for step in self.steps:
                        if step.completed:
                            st.write(f"- {step.name}: {self._format_time(step.duration)}")

    def _format_time(self, seconds: float) -> str:
        """時間をフォーマット"""
        if seconds < 60:
            return f"{seconds:.1f}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            return f"{minutes}分{seconds}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}時間{minutes}分"


def create_simple_progress(message: str = "処理中...") -> Callable[[float, str], None]:
    """シンプルなプログレス表示を作成"""
    progress_bar = st.progress(0.0)
    status_text = st.empty()
    time_info = st.empty()
    start_time = time.time()

    # 移動平均用のデータ
    progress_history = []

    def format_time(seconds: float) -> str:
        """時間を読みやすい形式にフォーマット"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            if secs > 0:
                return f"{minutes}分{secs}秒"
            return f"{minutes}分"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            if minutes > 0:
                return f"{hours}時間{minutes}分"
            return f"{hours}時間"

    def update(progress: float, status: str = ""):
        progress_bar.progress(progress)
        elapsed = time.time() - start_time

        # 進捗履歴を更新（移動平均用）
        progress_history.append((elapsed, progress))
        if len(progress_history) > 10:  # 最新10個のデータを保持
            progress_history.pop(0)

        if status:
            status_text.text(status)
        else:
            status_text.text(f"{message} {progress:.0%}")

        # 時間情報の表示
        if progress > 0.01 and progress < 0.99:  # 1%以上99%未満の場合
            # 移動平均で残り時間を計算
            if len(progress_history) >= 2:
                # 最新の進捗率の変化を計算
                time_diff = progress_history[-1][0] - progress_history[0][0]
                progress_diff = progress_history[-1][1] - progress_history[0][1]

                if progress_diff > 0:
                    # 残り時間を推定
                    rate = time_diff / progress_diff  # 1%あたりの時間
                    remaining = rate * (1.0 - progress)

                    # 時間情報を表示
                    elapsed_str = format_time(elapsed)
                    remaining_str = format_time(remaining)
                    time_info.markdown(f"⏱️ **経過時間**: {elapsed_str} | **残り時間**: 約{remaining_str}")
                else:
                    time_info.markdown(f"⏱️ **経過時間**: {format_time(elapsed)}")
            else:
                time_info.markdown(f"⏱️ **経過時間**: {format_time(elapsed)}")
        elif progress >= 0.99:
            time_info.markdown(f"⏱️ **総処理時間**: {format_time(elapsed)}")
        else:
            time_info.markdown("⏱️ **開始中...**")

    return update
