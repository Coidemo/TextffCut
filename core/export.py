"""
エクスポート処理モジュール（FCPXML、EDL、SRT等）
"""

import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from config import Config


def _xml_attr(value: str) -> str:
    """XML属性値用のエスケープ（ダブルクォートもエスケープ）

    xml.sax.saxutils.escape() は &, <, > のみエスケープするが、
    XML属性値（name="..." 等）では " も &quot; にエスケープが必要。
    """
    return xml_escape(value, {'"': "&quot;"})


# utils.environmentのインポートは実行時に行う（循環依存回避のため）
from utils.time_utils import frames_to_timecode

from .video import VideoInfo
import logging

logger = logging.getLogger(__name__)


def _safe_volume_db(value: object) -> str:
    """adjust-volume amount用の安全な文字列を返す。dB範囲 [-96, 12] にクランプ。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        v = 0.0
    v = max(-96.0, min(12.0, v))
    return f"{v:g}"


def optimize_fraction(value: float, base_fps: int = 30) -> str:
    """浮動小数点数を最適化された分数文字列に変換

    Args:
        value: 変換する値（秒）
        base_fps: 基準となるFPS

    Returns:
        最適化された分数文字列（例: "11/10s"）
    """
    # まず基準FPSでフレーム数に変換
    frames = round(value * base_fps)

    # Fractionで最適化
    frac = Fraction(frames, base_fps)

    # 分子が0の場合
    if frac.numerator == 0:
        return "0/1s"

    return f"{frac.numerator}/{frac.denominator}s"


@dataclass
class ExportSegment:
    """エクスポート用セグメント情報"""

    source_path: str | Path
    start_time: float
    end_time: float
    timeline_start: float

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time


class FCPXMLExporter:
    """FCPXMLエクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        project_name: str = "TextffCut Project",
        scale: tuple[float, float] = (1.0, 1.0),
        anchor: tuple[float, float] = (0.0, 0.0),
        timeline_resolution: str = "horizontal",  # "horizontal" or "vertical"
        overlay_settings: dict | None = None,
        bgm_settings: dict | None = None,
        additional_audio_settings: dict | None = None,
        title_settings: dict | None = None,
        ai_se_placements: list | None = None,
        blur_overlays: list[dict] | None = None,
    ) -> bool:
        """
        FCPXMLファイルをエクスポート

        Args:
            segments: エクスポートするセグメントのリスト
            output_path: 出力ファイルパス
            timeline_fps: タイムラインのFPS
            project_name: プロジェクト名
            scale: ズーム倍率（x, y）
            anchor: アンカー位置（x, y）

        Returns:
            成功したかどうか
        """
        try:
            # 動画情報を取得
            video_infos: dict[str, VideoInfo] = {}
            for seg in segments:
                source_path_str = str(seg.source_path)
                if source_path_str not in video_infos:
                    video_infos[source_path_str] = VideoInfo.from_file(seg.source_path)

            # XMLを構築
            xml_content = self._build_fcpxml(
                segments,
                video_infos,
                timeline_fps,
                project_name,
                scale,
                anchor,
                timeline_resolution,
                overlay_settings,
                bgm_settings,
                additional_audio_settings,
                title_settings,
                ai_se_placements,
                blur_overlays,
            )

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_content)

            return True

        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"FCPXML書き込み権限エラー: {str(e)}") from e
        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"FCPXML書き込みエラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"FCPXMLエクスポートエラー: {str(e)}") from e

    def _build_fcpxml(
        self,
        segments: list[ExportSegment],
        video_infos: dict[str, VideoInfo],
        timeline_fps: int,
        project_name: str,
        scale: tuple[float, float],
        anchor: tuple[float, float],
        timeline_resolution: str,
        overlay_settings: dict | None = None,
        bgm_settings: dict | None = None,
        additional_audio_settings: dict | None = None,
        title_settings: dict | None = None,
        ai_se_placements: list | None = None,
        blur_overlays: list[dict] | None = None,
    ) -> str:
        """FCPXMLコンテンツを構築（DaVinci Resolve完全互換）"""
        # 総時間を計算
        total_duration = sum(seg.duration for seg in segments)
        total_frames = round(total_duration * timeline_fps)

        # スピード変更機能は削除済み（DaVinci Resolve制限のため）

        # タイムライン解像度を決定
        if timeline_resolution == "vertical":
            timeline_width, timeline_height = 1080, 1920
            format_name = f"FFVideoFormatVertical{timeline_fps}"
        else:
            timeline_width, timeline_height = 1920, 1080
            format_name = f"FFVideoFormat1080p{timeline_fps}"

        # ソース動画の解像度を取得（デフォルト値を設定）
        source_width = 640
        source_height = 360
        # 実際の動画情報から解像度を取得できる場合は更新
        if segments and segments[0].source_path in video_infos:
            first_video_info = video_infos[str(segments[0].source_path)]
            if hasattr(first_video_info, "width") and hasattr(first_video_info, "height"):
                source_width = first_video_info.width
                source_height = first_video_info.height

        # XMLヘッダー
        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
    <resources>
        <format height="{timeline_height}" id="r0" name="{format_name}" frameDuration="1/{timeline_fps}s" width="{timeline_width}"/>
