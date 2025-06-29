"""
動画処理ゲートウェイインターフェース
"""

from typing import Protocol, List, Tuple, Optional, Callable
from domain.value_objects import FilePath, TimeRange, Duration


class IVideoProcessorGateway(Protocol):
    """動画処理機能へのゲートウェイ"""
    
    def extract_audio_segments(
        self,
        video_path: FilePath,
        time_ranges: List[TimeRange],
        output_dir: Optional[FilePath] = None
    ) -> List[FilePath]:
        """
        指定された時間範囲の音声セグメントを抽出
        
        Args:
            video_path: 動画ファイルパス
            time_ranges: 抽出する時間範囲
            output_dir: 出力ディレクトリ（Noneの場合は一時ディレクトリ）
            
        Returns:
            抽出された音声ファイルのパスリスト
            
        Raises:
            AudioExtractionError: 音声抽出失敗
        """
        ...
    
    def detect_silence(
        self,
        audio_path: FilePath,
        threshold: float = -35.0,
        min_silence_duration: float = 0.3,
        min_segment_duration: float = 0.3
    ) -> List[TimeRange]:
        """
        音声から無音部分を検出
        
        Args:
            audio_path: 音声ファイルパス
            threshold: 無音判定の閾値（dB）
            min_silence_duration: 最小無音時間（秒）
            min_segment_duration: 最小セグメント時間（秒）
            
        Returns:
            無音部分の時間範囲リスト
            
        Raises:
            SilenceDetectionError: 無音検出失敗
        """
        ...
    
    def calculate_keep_ranges(
        self,
        total_duration: Duration,
        silence_ranges: List[TimeRange],
        padding_start: float = 0.1,
        padding_end: float = 0.1
    ) -> List[TimeRange]:
        """
        無音部分を除いた残す部分の時間範囲を計算
        
        Args:
            total_duration: 全体の長さ
            silence_ranges: 無音部分の時間範囲
            padding_start: セグメント開始のパディング（秒）
            padding_end: セグメント終了のパディング（秒）
            
        Returns:
            残す部分の時間範囲リスト
        """
        ...
    
    def extract_segments(
        self,
        video_path: FilePath,
        time_ranges: List[TimeRange],
        output_dir: Optional[FilePath] = None,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> List[FilePath]:
        """
        指定された時間範囲の動画セグメントを抽出
        
        Args:
            video_path: 動画ファイルパス
            time_ranges: 抽出する時間範囲
            output_dir: 出力ディレクトリ
            progress_callback: 進捗通知用コールバック（0.0-1.0）
            
        Returns:
            抽出された動画ファイルのパスリスト
        """
        ...
    
    def combine_segments(
        self,
        segment_paths: List[FilePath],
        output_path: FilePath,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> None:
        """
        複数の動画セグメントを結合
        
        Args:
            segment_paths: 結合するセグメントのパス
            output_path: 出力ファイルパス
            progress_callback: 進捗通知用コールバック
            
        Raises:
            SegmentCombineError: セグメント結合失敗
        """
        ...
    
    def get_video_info(
        self,
        video_path: FilePath
    ) -> dict:
        """
        動画の情報を取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            動画情報（duration, fps, width, height等）
        """
        ...
    
    def create_thumbnail(
        self,
        video_path: FilePath,
        time: float,
        output_path: FilePath,
        width: Optional[int] = None,
        height: Optional[int] = None
    ) -> None:
        """
        指定時刻のサムネイルを生成
        
        Args:
            video_path: 動画ファイルパス
            time: サムネイルを取得する時刻（秒）
            output_path: 出力画像パス
            width: 幅（Noneの場合は元のサイズ）
            height: 高さ（Noneの場合は元のサイズ）
        """
        ...