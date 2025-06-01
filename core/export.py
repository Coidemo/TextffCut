"""
エクスポート処理モジュール（FCPXML、EDL、SRT等）
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from xml.etree import ElementTree as ET
import os

from config import Config
from utils.time_utils import format_timestamp, frames_to_timecode
from .transcription import TranscriptionResult
from .text_processor import TextProcessor
from .video import VideoInfo, VideoSegment


@dataclass
class ExportSegment:
    """エクスポート用セグメント情報"""
    source_path: str
    start_time: float
    end_time: float
    timeline_start: float
    
    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class FCPXMLExporter:
    """FCPXMLエクスポートクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        
    def export(
        self,
        segments: List[ExportSegment],
        output_path: str,
        timeline_fps: int = 30,
        project_name: str = "Buzz Clip Project"
    ) -> bool:
        """
        FCPXMLファイルをエクスポート
        
        Args:
            segments: エクスポートするセグメントのリスト
            output_path: 出力ファイルパス
            timeline_fps: タイムラインのFPS
            project_name: プロジェクト名
            
        Returns:
            成功したかどうか
        """
        try:
            # 動画情報を取得
            video_infos = {}
            for seg in segments:
                if seg.source_path not in video_infos:
                    video_infos[seg.source_path] = VideoInfo.from_file(seg.source_path)
            
            # XMLを構築
            xml_content = self._build_fcpxml(
                segments, video_infos, timeline_fps, project_name
            )
            
            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            return True
            
        except OSError as e:
            from utils.exceptions import FileNotFoundError as BuzzFileNotFoundError
            raise BuzzFileNotFoundError(f"FCPXML書き込みエラー: {str(e)}")
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"FCPXML書き込み権限エラー: {str(e)}")
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"FCPXMLエクスポートエラー: {str(e)}")
    
    def _build_fcpxml(
        self,
        segments: List[ExportSegment],
        video_infos: Dict[str, VideoInfo],
        timeline_fps: int,
        project_name: str
    ) -> str:
        """FCPXMLコンテンツを構築"""
        # 総時間を計算
        total_duration = sum(seg.duration for seg in segments)
        total_frames = int(total_duration * timeline_fps)
        
        # XMLヘッダー
        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
    <resources>
        <format width="1920" name="FFVideoFormat1080p{timeline_fps}" id="r0" height="1080" frameDuration="1/{timeline_fps}s"/>
'''
        
        # リソース（使用する動画ファイル）を追加
        resource_map = {}
        for i, (path, info) in enumerate(video_infos.items(), 1):
            resource_id = f"r{i}"
            resource_map[path] = resource_id
            
            # 動画の総フレーム数
            duration_frames = int(info.duration * timeline_fps)
            
            # Docker環境の場合はホストパスに変換
            if os.path.exists('/.dockerenv'):
                # /app/videos/xxx.mp4 -> HOST_VIDEOS_PATH/xxx.mp4
                video_filename = Path(path).name
                host_videos_path = os.getenv('HOST_VIDEOS_PATH', '/path/to/videos')
                file_url = f"file://{os.path.join(host_videos_path, video_filename)}"
            else:
                # ローカル環境は通常通り
                file_url = f"file://{Path(path).resolve()}"
            
            xml_content += f'''        <asset format="r0" name="{Path(path).name}" audioChannels="2" duration="{duration_frames}/{timeline_fps}s" audioSources="1" id="{resource_id}" hasVideo="1" hasAudio="1" start="0/1s">
            <media-rep src="{file_url}" kind="original-media"/>
        </asset>
'''
        
        xml_content += '''    </resources>
    <library>
        <event name="Buzz Clip Event">
            <project name="''' + project_name + '''">
                <sequence tcFormat="NDF" format="r0" duration="''' + f"{total_frames}/{timeline_fps}s" + '''" tcStart="0/1s">
                    <spine>
'''
        
        # クリップを追加
        current_timeline_pos = 0
        
        for i, seg in enumerate(segments, 1):
            resource_id = resource_map[seg.source_path]
            info = video_infos[seg.source_path]
            
            # フレーム単位で計算
            start_frames = int(seg.start_time * info.fps)
            duration_frames = int(seg.duration * timeline_fps)
            
            # タイムラインのFPSに合わせて変換
            timeline_start_frames = int(start_frames * (timeline_fps / info.fps))
            
            xml_content += f'''                        <asset-clip tcFormat="NDF" offset="{current_timeline_pos}/{timeline_fps}s" format="r0" name="Segment {i}" duration="{duration_frames}/{timeline_fps}s" ref="{resource_id}" enabled="1" start="{timeline_start_frames}/{timeline_fps}s">
                            <adjust-transform scale="1 1" anchor="0 0" position="0 0"/>
                        </asset-clip>
'''
            
            current_timeline_pos += duration_frames
        
        xml_content += '''                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>'''
        
        return xml_content




class EDLExporter:
    """EDL（Edit Decision List）エクスポートクラス"""
    
    def __init__(self, config: Config):
        self.config = config
    
    def export(
        self,
        segments: List[ExportSegment],
        output_path: str,
        timeline_fps: int = 30,
        title: str = "Buzz Clip EDL"
    ) -> bool:
        """
        EDLファイルをエクスポート
        
        Args:
            segments: エクスポートするセグメントのリスト
            output_path: 出力ファイルパス
            timeline_fps: タイムラインのFPS
            title: EDLタイトル
            
        Returns:
            成功したかどうか
        """
        try:
            # EDLヘッダー
            edl_content = f"TITLE: {title}\n"
            edl_content += f"FCM: NON-DROP FRAME\n\n"
            
            # 各セグメントをEDL形式で追加
            timeline_pos = 0.0
            
            for i, seg in enumerate(segments, 1):
                # タイムコードを計算
                source_in = frames_to_timecode(seg.start_time, timeline_fps)
                source_out = frames_to_timecode(seg.end_time, timeline_fps)
                record_in = frames_to_timecode(timeline_pos, timeline_fps)
                record_out = frames_to_timecode(timeline_pos + seg.duration, timeline_fps)
                
                # EDLエントリ
                edl_content += f"{i:03d}  001      V     C        "
                edl_content += f"{source_in} {source_out} "
                edl_content += f"{record_in} {record_out}\n"
                edl_content += f"* FROM CLIP NAME: {Path(seg.source_path).name}\n\n"
                
                timeline_pos += seg.duration
            
            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(edl_content)
            
            return True
            
        except OSError as e:
            from utils.exceptions import FileNotFoundError as BuzzFileNotFoundError
            raise BuzzFileNotFoundError(f"EDL書き込みエラー: {str(e)}")
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"EDL書き込み権限エラー: {str(e)}")
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"EDLエクスポートエラー: {str(e)}")