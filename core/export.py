"""
エクスポート処理モジュール（FCPXML、EDL、SRT等）
"""
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from xml.etree import ElementTree as ET

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
            
        except Exception as e:
            print(f"FCPXMLエクスポートエラー: {e}")
            return False
    
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
            
            xml_content += f'''        <asset format="r0" name="{Path(path).name}" audioChannels="2" duration="{duration_frames}/{timeline_fps}s" audioSources="1" id="{resource_id}" hasVideo="1" hasAudio="1" start="0/1s">
            <media-rep src="file://{Path(path).resolve()}" kind="original-media"/>
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


class SRTExporter:
    """SRT字幕エクスポートクラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.text_processor = TextProcessor()
    
    def export(
        self,
        transcription: TranscriptionResult,
        segments: List[VideoSegment],
        output_path: str,
        chars_per_line: Optional[int] = None,
        max_lines: Optional[int] = None,
        fps: Optional[float] = None,
        max_duration: Optional[float] = None
    ) -> bool:
        """
        SRT字幕ファイルをエクスポート
        
        Args:
            transcription: 文字起こし結果
            segments: 対象セグメント（時間範囲）
            output_path: 出力ファイルパス
            chars_per_line: 1行あたりの最大文字数
            max_lines: 最大行数
            
        Returns:
            成功したかどうか
        """
        try:
            chars_per_line = chars_per_line or self.config.ui.chars_per_line
            max_lines = max_lines or self.config.ui.max_subtitle_lines
            
            print(f"SRTExporter.export: 1行{chars_per_line}文字 × {max_lines}行, FPS: {fps}, 最大時間: {max_duration}で処理開始")
            
            # 字幕エントリを生成
            entries = self._generate_subtitle_entries(
                transcription, segments, chars_per_line, max_lines, fps, max_duration
            )
            
            print(f"SRTエクスポート: 全体で{len(entries)}個の字幕エントリ")
            
            # 字幕の時間範囲を確認
            if entries:
                first_time = entries[0]['start']
                last_time = entries[-1]['end']
                print(f"字幕の時間範囲: {first_time} ～ {last_time}")
            
            # SRTファイルに書き込み
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                for i, entry in enumerate(entries, 1):
                    f.write(f"{i}\n")
                    f.write(f"{entry['start']} --> {entry['end']}\n")
                    f.write('\n'.join(entry['lines']) + '\n\n')
                    
                    # デバッグ：最初の3つと最後のエントリを表示
                    if i <= 3 or i == len(entries):
                        print(f"字幕{i}: {entry['start']} --> {entry['end']}")
                        print(f"  内容: {entry['lines']}")
            
            return True
            
        except Exception as e:
            print(f"SRTエクスポートエラー: {e}")
            return False
    
    def _split_long_segment(
        self,
        text: str,
        start_time: float,
        end_time: float,
        chars_per_line: int,
        max_lines: int,
        fps: Optional[float] = None
    ) -> List[Dict]:
        """長いセグメントを適切な字幕サイズに分割"""
        entries = []
        
        # 1画面あたりの最大文字数
        max_chars_per_subtitle = chars_per_line * max_lines
        
        # デバッグ情報
        print(f"字幕分割: 1行{chars_per_line}文字 × {max_lines}行 = 最大{max_chars_per_subtitle}文字/画面")
        print(f"セグメント: {start_time:.1f}s-{end_time:.1f}s, テキスト長: {len(text)}文字")
        
        # 日本語の場合は文字単位で処理
        text = text.strip()
        total_chars = len(text)
        
        if total_chars == 0:
            return entries
        
        # セグメントの継続時間
        duration = end_time - start_time
        
        # テキストを適切なサイズに分割
        current_pos = 0
        
        while current_pos < total_chars:
            # 次の字幕の終了位置を計算
            end_pos = min(current_pos + max_chars_per_subtitle, total_chars)
            
            # 句読点で区切りを調整（より自然な分割のため）
            if end_pos < total_chars:
                # 句読点を探す
                for punct in ['。', '！', '？', '、']:
                    punct_pos = text.rfind(punct, current_pos, end_pos)
                    if punct_pos > current_pos:
                        end_pos = punct_pos + 1
                        break
            
            # 字幕テキストを抽出
            subtitle_text = text[current_pos:end_pos].strip()
            
            # デバッグ情報
            print(f"字幕分割 {len(entries)+1}: 位置 {current_pos}-{end_pos}, テキスト: '{subtitle_text}'")
            
            if subtitle_text:
                # 時間を計算（文字数に比例）
                subtitle_start = start_time + (current_pos / total_chars) * duration
                subtitle_end = start_time + (end_pos / total_chars) * duration
                
                # 行に分割
                lines = self.text_processor.split_text_into_lines(
                    subtitle_text,
                    chars_per_line,
                    max_lines
                )
                
                print(f"  行分割結果: {lines}")
                
                if lines:
                    entries.append({
                        'start': format_timestamp(subtitle_start, fps),
                        'end': format_timestamp(subtitle_end, fps),
                        'lines': lines
                    })
                else:
                    print(f"  警告: 行分割で空の結果")
            
            current_pos = end_pos
        
        print(f"分割結果: {len(entries)}個の字幕エントリを生成")
        return entries
    
    def _generate_subtitle_entries(
        self,
        transcription: TranscriptionResult,
        segments: List[VideoSegment],
        chars_per_line: int,
        max_lines: int,
        fps: Optional[float] = None,
        max_duration: Optional[float] = None
    ) -> List[Dict]:
        """字幕エントリを生成"""
        entries = []
        
        # 単一セグメントで全体をカバーする場合（結合音声から生成）
        if len(segments) == 1 and segments[0].start == 0:
            # 時間調整なしで直接使用
            for trans_seg in transcription.segments:
                # 最大時間を超える場合はスキップ
                if max_duration and trans_seg.start >= max_duration:
                    break
                
                # セグメントの終了時間を制限
                seg_end = trans_seg.end
                if max_duration and seg_end > max_duration:
                    seg_end = max_duration
                
                # 長いセグメントは分割
                segment_entries = self._split_long_segment(
                    trans_seg.text.strip(),
                    trans_seg.start,
                    seg_end,
                    chars_per_line,
                    max_lines,
                    fps
                )
                entries.extend(segment_entries)
        else:
            # 複数セグメントの場合は既存のロジックを使用
            for segment in segments:
                # セグメント内の文字起こしを抽出
                for trans_seg in transcription.segments:
                    # セグメントが時間範囲と重なる場合
                    if trans_seg.end > segment.start and trans_seg.start < segment.end:
                        # 時間を調整
                        start_time = max(trans_seg.start, segment.start) - segment.start
                        end_time = min(trans_seg.end, segment.end) - segment.start
                        
                        # 長いセグメントは分割
                        segment_entries = self._split_long_segment(
                            trans_seg.text.strip(),
                            start_time,
                            end_time,
                            chars_per_line,
                            max_lines,
                            fps
                        )
                        entries.extend(segment_entries)
        
        return entries


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
            
        except Exception as e:
            print(f"EDLエクスポートエラー: {e}")
            return False