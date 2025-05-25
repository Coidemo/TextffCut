import streamlit as st
import whisperx
import torch
import json
import os
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from typing import List, Dict, Set, Tuple, Optional, Any

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

def normalize_text(text: str) -> str:
    """テキストを正規化（空白の統一など）"""
    # 全角スペースを半角に変換
    text = text.replace('　', ' ')
    # 連続する空白を1つに
    text = re.sub(r'\s+', ' ', text)
    # 前後の空白を削除
    return text.strip()

def remove_spaces(text: str) -> str:
    """テキストから空白を除去"""
    return re.sub(r'\s+', '', text)

def get_word_positions(text: str) -> List[Tuple[int, int, str]]:
    """テキスト内の各単語の位置を取得"""
    positions = []
    current_pos = 0
    words = text.split()
    
    for word in words:
        pos = text.find(word, current_pos)
        if pos != -1:
            positions.append((pos, pos + len(word), word))
            current_pos = pos + len(word)
    
    return positions

def find_text_positions(original_text: str, edited_text: str) -> List[tuple[int, int, str]]:
    """
    編集後のテキストが元のテキストのどの部分から来ているかを特定
    
    Returns:
        List[tuple[int, int, str]]: [(開始位置, 終了位置, テキスト), ...]
    """
    positions = []
    
    # テキストを正規化
    original_text = normalize_text(original_text)
    edited_text = normalize_text(edited_text)
    
    # 空白を除去したテキストを準備
    original_no_spaces = remove_spaces(original_text)
    edited_no_spaces = remove_spaces(edited_text)
    
    # 編集後のテキストを文字単位で分割
    edited_chars = list(edited_no_spaces)
    
    # 連続した文字のグループを作成
    char_groups = []
    current_group = []
    
    for char in edited_chars:
        current_group.append(char)
        # 区切り文字で終わる文字の場合、グループを確定
        if any(char in ['。', '、', '！', '？', '．', '，']):
            char_groups.append(''.join(current_group))
            current_group = []
    
    # 残りの文字をグループに追加
    if current_group:
        char_groups.append(''.join(current_group))
    
    # 各グループを検索
    current_pos = 0
    for group in char_groups:
        # グループ全体を検索
        group_pos = original_no_spaces.find(group, current_pos)
        if group_pos != -1:
            # 元のテキストでの位置を計算
            original_pos = 0
            no_spaces_pos = 0
            while no_spaces_pos < group_pos:
                if not original_text[original_pos].isspace():
                    no_spaces_pos += 1
                original_pos += 1
            
            # グループの長さを計算（空白を考慮）
            group_length = 0
            for char in group:
                while original_pos + group_length < len(original_text) and original_text[original_pos + group_length].isspace():
                    group_length += 1
                group_length += 1
            
            positions.append((original_pos, original_pos + group_length, group))
            current_pos = group_pos + len(group)
    
    # 位置でソート
    positions.sort(key=lambda x: x[0])
    
    # 重複を除去（同じ位置の場合は長い方を残す）
    unique_positions = []
    for pos in positions:
        if not unique_positions or pos[0] > unique_positions[-1][1]:
            unique_positions.append(pos)
        elif pos[1] - pos[0] > unique_positions[-1][1] - unique_positions[-1][0]:
            unique_positions[-1] = pos
    
    return unique_positions

def highlight_differences(original_text: str, edited_text: str) -> tuple[str, List[tuple[int, int, str]], Set[str]]:
    """difffのような差分表示を生成"""
    # テキストを正規化
    original_text = normalize_text(original_text)
    edited_text = normalize_text(edited_text)
    
    # 空白を除去したテキストで差分を計算
    original_no_spaces = remove_spaces(original_text)
    edited_no_spaces = remove_spaces(edited_text)
    
    # 差分を計算
    matcher = SequenceMatcher(None, original_no_spaces, edited_no_spaces)
    highlighted_text = ""
    common_positions = []
    new_words = set()
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # 元のテキストでの位置を計算
            original_pos = 0
            no_spaces_pos = 0
            while no_spaces_pos < i1:
                if not original_text[original_pos].isspace():
                    no_spaces_pos += 1
                original_pos += 1
            
            # 長さを計算（空白を考慮）
            length = 0
            no_spaces_count = 0
            while no_spaces_count < (i2 - i1):
                if not original_text[original_pos + length].isspace():
                    no_spaces_count += 1
                length += 1
            
            highlighted_text += f"<span style='background-color: #fff9c4;'>{original_text[original_pos:original_pos+length]}</span>"
            common_positions.append((original_pos, original_pos + length, original_text[original_pos:original_pos+length]))
        elif tag == 'delete':
            highlighted_text += original_text[i1:i2]
        elif tag == 'insert':
            highlighted_text += f"<span style='background-color: #ffcdd2;'>{edited_text[j1:j2]}</span>"
            # 追加された部分の文字を収集（スペースを除く）
            new_words.update(c for c in edited_text[j1:j2] if not c.isspace())
        elif tag == 'replace':
            highlighted_text += original_text[i1:i2]
            highlighted_text += f"<span style='background-color: #ffcdd2;'>{edited_text[j1:j2]}</span>"
            # 置換された部分の文字を収集（スペースを除く）
            new_words.update(c for c in edited_text[j1:j2] if not c.isspace())
    
    return highlighted_text, common_positions, new_words

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
        tab1 = st.tabs(["✏️ テキスト編集"])[0]
        
        # 純粋なテキストを取得
        full_text = ""
        for seg in st.session_state.transcription_result["segments"]:
            if 'words' in seg:
                text = "".join(word['word'] for word in seg['words'])
            else:
                text = seg['text']
            full_text += text
        full_text = full_text.strip()
        
        with tab1:
            # テキスト編集機能
            st.subheader("テキスト編集")
            
            # 2カラムレイアウト
            col1, col2 = st.columns(2)
            
            # 変数の初期化
            common_positions = []
            new_words = set()
            
            with col1:
                st.markdown("#### 元のテキスト（差分表示）")
                # 編集用テキストエリアの値を取得
                edited_text = st.session_state.get('edited_text', '')
                
                # 差分表示を生成
                if edited_text:
                    highlighted_diff, common_positions, new_words = highlight_differences(full_text, edited_text)
                    st.markdown(highlighted_diff, unsafe_allow_html=True)
                    
                    # 新しい単語のエラー表示
                    if new_words:
                        st.error(f"以下の単語は元のテキストに存在しません（タイムスタンプと紐づけられません）：\n{', '.join(new_words)}")
                else:
                    st.markdown(full_text)
            
            with col2:
                st.markdown("#### 編集後のテキスト")
                
                # 編集用テキストエリア
                edited_text = st.text_area(
                    "テキストを編集してください",
                    value=st.session_state.get('edited_text', ''),
                    height=400,
                    help="元のテキストを編集してください。追加した部分は赤、共通部分は黄色で表示されます。"
                )
                
                # 更新ボタン
                if st.button("更新", type="primary"):
                    st.session_state.edited_text = edited_text
                    st.rerun()
            
            # 共通部分の位置情報を表示
            if edited_text and common_positions:
                with st.expander("共通部分の位置情報"):
                    for start, end, text in common_positions:
                        st.write(f"テキスト: {text}")
                        st.write(f"位置: {start}文字目から{end}文字目")
                        st.write(f"前後の文脈: ...{full_text[max(0, start-10):end+10]}...")
                        st.divider()

if __name__ == "__main__":
    main()
