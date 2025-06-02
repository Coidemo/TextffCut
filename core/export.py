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




class XMEMLExporter:
    """Premiere Pro用XMEML形式エクスポートクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        
    def export(
        self,
        segments: List[ExportSegment],
        output_path: str,
        timeline_fps: int = 30,
        project_name: str = "TextffCut Project"
    ) -> bool:
        """
        XMEMLファイルをエクスポート
        
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
            xml_content = self._build_xmeml(
                segments, video_infos, timeline_fps, project_name
            )
            
            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            return True
            
        except OSError as e:
            from utils.exceptions import FileNotFoundError as BuzzFileNotFoundError
            raise BuzzFileNotFoundError(f"XMEML書き込みエラー: {str(e)}")
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"XMEML書き込み権限エラー: {str(e)}")
        except Exception as e:
            from utils.exceptions import VideoProcessingError
            raise VideoProcessingError(f"XMEMLエクスポートエラー: {str(e)}")
    
    def _build_xmeml(
        self,
        segments: List[ExportSegment],
        video_infos: Dict[str, VideoInfo],
        timeline_fps: int,
        project_name: str
    ) -> str:
        """XMEMLコンテンツを構築（Premiere Pro完全互換）"""
        import uuid
        
        # 総時間を計算（フレーム数）
        total_duration_frames = sum(int(seg.duration * timeline_fps) for seg in segments)
        
        # XMLヘッダー
        xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
	<sequence id="sequence-1">
		<uuid>''' + str(uuid.uuid4()) + '''</uuid>
		<duration>''' + str(total_duration_frames) + '''</duration>
		<rate>
			<timebase>''' + str(timeline_fps) + '''</timebase>
			<ntsc>FALSE</ntsc>
		</rate>
		<name>''' + project_name + '''</name>
		<media>
			<video>
				<format>
					<samplecharacteristics>
						<rate>
							<timebase>''' + str(timeline_fps) + '''</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<codec>
							<name>Apple ProRes 422</name>
							<appspecificdata>
								<appname>Final Cut Pro</appname>
								<appmanufacturer>Apple Inc.</appmanufacturer>
								<appversion>7.0</appversion>
								<data>
									<qtcodec>
										<codecname>Apple ProRes 422</codecname>
										<codectypename>Apple ProRes 422</codectypename>
										<codectypecode>apcn</codectypecode>
										<codecvendorcode>appl</codecvendorcode>
										<spatialquality>1024</spatialquality>
										<temporalquality>0</temporalquality>
										<keyframerate>0</keyframerate>
										<datarate>0</datarate>
									</qtcodec>
								</data>
							</appspecificdata>
						</codec>
						<width>1920</width>
						<height>1080</height>
						<anamorphic>FALSE</anamorphic>
						<pixelaspectratio>square</pixelaspectratio>
						<fielddominance>none</fielddominance>
						<colordepth>24</colordepth>
					</samplecharacteristics>
				</format>
				<track>
