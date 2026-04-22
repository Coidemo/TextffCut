"""既存 SRT に対して meta.json (char_times) を backfill する.

字幕エディタが meta 無しの既存 SRT を開いた時、自動で transcription + clip_suggestions
から char_times を再構築して meta.json を書き出す.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from use_cases.ai.srt_edit_log import meta_path_for, save_srt_meta

logger = logging.getLogger(__name__)


def _load_suggestion_cache(base_dir: Path, srt_stem: str) -> dict | None:
    """{base_dir}/clip_suggestions/*.json から srt_stem に対応する suggestion を探す.

    suggestion.title をサニタイズして "{idx:02d}_{sanitized}" と比較.
    """
    cache_dir = base_dir / "clip_suggestions"
    if not cache_dir.exists():
        return None

    json_files = list(cache_dir.glob("*.json"))
    if not json_files:
        return None

    # 番号プレフィックス ("01_" 等) を抽出
    m = re.match(r"^(\d+)_", srt_stem)
    if not m:
        return None
    idx_1based = int(m.group(1))

    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            sugs = data.get("suggestions", [])
            if 0 < idx_1based <= len(sugs):
                return sugs[idx_1based - 1]
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _load_transcription_cache(base_dir: Path) -> object | None:
    """{base_dir}/transcriptions/*.json から最新の transcription を読み込む."""
    cache_dir = base_dir / "transcriptions"
    if not cache_dir.exists():
        return None
    json_files = sorted(cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            from domain.entities.transcription import (
                TranscriptionResult,
                TranscriptionSegment,
            )

            segs = [TranscriptionSegment.from_legacy_format(s) for s in data["segments"]]
            return TranscriptionResult(
                id="backfill",
                video_id="backfill",
                language=data.get("language", "ja"),
                segments=segs,
                duration=max(s.end for s in segs) if segs else 0.0,
                original_audio_path=data.get("original_audio_path", ""),
                model_size=data.get("model_size", ""),
                processing_time=data.get("processing_time", 0.0),
            )
        except Exception as e:
            logger.debug(f"transcription cache 読込失敗 {jf}: {e}")
            continue
    return None


def _reconstruct_char_times(
    time_ranges: list[tuple[float, float]],
    transcription: object,
    speed: float,
) -> tuple[str, list[tuple[float, float]]] | None:
    """_collect_parts_core → _build_char_time_map → _remove_inline_fillers で
    SRT 生成時と同じ full_text / char_times を再構築する.
    """
    try:
        from use_cases.ai.srt_subtitle_generator import (
            _build_char_time_map,
            _collect_parts_core,
            _remove_inline_fillers,
            build_timeline_map,
        )

        tmap = build_timeline_map(time_ranges)
        parts = _collect_parts_core(time_ranges, tmap, transcription, speed=speed)
        if not parts:
            return None
        full_text, char_times, seg_bounds = _build_char_time_map(parts)
        if not full_text:
            return None
        full_text, char_times, _ = _remove_inline_fillers(full_text, char_times, seg_bounds)
        if len(full_text) != len(char_times):
            return None
        return full_text, char_times
    except Exception as e:
        logger.warning(f"char_times 再構築失敗: {e}")
        return None


def ensure_srt_meta(
    base_dir: Path,
    srt_path: Path,
    *,
    default_speed: float = 1.2,
) -> tuple[str, list[tuple[float, float]]] | None:
    """meta が無ければ backfill. 成功すれば (full_text, char_times) を返す.

    既に meta が存在する場合はそのまま返す.
    backfill 不可能なら None.
    """
    from use_cases.ai.srt_edit_log import load_srt_meta

    existing = load_srt_meta(srt_path)
    if existing is not None:
        return existing

    suggestion = _load_suggestion_cache(base_dir, srt_path.stem)
    if not suggestion:
        logger.debug(f"suggestion not found for {srt_path.stem}")
        return None

    time_ranges = suggestion.get("time_ranges")
    if not time_ranges:
        return None
    # [(s, e), ...] 形式に正規化
    time_ranges_tuples = [(float(s), float(e)) for s, e in time_ranges]

    transcription = _load_transcription_cache(base_dir)
    if not transcription:
        logger.debug(f"transcription not found for {base_dir}")
        return None

    result = _reconstruct_char_times(time_ranges_tuples, transcription, default_speed)
    if not result:
        return None

    full_text, char_times = result
    try:
        save_srt_meta(srt_path, full_text, char_times)
        logger.info(f"SRT meta を backfill: {meta_path_for(srt_path).name}")
    except Exception as e:
        logger.warning(f"meta 保存失敗: {e}")

    return full_text, char_times
