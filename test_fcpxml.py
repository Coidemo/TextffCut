import streamlit as st
import subprocess
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from datetime import datetime

def get_video_info(video_path):
    """動画の情報（長さとフレームレート）を取得"""
    try:
        # フレームレートの取得
        fps_cmd = [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate,time_base",
            "-of", "json",
            str(video_path)
        ]
        fps_result = subprocess.run(fps_cmd, capture_output=True, text=True)
        fps = 30.0  # デフォルト値
        time_base = "1/30"  # デフォルト値
        if fps_result.returncode == 0:
            fps_info = json.loads(fps_result.stdout)
            if 'streams' in fps_info and len(fps_info['streams']) > 0:
                stream_info = fps_info['streams'][0]
                if 'r_frame_rate' in stream_info:
                    fps_str = stream_info['r_frame_rate']
                    num, den = map(int, fps_str.split('/'))
                    fps = num / den if den != 0 else 30.0
                if 'time_base' in stream_info:
                    time_base = stream_info['time_base']

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

        return fps, duration, time_base
    except Exception as e:
        st.warning(f"動画情報の取得中にエラーが発生しました: {str(e)}")
        return 30.0, None, "1/30"

def detect_silence(video_path, noise_threshold=-35, min_silence_duration=0.3):
    """動画から無音部分を検出"""
    try:
        # 無音部分を検出
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
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
                if current_start is None:
                    current_start = start
            elif 'silence_end' in line and current_start is not None:
                end = float(line.split('silence_end: ')[1].split(' |')[0])
                # 前の無音部分との間隔が0.5秒未満の場合は結合
                if silence_times and start - silence_times[-1] < 0.5:
                    silence_times[-1] = end
                else:
                    silence_times.extend([current_start, end])
                current_start = None
        
        return silence_times
    except Exception as e:
        st.error(f"無音検出中にエラーが発生しました: {str(e)}")
        return []

def parse_fps(fps_str):
    """フレームレート文字列を解析して数値に変換"""
    try:
        if '/' in fps_str:
            num, den = map(int, fps_str.split('/'))
            return num / den if den != 0 else 30.0
        return float(fps_str)
    except:
        return 30.0

def round_to_frame(time_seconds, source_fps, target_fps):
    """時間を指定されたフレームレートのフレーム単位に丸める"""
    # 元のフレームレートでのフレーム数を計算
    source_frames = round(time_seconds * source_fps)
    # 目標のフレームレートに変換
    target_frames = round(source_frames * (target_fps / source_fps))
    return target_frames / target_fps

