"""
Phase 2c: 骨子+結びベース候補生成

GPTに「骨子（核心の主張）」と「結び（まとめ）」のセグメント位置を特定させ、
結びをアンカーにして候補生成する。骨子が遠い場合は2range（骨子+結び）で対応。
"""

from __future__ import annotations

import logging

from domain.entities.clip_suggestion import TopicRange
from domain.entities.transcription import TranscriptionResult
from use_cases.ai.brute_force_clip_generator import ClipCandidate

logger = logging.getLogger(__name__)

# 言い切り判定用の文末パターン
# 句点系 (「。」「？」「！」) は VAD 統合後の Whisper 出力で文末に現れる典型パターン。
# VAD 統合 (PR #128) 前は Whisper が句点を出さず「です/ます」終わりで segment を切っていた
# ため動作していたが、VAD chunk 単位処理では Whisper が chunk 全体を 1 文として
# 句点付きで出力する傾向があり、句点を言い切りとして認識しないと Phase 2c の anchor が
# ほぼ全てスキップされる (実測: VAD 後 segment の 64% が「。」終わり、complete 判定 0.4%)。
_COMPLETE_ENDINGS = (
    "です",
    "ます",
    "ました",
    "ですね",
    "ますね",
    "ですよね",
    "んですよ",
    "んです",
    "思います",
    "しれません",
    "でした",
    "ですよ",
    "ますよ",
    "ません",
    "ですか",
    # 句点系 (VAD 統合後に典型的)
    "。",
    "?",
    "!",
    "?",
    "!",
)


def _is_ending_complete(text: str) -> bool:
    """テキストが言い切りで終わっているか判定する。"""
    end_text = text.rstrip()
    return any(end_text.endswith(e) for e in _COMPLETE_ENDINGS)


