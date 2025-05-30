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
        # Docker版：フルパス指定のみ
        st.info("🔗 ホスト側の動画ファイルパスを指定してください")
        
        # 前回のパスを設定から取得
        last_path = settings_manager.get('last_video_path', '')
        
        video_path = st.text_input(
            "動画ファイルのフルパス",
            value=last_path,
            placeholder="/Users/username/Desktop/video.mp4",
            help="ホスト側のパスを指定してください"
        )
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
        
        if Path(video_path).exists():
            path = Path(video_path)
            
            # 設定に保存
            settings_manager.set('last_video_path', video_path)
            
            # 出力ディレクトリの設定
            if is_docker:
                # Docker版：動画と同じフォルダに出力
                output_dir = path.parent
                st.markdown("### 📂 出力先")
                st.info(f"出力先: 動画と同じフォルダ（{output_dir}）")
            else:
                # ローカル版：従来の設定
                default_output = path.parent / "output"
                
                # 出力先の設定
                st.markdown("### 📂 出力先の設定")
                
                output_option = st.radio(
                    "出力先の設定",
                    ["🎯 動画と同じフォルダ内の'output'", "📁 カスタムフォルダ"],
                    horizontal=True,
                    index=0,
                    label_visibility="collapsed"
                )
                
                if output_option == "🎯 動画と同じフォルダ内の'output'":
                    output_dir = default_output
                    st.info(f"出力先: {output_dir}")
                else:
                    output_dir = st.text_input(
                        "カスタム出力ディレクトリ",
                        value=str(default_output)
                    )
                    # 引用符を除去
                    output_dir = output_dir.strip().strip('"').strip("'")
                    output_dir = Path(output_dir)
            
            return str(path), str(output_dir)
        else:
            st.error(f"指定されたファイルが見つかりません: {video_path}")
            return None
    
    return None


def cleanup_temp_files():
    """一時ファイルのクリーンアップ（現在は不要だが互換性のため残す）"""
    pass