"""

        # リソース（使用する動画ファイル）を追加
        # 同じ動画ファイルは同じアセットIDを使用
        resource_map = {}
        asset_counter = 1  # r1から開始（r0はタイムラインフォーマット）

        # 動画ファイルごとに1つのアセットを作成
        processed_files = set()
        for seg in segments:
            source_path_str = str(seg.source_path)
            if source_path_str not in video_infos or source_path_str in processed_files:
                continue

            processed_files.add(source_path_str)
            info = video_infos[source_path_str]
            resource_id = f"r{asset_counter}"

            # このファイルのすべてのセグメントに同じリソースIDを割り当て
            resource_map[source_path_str] = resource_id

            # 動画の総時間を分数で表現（DaVinci Resolveスタイル）
            source_fps = int(info.fps)
            total_frames = round(info.duration * source_fps)
            duration_frac = Fraction(total_frames, source_fps)
            duration_str = f"{duration_frac.numerator}/{duration_frac.denominator}s"

            # Docker環境の場合はホストパスに変換
            is_docker = os.path.exists("/.dockerenv")
            logger.info(
                f"Docker環境判定（動画）: is_docker={is_docker}, /.dockerenv存在={os.path.exists('/.dockerenv')}"
            )
            if is_docker:
                # /app/videos/xxx.mp4 -> HOST_VIDEOS_PATH/xxx.mp4
                video_filename = Path(source_path_str).name
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                # FCPXMLは file:// 形式（localhostなし）
                file_url = f"file://{os.path.join(host_videos_path, video_filename)}".replace("\\", "/")
                logger.info(f"Docker環境でのFCPXMLパス変換: {source_path_str} -> {file_url}")
            else:
                # ローカル環境は通常通り
                # DaVinci Resolveと同じくURLエンコードする
                from urllib.parse import quote

                file_path = Path(source_path_str).resolve()
                # パスをURLエンコード（スラッシュは除く）
                encoded_path = "/".join(quote(part, safe="") for part in str(file_path).split("/"))
                file_url = f"file://{encoded_path}"

            # DaVinci Resolveの属性順序に従う
            # タイムラインフォーマット（r0）を使用
            xml_content += (
                f'        <asset duration="{duration_str}" id="{resource_id}" '
                f'name="{_xml_attr(Path(source_path_str).name)}" start="0/1s" hasVideo="1" '
                f'format="r0" hasAudio="1" audioSources="1" audioChannels="2">\n'
                f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                f"        </asset>\n"
            )

            asset_counter += 1

        # 塗りつぶしオーバーレイ PNG のリソースを追加 (auto_blur, V2 lane)
        # blur_overlays: list[dict] — {"png_path": str, "start_sec": float, "end_sec": float}
        # PNG は動画解像度フルサイズの透過 PNG (BlurOverlayUseCase が生成)。
        # アライメント: 動画 asset-clip と同じ <adjust-conform type="fit"/> + 同じ scale/anchor を
        # 適用することで、source≠timeline 解像度 (4K source / 縦動画) でも video と完全一致する。
        # どの segment にも overlap しない overlay は orphan asset を防ぐため事前に除外する。
        seen_blur_paths: dict[str, str] = {}  # png_path -> resource_id
        if blur_overlays and segments:
            # 各 PNG が少なくとも 1 つの segment と重なるかチェックして登録対象を絞る
            paths_with_overlap: set[str] = set()
            for ov in blur_overlays:
                ov_start = float(ov["start_sec"])
                ov_end = float(ov["end_sec"])
                if ov_end <= ov_start:
                    continue
                for seg in segments:
                    if max(ov_start, seg.start_time) < min(ov_end, seg.end_time):
                        paths_with_overlap.add(ov["png_path"])
                        break

            for ov in blur_overlays:
                png_path = ov["png_path"]
                if png_path in seen_blur_paths or png_path not in paths_with_overlap:
                    continue
                resource_id = f"r{asset_counter}"
                seen_blur_paths[png_path] = resource_id
                asset_counter += 1

                file_url = Path(png_path).resolve().as_uri()
                xml_content += (
                    f'        <asset duration="0/1s" id="{resource_id}" '
                    f'name="{_xml_attr(Path(png_path).name)}" start="0/1s" hasVideo="1" '
                    f'format="r0">\n'
                    f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                    f"        </asset>\n"
                )

        # オーバーレイ画像のリソースを追加
        overlay_resource_ids = {}
        if overlay_settings:
            # 背景フレーム
            if "frame_path" in overlay_settings:
                frame_path = overlay_settings["frame_path"]
                resource_id = f"r{asset_counter}"
                overlay_resource_ids["frame"] = resource_id

                # ファイルパスの処理（Docker環境対応）
                is_docker = os.path.exists("/.dockerenv")
                logger.info(f"Docker環境チェック: {is_docker}, frame_path: {frame_path}")
                if is_docker and (frame_path.startswith("/app/videos/") or frame_path.startswith("videos/")):
                    host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                    relative_path = frame_path.replace("/app/videos/", "").replace("videos/", "")
                    file_url = f"file://{host_videos_path}/{relative_path}".replace("\\", "/")
                    logger.info(f"Docker環境でのオーバーレイパス変換: {frame_path} -> {file_url}")
                else:
                    # 絶対パスに変換してからURIに
                    file_url = Path(frame_path).resolve().as_uri()
                    logger.info(f"非Docker環境でのオーバーレイパス: {frame_path} -> {file_url}")

                # 画像フォーマット（縦型/横型に合わせる）
                xml_content += (
                    f'        <asset duration="0/1s" id="{resource_id}" '
                    f'name="{_xml_attr(Path(frame_path).name)}" start="0/1s" hasVideo="1" '
                    f'format="r0">\n'
                    f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                    f"        </asset>\n"
                )
                asset_counter += 1

        # タイトル画像のリソースを追加
        title_resource_id = None
        if title_settings and title_settings.get("title_path"):
            title_path = title_settings["title_path"]
            if Path(title_path).exists():
                title_resource_id = f"r{asset_counter}"
                asset_counter += 1

                # ファイルパスの処理（Docker環境対応）
                logger.info(f"タイトル画像を追加: {Path(title_path).name}")
                is_docker = os.path.exists("/.dockerenv")
                if is_docker and (title_path.startswith("/app/videos/") or title_path.startswith("videos/")):
                    host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                    relative_path = title_path.replace("/app/videos/", "").replace("videos/", "")
                    file_url = f"file://{host_videos_path}/{relative_path}".replace("\\", "/")
                else:
                    file_url = Path(title_path).resolve().as_uri()

                xml_content += (
                    f'        <asset duration="0/1s" id="{title_resource_id}" '
                    f'name="{_xml_attr(Path(title_path).name)}" start="0/1s" hasVideo="1" '
                    f'format="r0">\n'
                    f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                    f"        </asset>\n"
                )

        # BGMのリソースを追加
        bgm_resource_id = None
        if bgm_settings and "bgm_path" in bgm_settings:
            bgm_path = bgm_settings["bgm_path"]
            bgm_resource_id = f"r{asset_counter}"

            # ファイルパスの処理（Docker環境対応）
            is_docker = os.path.exists("/.dockerenv")
            logger.info(f"Docker環境チェック（BGM）: {is_docker}, bgm_path: {bgm_path}")
            if is_docker and (bgm_path.startswith("/app/videos/") or bgm_path.startswith("videos/")):
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                relative_path = bgm_path.replace("/app/videos/", "").replace("videos/", "")
                file_url = f"file://{host_videos_path}/{relative_path}".replace("\\", "/")
                logger.info(f"Docker環境でのBGMパス変換: {bgm_path} -> {file_url}")
            else:
                # 絶対パスに変換してからURIに
                file_url = Path(bgm_path).resolve().as_uri()
                logger.info(f"非Docker環境でのBGMパス: {bgm_path} -> {file_url}")

            # BGMの長さを取得（FFprobeを使用）
            from .video import VideoInfo

            bgm_info = VideoInfo.from_file(bgm_path)
            bgm_duration_str = optimize_fraction(bgm_info.duration, timeline_fps)

            xml_content += (
                f'        <asset duration="{bgm_duration_str}" id="{bgm_resource_id}" '
                f'name="{_xml_attr(Path(bgm_path).name)}" start="0/1s" hasAudio="1" '
                f'audioSources="1" audioChannels="2">\n'
                f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                f"        </asset>\n"
            )
            asset_counter += 1

        # 追加オーディオの準備（BGM以外のMP3ファイル）
        additional_audio_resource_ids = {}
        logger.info(f"追加オーディオ設定: {additional_audio_settings}")
        if additional_audio_settings and additional_audio_settings.get("audio_files"):
            audio_files = additional_audio_settings["audio_files"]
            volume = additional_audio_settings.get("volume", -20)

            # 各オーディオファイルの情報を取得してリソースとして登録
            for audio_path in audio_files:
                try:
                    audio_info = VideoInfo.from_file(audio_path)
                    resource_id = f"r{asset_counter}"
                    additional_audio_resource_ids[audio_path] = (resource_id, audio_info, volume)

                    # ファイルパスの処理（Docker環境対応）
                    is_docker = os.path.exists("/.dockerenv")
                    logger.info(f"Docker環境チェック（追加オーディオ）: {is_docker}, audio_path: {audio_path}")
                    if is_docker and (audio_path.startswith("/app/videos/") or audio_path.startswith("videos/")):
                        host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                        relative_path = audio_path.replace("/app/videos/", "").replace("videos/", "")
                        file_url = f"file://{host_videos_path}/{relative_path}".replace("\\", "/")
                        logger.info(f"Docker環境での追加オーディオパス変換: {audio_path} -> {file_url}")
                    else:
                        # 絶対パスに変換してからURIに
                        file_url = Path(audio_path).resolve().as_uri()
                        logger.info(f"非Docker環境での追加オーディオパス: {audio_path} -> {file_url}")

                    # リソースセクションに追加
                    audio_duration_str = optimize_fraction(audio_info.duration, timeline_fps)
                    xml_content += (
                        f'        <asset duration="{audio_duration_str}" id="{resource_id}" '
                        f'name="{_xml_attr(Path(audio_path).name)}" start="0/1s" hasAudio="1" '
                        f'audioSources="1" audioChannels="2">\n'
                        f'            <media-rep kind="original-media" src="{_xml_attr(file_url)}"/>\n'
                        f"        </asset>\n"
                    )
                    asset_counter += 1
                except Exception as e:
                    logger.warning(f"追加オーディオファイルの情報取得に失敗: {audio_path} - {e}")

        # sequenceのdurationも最適化された分数で
        total_duration_str = optimize_fraction(total_duration, timeline_fps)

        # DaVinci Resolveスタイルのイベント名とプロジェクト名
        event_name = _xml_attr(f"{project_name} (Resolve)")

        xml_content += (
            '''    </resources>
    <library>
        <event name="'''
            + event_name
            + '''">
            <project name="'''
            + event_name
            + '''">
                <sequence duration="'''
            + total_duration_str
            + """" tcStart="0/1s" format="r0" tcFormat="NDF">
                    <spine>
