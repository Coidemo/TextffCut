"""
ファイルアップロード関連のUIコンポーネント
"""
import streamlit as st
from pathlib import Path
from typing import Optional, Tuple

from utils import logger, settings_manager


def show_video_input() -> Optional[Tuple[str, str]]:
    """
    動画入力UI（フルパス入力）
    
    Returns:
        (動画ファイルパス, 出力ディレクトリパス) のタプル
    """
    st.markdown("### 🎬 動画ファイルの選択")
    
    # Docker環境の判定
    import os
    is_docker = os.path.exists('/.dockerenv')
    
    if is_docker:
        # Docker版：作業フォルダ内の動画を選択
        st.info("📁 videos/フォルダ内の動画ファイルを選択してください")
        
        # videosフォルダ内のファイルを取得
        videos_dir = Path("/app/videos")
        if videos_dir.exists():
            video_files = [f.name for f in videos_dir.glob("*.mp4") if f.is_file()]
            video_files.extend([f.name for f in videos_dir.glob("*.mov") if f.is_file()])
            video_files.extend([f.name for f in videos_dir.glob("*.avi") if f.is_file()])
            video_files = sorted(video_files)
            
            if video_files:
                selected_file = st.selectbox(
                    "動画ファイルを選択",
                    video_files,
                    help="作業フォルダのvideos/内にある動画ファイル"
                )
                video_path = str(videos_dir / selected_file) if selected_file else None
            else:
                st.warning("videos/フォルダに動画ファイルが見つかりません。")
                st.info("動画ファイルを作業フォルダの videos/ ディレクトリに配置してください。")
                video_path = None
        else:
            st.error("videos/フォルダが見つかりません。")
            video_path = None
    else:
        # ローカル版：従来のパス入力
        # 前回のパスを設定から取得
        last_path = settings_manager.get('last_video_path', '')
        
        video_path = st.text_input(
            "動画ファイルのフルパス",
            value=last_path,
            placeholder="/Users/username/Desktop/video.mp4"
        )
    
    # 引用符を除去
    if video_path:
        video_path = video_path.strip().strip('"').strip("'")
    
    if video_path:
        # パスの長さチェック（異常に長い場合は警告）
        if len(video_path) > 1000:
            st.error("入力されたパスが長すぎます。正しいファイルパスを入力してください。")
            return None
        
        # Docker環境でのパス変換
        container_video_path = video_path
        if is_docker and video_path.startswith('/Users/'):
            # ホストパスをコンテナパスに変換
            # /Users/username/... → /host/...
            # より単純な置換ロジックを使用
            username = video_path.split('/')[2]  # 'naoki'
            container_video_path = video_path.replace(f'/Users/{username}', '/host', 1)
            logger.info(f"パス変換: {video_path} → {container_video_path}")
        
        # 存在確認用のパス
        check_path = container_video_path if is_docker else video_path
        
        if Path(check_path).exists():
            path = Path(video_path)
            
            # 設定に保存（ホストパスを保存）
            settings_manager.set('last_video_path', video_path)
            
            # 出力ディレクトリの設定
            if is_docker:
                # Docker版：videosフォルダに出力
                output_dir = Path("/app/videos")
            else:
                # ローカル版：動画と同じ場所に直接出力
                # outputディレクトリは使用しない（動画と同じ場所に直接作成）
                output_dir = path.parent
            
            # Docker環境では変換後のパスを返す
            return_path = container_video_path if is_docker else str(path)
            return return_path, str(output_dir)
        else:
            st.error(f"指定されたファイルが見つかりません: {video_path}")
            return None
    
    return None


def cleanup_temp_files():
    """一時ファイルのクリーンアップ（現在は不要だが互換性のため残す）"""
    pass