'''
        
        # ビデオクリップを追加
        file_counter = 1
        file_map = {}
        video_clip_count = len(segments)
        
        for i, seg in enumerate(segments, 1):
            # ファイルIDを管理
            if seg.source_path not in file_map:
                file_map[seg.source_path] = f"file-{file_counter}"
                file_counter += 1
            
            file_id = file_map[seg.source_path]
            
            # フレーム数で計算
            start_frames = int(seg.start_time * timeline_fps)
            end_frames = int(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames
            
            # タイムライン上の位置
            timeline_start_frames = sum(int(s.duration * timeline_fps) for s in segments[:i-1])
            timeline_end_frames = timeline_start_frames + duration_frames
            
            # URLエンコードされたファイルパス
            from urllib.parse import quote
            encoded_filename = quote(Path(seg.source_path).name)
            
            # Docker環境の場合はホストパスに変換
            if os.path.exists('/.dockerenv'):
                host_videos_path = os.getenv('HOST_VIDEOS_PATH', '/path/to/videos')
                file_url = f"file://localhost{host_videos_path}/{encoded_filename}"
            else:
                file_url = f"file://localhost{Path(seg.source_path).resolve()}".replace('\\', '/')
            
            # 総ファイルduration
            total_file_duration = int(video_infos[seg.source_path].duration * timeline_fps)
            
            xml_content += f'''					<clipitem id="clipitem-{i}">
						<masterclipid>masterclip-1</masterclipid>
						<name>{Path(seg.source_path).stem}</name>
						<enabled>TRUE</enabled>
						<duration>{total_file_duration}</duration>
						<rate>
							<timebase>{timeline_fps}</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<start>{timeline_start_frames}</start>
						<end>{timeline_end_frames}</end>
						<in>{start_frames}</in>
						<out>{end_frames}</out>
						<alphatype>none</alphatype>
						<pixelaspectratio>square</pixelaspectratio>
						<anamorphic>FALSE</anamorphic>
						<file id="{file_id}">
							<name>{Path(seg.source_path).name}</name>
							<pathurl>{file_url}</pathurl>
							<rate>
								<timebase>{timeline_fps}</timebase>
								<ntsc>FALSE</ntsc>
							</rate>
							<duration>{total_file_duration}</duration>
							<timecode>
								<rate>
									<timebase>{timeline_fps}</timebase>
									<ntsc>FALSE</ntsc>
								</rate>
								<string>00:00:00:00</string>
								<frame>0</frame>
								<displayformat>NDF</displayformat>
							</timecode>
							<media>
								<video>
									<samplecharacteristics>
										<rate>
											<timebase>{timeline_fps}</timebase>
											<ntsc>FALSE</ntsc>
										</rate>
										<width>1920</width>
										<height>1080</height>
										<anamorphic>FALSE</anamorphic>
										<pixelaspectratio>square</pixelaspectratio>
										<fielddominance>none</fielddominance>
									</samplecharacteristics>
								</video>
								<audio>
									<samplecharacteristics>
										<depth>16</depth>
										<samplerate>48000</samplerate>
									</samplecharacteristics>
									<channelcount>2</channelcount>
								</audio>
							</media>
						</file>
						<link>
							<linkclipref>clipitem-{i}</linkclipref>
							<mediatype>video</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>2</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<logginginfo>
							<description></description>
							<scene></scene>
							<shottake></shottake>
							<lognote></lognote>
							<good></good>
							<originalvideofilename></originalvideofilename>
							<originalaudiofilename></originalaudiofilename>
						</logginginfo>
						<colorinfo>
							<lut></lut>
							<lut1></lut1>
							<asc_sop></asc_sop>
							<asc_sat></asc_sat>
							<lut2></lut2>
						</colorinfo>
						<labels>
							<label2>Iris</label2>
						</labels>
					</clipitem>
'''
        
        xml_content += '''					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
				</track>
			</video>
			<audio>
				<numOutputChannels>2</numOutputChannels>
				<format>
					<samplecharacteristics>
						<depth>16</depth>
						<samplerate>48000</samplerate>
					</samplecharacteristics>
				</format>
				<outputs>
					<group>
						<index>1</index>
						<numchannels>1</numchannels>
						<downmix>0</downmix>
						<channel>
							<index>1</index>
						</channel>
					</group>
					<group>
						<index>2</index>
						<numchannels>1</numchannels>
						<downmix>0</downmix>
						<channel>
							<index>2</index>
						</channel>
					</group>
				</outputs>
'''
        
        # オーディオトラック1を追加
        xml_content += '''				<track currentExplodedTrackIndex="0" totalExplodedTrackCount="2" premiereTrackType="Stereo">