"""
        )

        # インデントを設定（gap要素は使わない）
        indent = "                        "

        # blur が実際に asset 登録された場合のみレーンを +1 シフト (z 順序:
        #   動画 → blur(1) → frame(2) → title(3) → BGM(4) → extra audio(5) → SE(6))
        # 注: blur_overlays が渡されても、全 overlay が segment と overlap せず orphan
        # filter で落ちた場合は seen_blur_paths が空。その時は lane_offset=0 で通常通り.
        lane_offset = 1 if seen_blur_paths else 0

        # 各 segment の timeline 開始 frame を事前計算 (blur overlay の offset 計算用)
        seg_timeline_starts: list[int] = []
        _pos = 0
        for seg in segments:
            seg_timeline_starts.append(_pos)
            _pos += round(seg.duration * timeline_fps)

        # 動画 asset-clip + blur overlay で共通使用する scale/anchor 文字列を事前計算
        scale_str = f"{scale[0]:.6g} {scale[1]:.6g}".replace(".0 ", " ").replace(".0", "")
        anchor_str = f"{anchor[0]:.6g} {anchor[1]:.6g}".replace(".0 ", " ").replace(".0", "")

        # クリップを追加
        current_timeline_pos = 0

        for i, seg in enumerate(segments, 1):
            source_path_str = str(seg.source_path)
            resource_id = resource_map[source_path_str]  # 同じ動画ファイルは同じリソースIDを使用
            info = video_infos[source_path_str]

            # DaVinci Resolveスタイルの計算
            # offsetは最適化された分数で
            offset_str = optimize_fraction(current_timeline_pos / timeline_fps, timeline_fps)

            # durationの最適化
            duration_str = optimize_fraction(seg.duration, timeline_fps)

            # start値の最適化
            source_fps = int(info.fps)
            start_str = optimize_fraction(seg.start_time, source_fps)

            # DaVinci Resolveの属性順序に従う
            # タイムラインフォーマット（r0）を使用
            xml_content += (
                f'{indent}<asset-clip duration="{duration_str}" '
                f'name="{_xml_attr(Path(source_path_str).name)}" ref="{resource_id}" '
                f'start="{start_str}" offset="{offset_str}" enabled="1" '
                f'format="r0" tcFormat="NDF">\n'
            )

            # タイムライン上での実際の長さ（次のクリップのoffset計算用）
            timeline_duration_frames = round(seg.duration * timeline_fps)

            # timeMapは削除（DaVinci Resolveでのコンパウンドクリップ問題を回避）

            # DaVinci Resolveスタイルのadjust要素
            xml_content += f'{indent}    <adjust-conform type="fit"/>\n'
            # adjust-transformは常に出力（DaVinci Resolveスタイル）
            xml_content += f'{indent}    <adjust-transform position="0 0" scale="{scale_str}" anchor="{anchor_str}"/>\n'

            # ビデオクリップ内にオーバーレイ、BGM、追加オーディオは含めない

            xml_content += f"{indent}</asset-clip>\n"

            current_timeline_pos += timeline_duration_frames

        # 塗りつぶし PNG をレーン 1 に追加 (動画の直上、frame の下)
        # アライメント保証のため、video asset-clip と全く同じ <adjust-conform type="fit"/> +
        # 同じ scale/anchor を適用する。これで source/timeline 解像度差・縦動画クロップで
        # 完全に video と一致して追従する。
        # 元動画基準の start_sec/end_sec を、各 segment の source-range と重ね合わせて
        # timeline 上の offset/duration を計算する。
        if blur_overlays:
            for ov in blur_overlays:
                png_path = ov["png_path"]
                resource_id = seen_blur_paths.get(png_path)
                if not resource_id:
                    continue
                ov_start = float(ov["start_sec"])
                ov_end = float(ov["end_sec"])
                if ov_end <= ov_start:
                    continue
                png_name = Path(png_path).name
                # 各 segment で重なる範囲を切り出して video 要素を出力
                for seg, seg_start_frame in zip(segments, seg_timeline_starts):
                    overlap_s = max(ov_start, seg.start_time)
                    overlap_e = min(ov_end, seg.end_time)
                    if overlap_e <= overlap_s:
                        continue
                    timeline_offset_frames = seg_start_frame + round(
                        (overlap_s - seg.start_time) * timeline_fps
                    )
                    timeline_duration_frames = round((overlap_e - overlap_s) * timeline_fps)
                    if timeline_duration_frames <= 0:
                        continue
                    offset_frac = Fraction(timeline_offset_frames, timeline_fps)
                    duration_frac = Fraction(timeline_duration_frames, timeline_fps)
                    offset_str = f"{offset_frac.numerator}/{offset_frac.denominator}s"
                    duration_str = f"{duration_frac.numerator}/{duration_frac.denominator}s"
                    xml_content += (
                        f'{indent}<video duration="{duration_str}" lane="1" '
                        f'name="{_xml_attr(png_name)}" ref="{resource_id}" '
                        f'start="0/1s" offset="{offset_str}" enabled="1">\n'
                        f'{indent}    <adjust-conform type="fit"/>\n'
                        f'{indent}    <adjust-transform position="0 0" '
                        f'scale="{scale_str}" anchor="{anchor_str}"/>\n'
                        f"{indent}</video>\n"
                    )

        # オーバーレイ画像をspine直下に追加（全クリップの上に重なる）
        if overlay_settings and overlay_resource_ids and "frame" in overlay_resource_ids:
            xml_content += (
                f'{indent}<video duration="{total_duration_str}" lane="{1 + lane_offset}" '
                f'name="{_xml_attr(Path(overlay_settings["frame_path"]).name)}" ref="{overlay_resource_ids["frame"]}" '
                f'start="0/1s" offset="0/1s" enabled="1">\n'
                f'{indent}    <adjust-conform type="fit"/>\n'
                f'{indent}    <adjust-transform position="0 0" scale="1 1" anchor="0 0"/>\n'
                f"{indent}</video>\n"
            )

        # タイトル画像をspine直下に追加
        # タイトル画像はフレームと同じフルサイズ透過PNGなので position="0 0" で配置
        if title_resource_id and title_settings:
            xml_content += (
                f'{indent}<video duration="{total_duration_str}" lane="{2 + lane_offset}" '
                f'name="{_xml_attr(Path(title_settings["title_path"]).name)}" ref="{title_resource_id}" '
                f'start="0/1s" offset="0/1s" enabled="1">\n'
                f'{indent}    <adjust-conform type="none"/>\n'
                f'{indent}    <adjust-transform position="0 0" scale="1 1" anchor="0 0"/>\n'
                f"{indent}</video>\n"
            )

        # BGMをspine直下に追加（レーン3）
        if bgm_resource_id:
            bgm_volume = bgm_settings.get("bgm_volume", -25)
            bgm_loop = bgm_settings.get("bgm_loop", True)

            if bgm_loop:
                # ループ再生：タイムライン全体の長さに合わせて繰り返す
                bgm_offset = 0
                while bgm_offset < total_duration:
                    # BGMの残り時間を計算
                    remaining_duration = min(bgm_info.duration, total_duration - bgm_offset)
                    remaining_duration_str = optimize_fraction(remaining_duration, timeline_fps)
                    offset_str = f"{round(bgm_offset * timeline_fps)}/{timeline_fps}s"

                    xml_content += (
                        f'{indent}<asset-clip duration="{remaining_duration_str}" lane="{3 + lane_offset}" '
                        f'name="{_xml_attr(Path(bgm_path).name)}" ref="{bgm_resource_id}" '
                        f'start="0/1s" offset="{offset_str}" enabled="1">\n'
                        f'{indent}    <adjust-volume amount="{_safe_volume_db(bgm_volume)}"/>\n'
                        f"{indent}</asset-clip>\n"
                    )

                    bgm_offset += bgm_info.duration
            else:
                # ループなし：BGMの長さまたはタイムラインの長さの短い方を使用
                bgm_duration = min(bgm_info.duration, total_duration)
                bgm_duration_str = optimize_fraction(bgm_duration, timeline_fps)

                xml_content += (
                    f'{indent}<asset-clip duration="{bgm_duration_str}" lane="{3 + lane_offset}" '
                    f'name="{_xml_attr(Path(bgm_path).name)}" ref="{bgm_resource_id}" '
                    f'start="0/1s" offset="0/1s" enabled="1">\n'
                    f'{indent}    <adjust-volume amount="{_safe_volume_db(bgm_volume)}"/>\n'
                    f"{indent}</asset-clip>\n"
                )

        # 追加オーディオをspine直下に配置（レーン4に5フレームの隙間を開けて並べる）
        if additional_audio_resource_ids:
            current_offset = 0
            gap_frames = 5  # クリップ間の隙間（フレーム数）
            gap_duration = gap_frames / timeline_fps  # 秒に変換

            for audio_path, (resource_id, audio_info, volume) in additional_audio_resource_ids.items():
                # 残りの時間がオーディオの長さより短い場合は、残り時間分だけ配置
                remaining_duration = total_duration - current_offset
                if remaining_duration <= 0:
                    break

                audio_duration = min(audio_info.duration, remaining_duration)
                duration_str = optimize_fraction(audio_duration, timeline_fps)
                offset_str = f"{round(current_offset * timeline_fps)}/{timeline_fps}s"

                xml_content += (
                    f'{indent}<asset-clip duration="{duration_str}" lane="{4 + lane_offset}" '
                    f'name="{_xml_attr(Path(audio_path).name)}" ref="{resource_id}" '
                    f'start="0/1s" offset="{offset_str}" enabled="1">\n'
                )
                if volume != 0:
                    xml_content += f'{indent}    <adjust-volume amount="{_safe_volume_db(volume)}"/>\n'
                xml_content += f"{indent}</asset-clip>\n"

                # 次のクリップの開始位置は、現在のクリップの終了位置 + 隙間
                current_offset += audio_duration + gap_duration

        # AI配置SE（レーン5: 字幕内容に基づいてタイミング決定）
        if ai_se_placements and additional_audio_resource_ids:
            for placement in ai_se_placements:
                se_path = placement.se_file
                if se_path not in additional_audio_resource_ids:
                    logger.warning(f"AI SE配置: リソース未登録のSEファイル: {se_path}、スキップ")
                    continue

                resource_id, audio_info, volume = additional_audio_resource_ids[se_path]
                se_duration = min(audio_info.duration, total_duration - placement.timestamp)
                if se_duration <= 0:
                    continue

                duration_str = optimize_fraction(se_duration, timeline_fps)
                offset_str = optimize_fraction(placement.timestamp, timeline_fps)

                xml_content += (
                    f'{indent}<asset-clip duration="{duration_str}" lane="{5 + lane_offset}" '
                    f'name="{_xml_attr(Path(se_path).name)}" ref="{resource_id}" '
                    f'start="0/1s" offset="{offset_str}" enabled="1">\n'
                )
                if volume != 0:
                    xml_content += f'{indent}    <adjust-volume amount="{_safe_volume_db(volume)}"/>\n'
                xml_content += f"{indent}</asset-clip>\n"

        xml_content += """                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""

        return xml_content


