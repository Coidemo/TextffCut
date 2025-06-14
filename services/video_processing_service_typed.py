"""
動画処理サービス（型ヒント強化版）

型安全性を最大限に高めた動画処理サービスの実装例。
"""

from typing import List, Optional, Dict, Any, Callable, Tuple, TypeVar
from pathlib import Path
import tempfile
import shutil

from services.base import BaseService, ServiceResult
from config import Config
from core.video import VideoProcessor, VideoInfo, VideoSegment
from core.models import TranscriptionSegmentV2
from core.types import (
    VideoPath, TimeSeconds, ProgressCallback, TimeRange,
    SilenceDetectionOptions, VideoMetadata, Result
)
from core.constants import SilenceDetection
from utils.file_utils import ensure_directory, get_safe_filename
from typing import NamedTuple


# サービス固有の型定義
class TimeRange(NamedTuple):
    """時間範囲（名前付きタプル）"""
    start: TimeSeconds
    end: TimeSeconds


class SilenceDetectionResult(NamedTuple):
    """無音検出結果"""
    keep_ranges: List[TimeRange]
    silence_ranges: List[TimeRange]
    total_duration: TimeSeconds
    kept_duration: TimeSeconds
    removed_duration: TimeSeconds


# 型変数の定義
T = TypeVar('T')


