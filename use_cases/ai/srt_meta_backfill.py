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


def _load_suggestion_cache(base_dir: Path, srt_stem: str) -> tuple[dict, float] | None:
    """{base_dir}/clip_suggestions/*.json から srt_stem に対応する (suggestion, speed) を探す.

    suggestion.title をサニタイズして "{NN}_{sanitized}" と厳密一致させる.
    一致する suggestion が無ければ None (複数 JSON がある場合に間違った
    clip の time_ranges を使わないため).

    Returns:
        (suggestion_dict, speed_value) or None
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
    expected_rest = srt_stem[m.end() :]  # "AIで情報収集格差が爆増中!" 部分

    # sanitize_filename と同じロジックを再実装 (suggest_and_export との循環 import 回避)
    import unicodedata

    def _sanitize(title: str) -> str:
        t = unicodedata.normalize("NFKC", title)
        t = re.sub(r'[<>:"/\\|?*]', "", t)
        t = t.replace(" ", "_").replace("　", "_")
        if len(t) > 50:
            t = t[:50]
        return t.strip("_") or "untitled"

    # mtime 降順で探索 (新しいキャッシュから)
    json_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            sugs = data.get("suggestions", [])
            if not (0 < idx_1based <= len(sugs)):
                continue
            candidate = sugs[idx_1based - 1]
            title = candidate.get("title", "")
            if _sanitize(title) == expected_rest:
                # 生成時の speed (古いキャッシュには無いので 1.0 fallback)
                speed = float(data.get("speed", 1.0))
                return candidate, speed
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
) -> tuple[str, list[tuple[float, float]]] | None:
    """meta が無ければ backfill. 成功すれば (full_text, char_times) を返す.

    生成時の speed は clip_suggestions キャッシュに保存されていれば使用、
    無ければ 1.0 にフォールバック. 既に meta が存在する場合はそのまま返す.
    """
    from use_cases.ai.srt_edit_log import load_srt_meta

    existing = load_srt_meta(srt_path)
    if existing is not None:
        return existing

    found = _load_suggestion_cache(base_dir, srt_path.stem)
    if not found:
        logger.debug(f"suggestion not found for {srt_path.stem}")
        return None
    suggestion, speed = found

    time_ranges = suggestion.get("time_ranges")
    if not time_ranges:
        return None
    time_ranges_tuples = [(float(s), float(e)) for s, e in time_ranges]

    transcription = _load_transcription_cache(base_dir)
    if not transcription:
        logger.debug(f"transcription not found for {base_dir}")
        return None

    result = _reconstruct_char_times(time_ranges_tuples, transcription, speed)
    if not result:
        return None

    full_text, char_times = result
    try:
        save_srt_meta(srt_path, full_text, char_times)
        logger.info(f"SRT meta を backfill (speed={speed}): {meta_path_for(srt_path).name}")
    except Exception as e:
        logger.warning(f"meta 保存失敗: {e}")

    return full_text, char_times
