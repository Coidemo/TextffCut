"""
FCPXMLエクスポートユースケース
"""

from dataclasses import dataclass
from typing import Any

from domain.entities import VideoSegment
from domain.value_objects import Duration, FilePath
from use_cases.base import UseCase
from use_cases.exceptions import ExportError
from use_cases.interfaces import IExportGateway, IFileGateway


@dataclass
class ExportFCPXMLRequest:
    """FCPXMLエクスポートリクエスト"""

    video_path: FilePath
    output_path: FilePath
    segments: list[VideoSegment]
    timeline_name: str
    timeline_fps: float = 30.0
    remove_silence: bool = False
    metadata: dict[str, Any] | None = None

    def __post_init__(self):
        """パスの検証"""
        if not isinstance(self.video_path, FilePath):
            self.video_path = FilePath(str(self.video_path))
        if not isinstance(self.output_path, FilePath):
            self.output_path = FilePath(str(self.output_path))


@dataclass
class FCPXMLAsset:
    """FCPXMLアセット情報"""

    id: str
    name: str
    path: str
    duration: Duration
    fps: float
    width: int = 1920
    height: int = 1080
    audio_channels: int = 2
    audio_rate: int = 48000


@dataclass
class FCPXMLClip:
    """FCPXMLクリップ情報"""

    name: str
    start_time: float
    duration: float
    in_point: float
    out_point: float
    asset_id: str


@dataclass
class ExportFCPXMLResponse:
    """FCPXMLエクスポートレスポンス"""

    output_path: FilePath
    asset: FCPXMLAsset
    clips: list[FCPXMLClip]
    total_duration: Duration
    clip_count: int

    @property
    def timeline_duration(self) -> float:
        """タイムライン上の合計時間"""
        if not self.clips:
            return 0.0
        last_clip = max(self.clips, key=lambda c: c.start_time + c.duration)
        return last_clip.start_time + last_clip.duration


class ExportFCPXMLUseCase(UseCase[ExportFCPXMLRequest, ExportFCPXMLResponse]):
    """
    FCPXMLファイルをエクスポートするユースケース

    動画セグメントからFinal Cut Pro用のXMLファイルを生成します。
    無音削除オプションにより、クリップを隙間なく配置することができます。
    """

    def __init__(self, export_gateway: IExportGateway, file_gateway: IFileGateway):
        super().__init__()
        self.export_gateway = export_gateway
        self.file_gateway = file_gateway

    def validate_request(self, request: ExportFCPXMLRequest) -> None:
        """リクエストのバリデーション"""
        # ファイルの存在確認
        if not request.video_path.exists:
            raise ExportError(f"Video file not found: {request.video_path}")

        # セグメントの確認
        if not request.segments:
            raise ExportError("No segments provided for export")

        # 出力パスの親ディレクトリ確認
        output_parent = request.output_path.parent
        if not output_parent.exists:
            self.logger.info(f"Creating output directory: {output_parent}")
            output_parent.ensure_parent_exists()

        # 拡張子の確認
        if not request.output_path.extension.lower() == ".fcpxml":
            raise ExportError(f"Invalid output format: {request.output_path.extension}. " "Expected .fcpxml")

        # FPSの確認
        if request.timeline_fps <= 0:
            raise ExportError(f"Invalid timeline FPS: {request.timeline_fps}")

    def execute(self, request: ExportFCPXMLRequest) -> ExportFCPXMLResponse:
        """FCPXMLエクスポートの実行"""
        self.logger.info(f"Starting FCPXML export with {len(request.segments)} segments")

        try:
            # 動画情報の取得
            video_info = self._get_video_info(request.video_path)

            # アセット情報の作成
            asset = self._create_asset(request.video_path, video_info, request.timeline_fps)

            # クリップ情報の作成
            clips = self._create_clips(request.segments, asset.id, request.remove_silence)

            # FCPXMLの生成
            fcpxml_content = self.export_gateway.generate_fcpxml(
                timeline_name=request.timeline_name, asset=asset, clips=clips, metadata=request.metadata
            )

            # ファイルへの書き込み
            self.file_gateway.write_text(path=request.output_path, content=fcpxml_content, encoding="utf-8")

            # 合計時間の計算
            total_duration = Duration(seconds=sum(segment.duration for segment in request.segments))

            self.logger.info(
                f"FCPXML export completed. "
                f"Created {len(clips)} clips, "
                f"total duration: {total_duration.seconds:.1f}s"
            )

            return ExportFCPXMLResponse(
                output_path=request.output_path,
                asset=asset,
                clips=clips,
                total_duration=total_duration,
                clip_count=len(clips),
            )

        except Exception as e:
            self.logger.error(f"Failed to export FCPXML: {str(e)}")
            raise ExportError(f"Failed to export FCPXML: {str(e)}", cause=e)

    def _get_video_info(self, video_path: FilePath) -> dict[str, Any]:
        """動画情報を取得"""
        try:
            return self.export_gateway.get_video_info(video_path)
        except Exception as e:
            raise ExportError(f"Failed to get video info: {str(e)}", cause=e)

    def _create_asset(self, video_path: FilePath, video_info: dict[str, Any], timeline_fps: float) -> FCPXMLAsset:
        """アセット情報を作成"""
        # 動画の長さをフレーム数に変換
        duration_frames = int(video_info["duration"] * timeline_fps)
        duration = Duration(seconds=duration_frames / timeline_fps)

        return FCPXMLAsset(
            id="r1",  # FCPXMLの慣例に従い"r1"を使用
            name=video_path.name,
            path=str(video_path),
            duration=duration,
            fps=timeline_fps,
            width=video_info.get("width", 1920),
            height=video_info.get("height", 1080),
            audio_channels=video_info.get("audio_channels", 2),
            audio_rate=video_info.get("audio_rate", 48000),
        )

    def _create_clips(self, segments: list[VideoSegment], asset_id: str, remove_silence: bool) -> list[FCPXMLClip]:
        """クリップ情報を作成"""
        clips = []
        timeline_position = 0.0

        for i, segment in enumerate(segments):
            clip = FCPXMLClip(
                name=f"Clip {i+1}",
                start_time=timeline_position,
                duration=segment.duration,
                in_point=segment.start,
                out_point=segment.end,
                asset_id=asset_id,
            )
            clips.append(clip)

            # 無音削除モードの場合は隙間なく配置
            if remove_silence:
                timeline_position += segment.duration
            else:
                # 通常モードでは元の位置を維持
                timeline_position = segment.end

        return clips
