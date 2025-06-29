"""
SRT字幕エクスポートユースケース
"""

from dataclasses import dataclass
from typing import List, Optional, Callable, Tuple
from datetime import timedelta

from domain.value_objects import FilePath, TimeRange
from domain.entities import TranscriptionResult, TranscriptionSegment
from use_cases.base import UseCase
from use_cases.exceptions import ExportError
from use_cases.interfaces import IExportGateway, IFileGateway


@dataclass
class ExportSRTRequest:
    """SRTエクスポートリクエスト"""
    transcription: TranscriptionResult
    output_path: FilePath
    time_ranges: Optional[List[TimeRange]] = None
    max_chars_per_line: int = 40
    max_lines: int = 2
    remove_silence: bool = False
    silence_ranges: Optional[List[TimeRange]] = None
    progress_callback: Optional[Callable[[float], None]] = None
    
    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.output_path, FilePath):
            self.output_path = FilePath(str(self.output_path))


@dataclass
class SubtitleEntry:
    """字幕エントリ"""
    index: int
    start_time: float
    end_time: float
    text: str
    lines: List[str]
    
    @property
    def duration(self) -> float:
        """字幕の表示時間"""
        return self.end_time - self.start_time
    
    def to_srt_format(self) -> str:
        """SRT形式に変換"""
        start = self._format_time(self.start_time)
        end = self._format_time(self.end_time)
        text = "\n".join(self.lines)
        return f"{self.index}\n{start} --> {end}\n{text}"
    
    def _format_time(self, seconds: float) -> str:
        """時間をSRT形式（HH:MM:SS,mmm）に変換"""
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int((seconds - total_seconds) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


@dataclass
class ExportSRTResponse:
    """SRTエクスポートレスポンス"""
    output_path: FilePath
    entries: List[SubtitleEntry]
    total_entries: int
    total_duration: float
    filtered_segments: int
    
    @property
    def average_duration(self) -> float:
        """平均字幕表示時間"""
        if not self.entries:
            return 0.0
        return sum(e.duration for e in self.entries) / len(self.entries)


class ExportSRTUseCase(UseCase[ExportSRTRequest, ExportSRTResponse]):
    """
    SRT字幕ファイルをエクスポートするユースケース
    
    文字起こし結果からSRT形式の字幕ファイルを生成します。
    時間範囲フィルタリングや無音削除時の時間調整をサポートします。
    """
    
    def __init__(
        self,
        export_gateway: IExportGateway,
        file_gateway: IFileGateway
    ):
        super().__init__()
        self.export_gateway = export_gateway
        self.file_gateway = file_gateway
    
    def validate_request(self, request: ExportSRTRequest) -> None:
        """リクエストのバリデーション"""
        # 文字起こし結果の確認
        if not request.transcription.segments:
            raise ExportError("No transcription segments to export")
        
        # 出力パスの親ディレクトリ確認
        output_parent = request.output_path.parent
        if not output_parent.exists:
            self.logger.info(f"Creating output directory: {output_parent}")
            output_parent.ensure_parent_exists()
        
        # 拡張子の確認
        if not request.output_path.extension.lower() == ".srt":
            raise ExportError(
                f"Invalid output format: {request.output_path.extension}. "
                "Expected .srt"
            )
        
        # パラメータの範囲確認
        if request.max_chars_per_line <= 0:
            raise ExportError("max_chars_per_line must be positive")
        
        if request.max_lines <= 0:
            raise ExportError("max_lines must be positive")
        
        # 無音削除モードでの検証
        if request.remove_silence and not request.silence_ranges:
            raise ExportError(
                "silence_ranges required when remove_silence is True"
            )
    
    def execute(self, request: ExportSRTRequest) -> ExportSRTResponse:
        """SRTエクスポートの実行"""
        self.logger.info(
            f"Starting SRT export with {len(request.transcription.segments)} segments"
        )
        
        try:
            # 時間範囲でフィルタリング
            if request.progress_callback:
                request.progress_callback(0.1)  # 10%
            
            filtered_segments = self._filter_segments(
                request.transcription.segments,
                request.time_ranges
            )
            
            if not filtered_segments:
                raise ExportError("No segments remain after filtering")
            
            # 無音削除時の時間調整
            if request.progress_callback:
                request.progress_callback(0.3)  # 30%
            
            if request.remove_silence:
                adjusted_segments = self._adjust_for_silence_removal(
                    filtered_segments,
                    request.silence_ranges
                )
            else:
                adjusted_segments = filtered_segments
            
            # 字幕エントリの作成
            if request.progress_callback:
                request.progress_callback(0.5)  # 50%
            
            entries = self._create_subtitle_entries(
                adjusted_segments,
                request.max_chars_per_line,
                request.max_lines
            )
            
            # SRT形式のテキスト生成
            if request.progress_callback:
                request.progress_callback(0.8)  # 80%
            
            srt_content = self._generate_srt_content(entries)
            
            # ファイルへの書き込み
            self.file_gateway.write_text(
                path=request.output_path,
                content=srt_content,
                encoding="utf-8-sig"  # BOM付きUTF-8
            )
            
            # 統計情報の計算
            total_duration = max(
                (e.end_time for e in entries),
                default=0.0
            )
            
            if request.progress_callback:
                request.progress_callback(1.0)  # 100%
            
            self.logger.info(
                f"SRT export completed. "
                f"Created {len(entries)} subtitle entries "
                f"(filtered {len(request.transcription.segments) - len(filtered_segments)} segments)"
            )
            
            return ExportSRTResponse(
                output_path=request.output_path,
                entries=entries,
                total_entries=len(entries),
                total_duration=total_duration,
                filtered_segments=len(request.transcription.segments) - len(filtered_segments)
            )
            
        except Exception as e:
            self.logger.error(f"Failed to export SRT: {str(e)}")
            raise ExportError(
                f"Failed to export SRT: {str(e)}",
                cause=e
            )
    
    def _filter_segments(
        self,
        segments: List[TranscriptionSegment],
        time_ranges: Optional[List[TimeRange]]
    ) -> List[TranscriptionSegment]:
        """時間範囲でセグメントをフィルタリング"""
        if not time_ranges:
            return segments
        
        filtered = []
        for segment in segments:
            segment_range = TimeRange(segment.start, segment.end)
            for time_range in time_ranges:
                if segment_range.overlaps(time_range):
                    filtered.append(segment)
                    break
        
        return filtered
    
    def _adjust_for_silence_removal(
        self,
        segments: List[TranscriptionSegment],
        silence_ranges: List[TimeRange]
    ) -> List[TranscriptionSegment]:
        """無音削除による時間調整"""
        # TimeMapperを使用して時間マッピング
        time_mapper = self.export_gateway.create_time_mapper(
            silence_ranges=silence_ranges
        )
        
        adjusted = []
        for segment in segments:
            # セグメントの時間範囲を調整
            adjusted_range = time_mapper.map_time_range(
                TimeRange(segment.start, segment.end)
            )
            
            if adjusted_range:
                # 調整後のセグメントを作成
                adjusted_segment = TranscriptionSegment(
                    id=segment.id,  # IDを保持
                    start=adjusted_range.start,
                    end=adjusted_range.end,
                    text=segment.text,
                    words=segment.words,  # 単語情報はそのまま保持
                    chars=segment.chars   # 文字情報も保持
                )
                adjusted.append(adjusted_segment)
        
        return adjusted
    
    def _create_subtitle_entries(
        self,
        segments: List[TranscriptionSegment],
        max_chars_per_line: int,
        max_lines: int
    ) -> List[SubtitleEntry]:
        """字幕エントリを作成"""
        entries = []
        entry_index = 1
        
        # セグメントを結合可能なグループに分ける
        groups = self._group_segments(segments, max_chars_per_line * max_lines)
        
        for group in groups:
            # グループのテキストを結合
            combined_text = " ".join(seg.text.strip() for seg in group)
            
            # 行に分割
            lines = self._split_into_lines(combined_text, max_chars_per_line, max_lines)
            
            entry = SubtitleEntry(
                index=entry_index,
                start_time=group[0].start,
                end_time=group[-1].end,
                text=combined_text,
                lines=lines
            )
            entries.append(entry)
            entry_index += 1
        
        return entries
    
    def _group_segments(
        self,
        segments: List[TranscriptionSegment],
        max_chars: int
    ) -> List[List[TranscriptionSegment]]:
        """セグメントをグループ化"""
        groups = []
        current_group = []
        current_chars = 0
        
        for segment in segments:
            segment_chars = len(segment.text.strip())
            
            # 現在のグループに追加可能か確認
            # 空白を考慮（セグメント間にスペースが入る）
            space_chars = 1 if current_group else 0
            
            if current_group and current_chars + space_chars + segment_chars > max_chars:
                # グループを確定
                groups.append(current_group)
                current_group = [segment]
                current_chars = segment_chars
            else:
                current_group.append(segment)
                current_chars += space_chars + segment_chars
        
        # 最後のグループを追加
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def _split_into_lines(
        self,
        text: str,
        max_chars_per_line: int,
        max_lines: int
    ) -> List[str]:
        """テキストを行に分割"""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0
        
        for word in words:
            word_length = len(word)
            
            # 現在の行に追加可能か確認
            if current_line and current_length + word_length + 1 > max_chars_per_line:
                # 行を確定
                lines.append(" ".join(current_line))
                if len(lines) >= max_lines:
                    break
                current_line = [word]
                current_length = word_length
            else:
                current_line.append(word)
                current_length += word_length + (1 if current_line else 0)
        
        # 最後の行を追加
        if current_line and len(lines) < max_lines:
            lines.append(" ".join(current_line))
        
        return lines
    
    def _generate_srt_content(self, entries: List[SubtitleEntry]) -> str:
        """SRT形式のコンテンツを生成"""
        srt_lines = []
        for entry in entries:
            srt_lines.append(entry.to_srt_format())
        
        # エントリ間に空行を追加
        return "\n\n".join(srt_lines) + "\n"