class VideoProcessingService(BaseService):
    """動画処理のビジネスロジック（型ヒント強化版）"""
    
    def __init__(self, config: Config) -> None:
        """初期化"""
        super().__init__(config)
        self.video_processor: VideoProcessor = VideoProcessor(config)
    
    def execute(self, **kwargs: Any) -> ServiceResult:
        """汎用実行メソッド"""
        action: str = kwargs.get('action', 'process')
        
        if action == 'remove_silence':
            return self.remove_silence(**kwargs)
        elif action == 'extract_segments':
            return self.extract_segments(**kwargs)
        elif action == 'get_info':
            return self.get_video_info(**kwargs)
        else:
            return self.create_error_result(
                f"不明なアクション: {action}",
                "ValidationError"
            )
    
    def remove_silence(
        self,
        video_path: VideoPath,
        segments: List[TranscriptionSegmentV2],
        threshold: float = SilenceDetection.DEFAULT_THRESHOLD,
        min_silence_duration: float = SilenceDetection.MIN_SILENCE_DURATION,
        pad_start: float = SilenceDetection.DEFAULT_PAD_START,
        pad_end: float = SilenceDetection.DEFAULT_PAD_END,
        min_segment_duration: float = SilenceDetection.MIN_SEGMENT_DURATION,
        progress_callback: Optional[ProgressCallback] = None
    ) -> ServiceResult:
        """無音部分を削除してセグメントを調整"""
        try:
            # 入力検証
            video_file: Path = self.validate_file_exists(str(video_path))
            if not segments:
                raise ValidationError("処理するセグメントがありません")
            
            self.logger.info(
                f"無音削除開始: {len(segments)} セグメント, "
                f"閾値: {threshold}dB, パディング: {pad_start}/{pad_end}秒"
            )
            
            # 進捗通知のラップ
            wrapped_callback: Optional[ProgressCallback] = self._wrap_progress_callback(progress_callback)
            
            # 時間範囲を作成
            time_ranges: List[TimeRange] = [
                TimeRange(start=seg.start, end=seg.end)
                for seg in segments
            ]
            
            # 無音検出と削除
            detection_result: SilenceDetectionResult = self._detect_and_remove_silence(
                video_path=video_file,
                time_ranges=time_ranges,
                options=SilenceDetectionOptions(
                    threshold_db=threshold,
                    min_silence_duration=min_silence_duration,
                    pad_start=pad_start,
                    pad_end=pad_end,
                    min_segment_duration=min_segment_duration
                ),
                progress_callback=wrapped_callback
            )
            
            # セグメントを調整
            adjusted_segments: List[TranscriptionSegmentV2] = self._adjust_segments_with_silence(
                segments, detection_result.keep_ranges
            )
            
            # 統計情報を計算
            stats: Dict[str, Any] = {
                'original_duration': detection_result.total_duration,
                'kept_duration': detection_result.kept_duration,
                'removed_duration': detection_result.removed_duration,
                'reduction_ratio': detection_result.removed_duration / detection_result.total_duration if detection_result.total_duration > 0 else 0,
                'silence_count': len(detection_result.silence_ranges),
                'segment_count': len(adjusted_segments)
            }
            
            self.logger.info(
                f"無音削除完了: {stats['removed_duration']:.1f}秒削除 "
                f"({stats['reduction_ratio']:.1%}削減)"
            )
            
            return self.create_success_result(
                data={'segments': adjusted_segments},
                metadata=stats
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
        video_path: VideoPath,
        segments: List[TranscriptionSegmentV2],
        output_dir: str,
        format: str = "mp4",
        progress_callback: Optional[ProgressCallback] = None
    ) -> ServiceResult:
        """セグメントごとに動画を切り出し"""
        try:
            # 入力検証
            video_file: Path = self.validate_file_exists(str(video_path))
            output_path: Path = Path(output_dir)
            ensure_directory(output_path)
            
            if not segments:
                raise ValidationError("切り出すセグメントがありません")
            
            self.logger.info(f"セグメント切り出し開始: {len(segments)} セグメント")
            
            # 進捗通知のラップ
            wrapped_callback: Optional[ProgressCallback] = self._wrap_progress_callback(progress_callback)
            
            extracted_files: List[Dict[str, Any]] = []
            
            for i, segment in enumerate(segments):
                if wrapped_callback:
                    progress: float = i / len(segments)
                    wrapped_callback(progress, f"セグメント {i+1}/{len(segments)} を切り出し中")
                
                # 出力ファイル名を生成
                output_file: Path = output_path / f"segment_{i+1:04d}.{format}"
                
                # セグメントを切り出し
                success: bool = self._extract_single_segment(
                    video_file, segment, output_file
                )
                
                if success:
                    extracted_files.append({
                        'index': i,
                        'segment_id': segment.id,
                        'file_path': str(output_file),
                        'duration': segment.end - segment.start
                    })
            
            if wrapped_callback:
                wrapped_callback(1.0, "セグメント切り出し完了")
            
            self.logger.info(f"セグメント切り出し完了: {len(extracted_files)}ファイル")
            
            return self.create_success_result(
                data={'files': extracted_files},
                metadata={
                    'total_segments': len(segments),
                    'extracted_count': len(extracted_files),
                    'output_directory': str(output_path)
                }
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"セグメント切り出しエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"セグメント切り出し中にエラーが発生しました: {str(e)}")
            )
    
    def get_video_info(self, video_path: VideoPath) -> ServiceResult:
        """動画の情報を取得"""
        try:
            video_file: Path = self.validate_file_exists(str(video_path))
            
            # 動画情報を取得
            video_info: VideoInfo = VideoInfo.from_file(str(video_file))
            
            # VideoMetadata型に変換
            metadata: VideoMetadata = {
                'width': video_info.width,
                'height': video_info.height,
                'fps': video_info.fps,
                'duration': video_info.duration,
                'codec': video_info.codec,
                'bitrate': None,  # VideoInfoには含まれない
                'audio_codec': None,
                'audio_sample_rate': None,
                'audio_channels': None
            }
            
            return self.create_success_result(
                data=metadata,
                metadata={'file_path': str(video_file)}
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"動画情報取得エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"動画情報取得中にエラーが発生しました: {str(e)}")
            )
    
    def _detect_and_remove_silence(
        self,
        video_path: Path,
        time_ranges: List[TimeRange],
        options: SilenceDetectionOptions,
        progress_callback: Optional[ProgressCallback] = None
    ) -> SilenceDetectionResult:
        """無音検出と削除処理（内部メソッド）"""
        # 実装の詳細（省略）
        # 実際の実装では video_processor.remove_silence_new を呼び出す
        
        # ダミーの結果を返す
        total_duration: TimeSeconds = sum(r.end - r.start for r in time_ranges)
        kept_duration: TimeSeconds = total_duration * 0.8  # 仮に80%を残す
        
        return SilenceDetectionResult(
            keep_ranges=time_ranges,  # 実際は調整される
            silence_ranges=[],
            total_duration=total_duration,
            kept_duration=kept_duration,
            removed_duration=total_duration - kept_duration
        )
    
    def _adjust_segments_with_silence(
        self,
        segments: List[TranscriptionSegmentV2],
        keep_ranges: List[TimeRange]
    ) -> List[TranscriptionSegmentV2]:
        """セグメントを無音削除結果に基づいて調整（内部メソッド）"""
        adjusted: List[TranscriptionSegmentV2] = []
        
        for segment in segments:
            # セグメントと残す範囲の重複をチェック
            for keep_range in keep_ranges:
                if self._ranges_overlap(
                    (segment.start, segment.end),
                    (keep_range.start, keep_range.end)
                ):
                    # 重複部分を新しいセグメントとして追加
                    new_segment = TranscriptionSegmentV2(
                        id=segment.id,
                        text=segment.text,
                        start=max(segment.start, keep_range.start),
                        end=min(segment.end, keep_range.end),
                        words=segment.words,
                        confidence=segment.confidence,
                        language=segment.language,
                        speaker=segment.speaker,
                        transcription_completed=segment.transcription_completed,
                        alignment_completed=segment.alignment_completed,
                        metadata=segment.metadata
                    )
                    adjusted.append(new_segment)
        
        return adjusted
    
    def _ranges_overlap(
        self,
        range1: Tuple[TimeSeconds, TimeSeconds],
        range2: Tuple[TimeSeconds, TimeSeconds]
    ) -> bool:
        """時間範囲が重複するかチェック"""
        return range1[0] < range2[1] and range2[0] < range1[1]
    
    def _extract_single_segment(
        self,
        video_file: Path,
        segment: TranscriptionSegmentV2,
        output_file: Path
    ) -> bool:
        """単一セグメントを切り出し（内部メソッド）"""
        try:
            # 実際の実装では FFmpeg を使用
            # ここではダミー実装
            return True
        except Exception as e:
            self.logger.error(f"セグメント切り出しエラー: {e}")
            return False
    
    def _wrap_progress_callback(
        self,
        callback: Optional[ProgressCallback]
    ) -> Optional[ProgressCallback]:
        """進捗コールバックをラップ"""
        if callback is None:
            return None
        
        def wrapped(progress: float, message: str) -> None:
            try:
                callback(progress, message)
            except Exception as e:
                self.logger.warning(f"進捗通知エラー: {e}")
        
        return wrapped