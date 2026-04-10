"""
音声ベースのフィラー検出

Whisper APIで候補範囲を再文字起こし（フィラー検出モード）し、
通常の文字起こしと比較してフィラーの時間位置を特定する。
さらにピッチ分析でカット点の自然さをチェックする。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Whisperが検出しうる日本語フィラー
JAPANESE_FILLERS = {
    "あの",
    "あのー",
    "あのう",
    "えー",
    "えーと",
    "えっと",
    "えーっと",
    "まあ",
    "まぁ",
    "まあまあ",
    "なんか",
    "なんかこう",
    "なんかその",
    "うーん",
    "んー",
    "そうですね",
    "そう",
    "ちょっと",
    "やっぱ",
    "やっぱり",
}


@dataclass
class DetectedFiller:
    """検出されたフィラー"""

    text: str
    start: float
    end: float


@dataclass
class CutNaturalness:
    """カット点の自然さ評価"""

    position: float  # チェック位置（秒）
    is_natural: bool
    pitch_direction: str  # "falling", "rising", "flat"
    confidence: float  # 0-1


def detect_fillers_with_whisper(
    video_path: Path,
    time_ranges: list[tuple[float, float]],
    api_key: str,
) -> list[DetectedFiller]:
    """Whisper APIで候補範囲を再文字起こしし、フィラーを検出する。

    個別のrangeではなく、全体をカバーする大きな範囲を1回だけWhisperに送る。
    （短いrangeを個別に送るとtoo shortエラーが出る）

    Args:
        video_path: 動画ファイルパス
        time_ranges: 検出する時間範囲リスト
        api_key: OpenAI APIキー

    Returns:
        検出されたフィラーのリスト（時間位置付き）
    """
    if not time_ranges:
        return []

    from openai import OpenAI

    client = OpenAI(api_key=api_key)

    # 全rangeをカバーする最小〜最大の範囲を1つのWAVとして抽出
    overall_start = min(s for s, _ in time_ranges)
    overall_end = max(e for _, e in time_ranges)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    detected = []
    try:
        _extract_audio_range(video_path, overall_start, overall_end, tmp_path)

        with open(tmp_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ja",
                response_format="verbose_json",
                timestamp_granularities=["word"],
                prompt="えー、あの、まあ、なんか、えっと、うーん、そうですね、やっぱり、",
            )

        words = getattr(response, "words", []) or []
        for word_info in words:
            word_text = word_info.get("word", "") if isinstance(word_info, dict) else getattr(word_info, "word", "")
            word_start = word_info.get("start", 0) if isinstance(word_info, dict) else getattr(word_info, "start", 0)
            word_end = word_info.get("end", 0) if isinstance(word_info, dict) else getattr(word_info, "end", 0)

            # 読点・句点を除去してからフィラー判定
            cleaned = word_text.strip().rstrip("、。,.")
            if cleaned in JAPANESE_FILLERS:
                # WAV内の相対時間を元動画の絶対時間に変換
                abs_start = overall_start + word_start
                abs_end = overall_start + word_end

                # 検出されたフィラーがtime_ranges内にあるか確認
                for tr_start, tr_end in time_ranges:
                    if abs_start >= tr_start - 0.1 and abs_end <= tr_end + 0.1:
                        detected.append(
                            DetectedFiller(
                                text=cleaned,
                                start=abs_start,
                                end=abs_end,
                            )
                        )
                        break

        logger.info(f"Whisper filler detection: {len(detected)} fillers in {overall_end - overall_start:.0f}s range")

    except Exception as e:
        logger.warning(f"Whisper filler detection failed: {e}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return detected


def check_cut_naturalness(
    video_path: Path,
    cut_points: list[float],
    window_sec: float = 0.5,
) -> list[CutNaturalness]:
    """カット点のピッチを分析して自然さを評価する。

    末尾が下降ピッチ → 文末（自然な切れ目）
    末尾が上昇ピッチ → 文中（不自然な切れ目）
    末尾がフラット → 判定不能

    Args:
        video_path: 動画ファイルパス
        cut_points: チェックする時間位置リスト（各クリップの終端）
        window_sec: 分析ウィンドウ（カット点の前後何秒を見るか）

    Returns:
        各カット点の自然さ評価
    """
    import numpy as np

    results = []

    for point in cut_points:
        try:
            # カット点周辺の音声を抽出
            start = max(0, point - window_sec)
            end = point + 0.1  # 少しだけ後ろも

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = Path(tmp.name)

            _extract_audio_range(video_path, start, end, tmp_path)

            # librosaでピッチ分析
            import librosa

            y, sr = librosa.load(str(tmp_path), sr=16000)
            tmp_path.unlink(missing_ok=True)

            if len(y) < sr * 0.1:
                results.append(
                    CutNaturalness(
                        position=point,
                        is_natural=True,
                        pitch_direction="unknown",
                        confidence=0.0,
                    )
                )
                continue

            # F0（基本周波数）を抽出
            f0, voiced_flag, _ = librosa.pyin(y, fmin=80, fmax=400, sr=sr)

            if f0 is None or len(f0) == 0:
                results.append(
                    CutNaturalness(
                        position=point,
                        is_natural=True,
                        pitch_direction="unknown",
                        confidence=0.0,
                    )
                )
                continue

            # 有声フレームだけ取得
            voiced_f0 = f0[~np.isnan(f0)]
            if len(voiced_f0) < 4:
                results.append(
                    CutNaturalness(
                        position=point,
                        is_natural=True,
                        pitch_direction="flat",
                        confidence=0.3,
                    )
                )
                continue

            # 末尾1/3のピッチトレンドを分析
            tail_len = max(2, len(voiced_f0) // 3)
            tail = voiced_f0[-tail_len:]
            slope = (tail[-1] - tail[0]) / len(tail)

            # 閾値: Hz/フレーム
            if slope < -2.0:
                direction = "falling"
                is_natural = True
                confidence = min(1.0, abs(slope) / 10.0)
            elif slope > 2.0:
                direction = "rising"
                is_natural = False
                confidence = min(1.0, abs(slope) / 10.0)
            else:
                direction = "flat"
                is_natural = True  # フラットは許容
                confidence = 0.5

            results.append(
                CutNaturalness(
                    position=point,
                    is_natural=is_natural,
                    pitch_direction=direction,
                    confidence=confidence,
                )
            )

        except Exception as e:
            logger.warning(f"Pitch analysis failed at {point:.1f}s: {e}")
            results.append(
                CutNaturalness(
                    position=point,
                    is_natural=True,
                    pitch_direction="error",
                    confidence=0.0,
                )
            )

    return results


def apply_filler_removal(
    time_ranges: list[tuple[float, float]],
    fillers: list[DetectedFiller],
    transcription: "TranscriptionResult | None" = None,
    min_gap: float = 0.05,
) -> list[tuple[float, float]]:
    """検出されたフィラーの時間帯をtime_rangesから除去する。

    transcriptionが提供された場合、アライメントのword境界を参照して
    安全なカット位置を決定する（隣接する単語を切らないようにする）。

    Args:
        time_ranges: 元のtime_ranges
        fillers: 検出されたフィラー
        transcription: 文字起こし結果（word境界参照用）
        min_gap: この秒数以下のギャップはマージ

    Returns:
        フィラー除去後のtime_ranges
    """
    if not fillers:
        return time_ranges

    # フィラーのカット範囲をword境界で補正
    filler_ranges = []
    for filler in fillers:
        f_start, f_end = filler.start, filler.end
        if transcription:
            f_start, f_end = _snap_to_word_boundaries(f_start, f_end, transcription)
        filler_ranges.append((f_start, f_end))

    filler_ranges.sort()

    # 各time_rangeからフィラー部分を除去
    result = []
    for tr_start, tr_end in time_ranges:
        overlapping = [
            (max(f_start, tr_start), min(f_end, tr_end))
            for f_start, f_end in filler_ranges
            if f_start < tr_end and f_end > tr_start
        ]

        if not overlapping:
            result.append((tr_start, tr_end))
            continue

        current = tr_start
        for f_start, f_end in overlapping:
            if current < f_start - min_gap:
                result.append((current, f_start))
            current = f_end
        if current < tr_end - min_gap:
            result.append((current, tr_end))

    return result


def _snap_to_word_boundaries(
    filler_start: float,
    filler_end: float,
    transcription: "TranscriptionResult",
) -> tuple[float, float]:
    """フィラーのカット範囲をアライメントのword境界にスナップする。

    Whisperのフィラー検出タイムスタンプは粗いため、
    アライメントのwordタイムスタンプを参照して、
    フィラーに最も近いword境界でカットする。
    """
    best_start = filler_start
    best_end = filler_end

    for seg in transcription.segments:
        if seg.end < filler_start - 1 or seg.start > filler_end + 1:
            continue
        words = getattr(seg, "words", None) or []
        for w in words:
            w_start = w.start if hasattr(w, "start") else w.get("start", 0)
            w_end = w.end if hasattr(w, "end") else w.get("end", 0)

            # フィラー開始に最も近いword開始をsnap先にする
            if abs(w_start - filler_start) < 0.3:
                best_start = w_start

            # フィラー終了に最も近いword開始をsnap先にする
            # （word開始にスナップ = その単語を切らない）
            if abs(w_start - filler_end) < 0.3:
                best_end = w_start

    return best_start, best_end


def _extract_audio_range(video_path: Path, start: float, end: float, output_path: Path) -> None:
    """ffmpegで指定範囲の音声をWAVとして抽出する"""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        str(start),
        "-to",
        str(end),
        "-i",
        str(video_path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "wav",
        str(output_path),
    ]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg error: {result.stderr[:200]}")
