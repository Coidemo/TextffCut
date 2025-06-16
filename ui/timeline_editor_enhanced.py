import streamlit as st
from typing import List, Tuple, Optional
from core.timeline import Timeline, TimelineSegment
from core.preview import PreviewGenerator
from ui.timeline_editor import create_timeline_figure
from ui.timeline_advanced import (
    render_advanced_settings, 
    apply_dynamic_limits_to_sliders
)
import os
import time


def render_preview_player(preview_path: str, key: str):
    """プレビュー動画を再生するプレーヤーを表示"""
    if preview_path and os.path.exists(preview_path):
        st.video(preview_path, format="video/mp4", start_time=0)
    else:
        st.error("プレビューファイルが見つかりません")


def render_timeline_editor_with_preview(
    timeline: Timeline,
    video_path: str,
    video_duration: float,
    key_prefix: str = ""
) -> Timeline:
    """
    プレビュー機能と高度な設定を含む完全なタイムライン編集UI
    
    Args:
        timeline: 編集対象のタイムライン
        video_path: 元動画のパス
        video_duration: 元動画の総時間（秒）
        key_prefix: StreamlitのキーのプレフィックスKey prefix for avoiding conflicts
        
    Returns:
        編集後のタイムライン
    """
    st.subheader("🎬 タイムライン編集")
    
    # タイムラインの視覚表示
    if timeline.segments:
        fig = create_timeline_figure(timeline, video_duration)
        st.plotly_chart(fig, use_container_width=True)
    
    # 時間表示
    col1, col2, col3 = st.columns(3)
    with col1:
        original_duration = timeline.get_total_duration(adjusted=False)
        st.metric("元の合計時間", f"{original_duration:.2f} 秒")
    with col2:
        adjusted_duration = timeline.get_total_duration(adjusted=True)
        st.metric("調整後の合計時間", f"{adjusted_duration:.2f} 秒")
    with col3:
        diff = adjusted_duration - original_duration
        st.metric("差分", f"{diff:+.2f} 秒")
    
    # 高度な設定
    timeline, use_dynamic_limits = render_advanced_settings(timeline, video_duration, key_prefix)
    
    # 一括操作ボタン
    st.write("### 🎛️ 一括操作")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("🔄 すべてリセット", key=f"{key_prefix}_reset_all"):
            timeline.reset_all_gaps()
            st.rerun()
    
    with col2:
        batch_gap = st.number_input(
            "一括設定値（秒）",
            min_value=0.0,
            max_value=2.0,
            value=0.0,
            step=0.1,
            key=f"{key_prefix}_batch_gap"
        )
    
    with col3:
        if st.button("📋 一括設定", key=f"{key_prefix}_apply_all"):
            timeline.set_all_gaps(batch_gap)
            st.rerun()
    
    with col4:
        # 全体プレビューボタン
        if st.button("🎥 全体プレビュー", key=f"{key_prefix}_preview_all"):
            st.session_state[f"{key_prefix}_show_full_preview"] = True
    
    # 全体プレビューの表示
    if st.session_state.get(f"{key_prefix}_show_full_preview", False):
        with st.expander("🎥 全体プレビュー", expanded=True):
            with PreviewGenerator(video_path) as preview_gen:
                # 各つなぎ目のプレビューを生成
                preview_points = []
                enabled_segments = timeline.get_enabled_segments()
                
                for i in range(len(enabled_segments) - 1):
                    current_seg = enabled_segments[i]
                    next_seg = enabled_segments[i + 1]
                    
                    # 調整後のつなぎ目の時刻を計算
                    transition_point = (current_seg.end_time + current_seg.gap_after + 
                                      next_seg.start_time - next_seg.gap_before) / 2
                    
                    preview_points.append((
                        f"transition_{i}",
                        transition_point,
                        1.5,  # 前の時間
                        1.5   # 後の時間
                    ))
                
                # プレビューを生成
                with st.spinner("プレビューを生成中..."):
                    previews = preview_gen.generate_multiple_previews(preview_points)
                
                # プレビューを表示
                for i, (name, preview_path) in enumerate(previews):
                    if preview_path:
                        st.write(f"**つなぎ目 {i + 1}**")
                        render_preview_player(preview_path, f"{key_prefix}_preview_{name}")
            
            if st.button("プレビューを閉じる", key=f"{key_prefix}_close_full_preview"):
                st.session_state[f"{key_prefix}_show_full_preview"] = False
                st.rerun()
    
    # 各セグメントの個別調整
    st.write("### 📊 セグメント個別調整")
    
    enabled_segments = timeline.get_enabled_segments()
    adjusted_ranges = timeline.get_adjusted_ranges()
    
    for i, segment in enumerate(timeline.segments):
        with st.expander(
            f"セグメント {segment.index + 1} ({segment.start_time:.2f}秒 - {segment.end_time:.2f}秒)",
            expanded=False
        ):
            # プレビューボタン
            col_preview = st.columns([3, 1, 1])
            with col_preview[1]:
                if st.button("🎬 プレビュー", key=f"{key_prefix}_preview_seg_{i}"):
                    st.session_state[f"{key_prefix}_show_preview_{i}"] = True
            
            with col_preview[2]:
                # 有効/無効の切り替え
                segment.enabled = st.checkbox(
                    "有効",
                    value=segment.enabled,
                    key=f"{key_prefix}_enabled_{i}"
                )
            
            # プレビュー表示
            if st.session_state.get(f"{key_prefix}_show_preview_{i}", False):
                with st.container():
                    st.write("**📹 セグメントプレビュー**")
                    
                    # プレビュータイプ選択
                    preview_type = st.radio(
                        "プレビュータイプ",
                        ["セグメント全体", "前のつなぎ目", "後のつなぎ目"],
                        key=f"{key_prefix}_preview_type_{i}",
                        horizontal=True
                    )
                    
                    with PreviewGenerator(video_path) as preview_gen:
                        if preview_type == "セグメント全体":
                            # 調整後の範囲でプレビュー
                            if segment.enabled and i < len(adjusted_ranges):
                                adj_start, adj_end = adjusted_ranges[i]
                                preview_path = preview_gen.generate_segment_preview(
                                    adj_start, adj_end, max_duration=10.0
                                )
                        elif preview_type == "前のつなぎ目" and i > 0:
                            # 前のセグメントとのつなぎ目
                            prev_seg = enabled_segments[i-1] if i > 0 else None
                            if prev_seg:
                                transition = (prev_seg.end_time + segment.start_time) / 2
                                preview_path = preview_gen.generate_transition_preview(
                                    transition, 2.0, 2.0
                                )
                        else:  # 後のつなぎ目
                            if i < len(enabled_segments) - 1:
                                next_seg = enabled_segments[i+1]
                                transition = (segment.end_time + next_seg.start_time) / 2
                                preview_path = preview_gen.generate_transition_preview(
                                    transition, 2.0, 2.0
                                )
                        
                        if 'preview_path' in locals() and preview_path:
                            render_preview_player(preview_path, f"{key_prefix}_player_{i}")
                    
                    if st.button("閉じる", key=f"{key_prefix}_close_preview_{i}"):
                        st.session_state[f"{key_prefix}_show_preview_{i}"] = False
                        st.rerun()
            
            # ギャップ調整
            st.write("**⚙️ ギャップ調整**")
            
            # 動的制限を適用
            if use_dynamic_limits:
                max_before, max_after = apply_dynamic_limits_to_sliders(
                    timeline, video_duration, i, key_prefix
                )
            else:
                max_before = max_after = 2.0
            
            col1, col2 = st.columns(2)
            
            with col1:
                # 前のセグメントとのギャップ
                gap_before = st.slider(
                    "前のギャップ（秒）",
                    min_value=0.0,
                    max_value=max_before,
                    value=min(segment.gap_before, max_before),
                    step=0.1,
                    key=f"{key_prefix}_gap_before_{i}",
                    help="このセグメントの開始を早める秒数"
                )
                segment.gap_before = gap_before
            
            with col2:
                # 次のセグメントとのギャップ
                gap_after = st.slider(
                    "後のギャップ（秒）",
                    min_value=0.0,
                    max_value=max_after,
                    value=min(segment.gap_after, max_after),
                    step=0.1,
                    key=f"{key_prefix}_gap_after_{i}",
                    help="このセグメントの終了を遅らせる秒数"
                )
                segment.gap_after = gap_after
            
            # 調整後の範囲を表示
            if segment.enabled and i < len(adjusted_ranges):
                adj_start, adj_end = adjusted_ranges[i]
                st.info(f"📍 調整後: {adj_start:.2f}秒 - {adj_end:.2f}秒 (長さ: {adj_end - adj_start:.2f}秒)")
            
            # セグメント情報
            st.write(f"**元の長さ**: {segment.duration:.2f}秒")
    
    return timeline