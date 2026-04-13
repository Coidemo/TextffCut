"""
統合品質チェック→修正ループ

出来上がり音声を実際に文字起こしし、AIに品質判定させる。
テキストパターンマッチではなく、実際の聴こえ方で判断する。

チェック:
  1. デュレーション（指定範囲内か）
  2. 内容の完結性（出来上がり音声の文字起こし → AI判定）

修正:
  - truncate: 末尾を自然な文末まで切り詰め
  - extend: トピック範囲を超えて隣接セグメントを追加
  - trim_start: 冒頭の不要部分を削除
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


@dataclass
class QualityCheckResult:
    is_ok: bool
    issues: list[str] = field(default_factory=list)
    transcribed_text: str = ""


def run_quality_loop(
    suggestion: ClipSuggestion,
    video_path: Path,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
) -> ClipSuggestion | None:
    """出来上がり音声の文字起こし→AI判定による品質ループ。"""

    fix_counts: dict[str, int] = {}

    for iteration in range(MAX_ITERATIONS):
        # 出来上がり音声を文字起こし
        transcribed = _transcribe_output(suggestion, video_path, gateway)
        if not transcribed:
            logger.warning(f"文字起こし失敗: {suggestion.title}")
            break

        # デュレーションチェック
        total = suggestion.total_duration
        if total > max_duration:
            logger.info(f"duration_over ({total:.0f}s > {max_duration:.0f}s): {suggestion.title}")
            _trim_duration(suggestion, transcription, max_duration, gateway, video_path, min_duration=min_duration)
            continue
        if total < min_duration:
            logger.info(f"duration_under ({total:.0f}s < {min_duration:.0f}s): {suggestion.title}")
            extended = _extend_range(suggestion, transcription, min_duration, topic_end_time=suggestion.topic_end_time)
            if not extended:
                break
            continue

        # 音響分析（クリップ結合部の自然さ）
        audio_issues = []
        try:
            from use_cases.ai.audio_naturalness import analyze_join_naturalness

            joins = analyze_join_naturalness(video_path, suggestion.time_ranges)
            audio_issues = [f"クリップ{j.index+1}→{j.index+2}の結合部: {j.detail}" for j in joins if not j.is_natural]
        except Exception as e:
            logger.debug(f"音響分析スキップ: {e}")

        # AI品質判定（出来上がりテキスト + 音響分析結果）
        result = _ai_quality_check(suggestion.title, transcribed, gateway, audio_issues)

        if result.is_ok:
            logger.info(f"品質OK (iteration {iteration}): {suggestion.title}")
            return suggestion

        logger.info(f"品質問題 (iteration {iteration}): {result.issues}")

        # AI修正提案に基づいて修正
        modified = _apply_ai_fixes(
            suggestion,
            transcription,
            result,
            gateway,
            video_path,
            max_duration,
            min_duration=min_duration,
            fix_counts=fix_counts,
        )
        if not modified:
            logger.info(f"修正不可 → 終了: {suggestion.title}")
            break

    # 最終チェック
    total = suggestion.total_duration
    if total < min_duration or total > max_duration:
        logger.warning(f"デュレーション基準未達でスキップ: {suggestion.title} ({total:.0f}s)")
        return None

    # デュレーションOKなら最終判定（incomplete_contentのみ）
    transcribed = _transcribe_output(suggestion, video_path, gateway)
    if transcribed:
        final = _ai_quality_check(suggestion.title, transcribed, gateway)
        if not final.is_ok and "incomplete" in str(final.issues).lower():
            logger.warning(f"内容不完結でスキップ: {suggestion.title}")
            return None

    return suggestion


def _transcribe_output(
    suggestion: ClipSuggestion,
    video_path: Path,
    gateway: ClipSuggestionGatewayInterface | None = None,
) -> str | None:
    """出来上がり音声をffmpegで結合→Whisper文字起こし。"""
    if not suggestion.time_ranges:
        return None

    try:
        # gateway.client を使用（APIキーマネージャ経由で認証済み）
        if gateway and hasattr(gateway, "client"):
            client = gateway.client
        else:
            import os

            from dotenv import load_dotenv

            load_dotenv()
            from openai import OpenAI

            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
            if not api_key:
                return None
            client = OpenAI(api_key=api_key)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 各rangeの音声を抽出して結合
            parts = []
            for i, (start, end) in enumerate(suggestion.time_ranges):
                part_path = f"{tmpdir}/p{i}.wav"
                proc = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(start),
                        "-t",
                        str(end - start),
                        "-i",
                        str(video_path),
                        "-vn",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        part_path,
                    ],
                    capture_output=True,
                    timeout=15,
                )
                if proc.returncode != 0:
                    stderr = (
                        proc.stderr.decode(errors="replace")[:200]
                        if isinstance(proc.stderr, bytes)
                        else str(proc.stderr)[:200]
                    )
                    logger.warning(f"ffmpeg extract failed (part {i}): {stderr}")
                    return None
                parts.append(part_path)

            list_path = f"{tmpdir}/list.txt"
            with open(list_path, "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")

            combined_path = f"{tmpdir}/combined.wav"
            proc = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", combined_path],
                capture_output=True,
                timeout=15,
            )
            if proc.returncode != 0:
                stderr = (
                    proc.stderr.decode(errors="replace")[:200]
                    if isinstance(proc.stderr, bytes)
                    else str(proc.stderr)[:200]
                )
                logger.warning(f"ffmpeg concat failed: {stderr}")
                return None

            with open(combined_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="ja",
                    response_format="text",
                    prompt="えー、あの、まあ、なんか、えっと、",
                )

            return resp if isinstance(resp, str) else str(resp)

    except Exception as e:
        logger.warning(f"Output transcription failed: {e}")
        return None


def _ai_quality_check(
    title: str,
    transcribed_text: str,
    gateway: ClipSuggestionGatewayInterface,
    audio_issues: list[str] | None = None,
) -> QualityCheckResult:
    """出来上がりテキストをAIに判定させる。"""
    try:
        result = gateway.evaluate_clip_quality(
            title=title,
            transcribed_text=transcribed_text,
            audio_issues=audio_issues,
        )
        return QualityCheckResult(
            is_ok=result.get("ok", False),
            issues=result.get("issues", []) + result.get("fix_suggestions", []),
            transcribed_text=transcribed_text,
        )
    except Exception as e:
        logger.warning(f"AI quality check failed: {e}")
        return QualityCheckResult(is_ok=True, transcribed_text=transcribed_text)


def _apply_ai_fixes(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    check_result: QualityCheckResult,
    gateway: ClipSuggestionGatewayInterface,
    video_path: Path,
    max_duration: float = 60.0,
    min_duration: float = 0,
    fix_counts: dict[str, int] | None = None,
) -> bool:
    """AI判定の問題に基づいて修正する。"""
    if fix_counts is None:
        fix_counts = {}

    issues_str = " ".join(check_result.issues).lower()

    has_ending_issue = any(w in issues_str for w in ["末尾", "途中で切れ", "続きそう"])
    has_start_issue = any(w in issues_str for w in ["冒頭", "文脈", "何の話", "わからない"])
    has_conclusion_issue = any(w in issues_str for w in ["結論", "前置き", "incomplete"])
    has_redundancy = any(w in issues_str for w in ["冗長", "繰り返し", "シンプル", "回りくどい", "不要", "削除"])
    has_audio_issue = any(w in issues_str for w in ["音圧", "ピッチ", "音響", "カット"])

    # 冒頭に文脈がない → 前方に延長（AIに必要なセグメントを判断させる）
    if has_start_issue and fix_counts.get("extend_back", 0) < 2:
        extended = _extend_range_backward(
            suggestion,
            transcription,
            gateway,
            topic_start_time=suggestion.topic_start_time,
        )
        if extended:
            fix_counts["extend_back"] = fix_counts.get("extend_back", 0) + 1
            logger.info(f"  前方延長: → {suggestion.total_duration:.0f}s")
            return True

    # 結論がない or 末尾で切れている → 後方に延長
    if (has_conclusion_issue or has_ending_issue) and fix_counts.get("extend_fwd", 0) < 2:
        target = min(suggestion.total_duration + 15, max_duration)
        extended = _extend_range(
            suggestion,
            transcription,
            target,
            topic_end_time=suggestion.topic_end_time,
        )
        if extended:
            fix_counts["extend_fwd"] = fix_counts.get("extend_fwd", 0) + 1
            logger.info(f"  後方延長: → {suggestion.total_duration:.0f}s")
            return True

        # 延長できなかった場合のみ末尾トリム
        if has_ending_issue and len(suggestion.time_ranges) > 2 and fix_counts.get("trim_tail", 0) < 2:
            old = len(suggestion.time_ranges)
            suggestion.time_ranges = suggestion.time_ranges[:-1]
            suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
            fix_counts["trim_tail"] = fix_counts.get("trim_tail", 0) + 1
            logger.info(f"  末尾トリム: {old}→{len(suggestion.time_ranges)}クリップ")
            return True

    # タイトルと無関係な話題が混入 → 無関係セグメントを除去
    has_irrelevant = any(w in issues_str for w in ["無関係", "別の話題", "タイトルと関係", "別のテーマ"])
    if has_irrelevant and fix_counts.get("trim_irrelevant", 0) < 2:
        trimmed = _trim_irrelevant_segments(suggestion, transcription, gateway)
        if trimmed:
            fix_counts["trim_irrelevant"] = fix_counts.get("trim_irrelevant", 0) + 1
            logger.info(f"  無関係セグメント除去: → {suggestion.total_duration:.0f}s")
            return True

    # 冗長 or 音響不自然 → 中間カット
    if (has_redundancy or has_audio_issue) and len(suggestion.time_ranges) > 3 and fix_counts.get("trim_mid", 0) < 2:
        _trim_duration(
            suggestion, transcription, suggestion.total_duration, gateway, video_path, min_duration=min_duration
        )
        fix_counts["trim_mid"] = fix_counts.get("trim_mid", 0) + 1
        return True

    return False


def _trim_duration(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    max_duration: float,
    gateway: ClipSuggestionGatewayInterface | None = None,
    video_path: Path | None = None,
    min_duration: float = 0,
) -> None:
    """max_durationに収まるように中間の不要クリップを選択的に削除する。

    末尾から単純に削除するのではなく、AIに「主張と結論を残しつつ
    どのクリップを飛ばすか」を判断させる。
    """
    if not gateway or not video_path or len(suggestion.time_ranges) <= 3:
        # フォールバック: 末尾削除
        while suggestion.total_duration > max_duration and len(suggestion.time_ranges) > 1:
            suggestion.time_ranges = suggestion.time_ranges[:-1]
            suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        return

    # 出来上がり音声を文字起こし
    transcribed = _transcribe_output(suggestion, video_path, gateway)
    if not transcribed:
        # フォールバック
        while suggestion.total_duration > max_duration and len(suggestion.time_ranges) > 1:
            suggestion.time_ranges = suggestion.time_ranges[:-1]
            suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        return

    # 各クリップのテキストを取得
    clip_texts = []
    for i, (tr_start, tr_end) in enumerate(suggestion.time_ranges):
        texts = [seg.text for seg in transcription.segments if seg.end > tr_start and seg.start < tr_end]
        clip_texts.append(f"[{i}] ({tr_end - tr_start:.1f}s) {''.join(texts)[:80]}")

    excess = suggestion.total_duration - max_duration

    try:
        clips_text = (
            f"合計{suggestion.total_duration:.0f}秒（{excess:.0f}秒超過）\n\n"
            f"クリップ:\n{chr(10).join(clip_texts)}\n\n"
            f"出来上がりテキスト:\n{transcribed[:400]}"
        )
        remove_indices = gateway.trim_clips(
            title=suggestion.title,
            clips_text=clips_text,
            max_duration=max_duration,
        )

        if remove_indices:
            # 1回の削除数を time_ranges の 1/3（最低1）に制限
            max_remove = max(1, len(suggestion.time_ranges) // 3)
            if len(remove_indices) > max_remove:
                logger.info(f"  trim削除数制限: {len(remove_indices)}→{max_remove}個")
                remove_indices = remove_indices[:max_remove]
            remove_set = set(remove_indices)
            new_ranges = [r for i, r in enumerate(suggestion.time_ranges) if i not in remove_set]
            if new_ranges:
                new_dur = sum(e - s for s, e in new_ranges)
                # trim下限ガード: min_duration * 0.8 未満なら結果を破棄
                if min_duration and new_dur < min_duration * 0.8:
                    logger.info(f"  trim下限ガード: trim結果破棄 " f"({new_dur:.0f}s < {min_duration * 0.8:.0f}s)")
                    return
                old_dur = suggestion.total_duration
                suggestion.time_ranges = new_ranges
                suggestion.total_duration = new_dur
                logger.info(
                    f"  中間カット: {old_dur:.0f}s→{suggestion.total_duration:.0f}s "
                    f"({len(remove_indices)}クリップ削除)"
                )
                return

    except Exception as e:
        logger.warning(f"中間カット判定失敗: {e}")

    # フォールバック: 末尾削除
    while suggestion.total_duration > max_duration and len(suggestion.time_ranges) > 1:
        suggestion.time_ranges = suggestion.time_ranges[:-1]
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)


def _trim_irrelevant_segments(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
) -> bool:
    """タイトルと無関係なセグメントを特定して除去する。"""
    if not suggestion.time_ranges or not gateway:
        return False

    # time_ranges に含まれるセグメントを収集
    seg_dicts = []
    for seg in transcription.segments:
        for tr_start, tr_end in suggestion.time_ranges:
            if seg.end > tr_start and seg.start < tr_end:
                seg_dicts.append({"index": len(seg_dicts), "text": seg.text, "start": seg.start, "end": seg.end})
                break

    if len(seg_dicts) < 3:
        return False

    try:
        remove_indices = gateway.judge_segment_relevance(
            title=suggestion.title,
            segments=seg_dicts,
        )
    except Exception as e:
        logger.warning(f"無関係セグメント判定失敗: {e}")
        return False

    if not remove_indices:
        return False

    # 除去対象の時間帯を特定
    remove_times = set()
    for idx in remove_indices:
        if 0 <= idx < len(seg_dicts):
            remove_times.add((seg_dicts[idx]["start"], seg_dicts[idx]["end"]))

    if not remove_times:
        return False

    # time_ranges から除去対象と重なる部分を除外
    new_ranges = []
    for tr_start, tr_end in suggestion.time_ranges:
        is_removed = any(rs <= tr_start and re >= tr_end for rs, re in remove_times)
        if not is_removed:
            new_ranges.append((tr_start, tr_end))

    if not new_ranges or len(new_ranges) == len(suggestion.time_ranges):
        return False

    suggestion.time_ranges = new_ranges
    suggestion.total_duration = sum(e - s for s, e in new_ranges)
    return True


def _extend_range_backward(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface | None = None,
    max_segments: int = 8,
    topic_start_time: float | None = None,
) -> bool:
    """冒頭の前のセグメントを追加して文脈を補完する。

    前のセグメントの中から、この話題の文脈に必要なものだけをAIに選ばせる。
    前の話題のセグメントは追加しない。
    topic_start_timeが指定されている場合、その時間より前のセグメントは追加しない。
    """
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, detect_noise_tag

    if not suggestion.time_ranges:
        return False

    min_start = min(s for s, _ in suggestion.time_ranges)

    # 前のセグメント候補を収集
    candidates = []
    for seg in reversed(transcription.segments):
        if seg.end > min_start + 0.1:
            continue
        if min_start - seg.start > 30:
            break
        if topic_start_time is not None and seg.end < topic_start_time:
            logger.info(f"  _extend_range_backward: topic_start_time ({topic_start_time:.0f}s) で停止")
            break
        # ギャップチェック: 隣接セグメント間に5秒以上の空きがあれば話題境界とみなす
        if candidates and candidates[0].start - seg.end > 5:
            break
        # ノイズ・フィラーセグメントをスキップ
        seg_text = seg.text.strip()
        if detect_noise_tag(seg_text) or seg_text in FILLER_ONLY_TEXTS:
            continue
        candidates.insert(0, seg)
        if len(candidates) >= max_segments:
            break

    if not candidates:
        return False

    if not gateway:
        # フォールバック: 最初の2セグメントだけ追加
        prepend = [(seg.start, seg.end) for seg in candidates[-2:]]
        suggestion.time_ranges = prepend + suggestion.time_ranges
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        return True

    # AIに「この話題の文脈として必要なセグメントはどれか」を判断させる
    # 現在の冒頭テキストも含めて判断材料にする
    current_start_texts = []
    for seg in transcription.segments:
        for s, e in suggestion.time_ranges[:3]:
            if seg.end > s and seg.start < e:
                current_start_texts.append(seg.text)
                break
    current_start = "".join(current_start_texts)[:150]

    try:
        cand_desc = "\n".join(f"[{i}] ({seg.start:.0f}s) {seg.text}" for i, seg in enumerate(candidates))

        # judge_segment_relevanceを利用して不要セグメントを判定
        # ただしここでは「含めるべき」を選ぶため、逆に全体から除外を引く
        seg_dicts = [
            {"index": i, "text": seg.text, "start": seg.start, "end": seg.end} for i, seg in enumerate(candidates)
        ]
        remove_indices = gateway.judge_segment_relevance(
            title=f"{suggestion.title}（前方文脈補完）",
            segments=seg_dicts,
        )

        include_indices = [i for i in range(len(candidates)) if i not in set(remove_indices)]

        if include_indices:
            prepend = [(candidates[i].start, candidates[i].end) for i in include_indices]
            if prepend:
                suggestion.time_ranges = prepend + suggestion.time_ranges
                suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
                logger.info(f"  前方延長: {len(prepend)}セグメント追加")
                return True

    except Exception as e:
        logger.warning(f"前方延長AI判定失敗: {e}")

    return False


def _extend_range(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    target_duration: float,
    topic_end_time: float | None = None,
) -> bool:
    """トピック範囲外の隣接セグメントを追加して延長する。

    time_rangesの末尾ではなく、全time_rangesの最大endの後にある
    セグメントを探す（フィラー削除で細かく分割されていても正しく延長できる）。
    topic_end_timeが指定されている場合、その時間を超えるセグメントは追加しない。
    """
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS, detect_noise_tag

    if not suggestion.time_ranges:
        return False

    # 全rangesの最大end
    max_end = max(e for _, e in suggestion.time_ranges)

    # max_endの後にあるセグメントを探して追加
    added = False
    added_count = 0
    for seg in transcription.segments:
        if seg.start < max_end - 0.1:
            continue
        if seg.start > max_end + 5:
            # 5秒以上のギャップがあれば話題が変わったとみなす
            break
        if topic_end_time is not None and seg.start > topic_end_time:
            logger.info(f"  _extend_range: topic_end_time ({topic_end_time:.0f}s) で停止")
            break
        if added_count >= 15:
            break

        # ノイズ・フィラーセグメントをスキップ
        seg_text = seg.text.strip()
        if detect_noise_tag(seg_text) or seg_text in FILLER_ONLY_TEXTS:
            continue

        suggestion.time_ranges.append((seg.start, seg.end))
        max_end = seg.end
        added = True
        added_count += 1
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        if suggestion.total_duration >= target_duration:
            break

    return added
