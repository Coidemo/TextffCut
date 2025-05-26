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
import time

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

def format_time(seconds):
    """秒数を時間:分:秒の形式に変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}時間{minutes}分{seconds}秒"
    elif minutes > 0:
        return f"{minutes}分{seconds}秒"
    else:
        return f"{seconds}秒"

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
        
        # 進捗状況の表示用
        total_chunks = len(chunks)
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 並列処理で文字起こし
        segments_all = []
        completed_chunks = 0
        start_time = time.time()  # 開始時間を記録
        
        with ThreadPoolExecutor(max_workers=NUM_WORKERS) as exe:
            futures = [exe.submit(transcribe_chunk, ch, asr_model) for ch in chunks]
            for fut in as_completed(futures):
                segs, _ = fut.result()
                segments_all.extend(segs)
                completed_chunks += 1
                
                # 進捗状況の更新
                progress = completed_chunks / total_chunks
                progress_bar.progress(progress)
                
                # 残り時間の計算と表示
                if completed_chunks < total_chunks:
                    elapsed_time = time.time() - start_time
                    avg_time_per_chunk = elapsed_time / completed_chunks
                    remaining_chunks = total_chunks - completed_chunks
                    estimated_remaining_time = avg_time_per_chunk * remaining_chunks
                    
                    status_text.text(f"進捗: {completed_chunks}/{total_chunks} チャンク "
                                   f"（残り約{format_time(estimated_remaining_time)}）")
        
        # 結果を整形
        asr_result = {
            "language": "ja",
            "segments": sorted(segments_all, key=lambda x: x["start"])
        }
        
        # アライメント処理
        try:
            status_text.text("アライメント処理を実行中...")
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

def get_video_info(video_path):
    """動画の情報（長さとフレームレート）を取得"""
    try:
        # フレームレートの取得
        fps_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            "-of", "json",
            str(video_path)
        ]
        fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
        fps = 30.0  # デフォルト値
        if fps_result.returncode == 0:
            fps_info = json.loads(fps_result.stdout)
            if 'streams' in fps_info and len(fps_info['streams']) > 0:
                fps_str = fps_info['streams'][0]['r_frame_rate']
                num, den = map(int, fps_str.split('/'))
                fps = num / den if den != 0 else 30.0

        # 動画の長さの取得
        duration_cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ]
        duration_result = subprocess.run(duration_cmd, capture_output=True, text=True)
        duration = None
        if duration_result.returncode == 0:
            duration_info = json.loads(duration_result.stdout)
            if 'format' in duration_info and 'duration' in duration_info['format']:
                duration = float(duration_info['format']['duration'])

        return fps, duration
    except Exception as e:
        st.warning(f"動画情報の取得中にエラーが発生しました: {str(e)}")
        return 30.0, None  # エラー時はデフォルト値を返す

def get_ffmpeg_progress(process, total_duration, progress_bar, status_text, start_time, total_progress=0, segment_progress=1.0):
    """FFmpegの進捗情報を取得"""
    while process.poll() is None:
        # FFmpegの出力から進捗情報を取得
        output = process.stderr.readline()
        if not output:
            continue
            
        try:
            output = output.decode('utf-8', errors='ignore')
            if "time=" in output:
                # 時間情報を抽出（HH:MM:SS.mmm形式）
                time_str = output.split("time=")[1].split()[0]
                hours, minutes, seconds = time_str.split(":")
                current_time = float(hours) * 3600 + float(minutes) * 60 + float(seconds)
                
                # 進捗率を計算（セグメント内の進捗）
                segment_current = min(current_time / total_duration, 1.0)
                
                # 全体の進捗を計算（0.0から1.0の範囲に収める）
                total_current = min(total_progress + (segment_current * segment_progress), 1.0)
                progress_bar.progress(total_current)
                
                # 残り時間を計算
                elapsed_time = time.time() - start_time
                if total_current > 0:
                    estimated_total = elapsed_time / total_current
                    remaining = estimated_total - elapsed_time
                    status_text.text(f"全体の進捗: {total_current:.1%} (残り約{format_time(remaining)})")
        except Exception as e:
            # エラーを無視して処理を継続
            pass
    
    # セグメント完了時の進捗更新（0.0から1.0の範囲に収める）
    total_current = min(total_progress + segment_progress, 1.0)
    progress_bar.progress(total_current)
    return total_current

def extract_video_segments(video_path: str, segments: List[tuple[float, float]], output_dir: str):
    """動画から指定されたセグメントを切り出し"""
    try:
        # 出力ディレクトリを作成
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(exist_ok=True)
        
        # 各セグメントを切り出し
        output_files = []
        total_segments = len(segments)
        
        # 進捗表示の初期化
        progress_bar = st.progress(0)
        status_text = st.empty()
        start_time = time.time()
        total_progress = 0
        
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
                "-progress", "pipe:1",
                str(output_file)
            ]
            
            # 進捗表示用のステータス
            status_text.text(f"セグメント {i+1}/{total_segments} を処理中...")
            
            # プロセスを開始
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 進捗を表示（セグメントごとの進捗率を計算）
            segment_progress = 1.0 / total_segments
            total_progress = get_ffmpeg_progress(
                process,
                end - start,
                progress_bar,
                status_text,
                start_time,
                total_progress,
                segment_progress
            )
            
            if process.returncode != 0:
                raise Exception(f"FFmpeg error: {process.stderr.read()}")
            
            output_files.append(str(output_file))
        
        status_text.text("完了！")
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
            total_segments = len(segments)
            
            # 進捗表示の初期化
            progress_bar = st.progress(0)
            status_text = st.empty()
            start_time = time.time()
            total_progress = 0
            
            for i, (start, end) in enumerate(segments):
                # 進捗表示用のステータス
                status_text.text(f"セグメント {i+1}/{total_segments} を処理中...")
                
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
                        "-progress", "pipe:1",
                        str(temp_file)
                    ]
                    
                    # プロセスを開始
                    process = subprocess.Popen(
                        cmd,
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        universal_newlines=True
                    )
                    
                    # 進捗を表示（セグメントごとの進捗率を計算）
                    segment_progress = 1.0 / total_segments
                    total_progress = get_ffmpeg_progress(
                        process,
                        end - start,
                        progress_bar,
                        status_text,
                        start_time,
                        total_progress,
                        segment_progress
                    )
                    
                    if process.returncode != 0:
                        raise Exception(f"FFmpeg error: {process.stderr.read()}")
                    
                    # 動画の長さを取得
                    _, video_duration = get_video_info(temp_file)
                    if video_duration is None:
                        raise Exception("動画の長さを取得できませんでした")
                    
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
                        total_filler_segments = len(filler_segments)
                        
                        for j, (seg_start, seg_end) in enumerate(filler_segments):
                            # セグメントの長さをチェック
                            if seg_end - seg_start < 0.1:  # 0.1秒未満のセグメントは無視
                                continue
                            
                            status_text.text(f"セグメント {i+1}/{total_segments} の部分 {j+1}/{total_filler_segments} を処理中...")
                            
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
                                "-progress", "pipe:1",
                                str(segment_file)
                            ]
                            
                            # プロセスを開始
                            process = subprocess.Popen(
                                cmd,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                universal_newlines=True
                            )
                            
                            # 進捗を表示（セグメント内の部分ごとの進捗率を計算）
                            part_progress = segment_progress / total_filler_segments
                            total_progress = get_ffmpeg_progress(
                                process,
                                seg_end - seg_start,
                                progress_bar,
                                status_text,
                                start_time,
                                total_progress,
                                part_progress
                            )
                            
                            if process.returncode != 0:
                                raise Exception(f"FFmpeg error: {process.stderr.read()}")
                            
                            segment_files.append(str(segment_file))
                        
                        # セグメントを結合
                        if len(segment_files) > 1:
                            status_text.text(f"セグメント {i+1}/{total_segments} の部分を結合中...")
                            
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
                                "-progress", "pipe:1",
                                str(output_file)
                            ]
                            
                            # プロセスを開始
                            process = subprocess.Popen(
                                cmd,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                universal_newlines=True
                            )
                            
                            # 進捗を表示（結合処理の進捗率を計算）
                            combine_progress = segment_progress * 0.1  # 結合処理は全体の10%と仮定
                            total_progress = get_ffmpeg_progress(
                                process,
                                video_duration,
                                progress_bar,
                                status_text,
                                start_time,
                                total_progress,
                                combine_progress
                            )
                            
                            if process.returncode != 0:
                                raise Exception(f"FFmpeg error: {process.stderr.read()}")
                            
                            # 一時ファイルを削除
                            for file in segment_files:
                                Path(file).unlink()
                        elif segment_files:
                            # セグメントが1つの場合はそのままコピー
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", segment_files[0],
                                "-c", "copy",
                                "-progress", "pipe:1",
                                str(output_file)
                            ]
                            
                            # プロセスを開始
                            process = subprocess.Popen(
                                cmd,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                universal_newlines=True
                            )
                            
                            # 進捗を表示（コピー処理の進捗率を計算）
                            copy_progress = segment_progress * 0.1  # コピー処理は全体の10%と仮定
                            total_progress = get_ffmpeg_progress(
                                process,
                                video_duration,
                                progress_bar,
                                status_text,
                                start_time,
                                total_progress,
                                copy_progress
                            )
                            
                            if process.returncode != 0:
                                raise Exception(f"FFmpeg error: {process.stderr.read()}")
                            
                            # 一時ファイルを削除
                            Path(segment_files[0]).unlink()
                        else:
                            # 無音部分が見つからない場合は元のセグメントをコピー
                            cmd = [
                                "ffmpeg", "-y",
                                "-i", str(temp_file),
                                "-c", "copy",
                                "-progress", "pipe:1",
                                str(output_file)
                            ]
                            
                            # プロセスを開始
                            process = subprocess.Popen(
                                cmd,
                                stderr=subprocess.PIPE,
                                stdout=subprocess.PIPE,
                                universal_newlines=True
                            )
                            
                            # 進捗を表示（コピー処理の進捗率を計算）
                            copy_progress = segment_progress * 0.1  # コピー処理は全体の10%と仮定
                            total_progress = get_ffmpeg_progress(
                                process,
                                video_duration,
                                progress_bar,
                                status_text,
                                start_time,
                                total_progress,
                                copy_progress
                            )
                            
                            if process.returncode != 0:
                                raise Exception(f"FFmpeg error: {process.stderr.read()}")
                    
                    processed_segments.append(str(output_file))
                
                finally:
                    # 一時ファイルを削除
                    if temp_file.exists():
                        temp_file.unlink()
                    # 中間ファイルを削除
                    for file in output_dir.glob(f"segment_{i+1}_part_*.mp4"):
                        file.unlink()
            
            status_text.text("完了！")
            return processed_segments
            
    except Exception as e:
        st.error(f"動画の処理中にエラーが発生しました: {str(e)}")
        return None

def format_timestamp(seconds):
    """秒数をSRT形式のタイムスタンプに変換"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = seconds % 60
    milliseconds = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{int(seconds):02d},{milliseconds:03d}"

