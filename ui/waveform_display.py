"""
波形表示コンポーネント
Plotlyを使用してインタラクティブな波形を描画
"""

from typing import Any

import numpy as np

from core.waveform_processor import ClipWaveformData
from ui.timeline_color_scheme import TimelineColorScheme
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)

# plotlyの動的インポート
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    logger.warning("plotly is not installed. Waveform display will be disabled.")
    PLOTLY_AVAILABLE = False
    go = None
    make_subplots = None


class WaveformDisplay:
    """波形表示クラス"""

    def __init__(self, width: int = 800, height: int = 200, use_dark_mode: bool | None = None) -> None:
        self.width = width
        self.height = height
        # ダークモード対応のカラースキームを取得
        self.colors = TimelineColorScheme.get_colors(use_dark_mode)

    def render_waveform(
        self,
        waveform_data: ClipWaveformData,
        silence_regions: list[tuple[int, int]] | None = None,
        show_time_axis: bool = True,
    ) -> Any:
        """
        波形を描画

        Args:
            waveform_data: 波形データ
            silence_regions: 無音領域のリスト
            show_time_axis: 時間軸を表示するか

        Returns:
            Plotlyフィギュア
        """
        if not PLOTLY_AVAILABLE:
            logger.warning("plotly is not available. Cannot render waveform.")
            return None

        if not waveform_data.samples:
            return self._create_empty_figure()

        samples = np.array(waveform_data.samples)
        num_samples = len(samples)
        duration = waveform_data.duration

        # 時間軸の作成
        time_points = np.linspace(0, duration, num_samples)

        # フィギュアの作成（ダークモード対応のテンプレート使用）
        if TimelineColorScheme.is_dark_mode():
            fig = go.Figure(layout_template="plotly_dark")
        else:
            fig = go.Figure()

        # 背景色の設定（ダークモード対応）
        fig.update_layout(
            plot_bgcolor=self.colors["background"],
            paper_bgcolor=self.colors["background"],
            width=self.width,
            height=self.height,
            margin={"l": 50, "r": 20, "t": 30, "b": 50},
            showlegend=False,
            font={"color": self.colors["text_primary"]},  # フォント色も設定
        )

        # 無音領域の背景を描画
        if silence_regions:
            for start_idx, end_idx in silence_regions:
                if start_idx < num_samples and end_idx <= num_samples:
                    start_time = time_points[start_idx]
                    end_time = time_points[min(end_idx, num_samples - 1)]

                    fig.add_vrect(
                        x0=start_time,
                        x1=end_time,
                        fillcolor=self.colors["waveform_silence"],
                        opacity=0.3,
                        layer="below",
                        line_width=0,
                    )

        # 波形の描画（正の値）
        positive_samples = np.where(samples > 0, samples, np.nan)
        fig.add_trace(
            go.Scatter(
                x=time_points,
                y=positive_samples,
                mode="lines",
                line={"color": self.colors["waveform_positive"], "width": 1},
                fill="tozeroy",
                name="Positive",
                hovertemplate="時間: %{x:.2f}s<br>振幅: %{y:.3f}<extra></extra>",
            )
        )

        # 波形の描画（負の値）
        negative_samples = np.where(samples < 0, samples, np.nan)
        fig.add_trace(
            go.Scatter(
                x=time_points,
                y=negative_samples,
                mode="lines",
                line={"color": self.colors["waveform_negative"], "width": 1},
                fill="tozeroy",
                name="Negative",
                hovertemplate="時間: %{x:.2f}s<br>振幅: %{y:.3f}<extra></extra>",
            )
        )

        # 軸の設定（ダークモード対応）
        fig.update_xaxes(
            title="時間 (秒)" if show_time_axis else "",
            showgrid=True,
            gridcolor=self.colors["grid_lines"],
            zeroline=True,
            zerolinecolor=self.colors["grid_major"],
            range=[0, duration],
            tickfont={"color": self.colors["text_secondary"]},
        )

        fig.update_yaxes(
            title="振幅",
            showgrid=True,
            gridcolor=self.colors["grid_lines"],
            zeroline=True,
            zerolinecolor=self.colors["grid_major"],
            range=[-1.1, 1.1],
            tickfont={"color": self.colors["text_secondary"]},
        )

        # タイトル（ダークモード対応）
        title_text = f"セグメント {waveform_data.segment_id}: {format_time(waveform_data.start_time)} - {format_time(waveform_data.end_time)}"

        # 最終的なレイアウト設定（ダークモード対応強化）
        final_layout = {
            "title": {
                "text": title_text,
                "font": {"size": 14, "color": self.colors["text_primary"]},
                "x": 0.5,
                "xanchor": "center",
            },
            # 再度背景色を設定（確実に適用されるように）
            "plot_bgcolor": self.colors["background"],
            "paper_bgcolor": self.colors["background"],
            # ホバーラベルのスタイル
            "hoverlabel": {
                "bgcolor": self.colors["background"],
                "bordercolor": self.colors["grid_major"],
                "font": {"color": self.colors["text_primary"]},
            },
            # マージン設定（重要：背景色を見せるため）
            "margin": {"l": 50, "r": 20, "t": 50, "b": 50, "pad": 0},
            # オートサイズを無効化
            "autosize": True,
        }

        # ダークモードの場合は template を明示的に設定
        if TimelineColorScheme.is_dark_mode():
            final_layout["template"] = "plotly_dark"

        fig.update_layout(**final_layout)

        return fig

    def render_timeline_overview(self, segments: list[ClipWaveformData], total_duration: float) -> Any:
        """
        タイムライン全体の概要を表示

        Args:
            segments: セグメントの波形データリスト
            total_duration: 動画の総時間

        Returns:
            Plotlyフィギュア
        """
        if not PLOTLY_AVAILABLE:
            logger.warning("plotly is not available. Cannot render timeline overview.")
            return None

        fig = make_subplots(rows=1, cols=1, subplot_titles=["タイムライン概要"])

        # セグメントごとに色分けして表示（ダークモード対応）
        if TimelineColorScheme.is_dark_mode():
            colors = ["#EF5350", "#26C6DA", "#42A5F5", "#FFA726", "#66BB6A"]
        else:
            colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#FFA07A", "#98D8C8"]

        for i, segment in enumerate(segments):
            color = colors[i % len(colors)]

            # セグメントの範囲を矩形で表示
            fig.add_shape(
                type="rect",
                x0=segment.start_time,
                y0=0,
                x1=segment.end_time,
                y1=1,
                fillcolor=color,
                opacity=0.6,
                line={"color": color, "width": 2},
            )

            # セグメントIDを表示
            fig.add_annotation(
                x=(segment.start_time + segment.end_time) / 2,
                y=0.5,
                text=segment.segment_id,
                showarrow=False,
                font={"size": 10, "color": self.colors["text_primary"]},
            )

        # レイアウト設定
        fig.update_layout(
            width=self.width,
            height=100,
            margin={"l": 50, "r": 20, "t": 30, "b": 30},
            xaxis={
                "range": [0, total_duration],
                "title": "時間 (秒)",
                "showgrid": True,
                "gridcolor": self.colors["grid_lines"],
                "tickfont": {"color": self.colors["text_secondary"]},
            },
            yaxis={"range": [0, 1], "showticklabels": False, "showgrid": False},
            plot_bgcolor=self.colors["background"],
            paper_bgcolor=self.colors["background"],
            showlegend=False,
            font={"color": self.colors["text_primary"]},
        )

        return fig

    def _create_empty_figure(self) -> Any:
        """空の波形表示を作成"""
        if not PLOTLY_AVAILABLE:
            return None

        fig = go.Figure()

        fig.add_annotation(
            x=0.5,
            y=0.5,
            text="波形データがありません",
            showarrow=False,
            font={"size": 14, "color": "#999999"},
            xref="paper",
            yref="paper",
        )

        fig.update_layout(
            width=self.width,
            height=self.height,
            plot_bgcolor=self.colors["background"],
            paper_bgcolor=self.colors["background"],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )

        return fig
