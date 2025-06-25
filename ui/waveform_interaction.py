"""
波形インタラクション機能
波形上でのクリックやドラッグ操作を処理
"""

from typing import Optional, Tuple, Dict, Any, Callable
import streamlit as st

from core.waveform_processor import WaveformData
from utils.logging import get_logger

logger = get_logger(__name__)


class WaveformInteraction:
    """波形インタラクション管理クラス"""
    
    def __init__(self):
        self.click_handlers: Dict[str, Callable] = {}
        self.hover_info_enabled = True
        self.boundary_adjustment_enabled = True
        self.boundary_threshold = 0.1  # 境界検出の閾値（秒）
    
    def register_click_handler(self, handler_name: str, handler: Callable):
        """クリックハンドラーを登録"""
        self.click_handlers[handler_name] = handler
    
    def process_click_event(
        self, 
        click_data: Dict[str, Any], 
        waveform_data: WaveformData,
        segment_boundaries: list[float]
    ) -> Optional[Dict[str, Any]]:
        """
        波形上のクリックイベントを処理
        
        Args:
            click_data: Plotlyのクリックイベントデータ
            waveform_data: 波形データ
            segment_boundaries: セグメント境界のリスト
            
        Returns:
            処理結果
        """
        if not click_data:
            return None
        
        # クリック位置を時間に変換
        points = click_data.get("points", [])
        if not points:
            return None
        
        click_time = points[0].get("x", 0)
        click_amplitude = points[0].get("y", 0)
        
        logger.debug(f"Waveform clicked at time: {click_time:.2f}s, amplitude: {click_amplitude:.3f}")
        
        # 境界付近のクリックかチェック
        if self.boundary_adjustment_enabled:
            nearest_boundary = self._find_nearest_boundary(click_time, segment_boundaries)
            if nearest_boundary is not None:
                distance = abs(click_time - nearest_boundary)
                if distance <= self.boundary_threshold:
                    # 境界調整モード
                    return {
                        "action": "adjust_boundary",
                        "boundary_time": nearest_boundary,
                        "click_time": click_time,
                        "distance": distance
                    }
        
        # 通常のクリック
        return {
            "action": "select_time",
            "time": click_time,
            "amplitude": click_amplitude
        }
    
    def _find_nearest_boundary(self, time: float, boundaries: list[float]) -> Optional[float]:
        """最も近い境界を見つける"""
        if not boundaries:
            return None
        
        min_distance = float('inf')
        nearest = None
        
        for boundary in boundaries:
            distance = abs(time - boundary)
            if distance < min_distance:
                min_distance = distance
                nearest = boundary
        
        return nearest
    
    def create_interactive_waveform_config(self) -> Dict[str, Any]:
        """
        インタラクティブな波形のPlotly設定を作成
        
        Returns:
            Plotly設定辞書
        """
        config = {
            "displayModeBar": True,
            "displaylogo": False,
            "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
            "modeBarButtonsToAdd": [],
            "toImageButtonOptions": {
                "format": "png",
                "filename": "waveform",
                "height": 400,
                "width": 800,
                "scale": 2
            }
        }
        
        return config
    
    def add_boundary_markers(
        self, 
        fig: Any, 
        boundaries: list[float],
        selected_boundary: Optional[float] = None
    ):
        """
        波形図に境界マーカーを追加
        
        Args:
            fig: Plotlyフィギュア
            boundaries: 境界時間のリスト
            selected_boundary: 選択中の境界
        """
        import plotly.graph_objects as go
        
        for boundary in boundaries:
            color = "#FF6B6B" if boundary == selected_boundary else "#FFA500"
            width = 3 if boundary == selected_boundary else 2
            
            # 垂直線を追加
            fig.add_vline(
                x=boundary,
                line_color=color,
                line_width=width,
                line_dash="dash" if boundary != selected_boundary else "solid",
                annotation_text=f"{boundary:.1f}s",
                annotation_position="top",
                annotation_font_size=10
            )
            
            # インタラクション領域を追加（透明な矩形）
            fig.add_shape(
                type="rect",
                x0=boundary - self.boundary_threshold,
                y0=-1.1,
                x1=boundary + self.boundary_threshold,
                y1=1.1,
                fillcolor="rgba(255, 165, 0, 0.1)",
                line_width=0,
                layer="below"
            )
    
    def add_hover_info(self, fig: Any, waveform_data: WaveformData):
        """
        ホバー情報を追加
        
        Args:
            fig: Plotlyフィギュア  
            waveform_data: 波形データ
        """
        if not self.hover_info_enabled:
            return
        
        # カスタムホバーテンプレート
        hover_template = (
            "<b>時間:</b> %{x:.2f}秒<br>"
            "<b>振幅:</b> %{y:.3f}<br>"
            "<b>dB:</b> %{customdata:.1f}<br>"
            "<extra></extra>"
        )
        
        # 既存のトレースにホバーテンプレートを適用
        for trace in fig.data:
            if hasattr(trace, 'hovertemplate'):
                trace.hovertemplate = hover_template
    
    def create_adjustment_panel(
        self, 
        boundary_time: float,
        min_time: float,
        max_time: float
    ) -> Tuple[float, bool]:
        """
        境界調整パネルを作成
        
        Args:
            boundary_time: 現在の境界時間
            min_time: 最小時間
            max_time: 最大時間
            
        Returns:
            (新しい境界時間, 確定フラグ)
        """
        st.markdown("#### 🎯 境界位置の調整")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col1:
            st.metric("現在の位置", f"{boundary_time:.2f}秒")
        
        with col2:
            new_time = st.slider(
                "新しい位置",
                min_value=min_time,
                max_value=max_time,
                value=boundary_time,
                step=0.01,
                format="%.2f秒"
            )
        
        with col3:
            delta = new_time - boundary_time
            st.metric("変化量", f"{delta:+.2f}秒")
        
        # 微調整ボタン
        st.markdown("##### 微調整")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        
        adjustments = [
            (col1, "-1.0s", -1.0),
            (col2, "-0.5s", -0.5),
            (col3, "-0.1s", -0.1),
            (col4, "+0.1s", 0.1),
            (col5, "+0.5s", 0.5),
            (col6, "+1.0s", 1.0)
        ]
        
        for col, label, adjustment in adjustments:
            with col:
                if st.button(label, key=f"adjust_{label}"):
                    new_time = boundary_time + adjustment
                    new_time = max(min_time, min(new_time, max_time))
                    st.session_state.boundary_adjustment_time = new_time
        
        # 確定/キャンセルボタン
        col1, col2, col3 = st.columns([1, 1, 2])
        
        with col1:
            confirm = st.button("✅ 確定", type="primary")
        
        with col2:
            cancel = st.button("❌ キャンセル")
        
        if cancel:
            return boundary_time, False
        
        return new_time, confirm


class WaveformPlayback:
    """波形再生制御クラス"""
    
    def __init__(self):
        self.is_playing = False
        self.current_position = 0.0
        self.playback_speed = 1.0
    
    def create_playback_controls(self) -> Dict[str, Any]:
        """
        再生コントロールUIを作成
        
        Returns:
            コントロールの状態
        """
        col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
        
        with col1:
            if self.is_playing:
                if st.button("⏸️ 一時停止", key="pause_button"):
                    self.is_playing = False
            else:
                if st.button("▶️ 再生", key="play_button"):
                    self.is_playing = True
        
        with col2:
            if st.button("⏹️ 停止", key="stop_button"):
                self.is_playing = False
                self.current_position = 0.0
        
        with col3:
            speed_options = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
            self.playback_speed = st.selectbox(
                "速度",
                speed_options,
                index=speed_options.index(self.playback_speed),
                format_func=lambda x: f"{x}x",
                key="playback_speed"
            )
        
        with col4:
            st.progress(
                self.current_position,
                text=f"再生位置: {self.current_position:.1f}秒"
            )
        
        return {
            "is_playing": self.is_playing,
            "position": self.current_position,
            "speed": self.playback_speed
        }