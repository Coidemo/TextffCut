"""
タイムライン編集UI
動画セグメント間のギャップを視覚的に調整する機能を提供
"""
import streamlit as st
from typing import List, Tuple, Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.timeline import Timeline, TimelineSegment
from utils.time_utils import format_time


def create_timeline_figure(timeline: Timeline) -> go.Figure:
    """タイムラインの視覚的表現を作成
    
    Args:
        timeline: Timeline インスタンス
        
    Returns:
        Plotlyのfigureオブジェクト
    """
    fig = make_subplots(
        rows=2, cols=1,
        row_heights=[0.5, 0.5],
        vertical_spacing=0.15,
        subplot_titles=("元のセグメント", "調整後のセグメント")
    )
    
    # カラーパレット
    colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c', '#9b59b6', '#1abc9c']
    
    # 元のセグメントを表示（上段）
    for i, segment in enumerate(timeline.segments):
        if not segment.enabled:
            continue
            
        color = colors[i % len(colors)]
        
        # セグメントバー
        fig.add_trace(
            go.Scatter(
                x=[segment.start_time, segment.end_time, segment.end_time, segment.start_time, segment.start_time],
                y=[0, 0, 0.8, 0.8, 0],
                fill='toself',
                fillcolor=color,
                line=dict(color=color),
                name=f"セグメント {i+1}",
                text=f"セグメント {i+1}<br>{format_time(segment.start_time)} - {format_time(segment.end_time)}<br>長さ: {segment.duration:.1f}秒",
                hoverinfo='text',
                showlegend=False
            ),
            row=1, col=1
        )
        
        # セグメント番号
        fig.add_trace(
            go.Scatter(
                x=[(segment.start_time + segment.end_time) / 2],
                y=[0.4],
                mode='text',
                text=[str(i+1)],
                textfont=dict(size=12, color='white'),
                showlegend=False,
                hoverinfo='skip'
            ),
            row=1, col=1
        )
    
    # 調整後のセグメントを表示（下段）
    adjusted_ranges = timeline.get_adjusted_ranges()
    enabled_segments = [seg for seg in timeline.segments if seg.enabled]
    
    for i, (segment, (adj_start, adj_end)) in enumerate(zip(enabled_segments, adjusted_ranges)):
        color = colors[i % len(colors)]
        
        # 元の範囲（薄い色）
        fig.add_trace(
            go.Scatter(
                x=[segment.start_time, segment.end_time, segment.end_time, segment.start_time, segment.start_time],
                y=[0, 0, 0.8, 0.8, 0],
                fill='toself',
                fillcolor=color,
                opacity=0.3,
                line=dict(color=color, dash='dot'),
                name=f"元の範囲 {i+1}",
                showlegend=False,
                hoverinfo='skip'
            ),
            row=2, col=1
        )
        
        # 調整後の範囲（濃い色）
        fig.add_trace(
            go.Scatter(
                x=[adj_start, adj_end, adj_end, adj_start, adj_start],
                y=[0, 0, 0.8, 0.8, 0],
                fill='toself',
                fillcolor=color,
                opacity=0.7,
                line=dict(color=color),
                name=f"調整後 {i+1}",
                text=f"調整後セグメント {i+1}<br>{format_time(adj_start)} - {format_time(adj_end)}<br>長さ: {adj_end - adj_start:.1f}秒",
                hoverinfo='text',
                showlegend=False
            ),
            row=2, col=1
        )
        
        # ギャップ表示（前後）
        if segment.gap_before > 0:
            fig.add_trace(
                go.Scatter(
                    x=[adj_start, segment.start_time],
                    y=[0.4, 0.4],
                    mode='lines',
                    line=dict(color='red', width=3, dash='dash'),
                    name=f"ギャップ前 {i+1}",
                    text=f"前ギャップ: {segment.gap_before:.1f}秒",
                    hoverinfo='text',
                    showlegend=False
                ),
                row=2, col=1
            )
        
        if segment.gap_after > 0:
            fig.add_trace(
                go.Scatter(
                    x=[segment.end_time, adj_end],
                    y=[0.4, 0.4],
                    mode='lines',
                    line=dict(color='red', width=3, dash='dash'),
                    name=f"ギャップ後 {i+1}",
                    text=f"後ギャップ: {segment.gap_after:.1f}秒",
                    hoverinfo='text',
                    showlegend=False
                ),
                row=2, col=1
            )
    
    # レイアウト設定
    fig.update_xaxes(title_text="時間（秒）", row=2, col=1)
    fig.update_yaxes(visible=False, range=[-0.1, 1])
    
    fig.update_layout(
        height=400,
        showlegend=False,
        hovermode='closest',
        margin=dict(l=0, r=0, t=30, b=0)
    )
    
    return fig


