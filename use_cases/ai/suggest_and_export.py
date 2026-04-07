"""
一気通貫ユースケース: AI話題検出 → 力任せ候補生成 → AI選定 → 無音削除 → FCPXML

シンプルなパイプライン:
1. AI: 話題の時間範囲を検出
2. 機械: セグメント組み合わせで数百パターン生成 → 機械スコアで上位5件
3. AI: 出来上がり音声を文字起こしして最良を選定
4. 機械: wordsレベルフィラー仕上げ（音響チェック付き）
5. 機械: 無音削除（最終候補にのみ適用）
6. 機械: FCPXML生成

フィラー削除は行わない。フィラーセグメントを含むパターンは機械スコアで自然に
淘汰される（フィラーセグメントが多いほどスコアが下がるため）。
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
        # Phase 1-3: AI話題検出 → 力任せ候補生成 → AI選定
        use_case = GenerateClipSuggestionsUseCase(self.gateway)
        suggestions = use_case.execute(
            transcription=request.transcription,
            video_path=request.video_path,
            num_candidates=request.num_candidates,
            min_duration=request.min_duration,
            max_duration=request.max_duration,
            prompt_path=request.prompt_path,
        )

        detection = use_case.last_detection_result

        # 出力ディレクトリ
        video_name = request.video_path.stem
        base_dir = request.video_path.parent / f"{video_name}_TextffCut"
        fcpxml_dir = base_dir / "fcpxml"
        fcpxml_dir.mkdir(parents=True, exist_ok=True)

        # Phase 4: wordsレベルフィラー仕上げ（音響チェック付き）
        from use_cases.ai.word_level_filler_polish import polish_fillers

        for i, suggestion in enumerate(suggestions):
            suggestions[i] = polish_fillers(suggestion, request.transcription, request.video_path)

        # Phase 5: 無音削除（最終候補にのみ適用）
        if request.remove_silence:
            for suggestion in suggestions:
                self._apply_silence_removal(suggestion, request.video_path, base_dir)

        # キャッシュ保存
        cache_dir = base_dir / "clip_suggestions"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._save_cache(suggestions, detection, cache_dir / f"{detection.model_used}.json")

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

        # Phase 6: FCPXML + SRT生成
        exported_files: list[Path] = []
        for i, suggestion in enumerate(suggestions, 1):
            sanitized = _sanitize_filename(suggestion.title)

            # FCPXML
            fcpxml_path = fcpxml_dir / f"{i:02d}_{sanitized}.fcpxml"
            success = self._export_fcpxml(suggestion, request.video_path, fcpxml_path, media_config)
            if success:
                exported_files.append(fcpxml_path)

            # SRT字幕
            if request.generate_srt:
                from use_cases.ai.srt_subtitle_generator import generate_srt

                srt_path = fcpxml_dir / f"{i:02d}_{sanitized}.srt"
                generate_srt(
                    suggestion=suggestion,
                    transcription=request.transcription,
                    output_path=srt_path,
                    video_path=request.video_path,
                    max_chars_per_line=request.srt_max_chars,
                    max_lines=request.srt_max_lines,
                )

        return SuggestAndExportResult(
            suggestions=suggestions,
            exported_files=exported_files,
            output_dir=fcpxml_dir,
            detection_processing_time=detection.processing_time,
            detection_cost_usd=detection.estimated_cost_usd,
        )

    def _apply_silence_removal(self, suggestion: ClipSuggestion, video_path: Path, base_dir: Path) -> None:
        """1つの候補に無音削除を適用する。"""
        try:
            from config import Config
            from core.video import VideoProcessor

            vp = VideoProcessor(Config())
            temp_dir = str(base_dir / "temp_wav")

            new_ranges = vp.remove_silence_new(
                input_path=str(video_path),
                time_ranges=suggestion.time_ranges,
                output_dir=temp_dir,
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
                overlay_settings=media_config.overlay_settings if media_config else None,
                bgm_settings=media_config.bgm_settings if media_config else None,
                additional_audio_settings=media_config.additional_audio_settings if media_config else None,
            )
        except Exception as e:
            logger.warning(f"FCPXMLExporter failed ({e}), using simple FCPXML")
            return self._export_simple_fcpxml(suggestion, video_path, output_path)

    def _export_simple_fcpxml(self, suggestion: ClipSuggestion, video_path: Path, output_path: Path) -> bool:
        """ffprobeなしで簡易FCPXMLを生成する（DaVinci Resolve互換）"""
        from fractions import Fraction
        from urllib.parse import quote

        def to_frac(seconds: float, fps: int = 30) -> str:
            frames = round(seconds * fps)
            frac = Fraction(frames, fps)
            if frac.numerator == 0:
                return "0/1s"
            return f"{frac.numerator}/{frac.denominator}s"

        from xml.sax.saxutils import escape, quoteattr

        video_name = escape(video_path.name)
        title_escaped = escape(suggestion.title)
        encoded_path = quote(str(video_path), safe="/:")
        video_url = f"file://{encoded_path}"

        from core.export import ExportSegment

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
                f'                            <adjust-transform position="0 0" scale="1 1" anchor="0 0"/>\n'
                f"                        </asset-clip>\n"
            )

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE fcpxml>
<fcpxml version="1.9">
    <resources>
        <format height="1080" id="r0" name="FFVideoFormat1080p30" frameDuration="1/30s" width="1920"/>
        <asset id="r1" name="{video_name}" start="0/1s" hasVideo="1" format="r0" hasAudio="1" audioSources="1" audioChannels="2">
            <media-rep kind="original-media" src="{video_url}"/>
        </asset>
    </resources>
    <library>
        <event name="TextffCut">
            <project name="{title_escaped}">
                <sequence duration="{to_frac(total_dur)}" tcStart="0/1s" format="r0" tcFormat="NDF">
                    <spine>
{clips_xml}                    </spine>
                </sequence>
            </project>
        </event>
    </library>
</fcpxml>"""

        output_path.write_text(xml, encoding="utf-8")
        return True

    def _save_cache(self, suggestions, detection, path: Path) -> None:
        cache_data = {
            "model_used": detection.model_used,
            "processing_time": detection.processing_time,
            "token_usage": detection.token_usage,
            "estimated_cost_usd": detection.estimated_cost_usd,
            "topics": [t.to_dict() for t in detection.topics],
            "suggestions": [s.to_dict() for s in suggestions],
        }
        path.write_text(json.dumps(cache_data, ensure_ascii=False, indent=2), encoding="utf-8")


def _sanitize_filename(title: str, max_length: int = 50) -> str:
    title = unicodedata.normalize("NFKC", title)
    title = re.sub(r'[<>:"/\\|?*]', "", title)
    title = title.replace(" ", "_").replace("　", "_")
    if len(title) > max_length:
        title = title[:max_length]
    return title.strip("_") or "untitled"
