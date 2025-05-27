import subprocess
import time
from pathlib import Path
from typing import List, Tuple, Optional
import streamlit as st

class BuzzClipError(Exception):
    """アプリケーション固有の例外"""
    pass

def handle_ffmpeg_error(process: subprocess.Popen, operation: str) -> None:
    """FFmpegエラーの統一処理"""
    if process.returncode != 0:
        error_output = process.stderr.read()
        raise BuzzClipError(f"{operation}に失敗: {error_output}")

def format_time(seconds: float) -> str:
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

def get_video_info(video_path: str) -> Tuple[float, Optional[float]]:
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

def get_ffmpeg_progress(process: subprocess.Popen, total_duration: float, progress_bar: st.progress, 
                       status_text: st.empty, start_time: float, total_progress: float = 0, 
                       segment_progress: float = 1.0) -> float:
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