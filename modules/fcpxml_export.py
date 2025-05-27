"""
FCPXML出力のモジュール
"""

import os
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple, Dict, Any
import streamlit as st

from ..config import config
from ..utils import BuzzClipError, get_video_info

def create_fcpxml(video_paths: List[str], output_path: str, timeline_fps: int = 30) -> None:
    """FCPXMLファイルを生成"""
    try:
        # FCPXMLのルート要素を作成
        root = ET.Element("fcpxml", version="1.9")
        resources = ET.SubElement(root, "resources")
        library = ET.SubElement(root, "library")
        event = ET.SubElement(library, "event")
        project = ET.SubElement(event, "project")
        sequence = ET.SubElement(project, "sequence")
        spine = ET.SubElement(sequence, "spine")
        
        # プロジェクトの設定
        project.set("name", "Buzz Clip Project")
        sequence.set("format", "r1")
        
        # フォーマット要素の作成
        format_elem = ET.SubElement(resources, "format")
        format_elem.set("id", "r1")
        format_elem.set("name", "FFVideoFormat1080p30")
        format_elem.set("frameDuration", f"1/{timeline_fps}s")
        format_elem.set("width", "1920")
        format_elem.set("height", "1080")
        
        # 各ビデオクリップの処理
        current_time = 0
        for i, video_path in enumerate(video_paths, 1):
            # ビデオ情報の取得
            fps, duration = get_video_info(video_path)
            if duration is None:
                raise BuzzClipError(f"動画の長さを取得できません: {video_path}")
            
            # アセット要素の作成
            asset_elem = ET.SubElement(resources, "asset")
            asset_elem.set("id", f"r{i+1}")
            asset_elem.set("name", os.path.basename(video_path))
            asset_elem.set("src", f"file://{os.path.abspath(video_path)}")
            asset_elem.set("duration", f"{duration}/{timeline_fps}s")
            asset_elem.set("format", "r1")
            
            # クリップ要素の作成
            clip_elem = ET.SubElement(spine, "clip")
            clip_elem.set("name", os.path.basename(video_path))
            clip_elem.set("duration", f"{duration}/{timeline_fps}s")
            clip_elem.set("start", f"{current_time}/{timeline_fps}s")
            clip_elem.set("offset", "0/30s")
            
            # ビデオ要素の作成
            video_elem = ET.SubElement(clip_elem, "video")
            video_elem.set("ref", f"r{i+1}")
            video_elem.set("offset", "0/30s")
            video_elem.set("duration", f"{duration}/{timeline_fps}s")
            
            # オーディオ要素の作成
            audio_elem = ET.SubElement(clip_elem, "audio")
            audio_elem.set("ref", f"r{i+1}")
            audio_elem.set("offset", "0/30s")
            audio_elem.set("duration", f"{duration}/{timeline_fps}s")
            
            current_time += duration
        
        # XMLファイルの保存
        tree = ET.ElementTree(root)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
        
    except Exception as e:
        raise BuzzClipError(f"FCPXMLファイルの生成に失敗: {str(e)}")

def create_fcpxml_from_segments(video_path: str, segments: List[Tuple[float, float]], 
                              output_path: str, timeline_fps: int = 30) -> None:
    """セグメント情報からFCPXMLファイルを生成"""
    try:
        # 一時ディレクトリの作成
        temp_dir = Path("temp_segments")
        temp_dir.mkdir(exist_ok=True)
        
        # 各セグメントの動画を生成
        segment_paths = []
        for i, (start, end) in enumerate(segments, 1):
            segment_path = temp_dir / f"segment_{i}.mp4"
            
            # FFmpegコマンドの構築
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-ss", str(start),
                "-to", str(end),
                "-c:v", "libx264",
                "-preset", config.ffmpeg_preset,
                "-c:a", "aac",
                "-b:a", config.ffmpeg_audio_bitrate,
                str(segment_path)
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
            get_ffmpeg_progress(process, end - start, progress_bar, status_text, start_time)
            
            # エラーチェック
            if process.returncode != 0:
                raise BuzzClipError(f"セグメントの生成に失敗: {process.stderr.read()}")
            
            segment_paths.append(str(segment_path))
        
        # FCPXMLファイルの生成
        create_fcpxml(segment_paths, output_path, timeline_fps)
        
        # 一時ファイルの削除
        for path in segment_paths:
            os.unlink(path)
        temp_dir.rmdir()
        
    except Exception as e:
        raise BuzzClipError(f"FCPXMLファイルの生成に失敗: {str(e)}") 