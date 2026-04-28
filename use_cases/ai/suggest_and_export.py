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
from collections.abc import Callable
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
    enable_blur_overlay: bool = True  # 動画内テキスト塗りつぶし PNG オーバーレイ生成 (FCPXML V2 lane)
    # GUI/CLI 共通の進捗 callback。シグネチャは (progress 0.0-1.0, message) で
    # core/video.py::remove_silence_new 等と同型。callback 内例外は本処理を止めない。
    progress_reporter: Callable[[float, str], None] | None = None


@dataclass
class SuggestAndExportResult:
    suggestions: list[ClipSuggestion]
    exported_files: list[Path]
    output_dir: Path
    detection_processing_time: float
    detection_cost_usd: float
    srt_failed_count: int = 0  # Phase 5.6 で SRT 先行生成に失敗した clip 数


class SuggestAndExportUseCase:

    def __init__(self, gateway: ClipSuggestionGatewayInterface):
        self.gateway = gateway

    def execute(self, request: SuggestAndExportRequest) -> SuggestAndExportResult:
        import time as _time

        _phase_times: dict[str, float] = {}
        _t0 = _time.time()

        def _report(pct: float, message: str) -> None:
            """progress_reporter を安全に呼ぶ (callback 内例外は本処理を止めない)。"""
            if request.progress_reporter is None:
                return
            try:
                request.progress_reporter(pct, message)
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"progress_reporter callback で例外: {exc}")

        # Phase 1-3: AI話題検出 → 力任せ候補生成 → AI選定
        _report(0.0, "🔍 話題を検出中...")
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
        total = len(suggestions)

        # 出力ディレクトリ
        video_name = request.video_path.stem
        base_dir = request.video_path.parent / f"{video_name}_TextffCut"
        fcpxml_dir = base_dir / "fcpxml"
        fcpxml_dir.mkdir(parents=True, exist_ok=True)

        # 候補 0 件: 後段 Phase (空 cache 保存 / 空 list で AI 呼び出し / 不要な
        # メディア検出) を一切スキップして早期 return
        if total == 0:
            _report(1.0, "⚠️ 切り抜き候補が見つかりませんでした")
            logger.warning("候補 0 件: 後段 Phase をスキップ")
            return SuggestAndExportResult(
                suggestions=[],
                exported_files=[],
                output_dir=fcpxml_dir,
                detection_processing_time=detection.processing_time,
                detection_cost_usd=detection.estimated_cost_usd,
                srt_failed_count=0,
            )

        _report(0.30, f"✅ {total}件の話題を検出")

        _t3 = _time.time()
        # Phase 5: 無音削除（最終候補にのみ適用）
        if request.remove_silence:
            for i, suggestion in enumerate(suggestions):
                _report(0.35, f"🔇 無音削除中... ({i + 1}/{total})")
                self._apply_silence_removal(
                    suggestion, request.video_path, base_dir, transcription=request.transcription
                )

        # Phase 5.5: 速度変更
        actual_video_path = request.video_path

        if request.speed != 1.0:
            from config import Config
            from core.video import VideoProcessor

            speed = round(request.speed, 2)
            speed_label = f"{round(speed, 1)}x"
            _report(0.45, f"⚡ {speed_label}速度変更中...")
            vp = VideoProcessor(Config())
            speed_path = base_dir / f"source_{speed_label}.mp4"
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
            summary = media_config.summary()
            logger.info(summary)
            # GUI で素材検出結果を見える化 (preset_dir 解決ミス等の sanity check)
            _report(0.50, f"🎨 {summary}")

        _phase_times["Phase5 無音削除+速度変更"] = _time.time() - _t3
        _t4 = _time.time()

        # Phase 5.6: SRT 字幕を先行生成 (Phase 5.7 のタイトル画像 AI が
        # 字幕内容を踏まえてタイトルを生成するため、Phase 6 から前出ししている)
        srt_paths_list: list[Path | None] = [None] * len(suggestions)
        srt_failed_count = 0
        if request.generate_srt:
            from use_cases.ai.srt_subtitle_generator import generate_srt as _gen_srt

            _report(0.55, f"📝 SRT 字幕生成中... ({total}件)")
            for i, suggestion in enumerate(suggestions):
                sanitized = sanitize_filename(suggestion.title)
                srt_path = fcpxml_dir / f"{i+1:02d}_{sanitized}.srt"
                try:
                    result = _gen_srt(
                        suggestion=suggestion,
                        transcription=request.transcription,
                        output_path=srt_path,
                        max_chars_per_line=request.srt_max_chars,
                        max_lines=request.srt_max_lines,
                        speed=request.speed,
                    )
                    if result:
                        srt_paths_list[i] = result
                    else:
                        srt_failed_count += 1
                        logger.warning(f"SRT 先行生成失敗 (#{i+1}): generate_srt が None を返した")
                except Exception as e:  # noqa: BLE001
                    srt_failed_count += 1
                    logger.warning(f"SRT 先行生成失敗 (#{i+1}): {e}")
            if srt_failed_count > 0:
                logger.warning(
                    f"SRT 先行生成: {srt_failed_count}/{len(suggestions)} 件が失敗。"
                    "Phase 5.7 (タイトル画像) は対応 clip で SRT モード無効化、title ベースにフォールバック。"
                )

        # Phase 5.7: タイトル画像生成（バッチ1回のAI呼び出し、Phase A: SRT 渡す）
        title_image_paths: dict[int, Path] = {}
        if request.enable_title_image:
            _report(0.65, f"🖼 タイトル画像生成中... ({total}件)")
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
                    srt_paths=srt_paths_list,
                )
                # 部分失敗の可視化 (例: AI rate limit で N/total 件成功)
                title_failed = total - len(title_image_paths)
                if title_failed > 0:
                    _report(
                        0.68,
                        f"⚠️ タイトル画像: {len(title_image_paths)}/{total} 成功 ({title_failed} 件失敗)",
                    )
                    logger.warning(f"タイトル画像 partial failure: {title_failed}/{total}")

            except Exception as e:
                logger.warning(f"タイトル画像生成をスキップ: {e}")

        # Phase 5.8: アンカー自動検出（vertical + 手動指定なし + auto_anchor有効時）
        actual_anchor = request.anchor
        if request.auto_anchor and request.timeline_resolution == "vertical" and request.anchor == (0.0, 0.0):
            _report(0.75, "📍 アンカー検出中...")
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
                _report(
                    0.78,
                    f"✅ アンカー検出: ({actual_anchor[0]:.1f}, {actual_anchor[1]:.1f}) — {result.description}",
                )
            except Exception as e:
                logger.warning("アンカー自動検出スキップ: %s", e)

        _phase_times["Phase5.7 タイトル画像"] = _time.time() - _t4
        _t_blur = _time.time()

        # Phase 5.9: 動画内テキスト塗りつぶしオーバーレイ PNG 生成 (clip 単位)
        # 各 suggestion の time_ranges 範囲のみを OCR + track 化して PNG を出力。
        # FCPXML 出力時に V2 レーンに重ねる (動画と同じ scale/anchor を適用)。
        blur_overlays_per_clip: dict[int, list[dict]] = {}
        if request.enable_blur_overlay:
            try:
                from use_cases.auto_blur.blur_overlay_use_case import (
                    BlurOverlayUseCase,
                    is_apple_silicon,
                )

                if is_apple_silicon():
                    blur_uc = BlurOverlayUseCase()
                    blur_dir = base_dir / "blur_overlays"
                    for i, suggestion in enumerate(suggestions, 1):
                        sanitized = sanitize_filename(suggestion.title)
                        clip_id = f"{i:02d}_{sanitized}"
                        _report(0.80, f"🔒 塗りつぶし overlay 生成中... ({i}/{total})")
                        try:
                            result = blur_uc.execute(
                                video_path=actual_video_path,
                                clip_id=clip_id,
                                time_ranges=suggestion.time_ranges,
                                output_dir=blur_dir,
                            )
                            blur_overlays_per_clip[i] = [ov.to_dict() for ov in result.overlays]
                            # v2 では result.overlays は 0 件 (track なし) または 1 件 (合成 PNG)
                            n_pngs = len(result.overlays)
                            logger.info(
                                f"blur overlay [{clip_id}]: {n_pngs} 合成 PNG "
                                f"({'cached' if result.cached else f'{result.duration_sec:.1f}s'})"
                            )
                        except Exception as e:  # noqa: BLE001
                            logger.warning(f"blur overlay 生成失敗 ({clip_id}): {e}")
                else:
                    logger.info("Apple Silicon Mac 以外のため blur overlay 生成をスキップ")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"blur overlay 全体スキップ: {e}")

        _phase_times["Phase5.9 塗りつぶし overlay 生成"] = _time.time() - _t_blur
        _t6 = _time.time()
        # Phase 6: AI SE配置 + FCPXML + SRT生成
        exported_files: list[Path] = []
        for i, suggestion in enumerate(suggestions, 1):
            sanitized = sanitize_filename(suggestion.title)
            # 進捗を 0.85〜0.99 のレンジに per-clip でマップ (collision 回避 + 進む見え方)
            clip_progress = 0.85 + 0.14 * (i / total) if total else 0.85
            _report(clip_progress, f"📄 FCPXML 生成中... ({i}/{total})")

            # AI SE配置を計算（SEファイルがある場合）
            ai_se_placements = None
            if request.enable_se and media_config and media_config.additional_audio_settings:
                _report(clip_progress, f"🔊 AI SE配置中... ({i}/{total})")
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
                blur_overlays=blur_overlays_per_clip.get(i),
            )
            if success:
                exported_files.append(fcpxml_path)

            # SRT 字幕は Phase 5.6 で先行生成済み (Phase A 改善: タイトル画像 AI に
            # 最終 SRT を渡すため)。ここでは exported_files にパスを記録するのみ。
            if request.generate_srt and srt_paths_list[i - 1] is not None:
                exported_files.append(srt_paths_list[i - 1])

        _phase_times["Phase6b SE+FCPXML+SRT生成"] = _time.time() - _t6
        _total = _time.time() - _t0
        logger.info("=== パイプライン処理時間 ===")
        for phase, elapsed in _phase_times.items():
            pct = elapsed / _total * 100 if _total > 0 else 0
            logger.info(f"  {phase}: {elapsed:.1f}s ({pct:.0f}%)")
        logger.info(f"  合計: {_total:.1f}s")

        _report(1.0, f"✅ {total}件の切り抜きを生成完了")

        return SuggestAndExportResult(
            suggestions=suggestions,
            exported_files=exported_files,
            output_dir=fcpxml_dir,
            detection_processing_time=detection.processing_time,
            detection_cost_usd=detection.estimated_cost_usd,
            srt_failed_count=srt_failed_count if request.generate_srt else 0,
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
        blur_overlays: list[dict] | None = None,
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
                blur_overlays=blur_overlays,
            )
        except Exception as e:
            logger.warning(f"FCPXMLExporter failed ({e}), using simple FCPXML")
            if blur_overlays:
                # simple fallback は blur オーバーレイ未対応のため、生成済 PNG が
                # FCPXML に反映されない. 黙って落とすと UX 低下なので明示する.
                logger.warning(
                    f"⚠ blur overlay {len(blur_overlays)} 件が simple FCPXML "
                    "フォールバックでは反映されません (PNG キャッシュは保持). "
                    "FCPXMLExporter のエラーを修正することで解決します."
                )
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
