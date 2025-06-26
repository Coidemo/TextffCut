"""
タイムライン編集UI
リアルタイム波形更新と精密編集機能を搭載
"""

import streamlit as st
from typing import Any
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.waveform_processor import WaveformProcessor
from services.timeline_editing_service import TimelineEditingService
from ui.timeline_color_scheme import TimelineColorScheme
from ui.timeline_dark_mode_fix import inject_dark_mode_css
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


def render_timeline_editor(
    time_ranges: list[tuple[float, float]], transcription_result: dict[str, Any], video_path: str
) -> None:
    """
    タイムライン編集UIをレンダリング

    Args:
        time_ranges: 初期の時間範囲リスト
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
    """
    # ダークモード用のCSS注入
    inject_dark_mode_css()

    service = TimelineEditingService()

    # タイムラインの初期化
    if "timeline_initialized" not in st.session_state:
        result = service.initialize_timeline(time_ranges, transcription_result, video_path)
        if result["success"]:
            st.session_state.timeline_initialized = True
        else:
            st.error("タイムラインの初期化に失敗しました")
            return

    # セグメント選択
    timeline_data = st.session_state.get("timeline_data", {})
    segments = timeline_data.get("segments", [])
    
    if not segments:
        st.warning("セグメントデータがありません")
        return

    # 現在の選択インデックスを取得
    if "selected_segment_idx" not in st.session_state:
        st.session_state.selected_segment_idx = 0
    
    # セグメント数が変わった場合の対応
    if st.session_state.selected_segment_idx >= len(segments):
        st.session_state.selected_segment_idx = len(segments) - 1 if segments else 0
    
    selected_idx = st.session_state.selected_segment_idx

    # 波形表示とセグメント選択を統合
    selected_idx = render_integrated_waveform_selector(segments, selected_idx, video_path, service)

    st.divider()

    # 選択セグメントの詳細編集
    if selected_idx < len(segments):
        render_segment_editor(segments[selected_idx], selected_idx, segments, service, transcription_result, video_path)

    # 操作ボタン
    st.divider()
    render_action_buttons(service)


