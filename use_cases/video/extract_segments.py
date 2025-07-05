"""
動画セグメント抽出ユースケース
"""

from collections.abc import Callable
from dataclasses import dataclass

from domain.value_objects import Duration, FilePath, TimeRange
from use_cases.base import UseCase
from use_cases.exceptions import SegmentCombineError, VideoProcessingError
from use_cases.interfaces import IFileGateway, IVideoProcessorGateway


@dataclass
class ExtractSegmentsRequest:
    """セグメント抽出リクエスト"""

    video_path: FilePath
    time_ranges: list[TimeRange]
    output_path: FilePath
    combine_segments: bool = True
    keep_temp_files: bool = False
    progress_callback: Callable[[float], None] | None = None

    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))
        if not isinstance(self.output_path, FilePath):
            self.output_path = FilePath(str(self.output_path))


@dataclass
class SegmentInfo:
    """セグメント情報"""

    index: int
    time_range: TimeRange
    file_path: FilePath | None = None
    size_bytes: int | None = None

    @property
    def duration(self) -> float:
        """セグメントの継続時間"""
        return self.time_range.duration


@dataclass
class ExtractSegmentsResponse:
    """セグメント抽出レスポンス"""

    output_path: FilePath
    segment_infos: list[SegmentInfo]
    total_duration: Duration
    output_duration: Duration
    temp_files: list[FilePath]

    @property
    def segment_count(self) -> int:
        """セグメント数"""
        return len(self.segment_infos)

    @property
    def compression_ratio(self) -> float:
        """圧縮率（出力/入力）"""
        if self.total_duration.seconds == 0:
            return 1.0
        return self.output_duration.seconds / self.total_duration.seconds

    @property
    def total_size_bytes(self) -> int | None:
        """合計サイズ（バイト）"""
        sizes = [s.size_bytes for s in self.segment_infos if s.size_bytes is not None]
        return sum(sizes) if sizes else None


class ExtractVideoSegmentsUseCase(UseCase[ExtractSegmentsRequest, ExtractSegmentsResponse]):
    """
    動画から指定された時間範囲のセグメントを抽出するユースケース

    複数の時間範囲を指定して動画を切り出し、
    オプションで結合して1つのファイルにすることができます。
    """

    def __init__(self, video_gateway: IVideoProcessorGateway, file_gateway: IFileGateway):
        super().__init__()
        self.video_gateway = video_gateway
        self.file_gateway = file_gateway

    def validate_request(self, request: ExtractSegmentsRequest) -> None:
        """リクエストのバリデーション"""
        # ファイルの存在確認
        if not request.video_path.exists:
            raise VideoProcessingError(f"Video file not found: {request.video_path}")

        # 時間範囲の確認
        if not request.time_ranges:
            raise VideoProcessingError("No time ranges provided")

        # 出力パスの親ディレクトリ確認
        output_parent = request.output_path.parent
        if not output_parent.exists:
            self.logger.info(f"Creating output directory: {output_parent}")
            output_parent.ensure_parent_exists()

        # 拡張子の確認
        valid_extensions = [".mp4", ".mov", ".avi", ".mkv", ".webm"]
        if not request.output_path.validate_extension(valid_extensions):
            raise VideoProcessingError(f"Invalid output format: {request.output_path.extension}")

    def execute(self, request: ExtractSegmentsRequest) -> ExtractSegmentsResponse:
        """セグメント抽出の実行"""
        self.logger.info(f"Starting segment extraction for {len(request.time_ranges)} ranges")

        try:
            # 動画情報の取得
            video_info = self.video_gateway.get_video_info(request.video_path)
            total_duration = Duration(seconds=video_info["duration"])

            # 一時ディレクトリの作成
            temp_dir = self.file_gateway.create_temp_directory(prefix="segments_")

            # セグメントの抽出
            if request.progress_callback:
                request.progress_callback(0.1)  # 10%

            segment_files = self.video_gateway.extract_segments(
                video_path=request.video_path,
                time_ranges=request.time_ranges,
                output_dir=temp_dir,
                progress_callback=lambda p: (
                    request.progress_callback(0.1 + 0.6 * p) if request.progress_callback else None
                ),
            )

            # セグメント情報の作成
            segment_infos = []
            for i, (segment_file, time_range) in enumerate(zip(segment_files, request.time_ranges, strict=False)):
                size_bytes = self.file_gateway.get_size(segment_file) if segment_file.exists else None
                segment_infos.append(
                    SegmentInfo(index=i, time_range=time_range, file_path=segment_file, size_bytes=size_bytes)
                )

            # セグメントの結合（必要な場合）
            if request.combine_segments and len(segment_files) > 1:
                if request.progress_callback:
                    request.progress_callback(0.8)  # 80%

                self._combine_segments(segment_files, request.output_path)
                final_output = request.output_path

                # 一時ファイルのクリーンアップ（必要な場合）
                if not request.keep_temp_files:
                    self._cleanup_temp_files(segment_files, temp_dir)
                    temp_files = []
                else:
                    temp_files = segment_files

            elif len(segment_files) == 1:
                # 単一セグメントの場合は移動
                self.file_gateway.move_file(segment_files[0], request.output_path)
                final_output = request.output_path
                temp_files = []

                # 一時ディレクトリのクリーンアップ
                if self.file_gateway.exists(temp_dir):
                    self.file_gateway.delete_directory(temp_dir, recursive=True)

            else:
                # 結合しない場合
                final_output = request.output_path
                temp_files = segment_files if request.keep_temp_files else []

            # 出力の継続時間を計算
            output_duration = Duration(seconds=sum(tr.duration for tr in request.time_ranges))

            if request.progress_callback:
                request.progress_callback(1.0)  # 100%

            self.logger.info(
                f"Segment extraction completed. "
                f"Extracted {len(segment_infos)} segments. "
                f"Compression ratio: {output_duration.seconds/total_duration.seconds:.1%}"
            )

            return ExtractSegmentsResponse(
                output_path=final_output,
                segment_infos=segment_infos,
                total_duration=total_duration,
                output_duration=output_duration,
                temp_files=temp_files,
            )

        except SegmentCombineError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to extract segments: {str(e)}")
            raise VideoProcessingError(f"Failed to extract segments: {str(e)}", cause=e)

    def _combine_segments(self, segment_files: list[FilePath], output_path: FilePath) -> None:
        """セグメントを結合"""
        try:
            self.video_gateway.combine_segments(segment_paths=segment_files, output_path=output_path)
        except Exception as e:
            raise SegmentCombineError(f"Failed to combine segments: {str(e)}", cause=e)

    def _cleanup_temp_files(self, segment_files: list[FilePath], temp_dir: FilePath) -> None:
        """一時ファイルのクリーンアップ"""
        try:
            # セグメントファイルの削除
            for segment_file in segment_files:
                if self.file_gateway.exists(segment_file):
                    self.file_gateway.delete_file(segment_file)

            # 一時ディレクトリの削除
            if self.file_gateway.exists(temp_dir):
                self.file_gateway.delete_directory(temp_dir, recursive=True)
        except Exception as e:
            self.logger.warning(f"Failed to cleanup temp files: {str(e)}")
