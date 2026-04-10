"""
クリップ間の音響的自然さ分析

隣接クリップの結合部で音圧・ピッチ・スペクトルの不連続を検出する。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

WINDOW_SEC = 0.3  # 結合部の分析ウィンドウ（秒）


@dataclass
class JoinNaturalness:
    """クリップ結合部の自然さ評価"""

    index: int  # 何番目の結合部か（clip[index]の末尾 → clip[index+1]の冒頭）
    rms_diff: float  # 音圧差（dB）
    pitch_diff: float  # ピッチ差（Hz）
    is_natural: bool
    detail: str


def analyze_join_naturalness(
    video_path: Path,
    time_ranges: list[tuple[float, float]],
) -> list[JoinNaturalness]:
    """全クリップ結合部の音響的自然さを分析する。"""
    if len(time_ranges) < 2:
        return []

    results = []
    for i in range(len(time_ranges) - 1):
        _, end_a = time_ranges[i]
        start_b, _ = time_ranges[i + 1]

        try:
            result = _analyze_single_join(video_path, end_a, start_b, i)
            results.append(result)
        except Exception as e:
            logger.debug(f"Join analysis failed at {i}: {e}")
            results.append(
                JoinNaturalness(
                    index=i,
                    rms_diff=0,
                    pitch_diff=0,
                    is_natural=True,
                    detail="analysis_failed",
                )
            )

    unnatural = [r for r in results if not r.is_natural]
    if unnatural:
        logger.info(
            f"音響分析: {len(unnatural)}/{len(results)}箇所が不自然 " f"({', '.join(r.detail for r in unnatural[:3])})"
        )

    return results


def _analyze_single_join(
    video_path: Path,
    end_a: float,
    start_b: float,
    index: int,
) -> JoinNaturalness:
    """1つの結合部を分析する。"""
    import librosa

    with tempfile.TemporaryDirectory() as tmpdir:
        # クリップAの末尾
        tail_start = max(0, end_a - WINDOW_SEC)
        tail_path = f"{tmpdir}/tail.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(tail_start),
                "-t",
                str(WINDOW_SEC),
                "-i",
                str(video_path),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                tail_path,
            ],
            capture_output=True,
            timeout=10,
        )

        # クリップBの冒頭
        head_path = f"{tmpdir}/head.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_b),
                "-t",
                str(WINDOW_SEC),
                "-i",
                str(video_path),
                "-vn",
                "-ar",
                "16000",
                "-ac",
                "1",
                head_path,
            ],
            capture_output=True,
            timeout=10,
        )

        y_tail, sr = librosa.load(tail_path, sr=16000)
        y_head, _ = librosa.load(head_path, sr=16000)

        if len(y_tail) < 100 or len(y_head) < 100:
            return JoinNaturalness(
                index=index,
                rms_diff=0,
                pitch_diff=0,
                is_natural=True,
                detail="too_short",
            )

        # 音圧（RMS）比較
        rms_tail = np.sqrt(np.mean(y_tail**2))
        rms_head = np.sqrt(np.mean(y_head**2))
        if rms_tail > 0 and rms_head > 0:
            rms_diff_db = 20 * np.log10(rms_head / rms_tail)
        else:
            rms_diff_db = 0.0

        # ピッチ（F0）比較
        f0_tail, voiced_tail, _ = librosa.pyin(y_tail, fmin=80, fmax=400, sr=sr)
        f0_head, voiced_head, _ = librosa.pyin(y_head, fmin=80, fmax=400, sr=sr)

        f0_tail_mean = np.nanmean(f0_tail) if f0_tail is not None and np.any(~np.isnan(f0_tail)) else 0
        f0_head_mean = np.nanmean(f0_head) if f0_head is not None and np.any(~np.isnan(f0_head)) else 0
        pitch_diff = abs(f0_head_mean - f0_tail_mean) if f0_tail_mean > 0 and f0_head_mean > 0 else 0

        # 不自然さ判定
        issues = []
        if abs(rms_diff_db) > 12:
            issues.append(f"音圧差{rms_diff_db:.0f}dB")
        if pitch_diff > 80:
            issues.append(f"ピッチ差{pitch_diff:.0f}Hz")

        is_natural = len(issues) == 0
        detail = ", ".join(issues) if issues else "ok"

        return JoinNaturalness(
            index=index,
            rms_diff=rms_diff_db,
            pitch_diff=pitch_diff,
            is_natural=is_natural,
            detail=detail,
        )
