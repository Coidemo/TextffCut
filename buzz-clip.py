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
import subprocess
from datetime import datetime

# Streamlitの設定
st.set_page_config(
    page_title="Buzz Clip - 文字起こし", 
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded"
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
            
            # 共通部分の色を薄い緑色に変更
            highlighted_text += f"<span style='background-color: #e6ffe6;'>{original_text[original_pos:original_pos+length]}</span>"
            common_positions.append((original_pos, original_pos + length, original_text[original_pos:original_pos+length]))
        elif tag == 'delete':
            highlighted_text += original_text[i1:i2]
        elif tag == 'insert':
            # 追加部分の色を薄い赤色に変更
            highlighted_text += f"<span style='background-color: #ffe6e6;'>{edited_text[j1:j2]}</span>"
            # 追加された部分の文字を収集（スペースを除く）
            new_words.update(c for c in edited_text[j1:j2] if not c.isspace())
        elif tag == 'replace':
            highlighted_text += original_text[i1:i2]
            # 置換部分の色を薄い赤色に変更
            highlighted_text += f"<span style='background-color: #ffe6e6;'>{edited_text[j1:j2]}</span>"
            # 置換された部分の文字を収集（スペースを除く）
            new_words.update(c for c in edited_text[j1:j2] if not c.isspace())
    
    return highlighted_text, common_positions, new_words

def get_timestamp_for_position(segments: List[Dict], start_pos: int, end_pos: int) -> tuple[float, float]:
    """文字位置からタイムスタンプを取得"""
    start_time = None
    end_time = None
    current_pos = 0
    
    for seg in segments:
        if 'words' in seg:
            for word in seg['words']:
                word_len = len(word['word'])
                if start_time is None and current_pos <= start_pos < current_pos + word_len:
                    start_time = word['start']
                if end_time is None and current_pos < end_pos <= current_pos + word_len:
                    end_time = word['end']
                current_pos += word_len
        else:
            text = seg['text']
            if start_time is None and current_pos <= start_pos < current_pos + len(text):
                start_time = seg['start']
            if end_time is None and current_pos < end_pos <= current_pos + len(text):
                end_time = seg['end']
            current_pos += len(text)
        
        # 両方のタイムスタンプが見つかったら終了
        if start_time is not None and end_time is not None:
            break
    
    # タイムスタンプが見つからなかった場合のフォールバック
    if start_time is None:
        start_time = 0.0
    if end_time is None:
        end_time = 0.0
    
    return start_time, end_time

def extract_video_segments(video_path: str, segments: List[tuple[float, float]], output_dir: str):
    """動画から指定されたセグメントを切り出し"""
    try:
        # 出力ディレクトリを作成
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(exist_ok=True)
        
        # 各セグメントを切り出し
        output_files = []
        for i, (start, end) in enumerate(segments):
            output_file = output_dir / f"segment_{i+1}.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(start),
                "-to", str(end),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-b:a", "192k",
                "-avoid_negative_ts", "1",
                str(output_file)
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"FFmpeg error: {result.stderr}")
            output_files.append(str(output_file))
        
        return output_files
        
    except Exception as e:
        # エラーが発生した場合、出力ファイルを削除
        if 'output_files' in locals():
            for file in output_files:
                if Path(file).exists():
                    Path(file).unlink()
        raise e

