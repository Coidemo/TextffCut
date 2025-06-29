"""
無音検出ユースケース
"""

from dataclasses import dataclass
from typing import List, Optional, Callable

from domain.value_objects import FilePath, TimeRange, Duration
from use_cases.base import UseCase
from use_cases.exceptions import VideoProcessingError, AudioExtractionError, SilenceDetectionError
from use_cases.interfaces import IVideoProcessorGateway, IFileGateway


@dataclass
class DetectSilenceRequest:
    """無音検出リクエスト"""
    video_path: FilePath
    time_ranges: List[TimeRange]
    threshold: float = -35.0  # dB
    min_silence_duration: float = 0.3  # 秒
    min_segment_duration: float = 0.3  # 秒
    padding_start: float = 0.1  # 秒
    padding_end: float = 0.1  # 秒
    progress_callback: Optional[Callable[[float], None]] = None
    
    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))


@dataclass
class SilenceInfo:
    """無音情報"""
    time_range: TimeRange
    average_db: Optional[float] = None
    
    @property
    def duration(self) -> float:
        """無音の継続時間"""
        return self.time_range.duration


@dataclass
class DetectSilenceResponse:
    """無音検出レスポンス"""
    silence_ranges: List[TimeRange]
    keep_ranges: List[TimeRange]
    total_duration: Duration
    silence_duration: Duration
    keep_duration: Duration
    silence_infos: List[SilenceInfo]
    
    @property
    def silence_ratio(self) -> float:
        """無音の割合（0.0-1.0）"""
        if self.total_duration.seconds == 0:
            return 0.0
        return self.silence_duration.seconds / self.total_duration.seconds
    
    @property
    def compression_ratio(self) -> float:
        """圧縮率（削除後/元の長さ）"""
        if self.total_duration.seconds == 0:
            return 1.0
        return self.keep_duration.seconds / self.total_duration.seconds


class DetectSilenceUseCase(UseCase[DetectSilenceRequest, DetectSilenceResponse]):
    """
    動画から無音部分を検出するユースケース
    
    指定された時間範囲から音声を抽出し、無音部分を検出して
    残すべき部分（無音以外）の時間範囲を返します。
    """
    
    def __init__(
        self,
        video_gateway: IVideoProcessorGateway,
        file_gateway: IFileGateway
    ):
        super().__init__()
        self.video_gateway = video_gateway
        self.file_gateway = file_gateway
    
    def validate_request(self, request: DetectSilenceRequest) -> None:
        """リクエストのバリデーション"""
        # ファイルの存在確認
        if not request.video_path.exists:
            raise VideoProcessingError(
                f"Video file not found: {request.video_path}"
            )
        
        # 時間範囲の確認
        if not request.time_ranges:
            raise VideoProcessingError("No time ranges provided")
        
        # パラメータの範囲確認
        if not -60 <= request.threshold <= 0:
            raise VideoProcessingError(
                f"Threshold must be between -60 and 0 dB, got {request.threshold}"
            )
        
        if request.min_silence_duration <= 0:
            raise VideoProcessingError(
                "Minimum silence duration must be positive"
            )
    
    def execute(self, request: DetectSilenceRequest) -> DetectSilenceResponse:
        """無音検出の実行"""
        self.logger.info(
            f"Starting silence detection for {len(request.time_ranges)} ranges"
        )
        
        try:
            # 一時ディレクトリの作成
            temp_dir = self.file_gateway.create_temp_directory(prefix="silence_detection_")
            
            # 音声セグメントの抽出
            if request.progress_callback:
                request.progress_callback(0.1)  # 10%
            
            audio_files = self._extract_audio_segments(
                request.video_path,
                request.time_ranges,
                temp_dir
            )
            
            # 各セグメントから無音を検出
            all_silence_ranges = []
            silence_infos = []
            
            for i, (audio_file, time_range) in enumerate(zip(audio_files, request.time_ranges)):
                if request.progress_callback:
                    progress = 0.1 + (0.6 * i / len(audio_files))  # 10-70%
                    request.progress_callback(progress)
                
                # 無音検出
                silence_in_segment = self.video_gateway.detect_silence(
                    audio_path=audio_file,
                    threshold=request.threshold,
                    min_silence_duration=request.min_silence_duration,
                    min_segment_duration=request.min_segment_duration
                )
                
                # セグメントの開始時間でオフセット
                offset_silence = [
                    TimeRange(
                        start=time_range.start + sr.start,
                        end=time_range.start + sr.end
                    )
                    for sr in silence_in_segment
                ]
                
                all_silence_ranges.extend(offset_silence)
                
                # 無音情報の作成
                for sr in offset_silence:
                    silence_infos.append(SilenceInfo(time_range=sr))
            
            # 全体の長さを計算
            total_duration = Duration(
                seconds=sum(tr.duration for tr in request.time_ranges)
            )
            
            # 残す部分の計算
            if request.progress_callback:
                request.progress_callback(0.8)  # 80%
            
            keep_ranges = self.video_gateway.calculate_keep_ranges(
                total_duration=total_duration,
                silence_ranges=all_silence_ranges,
                padding_start=request.padding_start,
                padding_end=request.padding_end
            )
            
            # 統計情報の計算
            silence_duration = Duration(
                seconds=sum(sr.duration for sr in all_silence_ranges)
            )
            keep_duration = Duration(
                seconds=sum(kr.duration for kr in keep_ranges)
            )
            
            # 一時ファイルのクリーンアップ
            self._cleanup_temp_files(audio_files, temp_dir)
            
            if request.progress_callback:
                request.progress_callback(1.0)  # 100%
            
            self.logger.info(
                f"Silence detection completed. "
                f"Found {len(all_silence_ranges)} silence ranges, "
                f"keeping {len(keep_ranges)} ranges. "
                f"Compression ratio: {keep_duration.seconds/total_duration.seconds:.1%}"
            )
            
            return DetectSilenceResponse(
                silence_ranges=all_silence_ranges,
                keep_ranges=keep_ranges,
                total_duration=total_duration,
                silence_duration=silence_duration,
                keep_duration=keep_duration,
                silence_infos=silence_infos
            )
            
        except AudioExtractionError:
            raise
        except SilenceDetectionError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to detect silence: {str(e)}")
            raise VideoProcessingError(
                f"Failed to detect silence: {str(e)}",
                cause=e
            )
    
    def _extract_audio_segments(
        self,
        video_path: FilePath,
        time_ranges: List[TimeRange],
        output_dir: FilePath
    ) -> List[FilePath]:
        """音声セグメントを抽出"""
        try:
            return self.video_gateway.extract_audio_segments(
                video_path=video_path,
                time_ranges=time_ranges,
                output_dir=output_dir
            )
        except Exception as e:
            raise AudioExtractionError(
                f"Failed to extract audio segments: {str(e)}",
                cause=e
            )
    
    def _cleanup_temp_files(self, audio_files: List[FilePath], temp_dir: FilePath) -> None:
        """一時ファイルのクリーンアップ"""
        try:
            # 音声ファイルの削除
            for audio_file in audio_files:
                if self.file_gateway.exists(audio_file):
                    self.file_gateway.delete_file(audio_file)
            
            # 一時ディレクトリの削除
            if self.file_gateway.exists(temp_dir):
                self.file_gateway.delete_directory(temp_dir, recursive=True)
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temp files: {str(e)}")