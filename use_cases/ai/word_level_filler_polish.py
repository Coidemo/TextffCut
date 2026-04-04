"""
wordsレベルフィラー仕上げ削除（音響安全チェック付き）

力任せ探索 + 無音削除で選ばれた最終候補に対して、
セグメント内に残った純粋なフィラーをwords（1文字）タイムスタンプで
ピンポイント除去する。

カットするたびに音響チェック（音圧・ピッチの不連続）を行い、
不自然になったら**そのカットだけ取り消す**。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)

from use_cases.ai.filler_constants import FILLER_WORDS as PURE_FILLERS  # noqa: F401

# 音響チェックの閾値
MAX_RMS_DIFF_DB = 10.0   # この差以上は不自然
MAX_PITCH_DIFF_HZ = 60.0  # この差以上は不自然


def polish_fillers(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    video_path: Path,
) -> ClipSuggestion:
    """最終候補のtime_ranges内に残ったフィラーをwordsレベルで除去する。

    各フィラーカットを個別に適用し、音響チェックに通らなければ取り消す。
    transcriptionにwordsがない場合は、候補範囲だけアライメントを実行する。
    """
    if not suggestion.time_ranges:
        return suggestion

    # time_ranges内のセグメントからフィラー箇所を検出
    filler_cuts = _detect_fillers_in_ranges(
        suggestion.time_ranges, transcription
    )

    if not filler_cuts:
        return suggestion

    logger.info(f"フィラー仕上げ: {len(filler_cuts)}箇所検出 ({suggestion.title})")

    applied = 0
    reverted = 0

    for filler_text, filler_start, filler_end in filler_cuts:
        # カットを試みる
        new_ranges = _apply_single_cut(
            suggestion.time_ranges, filler_start, filler_end
        )

        if new_ranges == suggestion.time_ranges:
            continue  # 変化なし

        # 音響チェック: カット前後の音が自然につながるか
        is_natural = _check_cut_acoustics(
            video_path, suggestion.time_ranges, new_ranges,
            filler_start, filler_end
        )

        if is_natural:
            suggestion.time_ranges = new_ranges
            suggestion.total_duration = sum(e - s for s, e in new_ranges)
            applied += 1
            logger.debug(f"  ✓ カット: 「{filler_text}」({filler_start:.2f}s)")
        else:
            reverted += 1
            logger.debug(f"  ✗ 取消: 「{filler_text}」({filler_start:.2f}s) 音響不自然")

    if applied > 0 or reverted > 0:
        logger.info(
            f"フィラー仕上げ結果: {applied}カット適用, {reverted}取消 "
            f"→ {suggestion.total_duration:.1f}s"
        )

    return suggestion


def _detect_fillers_in_ranges(
    time_ranges: list[tuple[float, float]],
    transcription: TranscriptionResult,
) -> list[tuple[str, float, float]]:
    """time_ranges内のセグメントからフィラー箇所を検出する。

    Returns:
        [(filler_text, start_time, end_time), ...]
    """
    fillers = []

    for tr_start, tr_end in time_ranges:
        for seg in transcription.segments:
            if seg.end <= tr_start or seg.start >= tr_end:
                continue

            text = seg.text
            words = getattr(seg, 'words', None) or []
            if not words:
                continue

            # テキスト内のフィラー位置を検出
            pos = 0
            while pos < len(text):
                matched_filler = None
                for filler in PURE_FILLERS:
                    if text[pos:pos + len(filler)] == filler:
                        matched_filler = filler
                        break

                if matched_filler:
                    filler_len = len(matched_filler)

                    # wordsからフィラーの時間範囲を特定
                    f_start, f_end = _get_filler_time(words, pos, filler_len)

                    if f_start is not None and f_end is not None:
                        # time_ranges内に収まっているか確認
                        if f_start >= tr_start - 0.1 and f_end <= tr_end + 0.1:
                            fillers.append((matched_filler, f_start, f_end))

                    pos += filler_len
                else:
                    pos += 1

    return fillers


def _get_filler_time(
    words: list,
    char_pos: int,
    filler_len: int,
) -> tuple[float | None, float | None]:
    """wordsリスト（1文字ずつ）からフィラーの開始・終了時刻を取得する。"""
    if char_pos >= len(words) or char_pos + filler_len > len(words):
        return None, None

    first_word = words[char_pos]
    last_word = words[char_pos + filler_len - 1]

    f_start = first_word.start if hasattr(first_word, 'start') else first_word.get('start')
    f_end = last_word.end if hasattr(last_word, 'end') else last_word.get('end')

    return f_start, f_end


def _apply_single_cut(
    time_ranges: list[tuple[float, float]],
    cut_start: float,
    cut_end: float,
) -> list[tuple[float, float]]:
    """1つのフィラーをtime_rangesから除去する。"""
    new_ranges = []
    for tr_start, tr_end in time_ranges:
        if cut_start >= tr_end or cut_end <= tr_start:
            # このrangeには重ならない
            new_ranges.append((tr_start, tr_end))
        else:
            # 重なる → 分割
            if tr_start < cut_start - 0.02:
                new_ranges.append((tr_start, cut_start))
            if cut_end < tr_end - 0.02:
                new_ranges.append((cut_end, tr_end))
    return new_ranges


def _check_cut_acoustics(
    video_path: Path,
    old_ranges: list[tuple[float, float]],
    new_ranges: list[tuple[float, float]],
    cut_start: float,
    cut_end: float,
) -> bool:
    """カット前後の音響的自然さをチェックする。

    カット点の前0.2秒と後0.2秒の音圧・ピッチを比較し、
    差が大きければ不自然と判断する。
    """
    try:
        import librosa

        with tempfile.TemporaryDirectory() as tmpdir:
            # カット点の前の音声（cut_startの前0.3秒）
            before_start = max(0, cut_start - 0.3)
            before_path = f"{tmpdir}/before.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(before_start), "-t", "0.3",
                 "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1",
                 before_path],
                capture_output=True, timeout=10,
            )

            # カット点の後の音声（cut_endの後0.3秒）
            after_path = f"{tmpdir}/after.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(cut_end), "-t", "0.3",
                 "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1",
                 after_path],
                capture_output=True, timeout=10,
            )

            y_before, sr = librosa.load(before_path, sr=16000)
            y_after, _ = librosa.load(after_path, sr=16000)

            if len(y_before) < 100 or len(y_after) < 100:
                return True  # 短すぎる場合は許可

            # 音圧チェック
            rms_before = np.sqrt(np.mean(y_before ** 2))
            rms_after = np.sqrt(np.mean(y_after ** 2))
            if rms_before > 0 and rms_after > 0:
                rms_diff = abs(20 * np.log10(rms_after / rms_before))
                if rms_diff > MAX_RMS_DIFF_DB:
                    return False

            # ピッチチェック
            f0_before, _, _ = librosa.pyin(y_before, fmin=80, fmax=400, sr=sr)
            f0_after, _, _ = librosa.pyin(y_after, fmin=80, fmax=400, sr=sr)

            mean_before = np.nanmean(f0_before) if f0_before is not None and np.any(~np.isnan(f0_before)) else 0
            mean_after = np.nanmean(f0_after) if f0_after is not None and np.any(~np.isnan(f0_after)) else 0

            if mean_before > 0 and mean_after > 0:
                pitch_diff = abs(mean_after - mean_before)
                if pitch_diff > MAX_PITCH_DIFF_HZ:
                    return False

            return True

    except Exception as e:
        logger.debug(f"音響チェック失敗: {e}")
        return True  # チェック失敗時は許可