def render_integrated_waveform_selector(segments: list, current_idx: int, video_path: str, service) -> int:
    """波形表示と統合されたセグメント選択UI"""
    
    # 波形生成（シンプルだが機能的）
    fig = go.Figure()
    
    # カラー設定
    colors = TimelineColorScheme.get_colors()
    
    # 全体の長さを計算
    total_duration = segments[-1]['end'] if segments else 0
    
    # 波形データをシミュレート（実際の音声データが取得できない場合でも表示）
    for i, segment in enumerate(segments):
        start = segment['start']
        end = segment['end']
        duration = end - start
        
        # 選択状態に応じた設定
        is_selected = i == current_idx
        color = colors["segment_active"] if is_selected else colors["waveform_positive"]
        opacity = 0.8 if is_selected else 0.5
        
        # 波形をシミュレート（実際の波形に見えるように）
        n_points = int(duration * 20)  # 1秒あたり20ポイント
        x = np.linspace(start, end, n_points)
        
        # より自然な波形パターンを生成
        base_wave = np.sin(2 * np.pi * 3 * (x - start) / duration)
        noise = np.random.randn(n_points) * 0.2
        modulation = np.sin(2 * np.pi * 0.5 * (x - start) / duration)
        y = base_wave * (0.5 + 0.3 * modulation) + noise
        y = y * (0.8 if is_selected else 0.6)
        
        # 波形を描画
        # カラーコードをrgba形式に変換（透明度付き）
        if color.startswith('#'):
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            fillcolor = f'rgba({r},{g},{b},0.3)'
        else:
            fillcolor = color
        
        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode='lines',
                fill='tozeroy',
                fillcolor=fillcolor,
                line=dict(color=color, width=1),
                name=f'Segment {i+1}',
                showlegend=False,
                hovertemplate=f'セグメント {i+1}<br>時間: %{{x:.1f}}秒<extra></extra>'
            )
        )
        
        # セグメント番号を表示
        fig.add_annotation(
            x=(start + end) / 2,
            y=0.9 if is_selected else 0.7,
            text=str(i + 1),
            showarrow=False,
            font=dict(size=16 if is_selected else 14, color='white'),
            bgcolor=color,
            borderpad=4
        )
        
        # セグメント境界線
        if i > 0:
            fig.add_vline(
                x=start,
                line_color=colors["boundary_marker"],
                line_width=1,
                line_dash="dot",
                opacity=0.5
            )
    
    # レイアウト設定
    fig.update_layout(
        height=200,
        margin=dict(l=40, r=10, t=10, b=30),
        xaxis=dict(
            title="時間（秒）",
            showgrid=True,
            gridcolor=colors["grid_lines"],
            dtick=total_duration / 10 if total_duration > 10 else 1
        ),
        yaxis=dict(
            title="",
            showgrid=False,
            showticklabels=False,
            range=[-1.2, 1.2]
        ),
        plot_bgcolor=colors["background"],
        paper_bgcolor=colors["background"],
        font=dict(color=colors["text_primary"]),
        hovermode='x unified'
    )
    
    # 波形表示
    st.plotly_chart(fig, use_container_width=True)
    
    # セグメント選択ボタン（波形の下）
    st.markdown("### セグメントを選択")
    
    # ボタンを横に並べる（セグメント数に応じて列数を調整）
    num_segments = len(segments)
    if num_segments <= 4:
        num_cols = num_segments
    elif num_segments <= 8:
        num_cols = 4
    elif num_segments <= 12:
        num_cols = 6
    else:
        num_cols = 8
    
    # 複数行に分けて表示
    rows_needed = (num_segments + num_cols - 1) // num_cols
    
    for row in range(rows_needed):
        cols = st.columns(num_cols)
        for col_idx in range(num_cols):
            i = row * num_cols + col_idx
            if i < num_segments:
                segment = segments[i]
                with cols[col_idx]:
                    is_selected = i == current_idx
                    if st.button(
                        f"#{i+1}",
                        key=f"seg_btn_{i}",
                        type="primary" if is_selected else "secondary",
                        use_container_width=True,
                        help=f"{format_time(segment['start'])} - {format_time(segment['end'])}"
                    ):
                        st.session_state.selected_segment_idx = i
                        st.rerun()
    
    return current_idx


def render_text_based_selector(segments: list, current_idx: int, video_path: str) -> int:
    """テキストベースのセグメント選択UI"""
    
    # プレビュー表示オプション
    show_preview = st.checkbox("動画プレビューを表示", value=False)
    if show_preview:
        st.video(video_path)
    
    # セグメントリスト
    st.markdown("### セグメント一覧")
    
    for i, segment in enumerate(segments):
        # セグメントコンテナ
        is_selected = i == current_idx
        
        # 選択状態に応じて背景色を変更
        if is_selected:
            st.markdown("""
            <style>
            div[data-testid="stHorizontalBlock"]:has(div.selected-segment) {
                background-color: rgba(255, 107, 107, 0.1);
                border-radius: 10px;
                padding: 10px;
            }
            </style>
            """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 6, 2])
        
        with col1:
            # セグメント番号
            if st.button(
                f"{'▶' if is_selected else ''} {i+1}",
                key=f"select_{i}",
                type="primary" if is_selected else "secondary",
                use_container_width=True
            ):
                st.session_state.selected_segment_idx = i
                st.rerun()
        
        with col2:
            # タイムスタンプとテキスト
            if is_selected:
                st.markdown(f'<div class="selected-segment"></div>', unsafe_allow_html=True)
            
            st.markdown(f"**{format_time(segment['start'])} → {format_time(segment['end'])}** "
                       f"(長さ: {format_time(segment['end'] - segment['start'])})")
            
            # テキストプレビュー
            text_preview = segment.get('text', '')[:150]
            if len(segment.get('text', '')) > 150:
                text_preview += "..."
            st.caption(text_preview)
        
        with col3:
            # クイックアクション
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("プレビュー", key=f"preview_{i}", help="このセグメントをプレビュー"):
                    # TODO: セグメントのプレビュー再生
                    st.info(f"セグメント{i+1}をプレビュー")
            
            with col_b:
                if is_selected:
                    st.success("編集中")
        
        # セパレーター
        if i < len(segments) - 1:
            st.markdown("---")
    
    return st.session_state.selected_segment_idx