def split_text_into_lines(text, chars_per_line, max_lines):
    """テキストを行数と文字数制限に基づいて分割"""
    # 文末で分割
    sentences = re.split(r'([。．！？])', text)
    sentences = [''.join(i) for i in zip(sentences[::2], sentences[1::2] + [''])]
    
    lines = []
    current_line = ""
    
    for sentence in sentences:
        # 現在の行に文を追加した場合の長さ
        potential_line = current_line + sentence
        
        if len(potential_line) <= chars_per_line:
            current_line = potential_line
        else:
            # 現在の行が空でない場合は保存
            if current_line:
                lines.append(current_line)
                current_line = ""
            
            # 文が1行の文字数制限を超える場合は分割
            if len(sentence) > chars_per_line:
                # 単語の境界で分割
                words = re.findall(r'[一-龯ぁ-んァ-ンa-zA-Z0-9]+|[^一-龯ぁ-んァ-ンa-zA-Z0-9]', sentence)
                temp_line = ""
                
                for word in words:
                    # 現在の行に単語を追加した場合の長さ
                    if len(temp_line + word) <= chars_per_line:
                        temp_line += word
                    else:
                        # 現在の行が空でない場合は保存
                        if temp_line:
                            lines.append(temp_line)
                        # 単語が1行の文字数制限を超える場合は強制的に分割
                        if len(word) > chars_per_line:
                            # 文字単位で分割
                            remaining = word
                            while remaining:
                                if len(remaining) <= chars_per_line:
                                    temp_line = remaining
                                    remaining = ""
                                else:
                                    lines.append(remaining[:chars_per_line])
                                    remaining = remaining[chars_per_line:]
                            temp_line = ""
                        else:
                            temp_line = word
                
                if temp_line:
                    current_line = temp_line
            else:
                current_line = sentence
    
    # 最後の行を追加
    if current_line:
        lines.append(current_line)
    
    # 行数制限を適用
    if len(lines) > max_lines:
        # 最後の行を調整
        last_line = ' '.join(lines[max_lines-1:])
        lines = lines[:max_lines-1]
        # 最後の行が文字数制限を超える場合は省略
        if len(last_line) > chars_per_line:
            last_line = last_line[:chars_per_line-3] + '...'
        lines.append(last_line)
    
    return lines

