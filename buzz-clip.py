import streamlit as st
import whisperx
import torch
import json
import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Streamlitの設定
st.set_page_config(
    page_title="Buzz Clip - 文字起こし", 
    page_icon="🎙️",
    layout="wide"
)

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

def get_transcription_path(video_path, model_size):
    """文字起こし結果の保存パスを取得"""
    video_name = Path(video_path).stem
    return f"transcriptions/{video_name}_{model_size}.json"

def save_transcription(result, save_path):
    """文字起こし結果を保存"""
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

def load_transcription(save_path):
    """文字起こし結果を読み込み"""
    if os.path.exists(save_path):
        with open(save_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def transcribe_chunk(chunk, asr_model):
    """チャンク単位の文字起こし"""
    res = asr_model.transcribe(
        chunk["array"],
        batch_size=16,
        language="ja"
    )
    for seg in res["segments"]:
        seg["start"] += chunk["start"]
        seg["end"] += chunk["start"]
    return res["segments"], chunk["duration"]

def transcribe_audio(video_path, model_size, device):
    """音声の文字起こしとアライメント処理"""
    try:
        # 音声の読み込み
        audio = whisperx.load_audio(video_path)
        
        # 文字起こしモデルの読み込み
        asr_model = whisperx.load_model(
            model_size,
            device,
            compute_type="int8",
            language="ja"
        )
        
        # チャンク分割の設定
        CHUNK_SEC = 30
        SR = 16000
        NUM_WORKERS = os.cpu_count() // 2 or 4
        
        # チャンクの作成
        step = CHUNK_SEC * SR
        chunks = [
            {
                "array": audio[i:i+step],
                "start": i / SR,
                "duration": min(step, len(audio)-i) / SR
            }
            for i in range(0, len(audio), step)
        ]
        
        # 並列処理で文字起こし
        segments_all = []
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as exe:
            futures = [exe.submit(transcribe_chunk, ch, asr_model) for ch in chunks]
            for fut in as_completed(futures):
                segs, _ = fut.result()
                segments_all.extend(segs)
        
        # 結果を整形
        asr_result = {
            "language": "ja",
            "segments": sorted(segments_all, key=lambda x: x["start"])
        }
        
        # アライメント処理
        try:
            align_model, meta = whisperx.load_align_model("ja", device=device)
            aligned_result = whisperx.align(
                asr_result["segments"],
                align_model,
                meta,
                audio,
                device,
                return_char_alignments=True
            )
            
            return {
                "language": "ja",
                "segments": aligned_result["segments"]
            }
            
        except Exception as align_error:
            st.warning(f"アライメント処理に失敗しましたが、文字起こしは完了しています: {str(align_error)}")
            return asr_result
        
    except Exception as e:
        st.error(f"文字起こし中にエラーが発生しました: {str(e)}")
        return None

def main():
    st.title("🎙️ Buzz Clip - 文字起こし")
    
    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # モデル選択
        model_size = st.selectbox(
            "Whisperモデル",
            ["large-v3", "medium", "small", "base"],
            index=1,  # mediumをデフォルトに
            help="large-v3: 最高精度（メモリ使用量大）\nmedium: バランスが良い\nsmall/base: 軽量"
        )
        
        # デバイス情報
        device = "cuda" if torch.cuda.is_available() else "cpu"
        st.info(f"🖥️ デバイス: {device}")
        
        # メモリ使用量の警告
        if model_size == "large-v3" and device == "cpu":
            st.warning("⚠️ large-v3モデルはCPUで実行すると非常に時間がかかります")

    # 動画ファイル選択
    video_files = get_video_files()
    
    if not video_files:
        st.warning("📁 videosフォルダに動画ファイルがありません。")
        st.info("動画ファイルを以下のフォルダに配置してください: `videos/`")
        return
    
    selected_video = st.selectbox(
        "🎬 動画ファイルを選択",
        options=video_files,
        format_func=lambda x: x.name
    )
    
    video_path = str(selected_video.resolve())
    
    # 文字起こし処理
    st.header("📝 文字起こし")
    
    transcription_path = get_transcription_path(video_path, model_size)
    saved_result = load_transcription(transcription_path)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if saved_result:
            if st.button("💾 保存済み結果を使用", type="primary"):
                st.session_state.transcription_result = saved_result
                st.success("✅ 文字起こし結果を読み込みました！")
                st.rerun()
    
    with col2:
        if st.button("🚀 新しく文字起こし実行"):
            with st.spinner("文字起こし中..."):
                try:
                    # 文字起こしとアライメント処理を実行
                    result = transcribe_audio(video_path, model_size, device)
                    
                    if result:
                        # 結果を保存
                        save_transcription(result, transcription_path)
                        st.session_state.transcription_result = result
                        st.success("✅ 文字起こし完了！")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"❌ エラー: {str(e)}")
    
    # 文字起こし結果の表示
    if 'transcription_result' in st.session_state and st.session_state.transcription_result:
        st.header("📄 文字起こし結果")
        
        # タブで表示形式を切り替え
        tab1, tab2 = st.tabs(["📝 テキスト表示", "⏱️ 時間付き表示"])
        
        with tab1:
            # 純粋なテキスト表示
            full_text = ""
            for seg in st.session_state.transcription_result["segments"]:
                if 'words' in seg:
                    # 単語レベルのアライメントがある場合
                    text = " ".join(word['word'] for word in seg['words'])
                else:
                    # 通常のセグメントの場合
                    text = seg['text']
                full_text += text + " "
            
            # テキストエリアに表示
            st.text_area(
                "文字起こしテキスト",
                value=full_text.strip(),
                height=400,
                help="時間情報を除いた純粋な文字起こし結果です。コピーしてご利用いただけます。"
            )
        
        with tab2:
            # 既存の時間付き表示
            for seg in st.session_state.transcription_result["segments"]:
                with st.container():
                    st.write(f"**{seg['start']:.1f}s - {seg['end']:.1f}s**")
                    
                    # 単語レベルのアライメント情報がある場合は表示
                    if 'words' in seg:
                        text_with_times = ""
                        for word in seg['words']:
                            text_with_times += f"<span title='{word['start']:.1f}s'>{word['word']}</span> "
                        st.markdown(text_with_times, unsafe_allow_html=True)
                    else:
                        st.write(seg['text'])
                    
                    st.divider()

if __name__ == "__main__":
    main()
