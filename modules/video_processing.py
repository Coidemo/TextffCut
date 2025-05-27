"""
動画処理のモジュール
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
import streamlit as st

from ..config import config
from ..utils import BuzzClipError, handle_ffmpeg_error, get_ffmpeg_progress

def extract_segment(video_path: str, start_time: float, end_time: float, output_path: str) -> None:
    """動画からセグメントを抽出"""
    try:
        # FFmpegコマンドの構築
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(start_time),
            "-to", str(end_time),
            "-c:v", "libx264",
            "-preset", config.ffmpeg_preset,
            "-c:a", "aac",
            "-b:a", config.ffmpeg_audio_bitrate,
            output_path
        ]
        
        # コマンドの実行
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        start_time = time.time()
        
        # 進捗の監視
        get_ffmpeg_progress(process, end_time - start_time, progress_bar, status_text, start_time)
        
        # エラーチェック
        handle_ffmpeg_error(process, "セグメントの抽出")
        
    except Exception as e:
        raise BuzzClipError(f"セグメントの抽出に失敗: {str(e)}")

def remove_fillers_from_segment(video_path: str, start_time: float, end_time: float, 
                              output_path: str, noise_threshold: float = -35, 
                              min_silence_duration: float = 0.3) -> None:
    """セグメントから無音部分を除去"""
    try:
        # 一時ファイルの作成
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_path = temp_file.name
        
        # 無音部分の検出
        silence_cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ss", str(start_time),
            "-to", str(end_time),
            "-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}",
            "-f", "null",
            "-"
        ]
        
        process = subprocess.Popen(
            silence_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # 無音部分の時間範囲を取得
        silence_ranges = []
        for line in process.stderr:
            if "silence_start" in line:
                start = float(line.split("silence_start: ")[1])
            elif "silence_end" in line:
                end = float(line.split("silence_end: ")[1])
                silence_ranges.append((start, end))
        
        # 無音部分を除去した動画の生成
        if silence_ranges:
            # 無音部分を除いた時間範囲を計算
            valid_ranges = []
            current_start = start_time
            
            for silence_start, silence_end in silence_ranges:
                if silence_start > current_start:
                    valid_ranges.append((current_start, silence_start))
                current_start = silence_end
            
            if current_start < end_time:
                valid_ranges.append((current_start, end_time))
            
            # 各範囲を結合
            with open(temp_path, "w") as f:
                for start, end in valid_ranges:
                    f.write(f"file '{video_path}'\n")
                    f.write(f"inpoint {start}\n")
                    f.write(f"outpoint {end}\n")
            
            # 動画の結合
            concat_cmd = [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", temp_path,
                "-c:v", "libx264",
                "-preset", config.ffmpeg_preset,
                "-c:a", "aac",
                "-b:a", config.ffmpeg_audio_bitrate,
                output_path
            ]
            
            process = subprocess.Popen(
                concat_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 進捗表示
            progress_bar = st.progress(0)
            status_text = st.empty()
            start_time = time.time()
            
            # 進捗の監視
            get_ffmpeg_progress(process, end_time - start_time, progress_bar, status_text, start_time)
            
            # エラーチェック
            handle_ffmpeg_error(process, "無音部分の除去")
        else:
            # 無音部分がない場合は単純にコピー
            extract_segment(video_path, start_time, end_time, output_path)
        
        # 一時ファイルの削除
        os.unlink(temp_path)
        
    except Exception as e:
        raise BuzzClipError(f"無音部分の除去に失敗: {str(e)}")

def combine_segments(segment_paths: List[str], output_path: str) -> None:
    """複数のセグメントを結合"""
    try:
        # 一時ファイルの作成
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            temp_path = temp_file.name
            
            # セグメントリストの作成
            for path in segment_paths:
                temp_file.write(f"file '{path}'\n")
        
        # 動画の結合
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", temp_path,
            "-c:v", "libx264",
            "-preset", config.ffmpeg_preset,
            "-c:a", "aac",
            "-b:a", config.ffmpeg_audio_bitrate,
            output_path
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        
        # 進捗表示
        progress_bar = st.progress(0)
        status_text = st.empty()
        start_time = time.time()
        
        # 進捗の監視
        get_ffmpeg_progress(process, 1.0, progress_bar, status_text, start_time)
        
        # エラーチェック
        handle_ffmpeg_error(process, "セグメントの結合")
        
        # 一時ファイルの削除
        os.unlink(temp_path)
        
    except Exception as e:
        raise BuzzClipError(f"セグメントの結合に失敗: {str(e)}") 