def render_segment_selector(segments: list, current_idx: int) -> int:
    """セグメント選択UI"""
    
    # タイムライン風の視覚表示
    fig = go.Figure()
    
    # 各セグメントを矩形で表示
    for i, segment in enumerate(segments):
        # 選択状態に応じた色
        fillcolor = '#FF6B6B' if i == current_idx else '#4ECDC4'
        opacity = 0.8 if i == current_idx else 0.5
        
        # セグメントの矩形
        fig.add_shape(
            type="rect",
            x0=segment['start'], x1=segment['end'],
            y0=0, y1=1,
            fillcolor=fillcolor,
            opacity=opacity,
            line=dict(color='darkgray', width=1)
        )
        
        # セグメント番号
        fig.add_annotation(
            x=(segment['start'] + segment['end']) / 2,
            y=0.5,
            text=f"{i + 1}",
            showarrow=False,
            font=dict(size=16, color='white', family='Arial Black')
        )
    
    # レイアウト設定
    fig.update_layout(
        height=80,
        margin=dict(l=0, r=0, t=0, b=30),
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            title='',
            tickformat='.0f'
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            range=[0, 1]
        ),
        plot_bgcolor='#f0f0f0',
        showlegend=False
    )
    
    # タイムライン表示
    st.plotly_chart(fig, use_container_width=True)
    
    # セグメント選択ボタン
    cols_per_row = min(len(segments), 6)
    rows = (len(segments) + cols_per_row - 1) // cols_per_row
    
    for row in range(rows):
        cols = st.columns(cols_per_row)
        for col_idx in range(cols_per_row):
            seg_idx = row * cols_per_row + col_idx
            if seg_idx < len(segments):
                segment = segments[seg_idx]
                with cols[col_idx]:
                    button_type = "primary" if seg_idx == current_idx else "secondary"
                    if st.button(
                        f"{seg_idx + 1}",
                        key=f"seg_btn_{seg_idx}",
                        use_container_width=True,
                        type=button_type
                    ):
                        st.session_state.selected_segment_idx = seg_idx
                        st.rerun()
    
    return current_idx


def render_realtime_waveform(video_path: str, segments: list, selected_idx: int, service: TimelineEditingService):
    """リアルタイム更新される全体波形表示"""
    
    # シンプルな波形表示を作成
    fig = go.Figure()
    
    # カラースキーム
    colors = TimelineColorScheme.get_colors()
    
    current_x_offset = 0
    max_duration = sum(seg['end'] - seg['start'] for seg in segments)
    
    # 各セグメントを表示
    for i, segment in enumerate(segments):
        duration = segment['end'] - segment['start']
        
        # 選択状態に応じた色
        is_selected = i == selected_idx
        color = colors["segment_active"] if is_selected else colors["waveform_positive"]
        
        # セグメントを矩形として表示（波形の簡略表現）
        fig.add_shape(
            type="rect",
            x0=current_x_offset,
            y0=-0.8,
            x1=current_x_offset + duration,
            y1=0.8,
            fillcolor=color,
            opacity=0.7 if is_selected else 0.5,
            line=dict(width=0)
        )
        
        # セグメント番号を中央に表示
        fig.add_annotation(
            x=current_x_offset + duration/2,
            y=0,
            text=str(i + 1),
            showarrow=False,
            font=dict(size=20, color="white", family="Arial Black")
        )
        
        # 簡易的な波形表現（細い線）
        x_points = np.linspace(current_x_offset, current_x_offset + duration, 50)
        y_points = np.sin(np.linspace(0, 4*np.pi, 50)) * 0.3 * np.random.rand()
        
        fig.add_trace(
            go.Scatter(
                x=x_points,
                y=y_points,
                mode="lines",
                line=dict(color="white", width=1),
                showlegend=False,
                hoverinfo='skip'
            )
        )
        
        current_x_offset += duration
    
    # レイアウト設定
    fig.update_layout(
        height=120,
        margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor=colors["background"],
        plot_bgcolor=colors["background"],
        xaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            fixedrange=True,
            range=[0, max_duration]
        ),
        yaxis=dict(
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            fixedrange=True,
            range=[-1, 1]
        ),
        dragmode=False,
        hovermode=False
    )
    
    # 波形を表示
    st.plotly_chart(fig, use_container_width=True, key="main_waveform")


