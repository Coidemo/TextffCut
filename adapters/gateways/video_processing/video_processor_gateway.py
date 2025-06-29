"""
動画処理ゲートウェイの実装

既存のVideoProcessorクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

from typing import List, Optional, Callable
from pathlib import Path

from domain.value_objects import FilePath, TimeRange, Duration
from use_cases.interfaces import IVideoProcessorGateway
from core.video import VideoProcessor as LegacyVideoProcessor
from core.video import VideoInfo as LegacyVideoInfo
from core.video import SilenceInfo as LegacySilenceInfo
from config import Config
from utils.logging import get_logger
from utils.file_utils import ensure_directory

logger = get_logger(__name__)


class VideoProcessorGatewayAdapter(IVideoProcessorGateway):
    """
    動画処理ゲートウェイのアダプター実装
    
    既存のVideoProcessorクラスをラップし、ドメイン層のインターフェースに適合させます。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初期化
        
        Args:
            config: 設定オブジェクト（Noneの場合はデフォルト設定）
        """
        self._config = config or Config()
        self._legacy_processor = LegacyVideoProcessor(self._config)
    
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
        try:
            # 時間範囲をタプル形式に変換
            time_ranges_tuples = [(tr.start, tr.end) for tr in time_ranges]
            
            # 出力ディレクトリの設定
            out_dir = Path(str(output_dir)) if output_dir else None
            
            # レガシーメソッドを呼び出し
            temp_wav_path = self._legacy_processor.extract_audio_for_ranges(
                video_path=str(video_path),
                time_ranges=time_ranges_tuples,
                output_path=out_dir
            )
            
            # 単一のWAVファイルが返されるので、リストで返す
            return [FilePath(temp_wav_path)]
            
        except Exception as e:
            logger.error(f"Failed to extract audio segments: {e}")
            from use_cases.exceptions import AudioExtractionError
            raise AudioExtractionError(
                f"Failed to extract audio segments from {video_path}: {str(e)}",
                cause=e
            )
    
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
        try:
            # レガシーメソッドを呼び出し
            silence_info_list = self._legacy_processor.detect_silence_from_wav(
                wav_path=str(audio_path),
                threshold=threshold,
                min_silence_duration=min_silence_duration,
                min_segment_duration=min_segment_duration
            )
            
            # SilenceInfoをTimeRangeに変換
            silence_ranges = []
            for silence in silence_info_list:
                try:
                    silence_ranges.append(TimeRange(
                        start=silence.start,
                        end=silence.end
                    ))
                except ValueError as e:
                    logger.warning(f"Invalid silence range: {e}")
                    continue
            
            logger.info(f"Detected {len(silence_ranges)} silence ranges")
            return silence_ranges
            
        except Exception as e:
            logger.error(f"Failed to detect silence: {e}")
            from use_cases.exceptions import SilenceDetectionError
            raise SilenceDetectionError(
                f"Failed to detect silence from {audio_path}: {str(e)}",
                cause=e
            )
    
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
        try:
            # SilenceInfoのリストに変換
            silence_info_list = [
                LegacySilenceInfo(start=sr.start, end=sr.end)
                for sr in silence_ranges
            ]
            
            # レガシーメソッドを呼び出し
            keep_segments = self._legacy_processor._calculate_keep_segments(
                silence_info_list=silence_info_list,
                duration=total_duration.seconds,
                padding_start=padding_start,
                padding_end=padding_end
            )
            
            # TimeRangeに変換
            keep_ranges = []
            for start, end in keep_segments:
                try:
                    keep_ranges.append(TimeRange(start=start, end=end))
                except ValueError as e:
                    logger.warning(f"Invalid keep range: {e}")
                    continue
            
            logger.info(f"Calculated {len(keep_ranges)} keep ranges")
            return keep_ranges
            
        except Exception as e:
            logger.error(f"Failed to calculate keep ranges: {e}")
            # エラーを再発生させずに空のリストを返す
            return []
    
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
        try:
            extracted_paths = []
            
            # 出力ディレクトリの確保
            if output_dir:
                ensure_directory(Path(str(output_dir)))
            else:
                output_dir = FilePath(Path(str(video_path)).parent)
            
            # 各セグメントを抽出
            for i, time_range in enumerate(time_ranges):
                output_filename = f"segment_{i:04d}.mp4"
                output_path = Path(str(output_dir)) / output_filename
                
                # 進捗コールバックのラッパー
                def progress_wrapper(progress: float, message: str):
                    if progress_callback:
                        # 全体の進捗として計算
                        overall_progress = (i + progress) / len(time_ranges)
                        progress_callback(overall_progress)
                
                # レガシーメソッドを呼び出し
                success = self._legacy_processor.extract_segment(
                    input_path=str(video_path),
                    start=time_range.start,
                    end=time_range.end,
                    output_path=str(output_path),
                    progress_callback=progress_wrapper
                )
                
                if success and output_path.exists():
                    extracted_paths.append(FilePath(output_path))
                else:
                    logger.warning(f"Failed to extract segment {i}: {time_range}")
            
            logger.info(f"Extracted {len(extracted_paths)} segments")
            return extracted_paths
            
        except Exception as e:
            logger.error(f"Failed to extract segments: {e}")
            from use_cases.exceptions import VideoProcessingError
            raise VideoProcessingError(
                f"Failed to extract segments from {video_path}: {str(e)}",
                cause=e
            )
    
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
        try:
            # パスを文字列のリストに変換
            segment_paths_str = [str(sp) for sp in segment_paths]
            
            # 進捗コールバックのラッパー
            def progress_wrapper(progress: float, message: str):
                if progress_callback:
                    progress_callback(progress)
            
            # レガシーメソッドを呼び出し
            success = self._legacy_processor.combine_videos(
                segments=segment_paths_str,
                output=str(output_path),
                progress_callback=progress_wrapper
            )
            
            if not success:
                raise RuntimeError("Video combination failed")
            
            logger.info(f"Combined {len(segment_paths)} segments to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to combine segments: {e}")
            from use_cases.exceptions import SegmentCombineError
            raise SegmentCombineError(
                f"Failed to combine {len(segment_paths)} segments: {str(e)}",
                cause=e
            )
    
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
        try:
            # レガシーメソッドを呼び出し
            info = LegacyVideoInfo.from_file(str(video_path))
            
            # 辞書形式に変換
            return {
                "path": info.path,
                "duration": info.duration,
                "fps": info.fps,
                "width": info.width,
                "height": info.height,
                "codec": info.codec
            }
            
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            # エラー時は最小限の情報を返す
            return {
                "path": str(video_path),
                "error": str(e)
            }
    
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
        try:
            import subprocess
            
            # 出力ディレクトリを確保
            ensure_directory(Path(str(output_path)).parent)
            
            # FFmpegコマンドを構築
            cmd = [
                "ffmpeg",
                "-y",  # 上書き確認なし
                "-ss", str(time),  # シーク時刻
                "-i", str(video_path),  # 入力
                "-vframes", "1",  # 1フレームのみ
            ]
            
            # サイズ指定がある場合
            if width or height:
                scale_filter = []
                if width:
                    scale_filter.append(f"w={width}")
                if height:
                    scale_filter.append(f"h={height}")
                cmd.extend(["-vf", f"scale={':'.join(scale_filter)}"])
            
            cmd.append(str(output_path))
            
            # 実行
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True
            )
            
            logger.info(f"Created thumbnail at {time}s from {video_path}")
            
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr}")
            raise RuntimeError(f"Failed to create thumbnail: {e.stderr}")
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            raise