'''
        
        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]
            
            # フレーム数で計算（ビデオと同じ）
            start_frames = int(seg.start_time * timeline_fps)
            end_frames = int(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames
            
            # タイムライン上の位置
            timeline_start_frames = sum(int(s.duration * timeline_fps) for s in segments[:i-1])
            timeline_end_frames = timeline_start_frames + duration_frames
            
            # 総ファイルduration
            total_file_duration = int(video_infos[seg.source_path].duration * timeline_fps)
            
            xml_content += f'''					<clipitem id="clipitem-{video_clip_count + i}" premiereChannelType="stereo">
						<masterclipid>masterclip-1</masterclipid>
						<name>{Path(seg.source_path).stem}</name>
						<enabled>TRUE</enabled>
						<duration>{total_file_duration}</duration>
						<rate>
							<timebase>{timeline_fps}</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<start>{timeline_start_frames}</start>
						<end>{timeline_end_frames}</end>
						<in>{start_frames}</in>
						<out>{end_frames}</out>
						<file id="{file_id}"/>
						<sourcetrack>
							<mediatype>audio</mediatype>
							<trackindex>1</trackindex>
						</sourcetrack>
						<link>
							<linkclipref>clipitem-{i}</linkclipref>
							<mediatype>video</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>2</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<logginginfo>
							<description></description>
							<scene></scene>
							<shottake></shottake>
							<lognote></lognote>
							<good></good>
							<originalvideofilename></originalvideofilename>
							<originalaudiofilename></originalaudiofilename>
						</logginginfo>
						<colorinfo>
							<lut></lut>
							<lut1></lut1>
							<asc_sop></asc_sop>
							<asc_sat></asc_sat>
							<lut2></lut2>
						</colorinfo>
						<labels>
							<label2>Iris</label2>
						</labels>
					</clipitem>
'''
        
        xml_content += '''					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>1</outputchannelindex>
				</track>
'''
        
        # オーディオトラック2を追加
        xml_content += '''				<track currentExplodedTrackIndex="1" totalExplodedTrackCount="2" premiereTrackType="Stereo">
'''
        
        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]
            
            # フレーム数で計算（ビデオと同じ）
            start_frames = int(seg.start_time * timeline_fps)
            end_frames = int(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames
            
            # タイムライン上の位置
            timeline_start_frames = sum(int(s.duration * timeline_fps) for s in segments[:i-1])
            timeline_end_frames = timeline_start_frames + duration_frames
            
            # 総ファイルduration
            total_file_duration = int(video_infos[seg.source_path].duration * timeline_fps)
            
            xml_content += f'''					<clipitem id="clipitem-{video_clip_count * 2 + i}" premiereChannelType="stereo">
						<masterclipid>masterclip-1</masterclipid>
						<name>{Path(seg.source_path).stem}</name>
						<enabled>TRUE</enabled>
						<duration>{total_file_duration}</duration>
						<rate>
							<timebase>{timeline_fps}</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<start>{timeline_start_frames}</start>
						<end>{timeline_end_frames}</end>
						<in>{start_frames}</in>
						<out>{end_frames}</out>
						<file id="{file_id}"/>
						<sourcetrack>
							<mediatype>audio</mediatype>
							<trackindex>2</trackindex>
						</sourcetrack>
						<link>
							<linkclipref>clipitem-{i}</linkclipref>
							<mediatype>video</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>2</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<logginginfo>
							<description></description>
							<scene></scene>
							<shottake></shottake>
							<lognote></lognote>
							<good></good>
							<originalvideofilename></originalvideofilename>
							<originalaudiofilename></originalaudiofilename>
						</logginginfo>
						<colorinfo>
							<lut></lut>
							<lut1></lut1>
							<asc_sop></asc_sop>
							<asc_sat></asc_sat>
							<lut2></lut2>
						</colorinfo>
						<labels>
							<label2>Iris</label2>
						</labels>
					</clipitem>
'''
        
        xml_content += '''					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>2</outputchannelindex>
				</track>
			</audio>
		</media>
		<timecode>
			<rate>
				<timebase>''' + str(timeline_fps) + '''</timebase>
				<ntsc>FALSE</ntsc>
			</rate>
			<string>00:00:00:00</string>
			<frame>0</frame>
			<displayformat>NDF</displayformat>
		</timecode>
		<labels>
			<label2>Forest</label2>
		</labels>
		<logginginfo>
			<description></description>
			<scene></scene>
			<shottake></shottake>
			<lognote></lognote>
			<good></good>
			<originalvideofilename></originalvideofilename>
			<originalaudiofilename></originalaudiofilename>
		</logginginfo>
	</sequence>
</xmeml>'''
        
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