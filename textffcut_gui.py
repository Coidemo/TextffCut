#!/usr/bin/env python3
"""
TextffCut GUI版 - Streamlit実装
WhisperXアライメント機能を含む完全版
"""

import streamlit as st
import os
import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.transcription import Transcriber, TranscriptionResult
from core.video import VideoProcessor
from core.export import FCPXMLExporter
from core.text_processor import TextProcessor
from utils.logging import get_logger

logger = get_logger(__name__)

# ページ設定
st.set_page_config(
    page_title="TextffCut - 動画切り抜きツール",
    page_icon="🎬",
    layout="wide"
)

# セッション状態の初期化
if 'transcription_result' not in st.session_state:
    st.session_state.transcription_result = None
if 'time_ranges' not in st.session_state:
    st.session_state.time_ranges = None

def main():
    """メインアプリケーション"""
    st.title("🎬 TextffCut - 動画切り抜きツール")
    st.markdown("文字起こし・アライメント・切り抜きを統合した動画編集支援ツール")
    
    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # モデル設定
        model_size = st.selectbox(
            "Whisperモデル",
            ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
            index=4  # large
        )
        
        language = st.selectbox(
            "言語",
            ["ja", "en", "zh", "ko"],
            format_func=lambda x: {"ja": "日本語", "en": "英語", "zh": "中国語", "ko": "韓国語"}[x]
        )
        
        # 無音検出設定
        st.subheader("🔇 無音検出")
        remove_silence = st.checkbox("無音部分を削除", value=True)
        
        threshold = st.slider(
            "無音閾値 (dB)",
            min_value=-60,
            max_value=-20,
            value=-35,
            step=1
        )
        
        min_silence = st.slider(
            "最小無音時間 (秒)",
            min_value=0.1,
            max_value=2.0,
            value=0.3,
            step=0.1
        )
        
        # テキスト差分設定
        st.subheader("📝 テキスト差分")
        context_length = st.slider(
            "コンテキスト長",
            min_value=5,
            max_value=50,
            value=10,
            step=5
        )
    
    # メインエリア
    tabs = st.tabs(["📹 動画選択", "🎤 文字起こし", "📝 テキスト編集", "✂️ 切り抜き", "📊 結果"])
    
    with tabs[0]:
        st.header("動画ファイルの選択")
        
        # ファイルアップロード
        uploaded_file = st.file_uploader(
            "動画ファイルを選択",
            type=["mp4", "avi", "mov", "mkv", "webm"]
        )
        
        if uploaded_file:
            # 一時ファイルに保存
            temp_path = Path(tempfile.mkdtemp()) / uploaded_file.name
            with open(temp_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            
            st.session_state.video_path = str(temp_path)
            st.success(f"✅ ファイルをアップロード: {uploaded_file.name}")
            
            # 動画情報を表示
            try:
                processor = VideoProcessor()
                info = processor.get_video_info(st.session_state.video_path)
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("長さ", f"{int(info.duration)}秒")
                with col2:
                    st.metric("解像度", f"{info.width}x{info.height}")
                with col3:
                    st.metric("FPS", f"{info.fps:.1f}")
                with col4:
                    st.metric("コーデック", info.codec)
            except Exception as e:
                st.error(f"動画情報の取得に失敗: {str(e)}")
    
    with tabs[1]:
        st.header("文字起こし実行")
        
        if 'video_path' not in st.session_state:
            st.warning("先に動画ファイルを選択してください")
        else:
            if st.button("🎤 文字起こし開始", type="primary"):
                with st.spinner("文字起こし中..."):
                    try:
                        transcriber = Transcriber()
                        
                        # プログレスバー
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        
                        def progress_callback(message, progress=None):
                            status_text.text(message)
                            if progress is not None:
                                progress_bar.progress(progress)
                        
                        # 文字起こし実行
                        result = transcriber.transcribe(
                            st.session_state.video_path,
                            model_size=model_size,
                            language=language,
                            align=True,
                            progress_callback=progress_callback
                        )
                        
                        st.session_state.transcription_result = result
                        st.session_state.original_text = result.get_full_text()
                        
                        st.success(f"✅ 文字起こし完了！ セグメント数: {len(result.segments)}")
                        
                        # 結果を表示
                        with st.expander("文字起こし結果", expanded=True):
                            for i, seg in enumerate(result.segments[:10]):
                                st.write(f"{i+1}. [{seg.start:.2f}s - {seg.end:.2f}s] {seg.text}")
                            if len(result.segments) > 10:
                                st.write(f"... 他 {len(result.segments)-10} セグメント")
                        
                    except Exception as e:
                        st.error(f"文字起こしエラー: {str(e)}")
    
    with tabs[2]:
        st.header("テキスト編集")
        
        if st.session_state.transcription_result is None:
            st.warning("先に文字起こしを実行してください")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("オリジナルテキスト")
                original_text = st.text_area(
                    "文字起こし結果",
                    value=st.session_state.get('original_text', ''),
                    height=400,
                    key="original_text_area"
                )
            
            with col2:
                st.subheader("編集後テキスト")
                target_text = st.text_area(
                    "編集してください",
                    value=st.session_state.get('original_text', ''),
                    height=400,
                    key="target_text_area"
                )
            
            if st.button("🔍 差分検出", type="primary"):
                if original_text and target_text:
                    with st.spinner("差分を検出中..."):
                        try:
                            processor = TextProcessor()
                            differences = processor.find_differences(
                                st.session_state.transcription_result,
                                original_text,
                                target_text,
                                context_length=context_length
                            )
                            
                            # 時間範囲を計算
                            time_ranges = []
                            for diff in differences:
                                time_ranges.extend(diff.time_ranges)
                            
                            # 重複を除去
                            from textffcut_full import merge_time_ranges
                            st.session_state.time_ranges = merge_time_ranges(time_ranges)
                            
                            st.success(f"✅ 差分検出完了！ {len(differences)}箇所の変更を検出")
                            
                            # 差分を表示
                            with st.expander("検出された差分", expanded=True):
                                for i, diff in enumerate(differences[:5]):
                                    st.write(f"{i+1}. 位置: {diff.position}")
                                    st.write(f"   範囲: {diff.time_ranges}")
                                    st.write(f"   テキスト: {diff.changed_text[:50]}...")
                                if len(differences) > 5:
                                    st.write(f"... 他 {len(differences)-5} 箇所")
                            
                        except Exception as e:
                            st.error(f"差分検出エラー: {str(e)}")
    
    with tabs[3]:
        st.header("切り抜き設定")
        
        if st.session_state.time_ranges is None:
            st.warning("先にテキスト差分を検出してください")
        else:
            # 検出された範囲を表示
            total_duration = sum(end - start for start, end in st.session_state.time_ranges)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("検出セグメント数", len(st.session_state.time_ranges))
            with col2:
                st.metric("合計時間", f"{int(total_duration)}秒")
            
            # 時間範囲のプレビュー
            with st.expander("時間範囲", expanded=True):
                for i, (start, end) in enumerate(st.session_state.time_ranges[:10]):
                    st.write(f"{i+1}. {start:.2f}s - {end:.2f}s ({end-start:.2f}s)")
                if len(st.session_state.time_ranges) > 10:
                    st.write(f"... 他 {len(st.session_state.time_ranges)-10} セグメント")
            
            # エクスポート設定
            output_format = st.selectbox(
                "出力形式",
                ["FCPXML", "EDL"],
                help="編集ソフトウェアに合わせて選択"
            )
            
            if st.button("📤 エクスポート", type="primary"):
                with st.spinner("エクスポート中..."):
                    try:
                        # 出力ファイル名
                        base_name = Path(st.session_state.video_path).stem
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        output_name = f"{base_name}_edited_{timestamp}"
                        
                        if remove_silence:
                            # 無音削除
                            processor = VideoProcessor()
                            keep_ranges = processor.remove_silence_new(
                                st.session_state.video_path,
                                st.session_state.time_ranges,
                                threshold_db=threshold,
                                min_silence_duration=min_silence
                            )
                        else:
                            keep_ranges = st.session_state.time_ranges
                        
                        # FCPXMLエクスポート
                        if output_format == "FCPXML":
                            output_path = f"{output_name}.fcpxml"
                            exporter = FCPXMLExporter()
                            exporter.export(
                                video_path=st.session_state.video_path,
                                time_ranges=keep_ranges,
                                output_path=output_path,
                                project_name=base_name
                            )
                        
                        st.session_state.output_path = output_path
                        st.session_state.final_ranges = keep_ranges
                        st.success(f"✅ エクスポート完了！")
                        
                    except Exception as e:
                        st.error(f"エクスポートエラー: {str(e)}")
    
    with tabs[4]:
        st.header("処理結果")
        
        if 'output_path' in st.session_state:
            st.success(f"✅ 処理が完了しました！")
            
            # 統計情報
            if 'final_ranges' in st.session_state:
                total = sum(end - start for start, end in st.session_state.final_ranges)
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("最終セグメント数", len(st.session_state.final_ranges))
                with col2:
                    st.metric("合計時間", f"{int(total)}秒")
                with col3:
                    if 'video_path' in st.session_state:
                        processor = VideoProcessor()
                        info = processor.get_video_info(st.session_state.video_path)
                        st.metric("圧縮率", f"{total/info.duration*100:.1f}%")
            
            # ダウンロードボタン
            if os.path.exists(st.session_state.output_path):
                with open(st.session_state.output_path, 'r') as f:
                    content = f.read()
                
                st.download_button(
                    label="📥 FCPXMLをダウンロード",
                    data=content,
                    file_name=os.path.basename(st.session_state.output_path),
                    mime="text/xml"
                )
        else:
            st.info("処理を実行すると、ここに結果が表示されます")

if __name__ == "__main__":
    main()