import streamlit as st
from typing import Dict, List, Optional, Tuple
from core.timeline import Timeline
import json
import os
from datetime import datetime


class TimelinePresets:
    """タイムライン設定のプリセット管理"""
    
    # デフォルトプリセット
    DEFAULT_PRESETS = {
        "自然な会話": {
            "description": "会話の流れを重視した設定",
            "gap_before": 0.3,
            "gap_after": 0.3
        },
        "プレゼンテーション": {
            "description": "スライド切り替えなどに適した設定",
            "gap_before": 0.5,
            "gap_after": 0.5
        },
        "Vlog": {
            "description": "テンポの良い動画向け",
            "gap_before": 0.1,
            "gap_after": 0.1
        },
        "ドキュメンタリー": {
            "description": "じっくりと見せる設定",
            "gap_before": 0.7,
            "gap_after": 0.7
        }
    }
    
    def __init__(self, presets_file: str = "timeline_presets.json"):
        """
        Args:
            presets_file: プリセットを保存するファイルパス
        """
        self.presets_file = presets_file
        self.custom_presets = self.load_custom_presets()
    
    def load_custom_presets(self) -> Dict:
        """カスタムプリセットを読み込む"""
        if os.path.exists(self.presets_file):
            try:
                with open(self.presets_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def save_custom_presets(self):
        """カスタムプリセットを保存"""
        try:
            with open(self.presets_file, 'w', encoding='utf-8') as f:
                json.dump(self.custom_presets, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.error(f"プリセットの保存に失敗しました: {e}")
    
    def add_custom_preset(self, name: str, description: str, gap_before: float, gap_after: float):
        """カスタムプリセットを追加"""
        self.custom_presets[name] = {
            "description": description,
            "gap_before": gap_before,
            "gap_after": gap_after,
            "created_at": datetime.now().isoformat()
        }
        self.save_custom_presets()
    
    def delete_custom_preset(self, name: str):
        """カスタムプリセットを削除"""
        if name in self.custom_presets:
            del self.custom_presets[name]
            self.save_custom_presets()
    
    def get_all_presets(self) -> Dict:
        """すべてのプリセットを取得"""
        all_presets = {}
        all_presets.update(self.DEFAULT_PRESETS)
        all_presets.update(self.custom_presets)
        return all_presets
    
    def apply_preset(self, timeline: Timeline, preset_name: str):
        """プリセットをタイムラインに適用"""
        presets = self.get_all_presets()
        if preset_name in presets:
            preset = presets[preset_name]
            for segment in timeline.segments:
                segment.gap_before = preset["gap_before"]
                segment.gap_after = preset["gap_after"]


def calculate_dynamic_gap_limit(
    segment_index: int,
    timeline: Timeline,
    video_duration: float,
    gap_type: str = "before"
) -> float:
    """
    セグメントの位置と周囲の状況に基づいて動的にギャップの最大値を計算
    
    Args:
        segment_index: セグメントのインデックス
        timeline: タイムラインオブジェクト
        video_duration: 動画の総時間
        gap_type: "before" または "after"
        
    Returns:
        ギャップの最大値（秒）
    """
    segment = timeline.segments[segment_index]
    
    if gap_type == "before":
        # 前のギャップの最大値を計算
        if segment_index == 0:
            # 最初のセグメントの場合は開始時刻まで
            return min(2.0, segment.start_time)
        else:
            # 前のセグメントとの間隔
            prev_segment = timeline.segments[segment_index - 1]
            available_gap = segment.start_time - prev_segment.end_time
            return min(2.0, available_gap * 0.8)  # 80%まで使用可能
    else:
        # 後のギャップの最大値を計算
        if segment_index == len(timeline.segments) - 1:
            # 最後のセグメントの場合は動画の終わりまで
            available_gap = video_duration - segment.end_time
            return min(2.0, available_gap * 0.8)
        else:
            # 次のセグメントとの間隔
            next_segment = timeline.segments[segment_index + 1]
            available_gap = next_segment.start_time - segment.end_time
            return min(2.0, available_gap * 0.8)


def render_advanced_settings(timeline: Timeline, video_duration: float, key_prefix: str = "") -> Timeline:
    """
    タイムラインの高度な設定UIをレンダリング
    
    Args:
        timeline: 編集対象のタイムライン
        video_duration: 元動画の総時間
        key_prefix: StreamlitのキーのプレフィックスKey prefix for avoiding conflicts
        
    Returns:
        編集後のタイムライン
    """
    with st.expander("⚙️ 高度な設定", expanded=False):
        tab1, tab2, tab3 = st.tabs(["プリセット", "動的ギャップ制限", "キーボードショートカット"])
        
        # プリセットタブ
        with tab1:
            presets = TimelinePresets()
            all_presets = presets.get_all_presets()
            
            # プリセット選択と適用
            col1, col2 = st.columns([3, 1])
            with col1:
                selected_preset = st.selectbox(
                    "プリセットを選択",
                    options=["なし"] + list(all_presets.keys()),
                    key=f"{key_prefix}_preset_select"
                )
            
            with col2:
                if st.button("適用", key=f"{key_prefix}_apply_preset"):
                    if selected_preset != "なし":
                        presets.apply_preset(timeline, selected_preset)
                        st.success(f"プリセット「{selected_preset}」を適用しました")
                        st.rerun()
            
            # プリセットの詳細表示
            if selected_preset != "なし" and selected_preset in all_presets:
                preset = all_presets[selected_preset]
                st.info(f"📝 {preset['description']}")
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("前のギャップ", f"{preset['gap_before']} 秒")
                with col2:
                    st.metric("後のギャップ", f"{preset['gap_after']} 秒")
            
            # カスタムプリセットの作成
            st.divider()
            st.write("### カスタムプリセットの作成")
            
            with st.form(key=f"{key_prefix}_custom_preset_form"):
                preset_name = st.text_input("プリセット名")
                preset_desc = st.text_input("説明")
                col1, col2 = st.columns(2)
                with col1:
                    preset_gap_before = st.number_input("前のギャップ（秒）", 0.0, 2.0, 0.3, 0.1)
                with col2:
                    preset_gap_after = st.number_input("後のギャップ（秒）", 0.0, 2.0, 0.3, 0.1)
                
                if st.form_submit_button("プリセットを保存"):
                    if preset_name and preset_desc:
                        presets.add_custom_preset(
                            preset_name, preset_desc,
                            preset_gap_before, preset_gap_after
                        )
                        st.success(f"プリセット「{preset_name}」を保存しました")
                        st.rerun()
                    else:
                        st.error("プリセット名と説明を入力してください")
        
        # 動的ギャップ制限タブ
        with tab2:
            use_dynamic_limits = st.checkbox(
                "動的ギャップ制限を有効にする",
                value=True,
                key=f"{key_prefix}_use_dynamic_limits",
                help="セグメント間の利用可能な時間に基づいてギャップの最大値を自動調整します"
            )
            
            if use_dynamic_limits:
                st.info("✨ 動的ギャップ制限が有効です。各セグメントのギャップ最大値が自動的に調整されます。")
                
                # 制限の詳細表示
                with st.expander("制限の詳細を表示", expanded=False):
                    for i, segment in enumerate(timeline.segments):
                        max_before = calculate_dynamic_gap_limit(i, timeline, video_duration, "before")
                        max_after = calculate_dynamic_gap_limit(i, timeline, video_duration, "after")
                        
                        st.write(f"**セグメント {i + 1}**")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("前の最大ギャップ", f"{max_before:.2f} 秒")
                        with col2:
                            st.metric("後の最大ギャップ", f"{max_after:.2f} 秒")
        
        # キーボードショートカットタブ
        with tab3:
            st.write("### ⌨️ キーボードショートカット")
            st.info("""
            以下のショートカットが使用できます：
            
            - **Ctrl + R**: すべてのギャップをリセット
            - **Ctrl + A**: 一括設定を適用
            - **Ctrl + P**: プレビューを再生
            - **↑/↓**: セグメント間を移動
            - **←/→**: ギャップ値を0.1秒単位で調整
            """)
            
            # ショートカットヘルプの表示設定
            show_shortcuts = st.checkbox(
                "ショートカットヘルプを常に表示",
                value=False,
                key=f"{key_prefix}_show_shortcuts"
            )
            
            if show_shortcuts:
                st.session_state[f"{key_prefix}_show_shortcuts_help"] = True
    
    return timeline, use_dynamic_limits if 'use_dynamic_limits' in locals() else False


def apply_dynamic_limits_to_sliders(
    timeline: Timeline,
    video_duration: float,
    segment_index: int,
    key_prefix: str = ""
) -> Tuple[float, float]:
    """
    動的制限を適用したスライダーの最大値を返す
    
    Returns:
        (前のギャップ最大値, 後のギャップ最大値)
    """
    max_before = calculate_dynamic_gap_limit(segment_index, timeline, video_duration, "before")
    max_after = calculate_dynamic_gap_limit(segment_index, timeline, video_duration, "after")
    
    return max_before, max_after