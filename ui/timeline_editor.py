"""
タイムライン編集UI
"""
import streamlit as st
from typing import List, Tuple, Optional
import plotly.graph_objects as go
from core.timeline import Timeline, TimelineSegment
from utils.time_utils import format_time
import logging

logger = logging.getLogger(__name__)


def create_timeline_figure(timeline: Timeline) -> go.Figure:
    """タイムラインの視覚的表現を作成
    
    Args:
        timeline: タイムラインオブジェクト
        
    Returns:
        Plotly Figureオブジェクト
    """
    fig = go.Figure()
    
    enabled_segments = [seg for seg in timeline.segments if seg.enabled]
    if not enabled_segments:
        return fig
    
    # 元のセグメントを表示
    for i, segment in enumerate(enabled_segments):
        # セグメント本体
        fig.add_trace(go.Scatter(
            x=[segment.start, segment.end],
            y=[1, 1],
            mode='lines',
            line=dict(color='lightblue', width=20),
            name=f'セグメント {i+1}',
            hovertemplate=f'セグメント {i+1}<br>開始: %{{x:.1f}}秒<br>終了: %{{x:.1f}}秒<br>長さ: {segment.duration:.1f}秒<extra></extra>'
        ))
        
        # セグメントのラベル
        fig.add_annotation(
            x=(segment.start + segment.end) / 2,
            y=1,
            text=f'S{i+1}',
            showarrow=False,
            font=dict(size=12, color='white'),
            bgcolor='rgba(0,0,0,0.5)'
        )
    
    # 調整後のセグメントを表示
    adjusted_ranges = timeline.get_adjusted_ranges()
    for i, (start, end) in enumerate(adjusted_ranges):
        segment = enabled_segments[i]
        
        # ギャップ部分（前）
        if segment.gap_before > 0:
            fig.add_trace(go.Scatter(
                x=[start, segment.start],
                y=[0.5, 0.5],
                mode='lines',
                line=dict(color='red', width=10, dash='dot'),
                name=f'ギャップ前 {i+1}',
                hovertemplate=f'前ギャップ {i+1}<br>%{{x:.1f}}秒<extra></extra>',
                showlegend=False
            ))
        
        # 調整後セグメント
        fig.add_trace(go.Scatter(
            x=[start, end],
            y=[0.5, 0.5],
            mode='lines',
            line=dict(color='darkturquoise', width=20),
            name=f'調整後 {i+1}',
            hovertemplate=f'調整後セグメント {i+1}<br>開始: %{{x:.1f}}秒<br>終了: %{{x:.1f}}秒<br>長さ: {end-start:.1f}秒<extra></extra>',
            showlegend=False
        ))
        
        # ギャップ部分（後）
        if segment.gap_after > 0:
            fig.add_trace(go.Scatter(
                x=[segment.end, end],
                y=[0.5, 0.5],
                mode='lines',
                line=dict(color='red', width=10, dash='dot'),
                name=f'ギャップ後 {i+1}',
                hovertemplate=f'後ギャップ {i+1}<br>%{{x:.1f}}秒<extra></extra>',
                showlegend=False
            ))
    
    # レイアウト設定
    fig.update_layout(
        title='タイムライン（上: 元の範囲、下: 調整後）',
        xaxis_title='時間（秒）',
        yaxis=dict(
            range=[0, 1.5],
            ticktext=['調整後', '元'],
            tickvals=[0.5, 1],
            showgrid=False
        ),
        height=300,
        showlegend=False,
        hovermode='x unified'
    )
    
    return fig