class XMEMLExporter:
    """Premiere Pro用XMEML形式エクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        project_name: str = "TextffCut Project",
    ) -> bool:
        """
        XMEMLファイルをエクスポート

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
            video_infos: dict[str, VideoInfo] = {}
            for seg in segments:
                source_path_str = str(seg.source_path)
                if source_path_str not in video_infos:
                    video_infos[source_path_str] = VideoInfo.from_file(seg.source_path)

            # XMLを構築
            xml_content = self._build_xmeml(segments, video_infos, timeline_fps, project_name)

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(xml_content)

            return True

        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"XMEML書き込み権限エラー: {str(e)}") from e
        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"XMEML書き込みエラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"XMEMLエクスポートエラー: {str(e)}") from e

    def _build_xmeml(
        self, segments: list[ExportSegment], video_infos: dict[str, VideoInfo], timeline_fps: int, project_name: str
    ) -> str:
        """XMEMLコンテンツを構築（Premiere Pro完全互換）"""
        import uuid

        # 総時間を計算（フレーム数）
        total_duration_frames = sum(round(seg.duration * timeline_fps) for seg in segments)

        # XMLヘッダー
        xml_content = (
            """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE xmeml>
<xmeml version="4">
	<sequence id="sequence-1">
		<uuid>"""
            + str(uuid.uuid4())
            + """</uuid>
		<duration>"""
            + str(total_duration_frames)
            + """</duration>
		<rate>
			<timebase>"""
            + str(timeline_fps)
            + """</timebase>
			<ntsc>FALSE</ntsc>
		</rate>
		<name>"""
            + xml_escape(project_name)
            + """</name>
		<media>
			<video>
				<format>
					<samplecharacteristics>
						<rate>
							<timebase>"""
            + str(timeline_fps)
            + """</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<codec>
							<name>Apple ProRes 422</name>
							<appspecificdata>
								<appname>Final Cut Pro</appname>
								<appmanufacturer>Apple Inc.</appmanufacturer>
								<appversion>7.0</appversion>
								<data>
									<qtcodec>
										<codecname>Apple ProRes 422</codecname>
										<codectypename>Apple ProRes 422</codectypename>
										<codectypecode>apcn</codectypecode>
										<codecvendorcode>appl</codecvendorcode>
										<spatialquality>1024</spatialquality>
										<temporalquality>0</temporalquality>
										<keyframerate>0</keyframerate>
										<datarate>0</datarate>
									</qtcodec>
								</data>
							</appspecificdata>
						</codec>
						<width>1920</width>
						<height>1080</height>
						<anamorphic>FALSE</anamorphic>
						<pixelaspectratio>square</pixelaspectratio>
						<fielddominance>none</fielddominance>
						<colordepth>24</colordepth>
					</samplecharacteristics>
				</format>
				<track>
"""
        )

        # ビデオクリップを追加
        file_counter = 1
        file_map = {}
        video_clip_count = len(segments)

        for i, seg in enumerate(segments, 1):
            # ファイルIDを管理
            if seg.source_path not in file_map:
                file_map[seg.source_path] = f"file-{file_counter}"
                file_counter += 1

            file_id = file_map[seg.source_path]

            # フレーム数で計算
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # URLエンコードされたファイルパス

            # ファイルパスを処理
            # Docker環境の場合はホストパスに変換
            is_docker = os.path.exists("/.dockerenv")
            if is_docker and str(seg.source_path).startswith("/app/videos/"):
                # Docker環境: /app/videos/xxx.mp4 -> HOST_VIDEOS_PATH/xxx.mp4
                host_videos_path = os.getenv("HOST_VIDEOS_PATH", os.getenv("PWD", "") + "/videos")
                relative_path = str(seg.source_path).replace("/app/videos/", "")
                source_path = os.path.join(host_videos_path, relative_path)
                # Unix形式のパスに変換
                file_url = f"file://localhost{source_path}".replace("\\", "/")
            else:
                # ローカル環境: 実際のパスを使用
                source_path_resolved = Path(seg.source_path).resolve()

                # Windowsの場合はドライブレターの処理
                if os.name == "nt":
                    # C:\path\to\file -> /C:/path/to/file
                    file_url = f"file://localhost/{str(source_path_resolved)}".replace("\\", "/")
                else:
                    # Unix系: /path/to/file -> file://localhost/path/to/file
                    file_url = f"file://localhost{source_path_resolved}"

            # 総ファイルduration
            source_path_str = str(seg.source_path)
            total_file_duration = round(video_infos[source_path_str].duration * timeline_fps)

            xml_content += f"""					<clipitem id="clipitem-{i}">
						<masterclipid>masterclip-1</masterclipid>
						<name>{xml_escape(Path(seg.source_path).stem)}</name>
						<enabled>TRUE</enabled>
						<duration>{total_file_duration}</duration>
						<rate>
							<timebase>{timeline_fps}</timebase>
							<ntsc>FALSE</ntsc>
						</rate>
						<start>{timeline_start_frames}</start>
						<end>{timeline_end_frames}</end>
						<in>{start_frames}</in>
						<out>{end_frames}</out>
						<alphatype>none</alphatype>
						<pixelaspectratio>square</pixelaspectratio>
						<anamorphic>FALSE</anamorphic>
						<file id="{file_id}">
							<name>{xml_escape(Path(seg.source_path).name)}</name>
							<pathurl>{xml_escape(file_url)}</pathurl>
							<rate>
								<timebase>{timeline_fps}</timebase>
								<ntsc>FALSE</ntsc>
							</rate>
							<duration>{total_file_duration}</duration>
							<timecode>
								<rate>
									<timebase>{timeline_fps}</timebase>
									<ntsc>FALSE</ntsc>
								</rate>
								<string>00:00:00:00</string>
								<frame>0</frame>
								<displayformat>NDF</displayformat>
							</timecode>
							<media>
								<video>
									<samplecharacteristics>
										<rate>
											<timebase>{timeline_fps}</timebase>
											<ntsc>FALSE</ntsc>
										</rate>
										<width>1920</width>
										<height>1080</height>
										<anamorphic>FALSE</anamorphic>
										<pixelaspectratio>square</pixelaspectratio>
										<fielddominance>none</fielddominance>
									</samplecharacteristics>
								</video>
								<audio>
									<samplecharacteristics>
										<depth>16</depth>
										<samplerate>48000</samplerate>
									</samplecharacteristics>
									<channelcount>2</channelcount>
								</audio>
							</media>
						</file>
						<link>
							<linkclipref>clipitem-{i}</linkclipref>
							<mediatype>video</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>1</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<link>
							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>
							<mediatype>audio</mediatype>
							<trackindex>2</trackindex>
							<clipindex>{i}</clipindex>
							<groupindex>1</groupindex>
						</link>
						<logginginfo>
							<description></description>
							<scene></scene>
							<shottake></shottake>
							<lognote></lognote>
							<good></good>
							<originalvideofilename></originalvideofilename>
							<originalaudiofilename></originalaudiofilename>
						</logginginfo>
						<colorinfo>
							<lut></lut>
							<lut1></lut1>
							<asc_sop></asc_sop>
							<asc_sat></asc_sat>
							<lut2></lut2>
						</colorinfo>
						<labels>
							<label2>Iris</label2>
						</labels>
					</clipitem>
"""

        xml_content += """					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
				</track>
			</video>
			<audio>
				<numOutputChannels>2</numOutputChannels>
				<format>
					<samplecharacteristics>
						<depth>16</depth>
						<samplerate>48000</samplerate>
					</samplecharacteristics>
				</format>
				<outputs>
					<group>
						<index>1</index>
						<numchannels>1</numchannels>
						<downmix>0</downmix>
						<channel>
							<index>1</index>
						</channel>
					</group>
					<group>
						<index>2</index>
						<numchannels>1</numchannels>
						<downmix>0</downmix>
						<channel>
							<index>2</index>
						</channel>
					</group>
				</outputs>
"""

        # オーディオトラック1を追加
        xml_content += (
            '				<track currentExplodedTrackIndex="0" totalExplodedTrackCount="2" ' 'premiereTrackType="Stereo">\n'
        )

        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]

            # フレーム数で計算（ビデオと同じ）
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # 総ファイルduration
            total_file_duration = round(video_infos[str(seg.source_path)].duration * timeline_fps)

            xml_content += (
                f'					<clipitem id="clipitem-{video_clip_count + i}" '
                f'premiereChannelType="stereo">\n'
                f"						<masterclipid>masterclip-1</masterclipid>\n"
                f"						<name>{xml_escape(Path(seg.source_path).stem)}</name>\n"
                f"						<enabled>TRUE</enabled>\n"
                f"						<duration>{total_file_duration}</duration>\n"
                f"						<rate>\n"
                f"							<timebase>{timeline_fps}</timebase>\n"
                f"							<ntsc>FALSE</ntsc>\n"
                f"						</rate>\n"
                f"						<start>{timeline_start_frames}</start>\n"
                f"						<end>{timeline_end_frames}</end>\n"
                f"						<in>{start_frames}</in>\n"
                f"						<out>{end_frames}</out>\n"
                f'						<file id="{file_id}"/>\n'
                f"						<sourcetrack>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"						</sourcetrack>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{i}</linkclipref>\n"
                f"							<mediatype>video</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<logginginfo>\n"
                f"							<description></description>\n"
                f"							<scene></scene>\n"
                f"							<shottake></shottake>\n"
                f"							<lognote></lognote>\n"
                f"							<good></good>\n"
                f"							<originalvideofilename></originalvideofilename>\n"
                f"							<originalaudiofilename></originalaudiofilename>\n"
                f"						</logginginfo>\n"
                f"						<colorinfo>\n"
                f"							<lut></lut>\n"
                f"							<lut1></lut1>\n"
                f"							<asc_sop></asc_sop>\n"
                f"							<asc_sat></asc_sat>\n"
                f"							<lut2></lut2>\n"
                f"						</colorinfo>\n"
                f"						<labels>\n"
                f"							<label2>Iris</label2>\n"
                f"						</labels>\n"
                f"					</clipitem>\n"
            )

        xml_content += """					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>1</outputchannelindex>
				</track>
"""

        # オーディオトラック2を追加
        xml_content += (
            '				<track currentExplodedTrackIndex="1" totalExplodedTrackCount="2" ' 'premiereTrackType="Stereo">\n'
        )

        for i, seg in enumerate(segments, 1):
            file_id = file_map[seg.source_path]

            # フレーム数で計算（ビデオと同じ）
            start_frames = round(seg.start_time * timeline_fps)
            end_frames = round(seg.end_time * timeline_fps)
            duration_frames = end_frames - start_frames

            # タイムライン上の位置
            timeline_start_frames = sum(round(s.duration * timeline_fps) for s in segments[: i - 1])
            timeline_end_frames = timeline_start_frames + duration_frames

            # 総ファイルduration
            total_file_duration = round(video_infos[str(seg.source_path)].duration * timeline_fps)

            xml_content += (
                f'					<clipitem id="clipitem-{video_clip_count * 2 + i}" '
                f'premiereChannelType="stereo">\n'
                f"						<masterclipid>masterclip-1</masterclipid>\n"
                f"						<name>{xml_escape(Path(seg.source_path).stem)}</name>\n"
                f"						<enabled>TRUE</enabled>\n"
                f"						<duration>{total_file_duration}</duration>\n"
                f"						<rate>\n"
                f"							<timebase>{timeline_fps}</timebase>\n"
                f"							<ntsc>FALSE</ntsc>\n"
                f"						</rate>\n"
                f"						<start>{timeline_start_frames}</start>\n"
                f"						<end>{timeline_end_frames}</end>\n"
                f"						<in>{start_frames}</in>\n"
                f"						<out>{end_frames}</out>\n"
                f'						<file id="{file_id}"/>\n'
                f"						<sourcetrack>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"						</sourcetrack>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{i}</linkclipref>\n"
                f"							<mediatype>video</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>1</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<link>\n"
                f"							<linkclipref>clipitem-{video_clip_count * 2 + i}</linkclipref>\n"
                f"							<mediatype>audio</mediatype>\n"
                f"							<trackindex>2</trackindex>\n"
                f"							<clipindex>{i}</clipindex>\n"
                f"							<groupindex>1</groupindex>\n"
                f"						</link>\n"
                f"						<logginginfo>\n"
                f"							<description></description>\n"
                f"							<scene></scene>\n"
                f"							<shottake></shottake>\n"
                f"							<lognote></lognote>\n"
                f"							<good></good>\n"
                f"							<originalvideofilename></originalvideofilename>\n"
                f"							<originalaudiofilename></originalaudiofilename>\n"
                f"						</logginginfo>\n"
                f"						<colorinfo>\n"
                f"							<lut></lut>\n"
                f"							<lut1></lut1>\n"
                f"							<asc_sop></asc_sop>\n"
                f"							<asc_sat></asc_sat>\n"
                f"							<lut2></lut2>\n"
                f"						</colorinfo>\n"
                f"						<labels>\n"
                f"							<label2>Iris</label2>\n"
                f"						</labels>\n"
                f"					</clipitem>\n"
            )

        xml_content += (
            """					<enabled>TRUE</enabled>
					<locked>FALSE</locked>
					<outputchannelindex>2</outputchannelindex>
				</track>
			</audio>
		</media>
		<timecode>
			<rate>
				<timebase>"""
            + str(timeline_fps)
            + """</timebase>
				<ntsc>FALSE</ntsc>
			</rate>
			<string>00:00:00:00</string>
			<frame>0</frame>
			<displayformat>NDF</displayformat>
		</timecode>
		<labels>
			<label2>Forest</label2>
		</labels>
		<logginginfo>
			<description></description>
			<scene></scene>
			<shottake></shottake>
			<lognote></lognote>
			<good></good>
			<originalvideofilename></originalvideofilename>
			<originalaudiofilename></originalaudiofilename>
		</logginginfo>
	</sequence>
</xmeml>"""
        )

        return xml_content