def generate_srt_for_trimmed_video(segments, timestamps, output_path, chars_per_line=20, max_lines=2, fps=30):
    """切り抜き後の動画用の字幕ファイル（SRT）を生成"""
    with open(output_path, 'w', encoding='utf-8') as f:
        # 選択された部分のセグメントのみを抽出
        selected_segments = []
        
        for start, end in timestamps:
            # この切り抜き範囲内のセグメントを抽出
            for seg in segments:
                # セグメントが切り抜き範囲と重なる部分がある場合
                if seg['end'] > start and seg['start'] < end:
                    # セグメントの時間を相対的な時間に調整
                    adjusted_seg = seg.copy()
                    
                    # 文字単位のタイムスタンプがある場合はそれを使用
                    if 'chars' in seg:
                        adjusted_chars = []
                        for char in seg['chars']:
                            if char['end'] > start and char['start'] < end:
                                char_copy = char.copy()
                                if char_copy['start'] < start:
                                    char_copy['start'] = 0.0
                                else:
                                    char_copy['start'] = char_copy['start'] - start
                                
                                if char_copy['end'] > end:
                                    char_copy['end'] = end - start
                                else:
                                    char_copy['end'] = char_copy['end'] - start
                                
                                adjusted_chars.append(char_copy)
                        
                        if adjusted_chars:
                            adjusted_seg['chars'] = adjusted_chars
                            adjusted_seg['start'] = adjusted_chars[0]['start']
                            adjusted_seg['end'] = adjusted_chars[-1]['end']
                            adjusted_seg['text'] = ''.join(char['char'] for char in adjusted_chars)
                            selected_segments.append(adjusted_seg)
                    
                    # 単語単位のタイムスタンプがある場合
                    elif 'words' in seg:
                        adjusted_words = []
                        for word in seg['words']:
                            if word['end'] > start and word['start'] < end:
                                word_copy = word.copy()
                                if word_copy['start'] < start:
                                    word_copy['start'] = 0.0
                                else:
                                    word_copy['start'] = word_copy['start'] - start
                                
                                if word_copy['end'] > end:
                                    word_copy['end'] = end - start
                                else:
                                    word_copy['end'] = word_copy['end'] - start
                                
                                adjusted_words.append(word_copy)
                        
                        if adjusted_words:
                            adjusted_seg['words'] = adjusted_words
                            adjusted_seg['start'] = adjusted_words[0]['start']
                            adjusted_seg['end'] = adjusted_words[-1]['end']
                            adjusted_seg['text'] = ''.join(word['word'] for word in adjusted_words)
                            selected_segments.append(adjusted_seg)
        
        # 字幕を生成
        for i, segment in enumerate(selected_segments, 1):
            # タイムスタンプの生成（ミリ秒まで正確に）
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            
            # テキストを行に分割
            text = segment['text'].strip()
            lines = split_text_into_lines(text, chars_per_line, max_lines)
            
            # SRTフォーマットで書き込み
            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write('\n'.join(lines) + '\n\n')