def render_timeline_editor(timeline: Timeline, key_prefix: str = "") -> Timeline:
    """タイムライン編集UIをレンダリング
    
    Args:
        timeline: Timeline インスタンス
        key_prefix: Streamlitウィジェットのキープレフィックス
        
    Returns:
        編集されたTimelineインスタンス
    """
    # タイムラインのコピーを作成（元のデータを変更しないため）
    edited_timeline = timeline.copy()
    
    # 視覚的なタイムライン表示
    st.markdown("#### 📊 タイムライン")
    fig = create_timeline_figure(edited_timeline)
    st.plotly_chart(fig, use_container_width=True)
    
    # 統計情報
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("セグメント数", len([s for s in edited_timeline.segments if s.enabled]))
    with col2:
        original_duration = edited_timeline.get_original_duration()
        st.metric("元の合計時間", f"{original_duration:.1f}秒")
    with col3:
        adjusted_duration = edited_timeline.get_total_duration()
        diff = adjusted_duration - original_duration
        st.metric("調整後の合計時間", f"{adjusted_duration:.1f}秒", f"{diff:+.1f}秒")
    
    # ギャップ調整セクション
    st.markdown("#### 🎛️ ギャップ調整")
    
    # 一括設定
    with st.expander("⚙️ 一括設定", expanded=False):
        col1, col2 = st.columns([2, 1])
        with col1:
            bulk_gap = st.slider(
                "全セグメントのギャップ",
                min_value=0.0,
                max_value=2.0,
                value=0.0,
                step=0.1,
                key=f"{key_prefix}_bulk_gap"
            )
        with col2:
            if st.button("適用", key=f"{key_prefix}_apply_bulk"):
                edited_timeline.set_all_gaps(bulk_gap)
                st.rerun()
            if st.button("リセット", key=f"{key_prefix}_reset_all"):
                edited_timeline.reset_all_gaps()
                st.rerun()
    
    # 個別セグメント調整
    st.markdown("##### 個別調整")
    
    enabled_segments = [seg for seg in edited_timeline.segments if seg.enabled]
    
    if len(enabled_segments) > 1:
        # つなぎ目ごとの調整
        for i in range(len(enabled_segments) - 1):
            with st.container():
                col1, col2, col3 = st.columns([1, 3, 1])
                
                with col1:
                    st.markdown(f"**つなぎ目 {i+1}**")
                    st.caption(f"セグメント{i+1} → {i+2}")
                
                with col2:
                    current_gap = edited_timeline.get_gap_at_index(i)
                    new_gap = st.slider(
                        f"間隔（秒）",
                        min_value=0.0,
                        max_value=2.0,
                        value=current_gap,
                        step=0.1,
                        key=f"{key_prefix}_gap_{i}",
                        label_visibility="collapsed"
                    )
                    
                    if new_gap != current_gap:
                        edited_timeline.set_gap_at_index(i, new_gap)
                
                with col3:
                    # 調整後の範囲を表示
                    adjusted_ranges = edited_timeline.get_adjusted_ranges()
                    if i < len(adjusted_ranges) - 1:
                        end_time = adjusted_ranges[i][1]
                        start_time = adjusted_ranges[i + 1][0]
                        actual_gap = start_time - end_time
                        if actual_gap > 0:
                            st.caption(f"実際の間隔: {actual_gap:.1f}秒")
                        else:
                            st.caption("連続")
    
    # セグメントの有効/無効切り替え
    with st.expander("🎯 セグメントの有効/無効", expanded=False):
        cols = st.columns(min(len(edited_timeline.segments), 4))
        for i, segment in enumerate(edited_timeline.segments):
            with cols[i % len(cols)]:
                enabled = st.checkbox(
                    f"セグメント {i+1}",
                    value=segment.enabled,
                    key=f"{key_prefix}_enable_{i}"
                )
                segment.enabled = enabled
    
    return edited_timeline


def should_show_timeline_editor(time_ranges: List[Tuple[float, float]], process_type: str) -> bool:
    """タイムライン編集UIを表示すべきかどうかを判定
    
    Args:
        time_ranges: 時間範囲のリスト
        process_type: 処理タイプ（"切り抜きのみ" or "切り抜き + 無音削除"）
        
    Returns:
        表示すべきならTrue
    """
    # 複数セグメントがある場合のみ表示
    # 無音削除の場合は削除後のセグメント数で判定するため、ここでは切り抜きのみの場合
    if process_type == "切り抜きのみ" and len(time_ranges) > 1:
        return True
    
    return False