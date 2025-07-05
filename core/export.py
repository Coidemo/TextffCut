"""
エクスポート処理モジュール（FCPXML、EDL、SRT等）
"""

import os
from dataclasses import dataclass
from pathlib import Path

from config import Config
from utils.environment import IS_DOCKER
from utils.time_utils import frames_to_timecode

from .video import VideoInfo


@dataclass
class ExportSegment:
    """エクスポート用セグメント情報"""

    source_path: str | Path
    start_time: float
    end_time: float
    timeline_start: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class FCPXMLExporter:
    """FCPXMLエクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        project_name: str = "TextffCut Project",
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
            video_infos: dict[str, VideoInfo] = {}
            for seg in segments:
                source_path_str = str(seg.source_path)
                if source_path_str not in video_infos:
                    video_infos[source_path_str] = VideoInfo.from_file(seg.source_path)

            # XMLを構築
            xml_content = self._build_fcpxml(segments, video_infos, timeline_fps, project_name)

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_content)

            return True

        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"FCPXML書き込みエラー: {str(e)}") from e
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"FCPXML書き込み権限エラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"FCPXMLエクスポートエラー: {str(e)}") from e

    def _build_fcpxml(
        self, segments: list[ExportSegment], video_infos: dict[str, VideoInfo], timeline_fps: int, project_name: str
    ) -> str:
        """FCPXMLコンテンツを構築"""
        # 総時間を計算
        total_duration = sum(seg.duration for seg in segments)
        total_frames = round(total_duration * timeline_fps)

        # XMLヘッダー
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
    <resources>
        <format width="1920" name="FFVideoFormat1080p{timeline_fps}" id="r0" height="1080"
                frameDuration="1/{timeline_fps}s"/>
"""

        # リソース（使用する動画ファイル）を追加
        resource_map = {}
        for i, (path, info) in enumerate(video_infos.items(), 1):
            resource_id = f"r{i}"
            resource_map[path] = resource_id

            # 動画の総フレーム数
            duration_frames = round(info.duration * timeline_fps)

            # Docker環境の場合はホストパスに変換
            if IS_DOCKER:
                # /app/videos/xxx.mp4 -> HOST_VIDEOS_PATH/xxx.mp4
                video_filename = Path(path).name
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                file_url = f"file://{os.path.join(host_videos_path, video_filename)}"
            else:
                # ローカル環境は通常通り
                file_url = f"file://{Path(path).resolve()}"

            xml_content += (
                f'        <asset format="r0" name="{Path(path).name}" audioChannels="2" '
                f'duration="{duration_frames}/{timeline_fps}s" audioSources="1" '
                f'id="{resource_id}" hasVideo="1" hasAudio="1" start="0/1s">\n'
                f'            <media-rep src="{file_url}" kind="original-media"/>\n'
                f"        </asset>\n"
            )

        xml_content += (
            '''    </resources>
    <library>
        <event name="TextffCut Event">
            <project name="'''
            + project_name
            + '''">
                <sequence tcFormat="NDF" format="r0" duration="'''
            + f"{total_frames}/{timeline_fps}s"
            + """" tcStart="0/1s">
                    <spine>
"""
        )

        # クリップを追加
        current_timeline_pos = 0

        for i, seg in enumerate(segments, 1):
            source_path_str = str(seg.source_path)
            resource_id = resource_map[source_path_str]
            info = video_infos[source_path_str]

            # フレーム単位で計算
            start_frames = round(seg.start_time * info.fps)
            duration_frames = round(seg.duration * timeline_fps)

            # タイムラインのFPSに合わせて変換
            timeline_start_frames = round(start_frames * (timeline_fps / info.fps))

            xml_content += (
                f'                        <asset-clip tcFormat="NDF" '
                f'offset="{current_timeline_pos}/{timeline_fps}s" format="r0" '
                f'name="Segment {i}" duration="{duration_frames}/{timeline_fps}s" '
                f'ref="{resource_id}" enabled="1" '
                f'start="{timeline_start_frames}/{timeline_fps}s">\n'
                f'                            <adjust-transform scale="1 1" anchor="0 0" position="0 0"/>\n'
                f"                        </asset-clip>\n"
            )

            current_timeline_pos += duration_frames

        xml_content += """                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""

        return xml_content


class XMEMLExporter:
    """Premiere Pro用XMEML形式エクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        project_name: str = "TextffCut Project",
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
            video_infos: dict[str, VideoInfo] = {}
            for seg in segments:
                source_path_str = str(seg.source_path)
                if source_path_str not in video_infos:
                    video_infos[source_path_str] = VideoInfo.from_file(seg.source_path)

            # XMLを構築
            xml_content = self._build_xmeml(segments, video_infos, timeline_fps, project_name)

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_content)

            return True

        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"XMEML書き込みエラー: {str(e)}") from e
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"XMEML書き込み権限エラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"XMEMLエクスポートエラー: {str(e)}") from e

    def _build_xmeml(
        self, segments: list[ExportSegment], video_infos: dict[str, VideoInfo], timeline_fps: int, project_name: str
    ) -> str:
        """XMEMLコンテンツを構築（Premiere Pro完全互換）"""
        import uuid

        # 総時間を計算（フレーム数）
        total_duration_frames = sum(round(seg.duration * timeline_fps) for seg in segments)

        # XMLヘッダー
        xml_content = (
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
	<sequence id="sequence-1">
		<uuid>"""
            + str(uuid.uuid4())
            + """</uuid>
		<duration>"""
            + str(total_duration_frames)
            + """</duration>
		<rate>
			<timebase>"""
            + str(timeline_fps)
            + """</timebase>
			<ntsc>FALSE</ntsc>
		</rate>
		<name>"""
            + project_name
            + """</name>
		<media>
			<video>
				<format>
					<samplecharacteristics>
						<rate>
							<timebase>"""
            + str(timeline_fps)
            + """</timebase>
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
"""
        )

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
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # URLエンコードされたファイルパス

            # ファイルパスを処理
            # Docker環境の場合はホストパスに変換
            if IS_DOCKER and str(seg.source_path).startswith("/app/videos/"):
                # Docker環境: /app/videos/xxx.mp4 -> HOST_VIDEOS_PATH/xxx.mp4
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                relative_path = str(seg.source_path).replace("/app/videos/", "")
                source_path = os.path.join(host_videos_path, relative_path)
                # Unix形式のパスに変換
                file_url = f"file://localhost{source_path}".replace("\\", "/")
            else:
                # ローカル環境: 実際のパスを使用
                source_path_resolved = Path(seg.source_path).resolve()

                # Windowsの場合はドライブレターの処理
                if os.name == "nt":
                    # C:\path\to\file -> /C:/path/to/file
                    file_url = f"file://localhost/{str(source_path_resolved)}".replace("\\", "/")
                else:
                    # Unix系: /path/to/file -> file://localhost/path/to/file
                    file_url = f"file://localhost{source_path_resolved}"

            # 総ファイルduration
            source_path_str = str(seg.source_path)
            total_file_duration = round(video_infos[source_path_str].duration * timeline_fps)

            xml_content += f"""					<clipitem id="clipitem-{i}">
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
"""

        xml_content += """					<enabled>TRUE</enabled>
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
"""

        # オーディオトラック1を追加
        xml_content += (
            '				<track currentExplodedTrackIndex="0" totalExplodedTrackCount="2" ' 'premiereTrackType="Stereo">\n'
        )

        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]

            # フレーム数で計算（ビデオと同じ）
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # 総ファイルduration
            total_file_duration = round(video_infos[str(seg.source_path)].duration * timeline_fps)

            xml_content += (
                f'					<clipitem id="clipitem-{video_clip_count + i}" '
                f'premiereChannelType="stereo">\n'
                f"						<masterclipid>masterclip-1</masterclipid>\n"
                f"						<name>{Path(seg.source_path).stem}</name>\n"
                f"						<enabled>TRUE</enabled>\n"
                f"						<duration>{total_file_duration}</duration>\n"
                f"						<rate>\n"
                f"							<timebase>{timeline_fps}</timebase>\n"
                f"							<ntsc>FALSE</ntsc>\n"
                f"						</rate>\n"
                f"						<start>{timeline_start_frames}</start>\n"
                f"						<end>{timeline_end_frames}</end>\n"
                f"						<in>{start_frames}</in>\n"
                f"						<out>{end_frames}</out>\n"
                f'						<file id="{file_id}"/>\n'
                f"						<sourcetrack>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"						</sourcetrack>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{i}</linkclipref>\n"
                f"							<mediatype>video</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<logginginfo>\n"
                f"							<description></description>\n"
                f"							<scene></scene>\n"
                f"							<shottake></shottake>\n"
                f"							<lognote></lognote>\n"
                f"							<good></good>\n"
                f"							<originalvideofilename></originalvideofilename>\n"
                f"							<originalaudiofilename></originalaudiofilename>\n"
                f"						</logginginfo>\n"
                f"						<colorinfo>\n"
                f"							<lut></lut>\n"
                f"							<lut1></lut1>\n"
                f"							<asc_sop></asc_sop>\n"
                f"							<asc_sat></asc_sat>\n"
                f"							<lut2></lut2>\n"
                f"						</colorinfo>\n"
                f"						<labels>\n"
                f"							<label2>Iris</label2>\n"
                f"						</labels>\n"
                f"					</clipitem>\n"
            )

        xml_content += """					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>1</outputchannelindex>
				</track>
"""

        # オーディオトラック2を追加
        xml_content += (
            '				<track currentExplodedTrackIndex="1" totalExplodedTrackCount="2" ' 'premiereTrackType="Stereo">\n'
        )

        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]

            # フレーム数で計算（ビデオと同じ）
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # 総ファイルduration
            total_file_duration = round(video_infos[str(seg.source_path)].duration * timeline_fps)

            xml_content += (
                f'					<clipitem id="clipitem-{video_clip_count * 2 + i}" '
                f'premiereChannelType="stereo">\n'
                f"						<masterclipid>masterclip-1</masterclipid>\n"
                f"						<name>{Path(seg.source_path).stem}</name>\n"
                f"						<enabled>TRUE</enabled>\n"
                f"						<duration>{total_file_duration}</duration>\n"
                f"						<rate>\n"
                f"							<timebase>{timeline_fps}</timebase>\n"
                f"							<ntsc>FALSE</ntsc>\n"
                f"						</rate>\n"
                f"						<start>{timeline_start_frames}</start>\n"
                f"						<end>{timeline_end_frames}</end>\n"
                f"						<in>{start_frames}</in>\n"
                f"						<out>{end_frames}</out>\n"
                f'						<file id="{file_id}"/>\n'
                f"						<sourcetrack>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"						</sourcetrack>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{i}</linkclipref>\n"
                f"							<mediatype>video</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<logginginfo>\n"
                f"							<description></description>\n"
                f"							<scene></scene>\n"
                f"							<shottake></shottake>\n"
                f"							<lognote></lognote>\n"
                f"							<good></good>\n"
                f"							<originalvideofilename></originalvideofilename>\n"
                f"							<originalaudiofilename></originalaudiofilename>\n"
                f"						</logginginfo>\n"
                f"						<colorinfo>\n"
                f"							<lut></lut>\n"
                f"							<lut1></lut1>\n"
                f"							<asc_sop></asc_sop>\n"
                f"							<asc_sat></asc_sat>\n"
                f"							<lut2></lut2>\n"
                f"						</colorinfo>\n"
                f"						<labels>\n"
                f"							<label2>Iris</label2>\n"
                f"						</labels>\n"
                f"					</clipitem>\n"
            )

        xml_content += (
            """					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>2</outputchannelindex>
				</track>
			</audio>
		</media>
		<timecode>
			<rate>
				<timebase>"""
            + str(timeline_fps)
            + """</timebase>
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
</xmeml>"""
        )

        return xml_content


class EDLExporter:
    """EDL（Edit Decision List）エクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        title: str = "TextffCut EDL",
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
            edl_content += "FCM: NON-DROP FRAME\n\n"

            # 各セグメントをEDL形式で追加
            timeline_pos = 0.0

            for i, seg in enumerate(segments, 1):
                # タイムコードを計算
                source_in = frames_to_timecode(int(seg.start_time), timeline_fps)
                source_out = frames_to_timecode(int(seg.end_time), timeline_fps)
                record_in = frames_to_timecode(int(timeline_pos), timeline_fps)
                record_out = frames_to_timecode(int(timeline_pos + seg.duration), timeline_fps)

                # EDLエントリ
                edl_content += f"{i:03d}  001      V     C        "
                edl_content += f"{source_in} {source_out} "
                edl_content += f"{record_in} {record_out}\n"
                edl_content += f"* FROM CLIP NAME: {Path(seg.source_path).name}\n\n"

                timeline_pos += seg.duration

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(edl_content)

            return True

        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"EDL書き込みエラー: {str(e)}") from e
        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"EDL書き込み権限エラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"EDLエクスポートエラー: {str(e)}") from e
