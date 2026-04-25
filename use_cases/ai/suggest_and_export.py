"""
一気通貫ユースケース: AI話題検出 → 骨子+結び候補生成 → AI選定 → 無音削除 → FCPXML

パイプライン:
1. Phase 0: 早期フィラー検出
2. Phase 1: AI話題検出 + Phase 1.5: 境界補正
3. Phase 2c: 骨子+結びベース候補生成
4. Phase 3: AI最良候補選定 + Phase 3.5: 吃音除去
5. 無音削除 → FCPXML + SRT生成
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface
from use_cases.ai.generate_clip_suggestions import GenerateClipSuggestionsUseCase

logger = logging.getLogger(__name__)


@dataclass
class SuggestAndExportRequest:
    video_path: Path
    transcription: TranscriptionResult
    ai_model: str = "gpt-4.1-mini"
    num_candidates: int = 5
    min_duration: int = 30
    max_duration: int = 60
    prompt_path: str | None = None
    remove_silence: bool = True
    generate_srt: bool = True
    srt_max_chars: int = 11
    srt_max_lines: int = 2
    preset_dir: Path | None = None
    enable_frame: bool = True
    enable_bgm: bool = True
    enable_se: bool = True
    speed: float = 1.0  # 再生速度（1.0=等速、1.2=1.2倍速）
    scale: tuple[float, float] = (1.0, 1.0)  # ズーム倍率 (x, y)
    anchor: tuple[float, float] = (0.0, 0.0)  # アンカーポイント (x, y)
    timeline_resolution: str = "horizontal"  # タイムライン向き ("horizontal" or "vertical")
    enable_title_image: bool = True  # タイトル画像生成
    title_target_size: tuple[int, int] | None = None  # タイトル画像ターゲットサイズ (width, height)
    title_offset_y: int = 0  # タイトル表示位置の垂直オフセット（px、正=下方向）
    auto_anchor: bool = False  # 被写体位置からアンカーを自動検出（vertical時のみ有効）
    use_blurred_source: bool = True  # auto_blur で生成済みの source_blurred.mp4 があれば優先使用


@dataclass
class SuggestAndExportResult:
    suggestions: list[ClipSuggestion]
    exported_files: list[Path]
    output_dir: Path
    detection_processing_time: float
    detection_cost_usd: float


class SuggestAndExportUseCase:

    def __init__(self, gateway: ClipSuggestionGatewayInterface):
        self.gateway = gateway

    def execute(self, request: SuggestAndExportRequest) -> SuggestAndExportResult:
        import time as _time

        _phase_times: dict[str, float] = {}
        _t0 = _time.time()

        # Phase 1-3: AI話題検出 → 力任せ候補生成 → AI選定
        use_case = GenerateClipSuggestionsUseCase(self.gateway)
        suggestions = use_case.execute(
            transcription=request.transcription,
            num_candidates=request.num_candidates,
            min_duration=request.min_duration,
            max_duration=request.max_duration,
            prompt_path=request.prompt_path,
        )

        detection = use_case.last_detection_result
        _phase_times["Phase1-3 話題検出+候補生成+AI選定"] = _time.time() - _t0

        # 出力ディレクトリ
        video_name = request.video_path.stem
        base_dir = request.video_path.parent / f"{video_name}_TextffCut"
        fcpxml_dir = base_dir / "fcpxml"
        fcpxml_dir.mkdir(parents=True, exist_ok=True)

        _t3 = _time.time()
        # Phase 5: 無音削除（最終候補にのみ適用）
        if request.remove_silence:
            for suggestion in suggestions:
                self._apply_silence_removal(
                    suggestion, request.video_path, base_dir, transcription=request.transcription
                )

        # Phase 5.5: 速度変更
        actual_video_path = request.video_path
        used_blur_source = False  # auto_blur ぼかし版を採用したかの明示フラグ

        # auto_blur cache 検出: source_blurred.mp4 が存在 + use_blurred_source=True で適用
        if request.use_blurred_source:
            from use_cases.auto_blur import AutoBlurUseCase

            _blur_uc = AutoBlurUseCase()
            if _blur_uc.is_cached(request.video_path):
                blurred_path, _ = _blur_uc.get_cache_paths(request.video_path)
                actual_video_path = blurred_path
                used_blur_source = True
                logger.info(f"auto_blur cache hit、ぼかし版動画を使用: {blurred_path}")

        if request.speed != 1.0:
            from config import Config
            from core.video import VideoProcessor

            speed = round(request.speed, 2)
            speed_label = f"{round(speed, 1)}x"
            vp = VideoProcessor(Config())
            # auto_blur cache 利用時はファイル名に _blurred を付ける
            suffix = "_blurred" if used_blur_source else ""
            speed_path = base_dir / f"source_{speed_label}{suffix}.mp4"
            vp.create_speed_changed_video(str(actual_video_path), str(speed_path), speed)
            actual_video_path = speed_path
            logger.info(f"速度変更済み動画を使用: {speed_path}")

            # 全候補のtime_rangesを速度に合わせて調整（FFmpegと同じ丸め値を使用）
            for suggestion in suggestions:
                suggestion.time_ranges = [(s / speed, e / speed) for s, e in suggestion.time_ranges]
                suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)

        # キャッシュ保存 (speed は字幕エディタの meta backfill で使うため保存)
        cache_dir = base_dir / "clip_suggestions"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._save_cache(
            suggestions,
            detection,
            cache_dir / f"{detection.model_used}.json",
            speed=request.speed,
        )

        # メディア素材検出
        from utils.media_asset_detector import detect_media_assets

        media_config = detect_media_assets(
            request.video_path,
            request.preset_dir,
            enable_frame=request.enable_frame,
            enable_bgm=request.enable_bgm,
            enable_se=request.enable_se,
        )
        if media_config.has_any:
            logger.info(media_config.summary())

        _phase_times["Phase5 無音削除+速度変更"] = _time.time() - _t3
        _t4 = _time.time()
        # Phase 5.7: タイトル画像生成（バッチ1回のAI呼び出し）
        title_image_paths: dict[int, Path] = {}
        if request.enable_title_image:
            try:
                from use_cases.ai.title_image_generator import generate_title_images_batch

                titles_dir = base_dir / "title_images"

                frame_path = None
                if media_config and media_config.overlay_settings:
                    fp = media_config.overlay_settings.get("frame_path")
                    if fp:
                        frame_path = Path(fp)

                title_image_paths = generate_title_images_batch(
                    suggestions=suggestions,
                    output_dir=titles_dir,
                    orientation=request.timeline_resolution,
                    client=self.gateway.client,
                    model=request.ai_model,
                    font_dir=request.preset_dir / "fonts" if request.preset_dir else None,
                    frame_path=frame_path,
                    sanitize_fn=sanitize_filename,
                    target_size=request.title_target_size,
                    offset_y=request.title_offset_y,
                )

            except Exception as e:
                logger.warning(f"タイトル画像生成をスキップ: {e}")

        # Phase 5.8: アンカー自動検出（vertical + 手動指定なし + auto_anchor有効時）
        actual_anchor = request.anchor
        if request.auto_anchor and request.timeline_resolution == "vertical" and request.anchor == (0.0, 0.0):
            try:
                from use_cases.ai.auto_anchor_detector import detect_anchor, anchor_to_fcpxml

                # 最初の候補の中間時刻をフレーム抽出点に使用
                frame_t = 5.0
                if suggestions and suggestions[0].time_ranges:
                    first_range = suggestions[0].time_ranges[0]
                    frame_t = (first_range[0] + first_range[1]) / 2
                result = detect_anchor(
                    video_path=request.video_path,
                    client=self.gateway.client,
                    frame_time=frame_t,
                )
                from core.video import VideoInfo

                try:
                    vi = VideoInfo.from_file(request.video_path)
                    src_w, src_h = vi.width, vi.height
                except Exception:
                    logger.warning("VideoInfo取得失敗、デフォルト1920x1080を使用")
                    src_w, src_h = 1920, 1080
                actual_anchor = anchor_to_fcpxml(
                    result.anchor_x,
                    result.anchor_y,
                    src_w,
                    src_h,
                    request.scale,
                )
                logger.info("アンカー自動検出: %s — %s", actual_anchor, result.description)
            except Exception as e:
                logger.warning("アンカー自動検出スキップ: %s", e)

        _phase_times["Phase5.7 タイトル画像"] = _time.time() - _t4
        _t6 = _time.time()
        # Phase 6: AI SE配置 + FCPXML + SRT生成
        exported_files: list[Path] = []
        for i, suggestion in enumerate(suggestions, 1):
            sanitized = sanitize_filename(suggestion.title)

            # AI SE配置を計算（SEファイルがある場合）
            ai_se_placements = None
            if request.enable_se and media_config and media_config.additional_audio_settings:
                ai_se_placements = self._compute_ai_se_placements(
                    suggestion=suggestion,
                    transcription=request.transcription,
                    media_config=media_config,
                    srt_max_chars=request.srt_max_chars,
                    srt_max_lines=request.srt_max_lines,
                    ai_model=request.ai_model,
                    speed=request.speed,
                )

            # FCPXML（速度変更済み動画を参照）
            title_path = title_image_paths.get(i)
            title_settings = None
            if title_path:
                title_settings = {"title_path": str(title_path)}
            fcpxml_path = fcpxml_dir / f"{i:02d}_{sanitized}.fcpxml"
            success = self._export_fcpxml(
                suggestion,
                actual_video_path,
                fcpxml_path,
                media_config,
                scale=request.scale,
                anchor=actual_anchor,
                timeline_resolution=request.timeline_resolution,
                title_settings=title_settings,
                ai_se_placements=ai_se_placements,
            )
            if success:
                exported_files.append(fcpxml_path)

            # SRT字幕（速度変更済みタイムスタンプで生成）
            if request.generate_srt:
                from use_cases.ai.srt_subtitle_generator import generate_srt

                srt_path = fcpxml_dir / f"{i:02d}_{sanitized}.srt"
                generate_srt(
                    suggestion=suggestion,
                    transcription=request.transcription,
                    output_path=srt_path,
                    max_chars_per_line=request.srt_max_chars,
                    max_lines=request.srt_max_lines,
                    speed=request.speed,
                )

        _phase_times["Phase6b SE+FCPXML+SRT生成"] = _time.time() - _t6
        _total = _time.time() - _t0
        logger.info("=== パイプライン処理時間 ===")
        for phase, elapsed in _phase_times.items():
            pct = elapsed / _total * 100 if _total > 0 else 0
            logger.info(f"  {phase}: {elapsed:.1f}s ({pct:.0f}%)")
        logger.info(f"  合計: {_total:.1f}s")

        return SuggestAndExportResult(
            suggestions=suggestions,
            exported_files=exported_files,
            output_dir=fcpxml_dir,
            detection_processing_time=detection.processing_time,
            detection_cost_usd=detection.estimated_cost_usd,
        )

    def _compute_ai_se_placements(
        self,
        suggestion: ClipSuggestion,
        transcription: TranscriptionResult,
        media_config,
        srt_max_chars: int = 11,
        srt_max_lines: int = 2,
        ai_model: str = "gpt-4.1-mini",
        speed: float = 1.0,
    ) -> list | None:
        """字幕データからAI SE配置を計算する"""
        try:
            from use_cases.ai.se_placement import plan_se_placements
            from use_cases.ai.srt_subtitle_generator import (
                build_timeline_map,
                collect_parts,
                generate_srt_entries_from_segments,
            )
            from use_cases.ai.subtitle_image_renderer import SubtitleEntry

            se_files = [
                Path(p) for p in media_config.additional_audio_settings.get("audio_files", []) if Path(p).exists()
            ]
            if not se_files:
                return None

            tmap = build_timeline_map(suggestion.time_ranges)
            parts = collect_parts(suggestion.time_ranges, tmap, transcription, speed=speed)
            if not parts:
                return None

            segments = [{"text": text, "start": tl_s, "end": tl_e} for text, tl_s, tl_e in parts]
            srt_entries = generate_srt_entries_from_segments(
                segments,
                max_chars_per_line=srt_max_chars,
                max_lines=srt_max_lines,
            )
            if not srt_entries:
                return None

            sub_entries = [
                SubtitleEntry(
                    index=e.index,
                    start_time=e.start_time,
                    end_time=e.end_time,
                    text=e.text,
                )
                for e in srt_entries
            ]

            placements = plan_se_placements(
                client=self.gateway.client,
                subtitle_entries=sub_entries,
                se_files=se_files,
                model=ai_model,
            )
            return placements if placements else None

        except Exception as e:
            logger.warning(f"AI SE配置スキップ: {e}")
            return None

    def _apply_silence_removal(
        self,
        suggestion: ClipSuggestion,
        video_path: Path,
        base_dir: Path,
        transcription: TranscriptionResult | None = None,
    ) -> None:
        """1つの候補に無音削除を適用する。"""
        try:
            from config import Config
            from core.video import VideoProcessor

            vp = VideoProcessor(Config())
            temp_dir = str(base_dir / "temp_wav")

            words_list: list | None = None
            if transcription is not None:
                words_list = [w for seg in transcription.segments for w in (seg.words or [])]

            new_ranges = vp.remove_silence_new(
                input_path=str(video_path),
                time_ranges=suggestion.time_ranges,
                output_dir=temp_dir,
                transcription_words=words_list,
            )
            if new_ranges:
                old_dur = suggestion.total_duration
                suggestion.time_ranges = new_ranges
                suggestion.total_duration = sum(e - s for s, e in new_ranges)
                logger.info(
                    f"無音削除: {suggestion.title} "
                    f"{old_dur:.1f}s → {suggestion.total_duration:.1f}s "
                    f"({len(new_ranges)}クリップ)"
                )

            # temp_wav クリーンアップ
            import shutil

            temp_path = base_dir / "temp_wav"
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)

        except Exception as e:
            logger.warning(f"無音削除失敗 ({suggestion.title}): {e}")

    def _export_fcpxml(
        self,
        suggestion: ClipSuggestion,
        video_path: Path,
        output_path: Path,
        media_config: "MediaAssetConfig | None" = None,  # noqa: F821
        scale: tuple[float, float] = (1.0, 1.0),
        anchor: tuple[float, float] = (0.0, 0.0),
        timeline_resolution: str = "horizontal",
        title_settings: dict | None = None,
        ai_se_placements: list | None = None,
    ) -> bool:
        if not suggestion.time_ranges:
            return False

        try:
            from config import Config
            from core.export import ExportSegment, FCPXMLExporter

            segments = []
            timeline_pos = 0.0
            for start, end in suggestion.time_ranges:
                segments.append(
                    ExportSegment(
                        source_path=str(video_path),
                        start_time=start,
                        end_time=end,
                        timeline_start=timeline_pos,
                    )
                )
                timeline_pos += end - start

            exporter = FCPXMLExporter(Config())
            return exporter.export(
                segments=segments,
                output_path=str(output_path),
                project_name=suggestion.title,
                scale=scale,
                anchor=anchor,
                timeline_resolution=timeline_resolution,
                overlay_settings=media_config.overlay_settings if media_config else None,
                bgm_settings=media_config.bgm_settings if media_config else None,
                additional_audio_settings=media_config.additional_audio_settings if media_config else None,
                title_settings=title_settings,
                ai_se_placements=ai_se_placements,
            )
        except Exception as e:
            logger.warning(f"FCPXMLExporter failed ({e}), using simple FCPXML")
            return self._export_simple_fcpxml(
                suggestion,
                video_path,
                output_path,
                media_config=media_config,
                scale=scale,
                anchor=anchor,
                timeline_resolution=timeline_resolution,
                title_settings=title_settings,
                ai_se_placements=ai_se_placements,
            )

    def _export_simple_fcpxml(
        self,
        suggestion: ClipSuggestion,
        video_path: Path,
        output_path: Path,
        media_config: "MediaAssetConfig | None" = None,  # noqa: F821
        scale: tuple[float, float] = (1.0, 1.0),
        anchor: tuple[float, float] = (0.0, 0.0),
        timeline_resolution: str = "horizontal",
        title_settings: dict | None = None,
        ai_se_placements: list | None = None,
    ) -> bool:
        """ffprobeなしで簡易FCPXMLを生成する（DaVinci Resolve互換）"""
        from fractions import Fraction
        from urllib.parse import quote

        def to_frac(seconds: float, fps: int = 30) -> str:
            frames = round(seconds * fps)
            frac = Fraction(frames, fps)
            if frac.numerator == 0:
                return "0/1s"
            return f"{frac.numerator}/{frac.denominator}s"

        from xml.sax.saxutils import escape

        def _attr(v: str) -> str:
            return escape(v, {'"': "&quot;"})

        video_name = _attr(video_path.name)
        title_escaped = _attr(suggestion.title)
        encoded_path = quote(str(video_path), safe="/:")
        video_url = f"file://{encoded_path}"

        from core.export import ExportSegment, _safe_volume_db

        segments = []
        timeline_pos = 0.0
        for start, end in suggestion.time_ranges:
            segments.append(
                ExportSegment(
                    source_path=str(video_path),
                    start_time=start,
                    end_time=end,
                    timeline_start=timeline_pos,
                )
            )
            timeline_pos += end - start

        total_dur = timeline_pos

        clips_xml = ""
        for seg in segments:
            dur = seg.end_time - seg.start_time
            clips_xml += (
                f'                        <asset-clip duration="{to_frac(dur)}" '
                f'name="{video_name}" ref="r1" '
                f'start="{to_frac(seg.start_time)}" '
                f'offset="{to_frac(seg.timeline_start)}" '
                f'enabled="1" format="r0" tcFormat="NDF">\n'
                f'                            <adjust-conform type="fit"/>\n'
                f'                            <adjust-transform position="0 0" scale="{scale[0]:.6g} {scale[1]:.6g}" anchor="{anchor[0]:.6g} {anchor[1]:.6g}"/>\n'
                f"                        </asset-clip>\n"
            )

        if timeline_resolution == "vertical":
            fmt_w, fmt_h = 1080, 1920
            fmt_name = "FFVideoFormatVertical30"
        else:
            fmt_w, fmt_h = 1920, 1080
            fmt_name = "FFVideoFormat1080p30"

        # 次のリソースID（r0=format, r1=video）
        next_rid = 2

        # タイトル画像リソース（フルサイズ透過PNG — position="0 0"で配置）
        title_asset_xml = ""
        title_spine_xml = ""
        if title_settings and "title_path" in title_settings:
            title_path = title_settings["title_path"]
            if Path(title_path).exists():
                title_url = f"file://{quote(str(Path(title_path).resolve()), safe='/:')}"
                title_rid = f"r{next_rid}"
                next_rid += 1

                title_asset_xml = (
                    f'        <asset duration="0/1s" id="{title_rid}" '
                    f'name="{_attr(Path(title_path).name)}" start="0/1s" hasVideo="1" format="r0">\n'
                    f'            <media-rep kind="original-media" src="{_attr(title_url)}"/>\n'
                    f"        </asset>\n"
                )
                title_spine_xml = (
                    f'                        <video duration="{to_frac(total_dur)}" lane="2" '
                    f'name="{_attr(Path(title_path).name)}" ref="{title_rid}" '
                    f'start="0/1s" offset="0/1s" enabled="1">\n'
                    f'                            <adjust-conform type="none"/>\n'
                    f'                            <adjust-transform position="0 0" scale="1 1" anchor="0 0"/>\n'
                    f"                        </video>\n"
                )

        # SE リソース登録 + レーン4（SE一覧）+ レーン5（AI配置SE）
        se_asset_xml = ""
        se_lane4_xml = ""
        se_lane5_xml = ""
        se_rid_map: dict[str, tuple[str, float]] = {}  # path -> (resource_id, duration)

        if media_config and media_config.additional_audio_settings:
            audio_files = media_config.additional_audio_settings.get("audio_files", [])
            volume = media_config.additional_audio_settings.get("volume", -20)

            for audio_path in audio_files:
                ap = Path(audio_path)
                if not ap.exists():
                    continue
                rid = f"r{next_rid}"
                next_rid += 1

                audio_url = f"file://{quote(str(ap.resolve()), safe='/:')}"

                # デフォルト1秒のduration（ffprobeなしの簡易版）
                se_duration = 1.0
                try:
                    from core.video import VideoInfo

                    info = VideoInfo.from_file(audio_path)
                    se_duration = info.duration
                except Exception:
                    pass

                se_rid_map[str(ap)] = (rid, se_duration)

                se_asset_xml += (
                    f'        <asset duration="{to_frac(se_duration)}" id="{rid}" '
                    f'name="{_attr(ap.name)}" start="0/1s" hasAudio="1" '
                    f'audioSources="1" audioChannels="2">\n'
                    f'            <media-rep kind="original-media" src="{_attr(audio_url)}"/>\n'
                    f"        </asset>\n"
                )

            # レーン4: SE一覧（5フレーム間隔で並べる）
            current_offset = 0.0
            gap_duration = 5 / 30  # 5フレーム
            for audio_path in audio_files:
                norm_path = str(Path(audio_path))
                if norm_path not in se_rid_map:
                    continue
                rid, se_dur = se_rid_map[norm_path]
                audio_duration = min(se_dur, total_dur - current_offset)
                if audio_duration <= 0:
                    break
                se_lane4_xml += (
                    f'                        <asset-clip duration="{to_frac(audio_duration)}" lane="4" '
                    f'name="{_attr(Path(audio_path).name)}" ref="{rid}" '
                    f'start="0/1s" offset="{to_frac(current_offset)}" enabled="1">\n'
                )
                if volume != 0:
                    se_lane4_xml += f'                            <adjust-volume amount="{_safe_volume_db(volume)}"/>\n'
                se_lane4_xml += f"                        </asset-clip>\n"
                current_offset += audio_duration + gap_duration

            # レーン5: AI配置SE
            if ai_se_placements:
                for placement in ai_se_placements:
                    se_path = placement.se_file
                    if se_path not in se_rid_map:
                        continue
                    rid, se_dur = se_rid_map[se_path]
                    placed_dur = min(se_dur, total_dur - placement.timestamp)
                    if placed_dur <= 0:
                        continue
                    se_lane5_xml += (
                        f'                        <asset-clip duration="{to_frac(placed_dur)}" lane="5" '
                        f'name="{_attr(Path(se_path).name)}" ref="{rid}" '
                        f'start="0/1s" offset="{to_frac(placement.timestamp)}" enabled="1">\n'
                    )
                    if volume != 0:
                        se_lane5_xml += (
                            f'                            <adjust-volume amount="{_safe_volume_db(volume)}"/>\n'
                        )
                    se_lane5_xml += f"                        </asset-clip>\n"

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
    <resources>
        <format height="{fmt_h}" id="r0" name="{fmt_name}" frameDuration="1/30s" width="{fmt_w}"/>
        <asset id="r1" name="{video_name}" start="0/1s" hasVideo="1" format="r0" hasAudio="1" audioSources="1" audioChannels="2">
            <media-rep kind="original-media" src="{_attr(video_url)}"/>
        </asset>
{title_asset_xml}{se_asset_xml}    </resources>
    <library>
        <event name="TextffCut">
            <project name="{title_escaped}">
                <sequence duration="{to_frac(total_dur)}" tcStart="0/1s" format="r0" tcFormat="NDF">
                    <spine>
{clips_xml}{title_spine_xml}{se_lane4_xml}{se_lane5_xml}                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""

        output_path.write_text(xml, encoding="utf-8")
        return True

    def _save_cache(self, suggestions, detection, path: Path, *, speed: float = 1.0) -> None:
        cache_data = {
            "model_used": detection.model_used,
            "processing_time": detection.processing_time,
            "token_usage": detection.token_usage,
            "estimated_cost_usd": detection.estimated_cost_usd,
            "speed": float(speed),  # 字幕エディタの meta backfill で参照
            "topics": [t.to_dict() for t in detection.topics],
            "suggestions": [s.to_dict() for s in suggestions],
        }
        path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_filename(title: str, max_length: int = 50) -> str:
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r'[<>:"/\\|?*]', "", title)
    title = title.replace(" ", "_").replace("　", "_")
    if len(title) > max_length:
        title = title[:max_length]
    return title.strip("_") or "untitled"