def create_fcpxml(video_path, silence_times, output_path):
    """FCPXMLファイルを生成"""
    try:
        # 動画情報を取得
        source_fps, duration, time_base = get_video_info(video_path)
        if duration is None:
            raise Exception("動画の長さを取得できませんでした")
        
        # デバッグ情報
        st.write(f"素材のフレームレート: {source_fps}fps")
        st.write("無音検出結果:")
        for i in range(0, len(silence_times), 2):
            if i + 1 < len(silence_times):
                st.write(f"無音 {i//2 + 1}: {silence_times[i]:.3f}s - {silence_times[i+1]:.3f}s")
        
        # 動画のフルパスを取得
        video_full_path = str(Path(video_path).resolve())
        
        # FCPXMLの基本構造を作成
        root = ET.Element("fcpxml", version="1.9")
        resources = ET.SubElement(root, "resources")
        
        # タイムラインのフレームレート（30fps固定）
        timeline_fps = 30.0
        
        # フォーマット情報を追加
        format_id = "r0"
        format = ET.SubElement(resources, "format")
        format.set("id", format_id)
        format.set("name", "FFVideoFormat1080p30")
        format.set("frameDuration", "1/30s")
        format.set("width", "1920")
        format.set("height", "1080")
        
        # 動画リソースを追加
        video_name = Path(video_path).name
        video_id = "r1"
        asset = ET.SubElement(resources, "asset")
        asset.set("id", video_id)
        asset.set("name", video_name)
        asset.set("format", format_id)
        asset.set("audioChannels", "2")
        
        # 素材のフレームレートに基づいてdurationを設定
        asset_duration = round_to_frame(duration, source_fps, timeline_fps)
        asset.set("duration", f"{int(asset_duration * timeline_fps)}/{int(timeline_fps)}s")
        asset.set("audioSources", "1")
        asset.set("hasVideo", "1")
        asset.set("hasAudio", "1")
        asset.set("start", "0/1s")
        
        # media-rep要素を追加
        media_rep = ET.SubElement(asset, "media-rep")
        media_rep.set("src", f"file://{video_full_path}")
        media_rep.set("kind", "original-media")
        
        # ライブラリとイベントを作成
        library = ET.SubElement(root, "library")
        event = ET.SubElement(library, "event")
        event.set("name", "Timeline 1")
        
        # プロジェクトを作成
        project = ET.SubElement(event, "project")
        project.set("name", "Timeline 1")
        
        # シーケンスを作成
        sequence = ET.SubElement(project, "sequence")
        sequence.set("format", format_id)
        sequence.set("tcFormat", "NDF")
        sequence.set("tcStart", "3600/1s")
        
        # スパインを作成
        spine = ET.SubElement(sequence, "spine")
        
        # 無音部分を除いたセグメントを作成
        if silence_times:
            total_duration = 0
            current_offset = 3600  # 開始オフセット（秒）
            last_end = 0  # 前のクリップの終了位置
            clip_count = 0
            
            # 最初の無音部分より前のセグメント
            if silence_times[0] > 0:
                # フレーム単位に丸める
                segment_duration = round_to_frame(silence_times[0], source_fps, timeline_fps)
                frames = round(segment_duration * timeline_fps)
                
                clip = ET.SubElement(spine, "asset-clip")
                clip.set("ref", video_id)
                clip.set("offset", f"{int(current_offset * timeline_fps)}/{int(timeline_fps)}s")
                clip.set("duration", f"{frames}/{int(timeline_fps)}s")
                clip.set("start", "0/1s")
                clip.set("name", video_name)
                clip.set("format", format_id)
                clip.set("tcFormat", "NDF")
                clip.set("enabled", "1")
                clip.set("lane", "1")
                
                # トランスフォーム情報を追加
                transform = ET.SubElement(clip, "adjust-transform")
                transform.set("scale", "1 1")
                transform.set("anchor", "0 0")
                transform.set("position", "0 0")
                
                total_duration += segment_duration
                current_offset += segment_duration
                last_end = round_to_frame(silence_times[0], source_fps, timeline_fps)
                clip_count += 1
            
            # 無音部分の間のセグメント
            for i in range(0, len(silence_times)-1, 2):
                if i + 1 < len(silence_times):
                    silence_start, silence_end = silence_times[i], silence_times[i+1]
                    
                    # 次の無音部分までのセグメント
                    if i + 2 < len(silence_times):
                        next_silence = silence_times[i+2]
                        if next_silence - silence_end > 0:
                            # フレーム単位に丸める
                            segment_duration = round_to_frame(next_silence - silence_end, source_fps, timeline_fps)
                            frames = round(segment_duration * timeline_fps)
                            start_time = round_to_frame(last_end, source_fps, timeline_fps)
                            
                            clip = ET.SubElement(spine, "asset-clip")
                            clip.set("ref", video_id)
                            clip.set("offset", f"{int(current_offset * timeline_fps)}/{int(timeline_fps)}s")
                            clip.set("duration", f"{frames}/{int(timeline_fps)}s")
                            clip.set("start", f"{int(start_time * timeline_fps)}/{int(timeline_fps)}s")
                            clip.set("name", video_name)
                            clip.set("format", format_id)
                            clip.set("tcFormat", "NDF")
                            clip.set("enabled", "1")
                            clip.set("lane", "1")
                            
                            # トランスフォーム情報を追加
                            transform = ET.SubElement(clip, "adjust-transform")
                            transform.set("scale", "1 1")
                            transform.set("anchor", "0 0")
                            transform.set("position", "0 0")
                            
                            total_duration += segment_duration
                            current_offset += segment_duration
                            last_end = round_to_frame(next_silence, source_fps, timeline_fps)
                            clip_count += 1
            
            # 最後の無音部分より後のセグメント
            if silence_times[-1] < duration:
                # フレーム単位に丸める
                segment_duration = round_to_frame(duration - silence_times[-1], source_fps, timeline_fps)
                frames = round(segment_duration * timeline_fps)
                start_time = round_to_frame(last_end, source_fps, timeline_fps)
                
                clip = ET.SubElement(spine, "asset-clip")
                clip.set("ref", video_id)
                clip.set("offset", f"{int(current_offset * timeline_fps)}/{int(timeline_fps)}s")
                clip.set("duration", f"{frames}/{int(timeline_fps)}s")
                clip.set("start", f"{int(start_time * timeline_fps)}/{int(timeline_fps)}s")
                clip.set("name", video_name)
                clip.set("format", format_id)
                clip.set("tcFormat", "NDF")
                clip.set("enabled", "1")
                clip.set("lane", "1")
                
                # トランスフォーム情報を追加
                transform = ET.SubElement(clip, "adjust-transform")
                transform.set("scale", "1 1")
                transform.set("anchor", "0 0")
                transform.set("position", "0 0")
                
                total_duration += segment_duration
                clip_count += 1
            
            # シーケンスの長さを設定（フレーム単位で正確に計算）
            total_frames = round(total_duration * timeline_fps)
            sequence.set("duration", f"{total_frames}/{int(timeline_fps)}s")
            
            # デバッグ情報
            st.write(f"生成されたクリップ数: {clip_count}")
            st.write(f"総再生時間: {total_duration:.2f}秒")
        else:
            # 無音部分が見つからない場合は全体を1つのセグメントとして扱う
            frames = round(duration * timeline_fps)
            clip = ET.SubElement(spine, "asset-clip")
            clip.set("ref", video_id)
            clip.set("offset", "3600/1s")
            clip.set("duration", f"{frames}/{int(timeline_fps)}s")
            clip.set("start", "0/1s")
            clip.set("name", video_name)
            clip.set("format", format_id)
            clip.set("tcFormat", "NDF")
            clip.set("enabled", "1")
            clip.set("lane", "1")
            
            # トランスフォーム情報を追加
            transform = ET.SubElement(clip, "adjust-transform")
            transform.set("scale", "1 1")
            transform.set("anchor", "0 0")
            transform.set("position", "0 0")
            
            # シーケンスの長さを設定
            sequence.set("duration", f"{frames}/{int(timeline_fps)}s")
            
            # デバッグ情報
            st.write("無音部分が見つからなかったため、1つのクリップとして生成")
        
        # XMLをファイルに保存
        tree = ET.ElementTree(root)
        tree.write(output_path, encoding='utf-8', xml_declaration=True)
        
        return True
    except Exception as e:
        st.error(f"FCPXMLの生成中にエラーが発生しました: {str(e)}")
        return False

