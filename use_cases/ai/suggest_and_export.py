"""
一気通貫ユースケース: AI話題検出 → 機械的編集 → AI選定 → FCPXML出力
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
    remove_silence: bool = False


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
        use_case = GenerateClipSuggestionsUseCase(self.gateway)
        suggestions = use_case.execute(
            transcription=request.transcription,
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

        # キャッシュ保存
        cache_dir = base_dir / "clip_suggestions"
        cache_dir.mkdir(parents=True, exist_ok=True)
        self._save_cache(suggestions, detection, cache_dir / f"{detection.model_used}.json")

        # 処理順序:
        # 1. 音声フィラー検出（Whisper API、大きめrangesに対して）
        # 2. テキストフィラー削除（wordsベース）
        # 3. 無音削除（WAVベース、最後に間を詰める）
        # フィラー = 発話を消す → 先にやる
        # 無音 = 間を詰める → 最後にやる
        api_key = self._get_api_key()
        if api_key:
            suggestions = self._apply_audio_filler_removal(
                suggestions, request.video_path, api_key, request.transcription
            )

        suggestions = self._apply_text_filler_removal(
            suggestions, request.transcription
        )

        if request.remove_silence:
            suggestions = self._apply_silence_removal(
                suggestions, request.video_path, base_dir
            )

        # 統合品質チェック→修正ループ
        # （全チェック→種類別修正→再チェック を繰り返す）
        from use_cases.ai.clip_quality_loop import run_quality_loop

        quality_passed = []
        for suggestion in suggestions:
            result_or_none = run_quality_loop(
                suggestion=suggestion,
                video_path=request.video_path,
                transcription=request.transcription,
                gateway=self.gateway,
                min_duration=request.min_duration,
                max_duration=request.max_duration,
            )
            if result_or_none is not None:
                quality_passed.append(result_or_none)
            else:
                logger.info(f"スキップ: {suggestion.title}")
        suggestions = quality_passed

        # FCPXML生成
        exported_files: list[Path] = []
        for i, suggestion in enumerate(suggestions, 1):
            filename = f"{i:02d}_{_sanitize_filename(suggestion.title)}.fcpxml"
            output_path = fcpxml_dir / filename

            success = self._export_fcpxml(suggestion, request.video_path, output_path)
            if success:
                exported_files.append(output_path)

        return SuggestAndExportResult(
            suggestions=suggestions,
            exported_files=exported_files,
            output_dir=fcpxml_dir,
            detection_processing_time=detection.processing_time,
            detection_cost_usd=detection.estimated_cost_usd,
        )

    def _export_fcpxml(
        self, suggestion: ClipSuggestion, video_path: Path, output_path: Path
    ) -> bool:
        if not suggestion.time_ranges:
            return False

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

        try:
            from config import Config
            from core.export import FCPXMLExporter

            exporter = FCPXMLExporter(Config())
            return exporter.export(
                segments=segments,
                output_path=str(output_path),
                project_name=suggestion.title,
            )
        except Exception as e:
            # ffprobeがない等の場合は簡易FCPXML生成にフォールバック
            logger.warning(f"FCPXMLExporter failed ({e}), using simple FCPXML")
            return self._export_simple_fcpxml(segments, video_path, output_path, suggestion.title)

    def _export_simple_fcpxml(
        self, segments, video_path: Path, output_path: Path, title: str
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

        total_dur = sum(s.end_time - s.start_time for s in segments)
        video_name = video_path.name

        # URLエンコード（日本語パス対応）
        path_str = str(video_path)
        encoded_path = quote(path_str, safe="/:")
        video_url = f"file://{encoded_path}"

        # asset-clips生成
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
                f'                        </asset-clip>\n'
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
            <project name="{title}">
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

    def _apply_text_filler_removal(
        self,
        suggestions: list[ClipSuggestion],
        transcription: TranscriptionResult,
    ) -> list[ClipSuggestion]:
        """無音削除後のtime_rangesに対してwordsレベルでフィラーを除去する"""
        from use_cases.ai.mechanical_clip_editor import (
            FILLER_ONLY_TEXTS,
            _build_ranges_skipping_fillers,
        )

        for suggestion in suggestions:
            if not suggestion.time_ranges:
                continue

            new_ranges = []
            for tr_start, tr_end in suggestion.time_ranges:
                # このtime_range内のセグメントを探す
                for seg in transcription.segments:
                    if seg.end <= tr_start or seg.start >= tr_end:
                        continue

                    # セグメント全体がフィラーなら除外
                    if seg.text.strip() in FILLER_ONLY_TEXTS:
                        continue

                    # wordsレベルでフィラーをスキップ
                    sub_ranges = _build_ranges_skipping_fillers(seg)
                    for sr_start, sr_end, _ in sub_ranges:
                        # time_rangeとの重なり部分だけ採用
                        clipped_start = max(sr_start, tr_start)
                        clipped_end = min(sr_end, tr_end)
                        if clipped_start < clipped_end - 0.05:
                            new_ranges.append((clipped_start, clipped_end))

            if new_ranges:
                # 短すぎるクリップ（0.3秒未満）を除去
                new_ranges = [(s, e) for s, e in new_ranges if e - s >= 0.3]

                # 近接するクリップをマージ（0.15秒以内のギャップ）
                if new_ranges:
                    merged = [new_ranges[0]]
                    for s, e in new_ranges[1:]:
                        prev_s, prev_e = merged[-1]
                        if s - prev_e <= 0.15:
                            merged[-1] = (prev_s, e)
                        else:
                            merged.append((s, e))
                    new_ranges = merged

                old_dur = suggestion.total_duration
                suggestion.time_ranges = new_ranges
                suggestion.total_duration = sum(e - s for s, e in new_ranges)
                logger.info(
                    f"テキストフィラー削除: {suggestion.title} "
                    f"{old_dur:.1f}s → {suggestion.total_duration:.1f}s "
                    f"({len(new_ranges)}クリップ)"
                )

        return suggestions

    def _get_api_key(self) -> str:
        """APIキーを取得する"""
        import os
        return os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY") or ""

    def _apply_audio_filler_removal(
        self,
        suggestions: list[ClipSuggestion],
        video_path: Path,
        api_key: str,
        transcription: TranscriptionResult | None = None,
    ) -> list[ClipSuggestion]:
        """Whisper APIで音声フィラーを検出し除去する"""
        if not api_key:
            logger.warning("APIキー未設定のため音声フィラー検出をスキップ")
            return suggestions

        try:
            from use_cases.ai.audio_filler_detector import (
                apply_filler_removal,
                detect_fillers_with_whisper,
            )

            for suggestion in suggestions:
                if not suggestion.time_ranges:
                    continue
                try:
                    fillers = detect_fillers_with_whisper(
                        video_path, suggestion.time_ranges, api_key
                    )
                    if fillers:
                        old_ranges = len(suggestion.time_ranges)
                        suggestion.time_ranges = apply_filler_removal(
                            suggestion.time_ranges, fillers, transcription
                        )
                        suggestion.total_duration = sum(
                            e - s for s, e in suggestion.time_ranges
                        )
                        logger.info(
                            f"音声フィラー{len(fillers)}個除去: {suggestion.title} "
                            f"({old_ranges}→{len(suggestion.time_ranges)}クリップ)"
                        )
                except Exception as e:
                    logger.warning(f"音声フィラー検出失敗 ({suggestion.title}): {e}")
        except ImportError as e:
            logger.warning(f"音声フィラー検出モジュール読み込み失敗: {e}")

        return suggestions

    def _check_and_fix_naturalness(
        self,
        suggestions: list[ClipSuggestion],
        video_path: Path,
        transcription: TranscriptionResult | None = None,
    ) -> tuple[list[ClipSuggestion], int]:
        """ピッチ分析 + AIレビューでカットの自然さをチェック・修正する。

        Returns:
            (suggestions, fixed_count) fixed_countが0なら修正不要
        """
        total_fixed = 0
        try:
            from use_cases.ai.audio_filler_detector import check_cut_naturalness

            for suggestion in suggestions:
                if not suggestion.time_ranges or len(suggestion.time_ranges) < 2:
                    continue

                # 各クリップの終端でピッチ分析
                cut_points = [end for _, end in suggestion.time_ranges[:-1]]
                naturalness = check_cut_naturalness(video_path, cut_points)

                # ピッチに問題があるカット点を収集
                cut_issues = []
                for i, nat in enumerate(naturalness):
                    if not nat.is_natural and nat.confidence > 0.3:
                        cut_issues.append({
                            "index": i,
                            "direction": nat.pitch_direction,
                            "text": suggestion.text[i * 50 : (i + 1) * 50] if suggestion.text else "",
                        })

                if cut_issues:
                    logger.info(
                        f"ピッチ問題{len(cut_issues)}個検出: {suggestion.title}"
                    )

                # 常にAIレビューを実行（ピッチ問題がなくても文章の自然さをチェック）
                segments_text = self._get_text_for_ranges(
                    suggestion, transcription
                )

                reviews = self.gateway.review_naturalness(
                    suggestion.title, segments_text, cut_issues
                )

                # "extend"アクションを適用（隣接クリップを結合）
                old_count = len(suggestion.time_ranges)
                suggestion.time_ranges = self._apply_reviews(
                    suggestion.time_ranges, reviews
                )
                suggestion.total_duration = sum(
                    e - s for s, e in suggestion.time_ranges
                )
                if len(suggestion.time_ranges) != old_count:
                    total_fixed += old_count - len(suggestion.time_ranges)

        except ImportError as e:
            logger.warning(f"ピッチ分析モジュール読み込み失敗: {e}")
        except Exception as e:
            logger.warning(f"自然さチェック失敗: {e}")

        return suggestions, total_fixed

    def _get_text_for_ranges(
        self,
        suggestion: ClipSuggestion,
        transcription: TranscriptionResult | None,
    ) -> list[str]:
        """各time_rangeに対応するテキストを取得する"""
        if not transcription or not suggestion.time_ranges:
            return [f"({s:.1f}s-{e:.1f}s)" for s, e in suggestion.time_ranges]

        result = []
        for tr_start, tr_end in suggestion.time_ranges:
            texts = []
            for seg in transcription.segments:
                # セグメントがtime_rangeと重なるか
                if seg.end > tr_start and seg.start < tr_end:
                    texts.append(seg.text)
            clip_text = "".join(texts) if texts else ""
            result.append(f"({tr_start:.1f}s-{tr_end:.1f}s) {clip_text[:150]}")
        return result

    def _apply_reviews(
        self,
        time_ranges: list[tuple[float, float]],
        reviews: list[dict],
    ) -> list[tuple[float, float]]:
        """AIレビューの"extend"アクションを適用する（隣接クリップを結合）"""
        if not reviews:
            return time_ranges

        # extend対象のインデックスを収集
        extend_indices = set()
        for review in reviews:
            if review.get("action") == "extend":
                idx = review.get("index", -1)
                if 0 <= idx < len(time_ranges) - 1:
                    extend_indices.add(idx)

        if not extend_indices:
            return time_ranges

        # 結合処理
        merged = []
        i = 0
        while i < len(time_ranges):
            start, end = time_ranges[i]
            # extendなら次のクリップと結合
            while i in extend_indices and i + 1 < len(time_ranges):
                i += 1
                _, end = time_ranges[i]
            merged.append((start, end))
            i += 1

        return merged

    def _apply_silence_removal(
        self,
        suggestions: list[ClipSuggestion],
        video_path: Path,
        base_dir: Path,
    ) -> list[ClipSuggestion]:
        """各候補のtime_rangesに無音削除を適用する"""
        try:
            from config import Config
            from core.video import VideoProcessor

            vp = VideoProcessor(Config())
            temp_dir = str(base_dir / "temp_wav")

            for suggestion in suggestions:
                if not suggestion.time_ranges:
                    continue
                try:
                    new_ranges = vp.remove_silence_new(
                        input_path=str(video_path),
                        time_ranges=suggestion.time_ranges,
                        output_dir=temp_dir,
                    )
                    if new_ranges:
                        old_dur = suggestion.total_duration
                        suggestion.time_ranges = new_ranges
                        suggestion.total_duration = sum(
                            e - s for s, e in new_ranges
                        )
                        logger.info(
                            f"無音削除: {suggestion.title} "
                            f"{old_dur:.1f}s → {suggestion.total_duration:.1f}s "
                            f"({len(new_ranges)}クリップ)"
                        )
                except Exception as e:
                    logger.warning(f"無音削除失敗 ({suggestion.title}): {e}")

            # temp_wav クリーンアップ
            import shutil
            temp_path = base_dir / "temp_wav"
            if temp_path.exists():
                shutil.rmtree(temp_path, ignore_errors=True)

        except ImportError as e:
            logger.warning(f"無音削除に必要なモジュールが見つかりません: {e}")

        return suggestions

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
