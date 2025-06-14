"""
Docker専用ファイル選択UIコンポーネント
"""
import streamlit as st
from pathlib import Path
from typing import Optional, Tuple
import os

from utils.environment import VIDEOS_DIR, DEFAULT_HOST_PATH


def show_video_input() -> Optional[Tuple[str, str]]:
    """
    Docker専用動画選択UI
    
    Returns:
        (動画ファイルパス, 出力ディレクトリパス) のタプル
    """
    st.markdown("### 🎬 動画ファイルの選択")
    
    # Dockerコンテナ内の固定パス
    videos_dir = Path(VIDEOS_DIR)
    
    # ホスト側のパス（表示用）
    host_videos_path = os.getenv('HOST_VIDEOS_PATH', DEFAULT_HOST_PATH)
    
    if videos_dir.exists():
        # 動画ファイル一覧を取得
        video_files = []
        for ext in ["*.mp4", "*.mov", "*.avi", "*.mkv", "*.webm"]:
            video_files.extend([f.name for f in videos_dir.glob(ext) if f.is_file()])
        video_files = sorted(video_files)
        
        # 動画選択UI
        col1, col2 = st.columns([4, 1])
        with col1:
            selected_file = st.selectbox(
                "編集する動画を選択してください",
                [""] + video_files if video_files else ["（動画ファイルがありません）"],
                disabled=not video_files
            )
        with col2:
            st.markdown("<div style='margin-top: 1.875rem;'></div>", unsafe_allow_html=True)
            if st.button("🔄 更新", help="ファイルリストを更新", use_container_width=True):
                st.rerun()
        
        # 動画フォルダのパスを常に表示
        st.caption("📁 動画フォルダのパス:")
        st.code(host_videos_path, language=None)
        
        if video_files and selected_file:
            # フルパスを返す
            video_path = str(videos_dir / selected_file)
            
            # 動画と同じディレクトリを出力先として返す
            return video_path, str(videos_dir)
    else:
        st.error("videos/フォルダが見つかりません。")
    
    return None


def cleanup_temp_files():
    """一時ファイルのクリーンアップ（互換性のため残す）"""
    pass