def adjust_srt_for_no_fillers(srt_path, filler_segments, output_path):
    """無音削除後の動画用に字幕のタイミングを調整"""
    # 字幕ファイルを読み込み
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()
    
    # 字幕エントリを解析
    entries = []
    current_entry = None
    for line in srt_content.split('\n'):
        line = line.strip()
        if not line:
            if current_entry:
                entries.append(current_entry)
                current_entry = None
            continue
        
        if current_entry is None:
            current_entry = {'index': line}
        elif '-->' in line:
            start, end = line.split(' --> ')
            current_entry['start'] = start
            current_entry['end'] = end
        else:
            if 'text' not in current_entry:
                current_entry['text'] = line
            else:
                current_entry['text'] += '\n' + line
    
    if current_entry:
        entries.append(current_entry)
    
    # 無音削除後の時間に調整
    adjusted_entries = []
    current_offset = 0.0
    
    for start, end in filler_segments:
        segment_duration = end - start
        # このセグメント内の字幕を抽出
        for entry in entries:
            entry_start = time_to_seconds(entry['start'])
            entry_end = time_to_seconds(entry['end'])
            
            # 字幕がこのセグメントと重なる場合
            if entry_end > start and entry_start < end:
                adjusted_entry = entry.copy()
                
                # 開始時間の調整
                if entry_start < start:
                    adjusted_entry['start'] = format_timestamp(current_offset)
                else:
                    adjusted_entry['start'] = format_timestamp(current_offset + (entry_start - start))
                
                # 終了時間の調整
                if entry_end > end:
                    adjusted_entry['end'] = format_timestamp(current_offset + segment_duration)
                else:
                    adjusted_entry['end'] = format_timestamp(current_offset + (entry_end - start))
                
                adjusted_entries.append(adjusted_entry)
        
        current_offset += segment_duration
    
    # 調整後の字幕を書き込み
    with open(output_path, 'w', encoding='utf-8') as f:
        for i, entry in enumerate(adjusted_entries, 1):
            f.write(f"{i}\n")
            f.write(f"{entry['start']} --> {entry['end']}\n")
            f.write(f"{entry['text']}\n\n")