class EDLExporter:
    """EDL（Edit Decision List）エクスポートクラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def export(
        self,
        segments: list[ExportSegment],
        output_path: str | Path,
        timeline_fps: int = 30,
        title: str = "TextffCut EDL",
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
            edl_content += "FCM: NON-DROP FRAME\n\n"

            # 各セグメントをEDL形式で追加
            timeline_pos = 0.0

            for i, seg in enumerate(segments, 1):
                # タイムコードを計算
                source_in = frames_to_timecode(int(seg.start_time), timeline_fps)
                source_out = frames_to_timecode(int(seg.end_time), timeline_fps)
                record_in = frames_to_timecode(int(timeline_pos), timeline_fps)
                record_out = frames_to_timecode(int(timeline_pos + seg.duration), timeline_fps)

                # EDLエントリ
                edl_content += f"{i:03d}  001      V     C        "
                edl_content += f"{source_in} {source_out} "
                edl_content += f"{record_in} {record_out}\n"
                edl_content += f"* FROM CLIP NAME: {Path(seg.source_path).name}\n\n"

                timeline_pos += seg.duration

            # ファイルに保存
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(edl_content)

            return True

        except PermissionError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"EDL書き込み権限エラー: {str(e)}") from e
        except OSError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(f"EDL書き込みエラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"EDLエクスポートエラー: {str(e)}") from e