def main():
    st.title("FCPXML出力テスト")
    
    # 動画ファイル選択
    video_files = list(Path(".").glob("*.mp4"))
    if not video_files:
        st.warning("動画ファイルが見つかりません")
        return
    
    selected_video = st.selectbox(
        "動画ファイルを選択",
        options=video_files,
        format_func=lambda x: str(x.resolve())
    )
    
    # 無音検出のパラメータ
    st.subheader("無音検出の設定")
    noise_threshold = st.slider(
        "無音検出の閾値 (dB)",
        min_value=-50,
        max_value=-20,
        value=-45,  # 閾値を下げて、より小さな音も検出
        step=1
    )
    min_silence_duration = st.slider(
        "最小無音時間 (秒)",
        min_value=0.1,
        max_value=1.0,
        value=0.3,  # 最小無音時間を短くして、より短い無音も検出
        step=0.1
    )
    
    if st.button("FCPXMLを生成", type="primary"):
        with st.spinner("処理中..."):
            # 無音部分を検出
            silence_times = detect_silence(
                selected_video,
                noise_threshold=noise_threshold,
                min_silence_duration=min_silence_duration
            )
            
            if silence_times:
                st.info(f"無音部分を{len(silence_times)//2}箇所検出しました")
                
                # デバッグ情報を表示
                with st.expander("デバッグ情報"):
                    st.write("検出された無音部分:")
                    for i in range(0, len(silence_times), 2):
                        if i + 1 < len(silence_times):
                            start = silence_times[i]
                            end = silence_times[i+1]
                            duration = end - start
                            st.write(f"無音 {i//2 + 1}: {start:.3f}s - {end:.3f}s (長さ: {duration:.3f}秒)")
                
                # FCPXMLを生成
                output_path = Path("output") / f"{selected_video.stem}_no_silence.fcpxml"
                output_path.parent.mkdir(exist_ok=True)
                
                if create_fcpxml(selected_video, silence_times, output_path):
                    st.success(f"FCPXMLを生成しました: {output_path}")
            else:
                st.warning("無音部分が見つかりませんでした")

if __name__ == "__main__":
    main() 