def time_to_seconds(time_str):
    """SRT形式のタイムスタンプを秒数に変換"""
    hours, minutes, seconds = time_str.replace(',', '.').split(':')
    return float(hours) * 3600 + float(minutes) * 60 + float(seconds)

def combine_videos(input_files: List[str], output_file: str):
    """複数の動画ファイルを1つに結合"""
    try:
        # 結合用の一時ファイルリストを作成
        list_file = Path(output_file).parent / "concat_list.txt"
        with open(list_file, "w") as f:
            for file in input_files:
                f.write(f"file '{Path(file).resolve()}'\n")
        
        # 合計時間を計算
        total_duration = 0
        for file in input_files:
            cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                total_duration += float(result.stdout.strip())
        
        # 進捗表示の初期化
        progress_bar = st.progress(0)
        status_text = st.empty()
        start_time = time.time()
        
        # 動画を結合
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            "-progress", "pipe:1",
            str(output_file)
        ]
        
        # プロセスを開始
        process = subprocess.Popen(
            cmd,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            universal_newlines=True
        )
        
        # 進捗を表示
        get_ffmpeg_progress(process, total_duration, progress_bar, status_text, start_time)
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg error: {process.stderr.read()}")
        
        # 一時ファイルを削除
        list_file.unlink()
        
        status_text.text("完了！")
        return True
    except Exception as e:
        st.error(f"動画の結合中にエラーが発生しました: {str(e)}")
        return False

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
    
    # 文字起こしボタンを左寄せに配置
    if saved_result:
        if st.button("💾 保存済み結果を使用", type="primary"):
            st.session_state.transcription_result = saved_result
            st.success("✅ 文字起こし結果を読み込みました！")
            st.rerun()
    
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
                    if st.button("❌ 赤ハイライト部分を削除", type="secondary"):
                        # 赤ハイライト部分を除いたテキストを生成
                        cleaned_text = ""
                        for start, end, text in common_positions:
                            cleaned_text += text
                        st.session_state.edited_text = cleaned_text
                        st.rerun()
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
            
            st.caption(f"文字数: {len(edited_text)}文字 / 時間: {total_duration:.1f}秒（無音削除前）")
            
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
                    ["切り抜きのみ", "無音削除付き"],
                    index=1,
                    help="切り抜きのみ：指定した部分をそのまま切り出します\n無音削除付き：切り出した部分から無音を削除します"
                )
            
            with col2:
                if process_type == "無音削除付き":
                    st.markdown("#### 無音削除の設定")
                    st.info("現在の設定：\n"
                           f"- 無音検出の閾値: {st.session_state.get('noise_threshold', -35)}dB\n"
                           f"- 最小無音時間: {st.session_state.get('min_silence_duration', 0.3)}秒\n"
                           f"- 最小セグメント時間: {st.session_state.get('min_segment_duration', 0.3)}秒\n\n"
                           "設定を変更する場合は、左のサイドパネルの「無音設定」タブから変更してください。")
            
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
                    
                    with st.spinner("指定した箇所を切り出し、無音を削除中..."):
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
                                
                                # 結合した動画を生成
                                combined_output = str(Path(output_dir) / "combined.mp4")
                                if combine_videos(actual_files, combined_output):
                                    st.success("結合した動画を生成しました！")
                                    st.video(combined_output)
                                
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
                            st.error(f"無音の削除中にエラーが発生しました: {str(e)}")

if __name__ == "__main__":
    main()
