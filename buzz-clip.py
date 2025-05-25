import streamlit as st
import whisperx
import torch
import json
import os
import re
from pathlib import Path

# Streamlitの設定
st.set_page_config(page_title="Buzz Clip - 動画自動切り抜き", page_icon="🎙️")

st.title("Buzz Clip - 動画自動切り抜き")

# セッション状態の初期化
if 'keep_segments' not in st.session_state:
    st.session_state.keep_segments = []
if 'transcription_result' not in st.session_state:
    st.session_state.transcription_result = None

def get_video_files():
    """videosフォルダ内の動画ファイルを取得"""
    video_dir = Path("videos")
    if not video_dir.exists():
        video_dir.mkdir(exist_ok=True)
    
    video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv']
    video_files = []
    
    for ext in video_extensions:
        video_files.extend(list(video_dir.glob(f"*{ext}")))
    
    return sorted(video_files)

def split_text_into_chars(text, start_time, end_time):
    """テキストを文字単位に分割し、各文字の時間を計算"""
    chars = list(text)
    total_chars = len(chars)
    if total_chars == 0:
        return []
    
    time_per_char = (end_time - start_time) / total_chars
    char_segments = []
    
    for i, char in enumerate(chars):
        char_start = start_time + (i * time_per_char)
        char_end = char_start + time_per_char
        char_segments.append({
            'text': char,
            'start': char_start,
            'end': char_end
        })
    
    return char_segments

def add_to_keep_segments(char_seg):
    """KEEPセグメントに追加"""
    if char_seg not in st.session_state.keep_segments:
        st.session_state.keep_segments.append(char_seg)

def remove_from_keep_segments(index):
    """KEEPセグメントから削除"""
    st.session_state.keep_segments.pop(index)

def find_matching_segments(selected_text, transcription_result):
    """選択されたテキストに一致するセグメントを探す"""
    if not selected_text or not transcription_result:
        return []
    
    matching_segments = []
    for seg in transcription_result["segments"]:
        if selected_text in seg['text']:
            char_segments = split_text_into_chars(seg['text'], seg['start'], seg['end'])
            start_idx = seg['text'].find(selected_text)
            end_idx = start_idx + len(selected_text)
            
            # 選択されたテキストに対応する文字セグメントを抽出
            selected_segments = char_segments[start_idx:end_idx]
            matching_segments.extend(selected_segments)
    
    return matching_segments

# 動画ファイル選択
video_files = get_video_files()
if video_files:
    video_path = st.selectbox(
        "動画ファイルを選択",
        options=video_files,
        format_func=lambda x: x.name,
        help="videosフォルダ内の動画ファイルから選択してください"
    )
    video_path = str(video_path)
else:
    st.warning("videosフォルダに動画ファイルがありません。動画ファイルを追加してください。")
    video_path = None

if video_path:
    try:
        # パスを正規化
        video_path = os.path.abspath(os.path.expanduser(video_path))
        
        if os.path.exists(video_path):
            # モデル選択
            model_size = st.selectbox(
                "Whisperモデルサイズ",
                ["large-v3", "medium", "small", "base"],
                index=0,
                help="大きいモデルほど精度が高いですが、処理時間が長くなります"
            )
            
            # デバイス表示
            device = "cuda" if torch.cuda.is_available() else "cpu"
            st.info(f"使用デバイス: {device}")
            
            if st.button("文字起こし実行"):
                with st.spinner("文字起こし中...（数分かかる場合があります）"):
                    # 文字起こし本体
                    audio = whisperx.load_audio(video_path)
                    asr_model = whisperx.load_model(model_size, device, compute_type="float32")
                    result = asr_model.transcribe(audio, batch_size=16, language="ja")
                    
                    # 結果をセッション状態に保存
                    st.session_state.transcription_result = result
                    st.success("文字起こし完了！")

            # 文字起こし結果が存在する場合のみ表示
            if st.session_state.transcription_result:
                # 2カラムレイアウト
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.subheader("文字起こし結果")
                    # 全テキストを表示
                    full_text = ""
                    for seg in st.session_state.transcription_result["segments"]:
                        full_text += f"[{seg['start']:.1f}s] {seg['text']}\n"
                    
                    # テキストエリアで表示（選択可能）
                    st.text_area(
                        "文字起こしテキスト",
                        value=full_text,
                        height=400,
                        help="テキストをコピーして下の入力欄に貼り付けてください"
                    )
                    
                    # テキスト入力欄
                    selected_text = st.text_input(
                        "KEEPに追加するテキスト",
                        help="文字起こしテキストからコピーしたテキストを貼り付けてください"
                    )
                    
                    if st.button("選択テキストをKEEPに追加"):
                        if selected_text:
                            matching_segments = find_matching_segments(
                                selected_text,
                                st.session_state.transcription_result
                            )
                            if matching_segments:
                                for seg in matching_segments:
                                    add_to_keep_segments(seg)
                                st.success(f"選択されたテキストをKEEPリストに追加しました")
                            else:
                                st.error("選択されたテキストに一致するセグメントが見つかりませんでした")
                        else:
                            st.warning("テキストを入力してください")
                
                with col2:
                    st.subheader("KEEPリスト")
                    # 開始時間でソート
                    sorted_segments = sorted(st.session_state.keep_segments, key=lambda x: x['start'])
                    
                    for i, seg in enumerate(sorted_segments):
                        col = st.columns([3, 1])
                        with col[0]:
                            st.write(f"{seg['start']:.1f}s: {seg['text']}")
                        with col[1]:
                            if st.button("削除", key=f"del_{i}"):
                                remove_from_keep_segments(i)
                    
                    # 連続した文字を結合して表示
                    if sorted_segments:
                        st.subheader("結合テキスト")
                        combined_text = ""
                        for seg in sorted_segments:
                            combined_text += seg['text']
                        st.write(combined_text)
        else:
            st.error(f"ファイルが見つかりません: {video_path}")
    except Exception as e:
        st.error(f"エラー: {str(e)}")