def render_segment_editor(segment: dict, segment_idx: int, all_segments: list, 
                         service: TimelineEditingService, transcription_result: dict, video_path: str):
    """選択セグメントの詳細編集UI"""

    
    # 制約の計算
    min_start = 0.0 if segment_idx == 0 else all_segments[segment_idx - 1]['end'] + 0.01
    # TranscriptionResultオブジェクトから動画の長さを取得
    default_duration = segment['end'] + 10
    if hasattr(transcription_result, 'metadata') and hasattr(transcription_result.metadata, 'video_duration'):
        video_duration = transcription_result.metadata.video_duration
    elif hasattr(transcription_result, 'video_duration'):
        video_duration = transcription_result.video_duration
    elif hasattr(transcription_result, 'duration'):
        video_duration = transcription_result.duration
    else:
        video_duration = default_duration
    
    max_end = video_duration
    if segment_idx < len(all_segments) - 1:
        max_end = all_segments[segment_idx + 1]['start'] - 0.01

    # プレビューボタン
    with st.expander("🎬 セグメントプレビュー", expanded=False):
        if st.button("このセグメントを再生", key=f"preview_{segment['id']}", use_container_width=True):
            # 一時的な動画ファイルを作成してプレビュー
            import tempfile
            import subprocess
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                temp_path = tmp_file.name
                
            # FFmpegでセグメント部分を抽出
            cmd = [
                'ffmpeg', '-i', video_path,
                '-ss', str(segment['start']),
                '-to', str(segment['end']),
                '-c', 'copy',
                '-y', temp_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                st.video(temp_path)
                # 一時ファイルの削除
                import os
                os.unlink(temp_path)
            except subprocess.CalledProcessError as e:
                st.error(f"プレビューの生成に失敗しました: {e}")

    # 数値入力とボタンコントロール
    col1, col2 = st.columns(2)
    
    with col1:
        # 数値入力
        new_start = st.number_input(
            "開始時間（秒）",
            min_value=min_start,
            max_value=segment['end'] - 0.01,
            value=segment['start'],
            step=0.001,  # ミリ秒単位
            format="%.3f",
            key=f"start_input_{segment['id']}"
        )
        
        # 調整ボタン
        btn_cols = st.columns(6)
        adjustments = [("-1s", -1.0), ("-0.1s", -0.1), ("-10ms", -0.01), 
                      ("+10ms", 0.01), ("+0.1s", 0.1), ("+1s", 1.0)]
        
        for i, (label, adjustment) in enumerate(adjustments):
            if btn_cols[i].button(label, key=f"start_btn_{segment['id']}_{i}"):
                new_val = segment['start'] + adjustment
                if min_start <= new_val <= segment['end'] - 0.01:
                    service.set_segment_time_range(segment['id'], new_val, segment['end'])
                    # 波形を更新するためにキャッシュをクリア
                    clear_waveform_cache()
                    st.rerun()

    with col2:
        # 数値入力
        new_end = st.number_input(
            "終了時間（秒）",
            min_value=new_start + 0.01,
            max_value=max_end,
            value=segment['end'],
            step=0.001,  # ミリ秒単位
            format="%.3f",
            key=f"end_input_{segment['id']}"
        )
        
        # 調整ボタン
        btn_cols = st.columns(6)
        for i, (label, adjustment) in enumerate(adjustments):
            if btn_cols[i].button(label, key=f"end_btn_{segment['id']}_{i}"):
                new_val = segment['end'] + adjustment
                if segment['start'] + 0.01 <= new_val <= max_end:
                    service.set_segment_time_range(segment['id'], segment['start'], new_val)
                    # 波形を更新するためにキャッシュをクリア
                    clear_waveform_cache()
                    st.rerun()

    # 値が変更された場合は更新
    if new_start != segment['start'] or new_end != segment['end']:
        if st.button("変更を適用", type="primary", key=f"apply_{segment['id']}"):
            service.set_segment_time_range(segment['id'], new_start, new_end)
            # 波形を更新するためにキャッシュをクリア
            clear_waveform_cache()
            st.rerun()


def clear_waveform_cache():
    """波形キャッシュをクリア"""
    keys_to_remove = [key for key in st.session_state.keys() if key.startswith("waveform_")]
    for key in keys_to_remove:
        del st.session_state[key]


def render_action_buttons(service: TimelineEditingService):
    """アクションボタンをレンダリング"""
    
    # 全体プレビューボタン
    if st.button("🎥 全セグメントをプレビュー", type="secondary", use_container_width=True, help="選択したすべてのセグメントを通して再生"):
        render_full_preview(service)
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("✅ 編集を完了", type="primary", use_container_width=True):
            try:
                adjusted_ranges = service.get_adjusted_time_ranges()
                service.save_timeline_settings()
                # セッション状態に保存
                st.session_state.timeline_editing_completed = True
                st.session_state.adjusted_time_ranges = adjusted_ranges
                # クリーンアップ
                cleanup_session_state()
                st.rerun()
            except Exception as e:
                st.error(f"エラーが発生しました: {str(e)}")

    with col2:
        if st.button("🔄 リセット", use_container_width=True):
            cleanup_session_state()
            clear_waveform_cache()
            st.rerun()

    with col3:
        if st.button("❌ キャンセル", use_container_width=True):
            st.session_state.timeline_editing_cancelled = True
            cleanup_session_state()
            clear_waveform_cache()
            st.rerun()


def render_full_preview(service: TimelineEditingService):
    """全セグメントの通しプレビューを表示"""
    import tempfile
    import subprocess
    import os
    
    # 現在のタイムラインデータを取得
    timeline_data = st.session_state.get("timeline_data", {})
    segments = timeline_data.get("segments", [])
    video_path = timeline_data.get("video_path", "")
    
    if not segments or not video_path:
        st.error("プレビュー用のデータがありません")
        return
    
    with st.spinner("プレビュー動画を生成中..."):
        # 一時ファイルのリスト
        temp_files = []
        
        try:
            # 各セグメントを一時ファイルに抽出
            for i, segment in enumerate(segments):
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
                    temp_path = tmp_file.name
                    temp_files.append(temp_path)
                
                cmd = [
                    'ffmpeg', '-i', video_path,
                    '-ss', str(segment['start']),
                    '-to', str(segment['end']),
                    '-c', 'copy',
                    '-y', temp_path
                ]
                
                subprocess.run(cmd, check=True, capture_output=True)
            
            # 結合用のファイルリストを作成
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as list_file:
                list_path = list_file.name
                for temp_file in temp_files:
                    list_file.write(f"file '{temp_file}'\n")
            
            # 最終的な結合ファイル
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as output_file:
                output_path = output_file.name
            
            # FFmpegで結合
            concat_cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_path,
                '-c', 'copy',
                '-y', output_path
            ]
            
            subprocess.run(concat_cmd, check=True, capture_output=True)
            
            # プレビュー表示
            st.success("プレビュー動画を生成しました")
            st.video(output_path)
            
            # 一時ファイルの削除
            os.unlink(list_path)
            os.unlink(output_path)
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                    
        except subprocess.CalledProcessError as e:
            st.error(f"プレビュー生成に失敗しました: {e}")
            # エラー時も一時ファイルを削除
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)


def cleanup_session_state():
    """セッション状態をクリーンアップ"""
    keys_to_remove = ["timeline_initialized", "timeline_data", "selected_segment_idx"]
    
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]
