import streamlit as st
import whisperx
import torch
import json
import os

# Streamlitの設定
st.set_page_config(page_title="Buzz Clip - 動画自動切り抜き", page_icon="🎙️")

st.title("Buzz Clip - 動画自動切り抜き")

# セッション状態の初期化
if 'keep_segments' not in st.session_state:
    st.session_state.keep_segments = []

# ファイルパス入力
video_path = st.text_input("動画ファイルのパスを入力", placeholder="/path/to/your/video.mp4")

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
                    
                    # 2カラムレイアウト
                    col1, col2 = st.columns([2, 1])
                    
                    with col1:
                        st.subheader("文字起こし結果")
                        for seg in result["segments"]:
                            if st.button(f"KEEP: {seg['start']:.1f} - {seg['end']:.1f} : {seg['text']}", key=f"seg_{seg['start']}"):
                                if seg not in st.session_state.keep_segments:
                                    st.session_state.keep_segments.append(seg)
                                    st.rerun()
                    
                    with col2:
                        st.subheader("KEEPリスト")
                        for i, seg in enumerate(st.session_state.keep_segments):
                            st.write(f"{seg['start']:.1f} - {seg['end']:.1f} : {seg['text']}")
                            if st.button("削除", key=f"del_{i}"):
                                st.session_state.keep_segments.pop(i)
                                st.rerun()
        else:
            st.error(f"ファイルが見つかりません: {video_path}")
    except Exception as e:
        st.error(f"エラー: {str(e)}")
