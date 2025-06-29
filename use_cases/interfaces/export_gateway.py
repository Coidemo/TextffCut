"""
エクスポートゲートウェイインターフェース
"""

from typing import Protocol, List, Optional, Dict, Any, Tuple
from domain.entities import TranscriptionResult, VideoSegment
from domain.value_objects import FilePath, TimeRange


class ExportSegment:
    """エクスポート用のセグメント情報"""
    def __init__(
        self,
        video_path: FilePath,
        time_range: TimeRange,
        label: Optional[str] = None
    ):
        self.video_path = video_path
        self.time_range = time_range
        self.label = label


class TimeMapper:
    """時間マッピングユーティリティ"""
    def __init__(self, silence_ranges: List[TimeRange]):
        self.silence_ranges = silence_ranges
    
    def map_time_range(self, time_range: TimeRange) -> Optional[TimeRange]:
        """時間範囲をマッピング"""
        # 実装はアダプター層で行う
        pass


class IExportGateway(Protocol):
    """エクスポート機能の基本インターフェース"""
    
    def export(
        self,
        segments: List[ExportSegment],
        output_path: FilePath,
        **options: Any
    ) -> None:
        """
        セグメントをエクスポート
        
        Args:
            segments: エクスポートするセグメント
            output_path: 出力ファイルパス
            **options: エクスポートオプション
            
        Raises:
            ExportError: エクスポート失敗
        """
        ...
    
    def get_video_info(self, video_path: FilePath) -> Dict[str, Any]:
        """動画情報を取得"""
        ...
    
    def generate_fcpxml(
        self,
        timeline_name: str,
        asset: Any,  # FCPXMLAsset
        clips: List[Any],  # List[FCPXMLClip]
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """FCPXMLコンテンツを生成"""
        ...
    
    def create_time_mapper(self, silence_ranges: List[TimeRange]) -> TimeMapper:
        """時間マッピングユーティリティを作成"""
        ...


class IFCPXMLExportGateway(IExportGateway, Protocol):
    """Final Cut Pro XML エクスポートゲートウェイ"""
    
    def export(
        self,
        segments: List[ExportSegment],
        output_path: FilePath,
        project_name: str = "TextffCut Project",
        fps: float = 30.0,
        width: int = 1920,
        height: int = 1080,
        **options: Any
    ) -> None:
        """
        FCPXMLファイルをエクスポート
        
        Args:
            segments: エクスポートするセグメント
            output_path: 出力ファイルパス
            project_name: プロジェクト名
            fps: フレームレート
            width: 動画の幅
            height: 動画の高さ
        """
        ...


class IPremiereXMLExportGateway(IExportGateway, Protocol):
    """Premiere Pro XML エクスポートゲートウェイ"""
    
    def export(
        self,
        segments: List[ExportSegment],
        output_path: FilePath,
        project_name: str = "TextffCut Project",
        fps: float = 30.0,
        width: int = 1920,
        height: int = 1080,
        audio_channels: int = 2,
        **options: Any
    ) -> None:
        """
        Premiere Pro用XMLファイルをエクスポート
        
        Args:
            segments: エクスポートするセグメント
            output_path: 出力ファイルパス
            project_name: プロジェクト名
            fps: フレームレート
            width: 動画の幅
            height: 動画の高さ
            audio_channels: オーディオチャンネル数
        """
        ...


class ISRTExportGateway(Protocol):
    """SRT字幕エクスポートゲートウェイ"""
    
    def export_from_transcription(
        self,
        transcription_result: TranscriptionResult,
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2,
        min_duration: float = 0.5,
        max_duration: float = 7.0
    ) -> None:
        """
        文字起こし結果からSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
            min_duration: 最小表示時間（秒）
            max_duration: 最大表示時間（秒）
        """
        ...
    
    def export_from_diff(
        self,
        transcription_result: TranscriptionResult,
        time_ranges: List[TimeRange],
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2,
        min_duration: float = 0.5,
        max_duration: float = 7.0
    ) -> None:
        """
        差分結果からSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            time_ranges: 出力する時間範囲
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
            min_duration: 最小表示時間（秒）
            max_duration: 最大表示時間（秒）
        """
        ...
    
    def export_with_time_mapping(
        self,
        transcription_result: TranscriptionResult,
        time_mapping: List[Tuple[TimeRange, TimeRange]],
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2
    ) -> None:
        """
        時間マッピングを適用してSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            time_mapping: 元の時間→新しい時間のマッピング
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
        """
        ...