def generate_core_conclusion_candidates(
    topic: TopicRange,
    transcription: TranscriptionResult,
    cores: list[dict],
    conclusions: list[dict],
    min_duration: float,
    max_duration: float,
    cc_to_local: list[int] | None = None,
) -> list[ClipCandidate]:
    """骨子+結びベースで候補を生成する。

    Args:
        topic: 話題範囲
        transcription: 文字起こし結果
        cores: [{"start": int, "end": int, "summary": str}] (topic内0始まりindex)
        conclusions: 同上
        min_duration: 最小秒数
        max_duration: 最大秒数

    Returns:
        ClipCandidateリスト
    """
    segments = transcription.segments
    topic_start = topic.segment_start_index
    topic_end = topic.segment_end_index

    # topic範囲のセグメントを抽出
    topic_segs = segments[topic_start : topic_end + 1]
    n = len(topic_segs)
    if n == 0 or not conclusions:
        return []

    # GPTインデックスをtopic内ローカルインデックスに変換（コピーして元を破壊しない）
    if cc_to_local:
        cores = [dict(c) for c in cores]
        conclusions = [dict(c) for c in conclusions]
        valid_cores: list[dict] = []
        valid_conclusions: list[dict] = []
        for item, dest in [(c, valid_cores) for c in cores] + [(c, valid_conclusions) for c in conclusions]:
            s = item["start"]
            e = item["end"]
            if s >= len(cc_to_local) or e >= len(cc_to_local):
                logger.warning(f"cc_to_local範囲外: start={s}, end={e}, len={len(cc_to_local)}")
                continue
            item["start"] = cc_to_local[s]
            item["end"] = cc_to_local[e]
            dest.append(item)
        cores = valid_cores
        conclusions = valid_conclusions
        if not conclusions:
            return []

    seg_starts = [s.start for s in topic_segs]
    seg_ends = [s.end for s in topic_segs]

    candidates: list[ClipCandidate] = []

    for concl in conclusions:
        concl_start = concl["start"]
        concl_end = concl["end"]

        # 範囲チェック
        if concl_end >= n or concl_start < 0:
            continue

        # アンカー末尾が言い切りでない場合、次の結論セグメントまで延長して言い切りを探す
        anchor_end = concl_end
        anchor_text = "".join(topic_segs[j].text for j in range(concl_start, anchor_end + 1))
        if not _is_ending_complete(anchor_text):
            # concl_end以降で言い切りを探す（最大5セグメント先まで）
            found = False
            for ext in range(concl_end + 1, min(concl_end + 6, n)):
                ext_text = topic_segs[ext].text.rstrip()
                if _is_ending_complete(ext_text):
                    anchor_end = ext
                    found = True
                    break
            if not found:
                # 言い切りが見つからない → このアンカーはスキップ
                logger.debug(f"Phase 2c: 結び[{concl_start}-{concl_end}]に言い切りなし、スキップ")
                continue

        anchor_end_time = seg_ends[anchor_end]

        # --- パターンA: 1range（連続） ---
        for start_idx in range(anchor_end, -1, -1):
            dur = anchor_end_time - seg_starts[start_idx]
            if dur > max_duration:
                break
            if dur < min_duration:
                continue

            has_core = any(start_idx <= cr["start"] and anchor_end >= cr["end"] for cr in cores)

            # セグメントindices（topic内indexからglobal indexに変換）
            global_indices = list(range(topic_start + start_idx, topic_start + anchor_end + 1))
            topic_seg_slice = topic_segs[start_idx : anchor_end + 1]
            text = "".join(s.text for s in topic_seg_slice)

            # time_rangesを構築
            time_ranges = _build_time_ranges(topic_seg_slice)

            candidate = ClipCandidate(
                segments=list(topic_seg_slice),
                segment_indices=global_indices,
                text=text,
                time_ranges=time_ranges,
                total_duration=sum(e - s for s, e in time_ranges),
                has_core=has_core,
            )
            candidates.append(candidate)

        # --- パターンB: 2range（骨子+結び、間をスキップ） ---
        for core in cores:
            core_start = core["start"]
            core_end_orig = core["end"]

            # 骨子が結びより後ろならスキップ
            if core_start > concl_start:
                continue

            # 1rangeで収まる場合はパターンAで既に生成済み
            full_dur = anchor_end_time - seg_starts[core_start]
            if full_dur <= max_duration:
                continue

            # 結びrangeの開始点をスライド（結びの前に少し文脈を足す）
            for concl_range_start in range(concl_start, max(concl_start - 10, -1), -1):
                # 骨子rangeの終了点をスライド（骨子の後に少し文脈を足す）
                for core_end in range(core_end_orig, min(core_end_orig + 5, concl_range_start)):
                    core_dur = seg_ends[core_end] - seg_starts[core_start]
                    concl_dur = anchor_end_time - seg_starts[concl_range_start]
                    total_dur = core_dur + concl_dur

                    if total_dur < min_duration:
                        continue
                    if total_dur > max_duration:
                        break

                    # Range 1 (骨子)
                    range1_segs = topic_segs[core_start : core_end + 1]
                    range1_indices = list(range(topic_start + core_start, topic_start + core_end + 1))

                    # Range 2 (結び)
                    range2_segs = topic_segs[concl_range_start : anchor_end + 1]
                    range2_indices = list(range(topic_start + concl_range_start, topic_start + anchor_end + 1))

                    all_segs = list(range1_segs) + list(range2_segs)
                    all_indices = range1_indices + range2_indices
                    text = "".join(s.text for s in all_segs)

                    time_ranges = _build_time_ranges(range1_segs) + _build_time_ranges(range2_segs)

                    candidate = ClipCandidate(
                        segments=all_segs,
                        segment_indices=all_indices,
                        text=text,
                        time_ranges=time_ranges,
                        total_duration=sum(e - s for s, e in time_ranges),
                        has_core=True,
                    )
                    candidates.append(candidate)

    # 重複除去 & ソート（言い切り末尾 > 骨子含む > 短い順）
    seen: set[tuple[int, ...]] = set()
    unique: list[ClipCandidate] = []
    for c in candidates:
        key = tuple(c.segment_indices)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    # 言い切り末尾 > 骨子含む > 短い順
    unique.sort(key=lambda c: (not _is_ending_complete(c.text), not c.has_core, c.total_duration))

    logger.info(f"Phase 2c: {len(unique)}候補生成 ({topic.title})")
    return unique


def _build_time_ranges(
    segs: list,
    gap_threshold: float = 0.5,
) -> list[tuple[float, float]]:
    """セグメントリストから連続するtime_rangesを構築する。"""
    if not segs:
        return []

    ranges: list[tuple[float, float]] = []
    for seg in segs:
        if ranges and seg.start - ranges[-1][1] <= gap_threshold:
            ranges[-1] = (ranges[-1][0], seg.end)
        else:
            ranges.append((seg.start, seg.end))

    return ranges