def remove_fillers_from_video(video_path: str, output_dir: str, segments: List[tuple[float, float]] = None, noise_threshold: float = -35, min_silence_duration: float = 0.3, min_segment_duration: float = 0.3):
    """動画から無音部分を削除"""
    try:
        # 出力ディレクトリを作成
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 共通部分が指定されている場合は、その部分のみを処理
        if segments:
            processed_segments = []
            for i, (start, end) in enumerate(segments):
                # 一時ファイル名を生成
                temp_file = output_dir / f"temp_{i+1}.mp4"
                output_file = output_dir / f"segment_{i+1}.mp4"
                
                try:
                    # 共通部分を切り出し
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(video_path),
                        "-ss", str(start),
                        "-to", str(end),
                        "-c:v", "libx264",
                        "-preset", "ultrafast",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-avoid_negative_ts", "1",
                        str(temp_file)
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise Exception(f"FFmpeg error: {result.stderr}")
                    
                    # 動画の長さを取得
                    cmd = [
                        "ffprobe", "-v", "error",
                        "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1",
                        str(temp_file)
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise Exception(f"FFprobe error: {result.stderr}")
                    video_duration = float(result.stdout.strip())
                    
                    # 無音部分を検出
                    cmd = [
                        "ffmpeg", "-y",
                        "-i", str(temp_file),
                        "-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}",
                        "-f", "null",
                        "-"
                    ]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    # 無音部分の時間を抽出
                    silence_times = []
                    current_start = None
                    for line in result.stderr.split('\n'):
                        if 'silence_start' in line:
                            start = float(line.split('silence_start: ')[1].split(' |')[0])
                            current_start = start
                        elif 'silence_end' in line and current_start is not None:
                            end = float(line.split('silence_end: ')[1].split(' |')[0])
                            silence_times.extend([current_start, end])
                            current_start = None
                    
                    # 無音部分を除外したセグメントを作成
                    filler_segments = []
                    
                    # 無音部分を除外したセグメントを作成
                    if silence_times:
                        # 最初の無音部分より前のセグメント
                        if silence_times[0] > 0:
                            filler_segments.append((0, silence_times[0]))
                        
                        # 無音部分の間のセグメント
                        for j in range(0, len(silence_times)-1, 2):
                            if j + 1 < len(silence_times):
                                silence_start, silence_end = silence_times[j], silence_times[j+1]
                                # 無音部分が短すぎる場合は無視
                                if silence_end - silence_start < min_silence_duration:
                                    continue
                                
                                # 次の無音部分までのセグメント
                                if j + 2 < len(silence_times):
                                    next_silence = silence_times[j+2]
                                    if next_silence - silence_end > 0:
                                        filler_segments.append((silence_end, next_silence))
                        
                        # 最後の無音部分より後のセグメント
                        if silence_times[-1] < video_duration:
                            filler_segments.append((silence_times[-1], video_duration))
                    else:
                        # 無音部分が見つからない場合は全体を1つのセグメントとして扱う
                        filler_segments.append((0, video_duration))
                    
                    # セグメントを切り出し
                    if filler_segments:
                        segment_files = []
                        for j, (seg_start, seg_end) in enumerate(filler_segments):
                            # セグメントの長さをチェック
                            if seg_end - seg_start < 0.1:  # 0.1秒未満のセグメントは無視
                                continue
                                
                            segment_file = output_dir / f"segment_{i+1}_part_{j+1}.mp4"
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", str(temp_file),
                                "-ss", str(seg_start),
                                "-to", str(seg_end),
                                "-c:v", "libx264",
                                "-preset", "ultrafast",
                                "-c:a", "aac",
                                "-b:a", "192k",
                                "-avoid_negative_ts", "1",
                                str(segment_file)
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode != 0:
                                raise Exception(f"FFmpeg error: {result.stderr}")
                            segment_files.append(str(segment_file))
                        
                        # セグメントを結合
                        if len(segment_files) > 1:
                            list_file = output_dir / f"segments_list_{i+1}.txt"
                            with open(list_file, "w") as f:
                                for file in segment_files:
                                    f.write(f"file '{Path(file).resolve()}'\n")
                            
                            cmd = [
                                "ffmpeg", "-y",
                                "-f", "concat",
                                "-safe", "0",
                                "-i", str(list_file),
                                "-c", "copy",
                                str(output_file)
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode != 0:
                                raise Exception(f"FFmpeg error: {result.stderr}")
                            
                            # 一時ファイルを削除
                            for file in segment_files:
                                Path(file).unlink()
                        elif segment_files:
                            # セグメントが1つの場合はそのままコピー
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", segment_files[0],
                                "-c", "copy",
                                str(output_file)
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode != 0:
                                raise Exception(f"FFmpeg error: {result.stderr}")
                            
                            # 一時ファイルを削除
                            Path(segment_files[0]).unlink()
                        else:
                            # 無音部分が見つからない場合は元のセグメントをコピー
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", str(temp_file),
                                "-c", "copy",
                                str(output_file)
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True)
                            if result.returncode != 0:
                                raise Exception(f"FFmpeg error: {result.stderr}")
                    else:
                        # 無音部分が見つからない場合は元のセグメントをコピー
                        cmd = [
                            "ffmpeg", "-y",
                            "-i", str(temp_file),
                            "-c", "copy",
                            str(output_file)
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        if result.returncode != 0:
                            raise Exception(f"FFmpeg error: {result.stderr}")
                    
                    processed_segments.append(str(output_file))
                
                finally:
                    # 一時ファイルを削除
                    if temp_file.exists():
                        temp_file.unlink()
                    # 中間ファイルを削除
                    for file in output_dir.glob(f"segment_{i+1}_part_*.mp4"):
                        file.unlink()
            
            return processed_segments
            
    except Exception as e:
        st.error(f"動画の処理中にエラーが発生しました: {str(e)}")
        return None

def remove_fillers(text: str) -> str:
    """フィラーを削除"""
    # セッション状態からフィラーリストを取得
    fillers = st.session_state.get('fillers', [
        "あの", "その", "えー", "えっと", "まあ", "なんか", "なんとなく",
        "あのー", "そのー", "えーと", "まあまあ", "なんかね", "なんとなくね",
        "あのね", "そのね", "えーね", "えっとね", "まあね"
    ])
    
    # フィラーを削除
    for filler in fillers:
        if filler:  # 空のフィラーは無視
            text = text.replace(filler, "")
    
    # 連続する空白を1つに
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

def main():
    st.title("🎙️ Buzz Clip - 文字起こし")
    
    # サイドバー
    with st.sidebar:
        # タブで設定を整理
        tab1, tab2 = st.tabs(["⚙️ 基本設定", "❓ ヘルプ"])
        
        with tab1:
            st.header("基本設定")
            
            # モデル選択
            model_size = st.selectbox(
                "Whisperモデル",
                ["large-v3", "medium", "small", "base"],
                index=1,
                help="large-v3: 最高精度（メモリ使用量大）\nmedium: バランスが良い\nsmall/base: 軽量"
            )
            
            # デバイス情報
            device = "cuda" if torch.cuda.is_available() else "cpu"
            st.info(f"🖥️ デバイス: {device}")
            
            # メモリ使用量の警告
            if model_size == "large-v3" and device == "cpu":
                st.warning("⚠️ large-v3モデルはCPUで実行すると非常に時間がかかります")
            
            # 無音検出のパラメータ
            st.subheader("無音検出の設定")
            
            # デフォルト値の定義
            DEFAULT_NOISE_THRESHOLD = -35
            DEFAULT_MIN_SILENCE_DURATION = 0.3
            DEFAULT_MIN_SEGMENT_DURATION = 0.3
            
            # デフォルトに戻すボタン
            if st.button("🔧 パラメータをデフォルトに戻す", use_container_width=True):
                st.session_state.noise_threshold = DEFAULT_NOISE_THRESHOLD
                st.session_state.min_silence_duration = DEFAULT_MIN_SILENCE_DURATION
                st.session_state.min_segment_duration = DEFAULT_MIN_SEGMENT_DURATION
                st.rerun()
            
            noise_threshold = st.slider(
                "無音検出の閾値 (dB)",
                min_value=-50,
                max_value=-20,
                value=st.session_state.get('noise_threshold', DEFAULT_NOISE_THRESHOLD),
                step=1,
                help="無音と判定する音量の閾値。値が小さいほど厳密に検出します。",
                key="extract_noise_threshold"
            )
            st.session_state.noise_threshold = noise_threshold
            
            min_silence_duration = st.slider(
                "最小無音時間 (秒)",
                min_value=0.1,
                max_value=1.0,
                value=st.session_state.get('min_silence_duration', DEFAULT_MIN_SILENCE_DURATION),
                step=0.1,
                help="無音と判定する最小の時間。値が大きいほど長い無音が必要です。"
            )
            st.session_state.min_silence_duration = min_silence_duration
            
            min_segment_duration = st.slider(
                "最小セグメント時間 (秒)",
                min_value=0.1,
                max_value=1.0,
                value=st.session_state.get('min_segment_duration', DEFAULT_MIN_SEGMENT_DURATION),
                step=0.1,
                help="セグメントとして残す最小の時間。値が小さいほど細かく分割されます。"
            )
            st.session_state.min_segment_duration = min_segment_duration
        
        with tab2:
            st.header("ヘルプ")
            st.markdown("""
            ### 使い方
            1. 動画ファイルを`videos`フォルダに配置
            2. 動画を選択して文字起こしを実行
            3. テキストを編集して必要な部分を抽出
            4. 動画の切り出しや無音部分の削除を実行
            
            ### よくある質問
            Q: 対応している動画形式は？  
            A: MP4, MOV, AVI, MKV, WMVに対応しています。
            
            Q: 文字起こしの精度は？  
            A: Whisperモデルのサイズによって異なります。large-v3が最も高精度です。
            
            Q: 無音部分の削除とは？  
            A: 指定した閾値以下の音量が一定時間続く部分を削除します。
            """)

    # 動画ファイル選択
    video_files = get_video_files()
    
    if not video_files:
        st.warning("📁 videosフォルダに動画ファイルがありません。")
        st.info("動画ファイルを以下のフォルダに配置してください: `videos/`")
        return
    
    # 入力と出力のパス設定
    col1, col2 = st.columns(2)
    with col1:
        input_dir = st.text_input(
            "📥 入力フォルダ",
            value=str(Path("videos").resolve()),
            help="元の動画ファイルを格納するフォルダのフルパス"
        )
    with col2:
        output_dir = st.text_input(
            "📤 出力フォルダ",
            value=str(Path("output").resolve()),
            help="切り抜き動画が保存されるフォルダのフルパス"
        )
    
    # 入力フォルダの存在確認
    input_path = Path(input_dir)
    if not input_path.exists():
        st.error(f"入力フォルダが見つかりません: {input_dir}")
        return
    
    # 出力フォルダの作成
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    selected_video = st.selectbox(
        "🎬 動画ファイルを選択",
        options=video_files,
        format_func=lambda x: str(x.resolve())
    )
    
    video_path = str(selected_video)
    
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
        st.header("✂️ 切り抜き箇所の指定")
        
        # 純粋なテキストを取得
        full_text = ""
        for seg in st.session_state.transcription_result["segments"]:
            if 'words' in seg:
                text = "".join(word['word'] for word in seg['words'])
            else:
                text = seg['text']
            full_text += text
        full_text = full_text.strip()
        
        # 2カラムレイアウト
        col1, col2 = st.columns(2)
        
        # 変数の初期化
        common_positions = []
        new_words = set()
        
        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した文章が緑色でハイライトされます")
            
            # 編集用テキストエリアの値を取得
            edited_text = st.session_state.get('edited_text', '')
            
            # 差分表示を生成
            if edited_text:
                highlighted_diff, common_positions, new_words = highlight_differences(full_text, edited_text)
                st.markdown(
                    f'<div style="height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">{highlighted_diff}</div>',
                    unsafe_allow_html=True
                )
                
                # 新しい単語のエラー表示
                if new_words:
                    st.error("元の動画に存在しない部分があります。赤いハイライトを確認してください")
            else:
                st.markdown(
                    f'<div style="height: 400px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 5px;">{full_text}</div>',
                    unsafe_allow_html=True
                )
        
        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く文章をコピペしてください")
            
            # 編集用テキストエリア
            edited_text = st.text_area(
                label="",
                value=st.session_state.get('edited_text', ''),
                height=400,
                label_visibility="collapsed"
            )
            
            # 文字数カウンター
            total_duration = 0
            for start, end, _ in common_positions:
                start_time, end_time = get_timestamp_for_position(
                    st.session_state.transcription_result["segments"],
                    start,
                    end
                )
                total_duration += end_time - start_time
            
            st.caption(f"文字数: {len(edited_text)}文字 / 時間: {total_duration:.1f}秒（フィラー削除前）")
            
            # 更新ボタン
            if st.button("🔄 更新", type="primary"):
                st.session_state.edited_text = edited_text
                st.rerun()
        
        # 切り抜き箇所の抽出セクション
        if edited_text and common_positions:
            st.header("🎬 切り抜き箇所の抽出")
            
            # 処理オプション
            st.markdown("### 処理オプション")
            col1, col2 = st.columns(2)
            
            with col1:
                process_type = st.radio(
                    "処理方法",
                    ["切り抜きのみ", "フィラー削除付き"],
                    index=1,  # デフォルトを「フィラー削除付き」に設定
                    help="切り抜きのみ：指定した部分をそのまま切り出します\nフィラー削除付き：切り出した部分からフィラーを削除します"
                )
            
            with col2:
                if process_type == "フィラー削除付き":
                    st.markdown("#### フィラー削除の設定")
                    st.info("現在の設定：\n"
                           f"- 無音検出の閾値: {st.session_state.get('noise_threshold', -35)}dB\n"
                           f"- 最小無音時間: {st.session_state.get('min_silence_duration', 0.3)}秒\n"
                           f"- 最小セグメント時間: {st.session_state.get('min_segment_duration', 0.3)}秒\n\n"
                           "設定を変更する場合は、左のサイドパネルの「フィラー設定」タブから変更してください。")
            
            # 処理実行ボタン
            if st.button("🚀 処理を実行", type="primary", use_container_width=True):
                # タイムスタンプ情報を収集
                timestamps = []
                for start, end, _ in common_positions:
                    start_time, end_time = get_timestamp_for_position(
                        st.session_state.transcription_result["segments"],
                        start,
                        end
                    )
                    timestamps.append((start_time, end_time))
                
                # 出力ディレクトリの設定
                if process_type == "切り抜きのみ":
                    output_dir = f"{output_dir}/{Path(video_path).stem}_segments"
                    # 既存の出力フォルダを削除
                    output_path = Path(output_dir)
                    if output_path.exists():
                        import shutil
                        try:
                            shutil.rmtree(output_path)
                            st.info(f"既存の出力フォルダを削除しました: {output_dir}")
                        except Exception as e:
                            st.warning(f"既存の出力フォルダの削除に失敗しました: {str(e)}")
                    
                    # 出力ディレクトリを作成
                    output_path.mkdir(parents=True, exist_ok=True)
                    
                    with st.spinner("指定した箇所を切り出し中..."):
                        try:
                            output_files = extract_video_segments(video_path, timestamps, output_dir)
                            if output_files:
                                st.success(f"切り出しが完了しました！ {len(output_files)}個の動画を生成しました。")
                                
                                # 抽出部分と動画を横並びで表示
                                with st.expander("抽出部分と生成された動画", expanded=False):
                                    for i, ((start, end, text), file) in enumerate(zip(common_positions, output_files)):
                                        start_time, end_time = get_timestamp_for_position(
                                            st.session_state.transcription_result["segments"],
                                            start,
                                            end
                                        )
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown(f"**{start_time:.1f}s - {end_time:.1f}s**")
                                            st.markdown(text)
                                        with col2:
                                            st.video(file)
                                        st.markdown("---")
                            else:
                                st.error("動画の切り出しに失敗しました。")
                                
                        except Exception as e:
                            st.error(f"動画の処理中にエラーが発生しました: {str(e)}")
                else:
                    output_dir = f"{output_dir}/{Path(video_path).stem}_no_fillers"
                    # 既存の出力フォルダを削除
                    output_path = Path(output_dir)
                    if output_path.exists():
                        import shutil
                        try:
                            shutil.rmtree(output_path)
                        except Exception as e:
                            st.warning(f"既存の出力フォルダの削除に失敗しました: {str(e)}")
                    
                    # 出力ディレクトリを作成
                    output_path.mkdir(parents=True, exist_ok=True)
                    
                    with st.spinner("指定した箇所を切り出し、フィラーを削除中..."):
                        try:
                            output_files = remove_fillers_from_video(
                                video_path,
                                output_dir,
                                timestamps,
                                noise_threshold=st.session_state.get('noise_threshold', -35),
                                min_silence_duration=st.session_state.get('min_silence_duration', 0.3),
                                min_segment_duration=st.session_state.get('min_segment_duration', 0.3)
                            )
                            if output_files:
                                # 出力ファイルの数を正確にカウント
                                actual_files = [f for f in output_files if Path(f).exists()]
                                
                                # 合計時間を計算
                                total_duration = 0
                                for file in actual_files:
                                    cmd = [
                                        "ffprobe", "-v", "error",
                                        "-show_entries", "format=duration",
                                        "-of", "default=noprint_wrappers=1:nokey=1",
                                        file
                                    ]
                                    result = subprocess.run(cmd, capture_output=True, text=True)
                                    if result.returncode == 0:
                                        total_duration += float(result.stdout.strip())
                                
                                st.success(f"処理が完了しました！\n"
                                         f"出力先: {output_dir}\n"
                                         f"生成した動画: {len(actual_files)}個\n"
                                         f"合計時間: {total_duration:.1f}秒")
                                
                                # 抽出部分と動画を横並びで表示
                                with st.expander("抽出部分と生成された動画", expanded=False):
                                    for i, ((start, end, text), file) in enumerate(zip(common_positions, actual_files)):
                                        start_time, end_time = get_timestamp_for_position(
                                            st.session_state.transcription_result["segments"],
                                            start,
                                            end
                                        )
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            st.markdown(f"**{start_time:.1f}s - {end_time:.1f}s**")
                                            st.markdown(text)
                                        with col2:
                                            st.video(file)
                                        st.markdown("---")
                            else:
                                st.error("動画の処理に失敗しました。")
                            
                        except Exception as e:
                            st.error(f"フィラーの削除中にエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()
