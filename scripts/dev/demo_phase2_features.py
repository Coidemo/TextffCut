"""
Phase 2機能のデモアプリケーション
キーボードショートカットとインタラクティブ操作のデモ
"""

import streamlit as st
from pathlib import Path
import numpy as np

from core.waveform_processor import WaveformProcessor, WaveformData
from ui.waveform_display import WaveformDisplay
from ui.waveform_interaction import WaveformInteraction, WaveformPlayback
from ui.keyboard_handler import KeyboardShortcuts, inject_keyboard_handler_script


def main():
    st.set_page_config(
        page_title="Phase 2 機能デモ", 
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🎮 タイムライン編集 Phase 2 デモ")
    st.markdown("キーボードショートカットとインタラクティブ操作の実装確認")
    
    # セッション状態の初期化
    if "keyboard_shortcuts" not in st.session_state:
        st.session_state.keyboard_shortcuts = KeyboardShortcuts()
    
    if "waveform_interaction" not in st.session_state:
        st.session_state.waveform_interaction = WaveformInteraction()
    
    if "playback_control" not in st.session_state:
        st.session_state.playback_control = WaveformPlayback()
    
    if "demo_segment_start" not in st.session_state:
        st.session_state.demo_segment_start = 0.0
    
    if "demo_segment_end" not in st.session_state:
        st.session_state.demo_segment_end = 5.0
    
    keyboard = st.session_state.keyboard_shortcuts
    interaction = st.session_state.waveform_interaction
    playback = st.session_state.playback_control
    
    # JavaScriptの注入
    inject_keyboard_handler_script()
    
    # サイドバー
    with st.sidebar:
        st.header("🎛️ コントロール")
        
        # キーボードショートカットのヘルプ
        with st.expander("⌨️ キーボードショートカット", expanded=True):
            st.markdown(keyboard.get_help_text())
        
        st.divider()
        
        # インタラクション設定
        st.subheader("🖱️ インタラクション設定")
        interaction.hover_info_enabled = st.checkbox(
            "ホバー情報を表示",
            value=interaction.hover_info_enabled
        )
        interaction.boundary_adjustment_enabled = st.checkbox(
            "境界調整を有効化",
            value=interaction.boundary_adjustment_enabled
        )
        interaction.boundary_threshold = st.slider(
            "境界検出の閾値（秒）",
            min_value=0.05,
            max_value=0.5,
            value=interaction.boundary_threshold,
            step=0.05
        )
    
    # メインコンテンツ
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("📊 インタラクティブ波形表示")
        
        # デモ用の波形データを生成
        waveform_data = create_demo_waveform()
        
        # 波形表示
        display = WaveformDisplay()
        fig = display.render_waveform(
            waveform_data,
            show_time_axis=True
        )
        
        if fig:
            # セグメント境界を追加
            boundaries = [
                st.session_state.demo_segment_start,
                st.session_state.demo_segment_end
            ]
            interaction.add_boundary_markers(fig, boundaries)
            
            # インタラクティブ設定
            config = interaction.create_interactive_waveform_config()
            
            # 波形表示
            selected_points = st.plotly_chart(
                fig,
                use_container_width=True,
                config=config,
                key="demo_waveform",
                on_select="rerun"
            )
            
            # クリックイベントの処理
            if selected_points and "selection" in selected_points:
                st.info("波形がクリックされました！")
                click_result = interaction.process_click_event(
                    selected_points["selection"],
                    waveform_data,
                    boundaries
                )
                
                if click_result:
                    st.json(click_result)
    
    with col2:
        st.header("🎮 再生コントロール")
        
        # 再生コントロール
        playback_state = playback.create_playback_controls()
        
        st.divider()
        
        # セグメント情報
        st.subheader("📍 セグメント情報")
        st.metric(
            "開始時間", 
            f"{st.session_state.demo_segment_start:.2f}秒"
        )
        st.metric(
            "終了時間",
            f"{st.session_state.demo_segment_end:.2f}秒"
        )
        st.metric(
            "長さ",
            f"{st.session_state.demo_segment_end - st.session_state.demo_segment_start:.2f}秒"
        )
    
    st.divider()
    
    # キーボード操作のデモ
    st.header("⌨️ キーボード操作デモ")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("時間調整")
        
        # キーボードハンドラーの登録
        def adjust_demo_start(value: float):
            st.session_state.demo_segment_start += value
            st.session_state.demo_segment_start = max(0, st.session_state.demo_segment_start)
            st.rerun()
        
        def adjust_demo_end(value: float):
            st.session_state.demo_segment_end += value
            st.session_state.demo_segment_end = max(
                st.session_state.demo_segment_start + 0.1,
                st.session_state.demo_segment_end
            )
            st.rerun()
        
        keyboard.register_handler("adjust_start_time", adjust_demo_start)
        keyboard.register_handler("adjust_end_time", adjust_demo_end)
        
        st.info("↑↓キーで開始時間を調整\nShift+↑↓で終了時間を調整")
    
    with col2:
        st.subheader("再生制御")
        
        def toggle_demo_playback():
            playback.is_playing = not playback.is_playing
            st.rerun()
        
        keyboard.register_handler("toggle_playback", toggle_demo_playback)
        
        st.info("Spaceキーで再生/停止")
        
        if playback.is_playing:
            st.success("🎵 再生中...")
        else:
            st.warning("⏸️ 停止中")
    
    with col3:
        st.subheader("セグメント移動")
        
        # デモ用のセグメントリスト
        demo_segments = ["Segment 1", "Segment 2", "Segment 3"]
        
        if "current_segment_idx" not in st.session_state:
            st.session_state.current_segment_idx = 0
        
        def previous_segment():
            if st.session_state.current_segment_idx > 0:
                st.session_state.current_segment_idx -= 1
                st.rerun()
        
        def next_segment():
            if st.session_state.current_segment_idx < len(demo_segments) - 1:
                st.session_state.current_segment_idx += 1
                st.rerun()
        
        keyboard.register_handler("previous_segment", previous_segment)
        keyboard.register_handler("next_segment", next_segment)
        
        st.info("←→キーでセグメント移動")
        st.write(f"現在: **{demo_segments[st.session_state.current_segment_idx]}**")
    
    # インタラクティブ境界調整のデモ
    st.divider()
    st.header("🎯 境界調整デモ")
    
    if st.button("境界調整パネルを表示"):
        with st.container():
            new_time, confirmed = interaction.create_adjustment_panel(
                st.session_state.demo_segment_end,
                st.session_state.demo_segment_start + 0.1,
                10.0
            )
            
            if confirmed:
                st.session_state.demo_segment_end = new_time
                st.success(f"境界を {new_time:.2f}秒 に更新しました")
                st.rerun()


def create_demo_waveform() -> WaveformData:
    """デモ用の波形データを生成"""
    # 5秒間のサンプルデータ
    duration = 5.0
    sample_rate = 44100
    num_samples = 1600  # 表示用にダウンサンプリング
    
    # 複雑な波形を生成（音声 + 無音部分）
    t = np.linspace(0, duration, num_samples)
    
    # 基本周波数
    base_freq = 440  # A4
    
    # 波形生成
    samples = []
    for i, time in enumerate(t):
        if 1.0 <= time <= 1.5 or 3.0 <= time <= 3.3:
            # 無音部分
            sample = 0.01 * np.random.randn()
        else:
            # 音声部分（複数の周波数を合成）
            sample = (
                0.5 * np.sin(2 * np.pi * base_freq * time) +
                0.3 * np.sin(2 * np.pi * base_freq * 2 * time) +
                0.2 * np.sin(2 * np.pi * base_freq * 0.5 * time)
            )
            # エンベロープを適用
            envelope = np.exp(-0.5 * ((time - 2.5) / 2) ** 2)
            sample *= envelope
        
        samples.append(sample)
    
    # 正規化
    samples = np.array(samples)
    max_amp = np.max(np.abs(samples))
    if max_amp > 0:
        samples = samples / max_amp
    
    return WaveformData(
        segment_id="demo",
        sample_rate=sample_rate,
        samples=samples.tolist(),
        duration=duration,
        start_time=0.0,
        end_time=duration
    )


if __name__ == "__main__":
    main()