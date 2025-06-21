"""
動画処理サービス

動画の無音検出、セグメント調整、動画編集のビジネスロジックを提供。
"""

from typing import List, Tuple, Optional, Dict, Any, Callable
from pathlib import Path
import tempfile
import shutil

from .base import BaseService, ServiceResult, ValidationError, ProcessingError
from config import Config
from core.video import VideoProcessor, VideoInfo, VideoSegment
from core import TranscriptionSegment as Segment
from typing import NamedTuple

# TimeRangeの定義
class TimeRange(NamedTuple):
    start: float
    end: float
from core.constants import SilenceDetection
from utils.file_utils import ensure_directory, get_safe_filename


class VideoProcessingService(BaseService):
    """動画処理のビジネスロジック
    
    責任:
    - 無音部分の検出
    - セグメントの調整（パディング、マージ）
    - 動画の切り出しと結合
    - エクスポート用のセグメント準備
    """
    
    def _initialize(self):
        """サービス固有の初期化"""
        self.video_processor = VideoProcessor(self.config)
        self.temp_dir = Path("temp")
        ensure_directory(self.temp_dir)
    
    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド（remove_silenceにデリゲート）"""
        return self.remove_silence(**kwargs)
    
    def remove_silence(
        self,
        video_path: str,
        segments: List[Segment],
        threshold: float = SilenceDetection.DEFAULT_THRESHOLD,
        min_silence_duration: float = SilenceDetection.MIN_SILENCE_DURATION,
        pad_start: float = 0.0,
        pad_end: float = 0.0,
        min_segment_duration: float = SilenceDetection.MIN_SEGMENT_DURATION,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """無音部分を削除してセグメントを調整
        
        Args:
            video_path: 動画ファイルパス
            segments: 処理対象のセグメント
            threshold: 無音判定の閾値（dB）
            min_silence_duration: 最小無音時間（秒）
            pad_start: セグメント開始前のパディング（秒）
            pad_end: セグメント終了後のパディング（秒）
            min_segment_duration: 最小セグメント時間（秒）
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: 調整されたセグメント
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not segments:
                raise ValidationError("処理するセグメントがありません")
            
            self.logger.info(
                f"無音削除開始: {len(segments)} セグメント, "
                f"閾値: {threshold}dB, パディング: {pad_start}/{pad_end}秒"
            )
            
            # 進捗通知のラップ
            wrapped_callback = self._wrap_progress_callback(progress_callback)
            
            # 時間範囲を作成
            time_ranges = [
                TimeRange(start=seg.start, end=seg.end)
                for seg in segments
            ]
            
            # 無音検出と削除
            keep_ranges_tuples = self.video_processor.remove_silence_new(
                input_path=str(video_file),
                time_ranges=time_ranges,
                output_dir=str(self.temp_dir),
                noise_threshold=threshold,
                min_silence_duration=min_silence_duration,
                padding_start=pad_start,
                padding_end=pad_end,
                min_segment_duration=min_segment_duration,
                progress_callback=wrapped_callback
            )
            
            # タプルをTimeRangeオブジェクトに変換
            keep_ranges = [
                TimeRange(start=start, end=end)
                for start, end in keep_ranges_tuples
            ]
            
            # セグメントを調整
            adjusted_segments = self._adjust_segments_with_silence(
                segments, keep_ranges
            )
            
            # 統計情報を計算
            stats = self._calculate_silence_stats(
                segments, adjusted_segments, keep_ranges
            )
            
            metadata = {
                'original_segments': len(segments),
                'adjusted_segments': len(adjusted_segments),
                'silence_removed': stats['silence_removed'],
                'total_duration': stats['total_duration'],
                'kept_duration': stats['kept_duration'],
                'removal_ratio': stats['removal_ratio'],
                'threshold': threshold,
                'pad_start': pad_start,
                'pad_end': pad_end
            }
            
            self.logger.info(
                f"無音削除完了: {len(adjusted_segments)} セグメント, "
                f"削除時間: {stats['silence_removed']:.1f}秒 "
                f"({stats['removal_ratio']:.1%})"
            )
            
            return self.create_success_result(
                data=adjusted_segments,
                metadata=metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"無音削除エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"無音削除中にエラーが発生しました: {str(e)}")
            )
    
    def extract_segments(
        self,
        video_path: str,
        segments: List[Segment],
        output_dir: str,
        format: str = "mp4",
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """セグメントごとに動画を切り出し
        
        Args:
            video_path: 動画ファイルパス
            segments: 切り出すセグメント
            output_dir: 出力ディレクトリ
            format: 出力形式
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: 切り出されたファイルパスのリスト
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            output_path = Path(output_dir)
            ensure_directory(output_path)
            
            if not segments:
                raise ValidationError("切り出すセグメントがありません")
            
            self.logger.info(f"セグメント切り出し開始: {len(segments)} セグメント")
            
            # 進捗通知のラップ
            wrapped_callback = self._wrap_progress_callback(progress_callback)
            
            extracted_files = []
            
            for i, segment in enumerate(segments):
                if wrapped_callback:
                    progress = i / len(segments)
                    wrapped_callback(progress, f"セグメント {i+1}/{len(segments)} を切り出し中")
                
                # 出力ファイル名を生成
                output_file = output_path / f"segment_{i+1:04d}.{format}"
                
                # セグメントを切り出し
                success = self.video_processor.extract_segment(
                    input_path=str(video_file),
                    start=segment.start,
                    end=segment.end,
                    output_path=str(output_file)
                )
                
                if success and output_file.exists():
                    extracted_files.append(str(output_file))
                else:
                    self.logger.warning(f"セグメント {i+1} の切り出しに失敗")
            
            if wrapped_callback:
                wrapped_callback(1.0, "切り出し完了")
            
            metadata = {
                'segments_count': len(segments),
                'extracted_count': len(extracted_files),
                'output_format': format,
                'output_dir': str(output_path)
            }
            
            self.logger.info(
                f"セグメント切り出し完了: {len(extracted_files)}/{len(segments)} ファイル"
            )
            
            return self.create_success_result(
                data=extracted_files,
                metadata=metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"セグメント切り出しエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"セグメント切り出し中にエラーが発生しました: {str(e)}")
            )
    
    def merge_videos(
        self,
        video_files: List[str],
        output_path: str,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """複数の動画ファイルを結合
        
        Args:
            video_files: 結合する動画ファイルのリスト
            output_path: 出力ファイルパス
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: 結合された動画ファイルパス
        """
        try:
            # 入力検証
            if not video_files:
                raise ValidationError("結合する動画ファイルがありません")
            
            for video_file in video_files:
                self.validate_file_exists(video_file)
            
            self.logger.info(f"動画結合開始: {len(video_files)} ファイル")
            
            # 進捗通知のラップ
            wrapped_callback = self._wrap_progress_callback(progress_callback)
            
            # 一時ファイルリストを作成
            with tempfile.NamedTemporaryFile(
                mode='w', 
                suffix='.txt', 
                dir=self.temp_dir,
                delete=False
            ) as f:
                for video_file in video_files:
                    f.write(f"file '{video_file}'\n")
                list_file = f.name
            
            try:
                # ffmpegで結合
                success = self.video_processor.combine_videos(
                    list_file=list_file,
                    output_path=output_path
                )
                
                if not success or not Path(output_path).exists():
                    raise ProcessingError("動画の結合に失敗しました")
                
                # 出力ファイルの情報を取得
                video_info = VideoInfo.from_file(output_path)
                
                metadata = {
                    'input_count': len(video_files),
                    'output_duration': video_info.duration,
                    'output_size': Path(output_path).stat().st_size
                }
                
                self.logger.info(
                    f"動画結合完了: {video_info.duration:.1f}秒, "
                    f"{metadata['output_size'] / 1024 / 1024:.1f}MB"
                )
                
                return self.create_success_result(
                    data=output_path,
                    metadata=metadata
                )
                
            finally:
                # 一時ファイルを削除
                Path(list_file).unlink(missing_ok=True)
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"動画結合エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"動画結合中にエラーが発生しました: {str(e)}")
            )
    
    def get_video_info(self, video_path: str) -> ServiceResult:
        """動画の情報を取得
        
        Args:
            video_path: 動画ファイルパス
            
        Returns:
            ServiceResult: 動画情報
        """
        try:
            video_file = self.validate_file_exists(video_path)
            
            # 動画情報を取得
            video_info = VideoInfo.from_file(str(video_file))
            
            info_dict = {
                'duration': video_info.duration,
                'fps': video_info.fps,
                'width': video_info.width,
                'height': video_info.height,
                'codec': video_info.codec,
                'size': video_file.stat().st_size,
                'format': video_file.suffix.lstrip('.')
            }
            
            return self.create_success_result(
                data=info_dict,
                metadata={'file_path': str(video_file)}
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"動画情報取得エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"動画情報取得中にエラーが発生しました: {str(e)}")
            )
    
    def _adjust_segments_with_silence(
        self,
        segments: List[Segment],
        keep_ranges: List[TimeRange]
    ) -> List[Segment]:
        """無音削除結果に基づいてセグメントを調整
        
        Args:
            segments: 元のセグメント
            keep_ranges: 保持する時間範囲
            
        Returns:
            調整されたセグメント
        """
        adjusted_segments = []
        
        for segment in segments:
            # セグメントと重複するkeep_rangeを探す
            segment_keep_ranges = []
            
            for keep_range in keep_ranges:
                # セグメントと時間範囲が重複するかチェック
                if (keep_range.start < segment.end and 
                    keep_range.end > segment.start):
                    # 重複部分を計算
                    overlap_start = max(keep_range.start, segment.start)
                    overlap_end = min(keep_range.end, segment.end)
                    
                    if overlap_end > overlap_start:
                        segment_keep_ranges.append(
                            TimeRange(start=overlap_start, end=overlap_end)
                        )
            
            # keep_rangeがある場合は調整されたセグメントを作成
            if segment_keep_ranges:
                # 各keep_rangeを個別のセグメントとして追加（無音削除の結果を反映）
                for keep_range in segment_keep_ranges:
                    adjusted_segment = Segment(
                        start=keep_range.start,
                        end=keep_range.end,
                        text=segment.text,
                        words=segment.words
                    )
                    adjusted_segments.append(adjusted_segment)
        
        return adjusted_segments
    
    def _calculate_silence_stats(
        self,
        original_segments: List[Segment],
        adjusted_segments: List[Segment],
        keep_ranges: List[TimeRange]
    ) -> Dict[str, float]:
        """無音削除の統計情報を計算
        
        Args:
            original_segments: 元のセグメント
            adjusted_segments: 調整後のセグメント
            keep_ranges: 保持された時間範囲
            
        Returns:
            統計情報
        """
        # 元の総時間
        total_duration = sum(
            seg.end - seg.start for seg in original_segments
        )
        
        # 保持された時間
        kept_duration = sum(
            range.end - range.start for range in keep_ranges
        )
        
        # 削除された時間
        silence_removed = total_duration - kept_duration
        
        # 削除率
        removal_ratio = silence_removed / total_duration if total_duration > 0 else 0
        
        return {
            'total_duration': total_duration,
            'kept_duration': kept_duration,
            'silence_removed': silence_removed,
            'removal_ratio': removal_ratio
        }
    
    def _wrap_progress_callback(
        self,
        callback: Optional[Callable[[float, str], None]]
    ) -> Optional[Callable[[float, str], None]]:
        """進捗通知コールバックをラップ
        
        Args:
            callback: 元のコールバック
            
        Returns:
            ラップされたコールバック
        """
        if not callback:
            return None
        
        def wrapped(progress: float, message: str):
            # ログ出力
            self.logger.debug(f"進捗: {progress:.1%} - {message}")
            # 元のコールバックを呼び出し
            callback(progress, message)
        
        return wrapped