def timeline_editor(time_ranges: List[Tuple[float, float]], key_prefix: str = "") -> Optional[Timeline]:
    """タイムライン編集UI
    
    Args:
        time_ranges: 元の時間範囲のリスト
        key_prefix: Streamlitキーのプレフィックス
        
    Returns:
        編集されたタイムラインオブジェクト（変更がない場合はNone）
    """
    if not time_ranges:
        st.warning("編集可能なセグメントがありません")
        return None
    
    # セッション状態にタイムラインを保存
    timeline_key = f"{key_prefix}_timeline"
    if timeline_key not in st.session_state:
        st.session_state[timeline_key] = Timeline(time_ranges)
    
    timeline: Timeline = st.session_state[timeline_key]
    
    # セグメント数が1つの場合は編集不要
    if len(timeline.segments) == 1:
        st.info("セグメントが1つのみのため、タイムライン調整は不要です")
        return None
    
    # タイムライン表示
    st.markdown("#### 🎬 タイムライン編集")
    
    # 視覚的なタイムラインを表示
    fig = create_timeline_figure(timeline)
    st.plotly_chart(fig, use_container_width=True)
    
    # 調整前後の合計時間を表示
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("元の合計時間", format_time(timeline.get_total_duration()))
    with col2:
        adjusted_duration = timeline.get_adjusted_duration()
        diff = adjusted_duration - timeline.get_total_duration()
        st.metric("調整後の合計時間", format_time(adjusted_duration), f"{diff:+.1f}秒")
    with col3:
        st.metric("セグメント数", timeline.get_segment_count())
    
    # セグメント間のギャップ調整
    st.markdown("##### 各セグメント間の調整")
    
    # 一括設定
    with st.expander("一括設定", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            all_gap_before = st.number_input(
                "全セグメントの前ギャップ（秒）",
                min_value=0.0,
                max_value=2.0,
                value=0.0,
                step=0.1,
                key=f"{key_prefix}_all_gap_before"
            )
        with col2:
            all_gap_after = st.number_input(
                "全セグメントの後ギャップ（秒）",
                min_value=0.0,
                max_value=2.0,
                value=0.0,
                step=0.1,
                key=f"{key_prefix}_all_gap_after"
            )
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("一括適用", key=f"{key_prefix}_apply_all"):
                timeline.set_all_gaps(all_gap_before, all_gap_after)
                st.success("一括設定を適用しました")
                st.rerun()
        with col2:
            if st.button("リセット", key=f"{key_prefix}_reset_all"):
                timeline.reset_all_gaps()
                st.success("すべてのギャップをリセットしました")
                st.rerun()
    
    # 個別調整
    enabled_segments = [seg for seg in timeline.segments if seg.enabled]
    
    for i, segment in enumerate(enabled_segments):
        with st.container():
            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
            
            with col1:
                # セグメント情報
                st.markdown(f"**セグメント {i+1}**")
                st.caption(f"{format_time(segment.start)} - {format_time(segment.end)}")
            
            with col2:
                # 前のセグメントからのギャップ
                if i > 0:
                    segment.gap_before = st.slider(
                        "前ギャップ",
                        min_value=0.0,
                        max_value=2.0,
                        value=segment.gap_before,
                        step=0.1,
                        key=f"{key_prefix}_gap_before_{i}",
                        help="前のセグメントとの間に追加する時間（秒）"
                    )
                else:
                    st.empty()
            
            with col3:
                # 次のセグメントへのギャップ
                if i < len(enabled_segments) - 1:
                    segment.gap_after = st.slider(
                        "後ギャップ",
                        min_value=0.0,
                        max_value=2.0,
                        value=segment.gap_after,
                        step=0.1,
                        key=f"{key_prefix}_gap_after_{i}",
                        help="次のセグメントとの間に追加する時間（秒）"
                    )
                else:
                    st.empty()
            
            with col4:
                # 有効/無効の切り替え
                segment.enabled = st.checkbox(
                    "有効",
                    value=segment.enabled,
                    key=f"{key_prefix}_enabled_{i}"
                )
            
            # 調整後の範囲を表示
            if segment.gap_before > 0 or segment.gap_after > 0:
                adjusted_ranges = timeline.get_adjusted_ranges()
                if i < len(adjusted_ranges):
                    adj_start, adj_end = adjusted_ranges[i]
                    st.caption(f"→ 調整後: {format_time(adj_start)} - {format_time(adj_end)}")
    
    # ギャップ検証
    if not timeline.validate_gaps():
        st.warning("⚠️ ギャップ設定に問題がある可能性があります")
    
    return timeline