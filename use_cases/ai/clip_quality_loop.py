"""
統合品質チェック→修正ループ

全品質チェック → 問題の種類に応じた修正 → 再チェック を繰り返す。

チェック項目:
  1. デュレーション（指定範囲内か）
  2. ピッチ自然さ（カット点のイントネーション）
  3. テキスト自然さ（文として途中で切れていないか）

修正アクション:
  - extend: 不自然なカット点を隣接クリップと結合
  - trim_redundant: デュレーション超過時に不要な文を削除
  - split: 長すぎるクリップをより良い位置で分割
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 5


@dataclass
class QualityIssue:
    """検出された品質問題"""
    type: str   # "duration_over", "duration_under", "unnatural_cut", "unnatural_text"
    detail: str
    clip_index: int | None = None  # 問題のあるクリップインデックス


@dataclass
class QualityCheckResult:
    """品質チェック結果"""
    is_ok: bool
    issues: list[QualityIssue] = field(default_factory=list)


def run_quality_loop(
    suggestion: ClipSuggestion,
    video_path: Path,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
) -> ClipSuggestion:
    """統合品質チェック→修正ループを実行する。

    全チェック → 問題に応じた修正 → 再チェック を最大MAX_ITERATIONS回繰り返す。
    """
    for iteration in range(MAX_ITERATIONS):
        # 全品質チェック
        result = _run_all_checks(
            suggestion, video_path, transcription, min_duration, max_duration
        )

        if result.is_ok:
            logger.info(f"品質OK (iteration {iteration}): {suggestion.title}")
            return suggestion

        logger.info(
            f"品質問題{len(result.issues)}件 (iteration {iteration}): "
            f"{[i.type for i in result.issues]}"
        )

        # 問題の種類に応じた修正
        modified = _apply_fixes(
            suggestion, result.issues, video_path, transcription, gateway,
            min_duration, max_duration,
        )

        if not modified:
            logger.info(f"修正不可 → ループ終了: {suggestion.title}")
            break

        # デュレーション再計算
        suggestion.total_duration = sum(
            e - s for s, e in suggestion.time_ranges
        )

    # ループ終了後も品質基準を満たさない → スキップ
    final_check = _run_all_checks(
        suggestion, video_path, transcription, min_duration, max_duration
    )
    if not final_check.is_ok:
        logger.warning(
            f"品質基準を満たせずスキップ: {suggestion.title} "
            f"(issues: {[i.type for i in final_check.issues]})"
        )
        return None

    return suggestion


def _run_all_checks(
    suggestion: ClipSuggestion,
    video_path: Path,
    transcription: TranscriptionResult,
    min_duration: float,
    max_duration: float,
) -> QualityCheckResult:
    """全品質チェックを実行する"""
    issues = []

    if not suggestion.time_ranges:
        return QualityCheckResult(is_ok=False, issues=[
            QualityIssue(type="no_ranges", detail="time_rangesが空")
        ])

    total = sum(e - s for s, e in suggestion.time_ranges)

    # 1. デュレーションチェック
    if total > max_duration:
        issues.append(QualityIssue(
            type="duration_over",
            detail=f"合計{total:.0f}秒（最大{max_duration:.0f}秒超過）",
        ))
    elif total < min_duration:
        issues.append(QualityIssue(
            type="duration_under",
            detail=f"合計{total:.0f}秒（最小{min_duration:.0f}秒未満）",
        ))

    # 2. ピッチ自然さチェック（クリップが2つ以上ある場合）
    if len(suggestion.time_ranges) >= 2:
        try:
            from use_cases.ai.audio_filler_detector import check_cut_naturalness
            cut_points = [end for _, end in suggestion.time_ranges[:-1]]
            naturalness_results = check_cut_naturalness(video_path, cut_points)
            for i, nat in enumerate(naturalness_results):
                if not nat.is_natural and nat.confidence > 0.3:
                    issues.append(QualityIssue(
                        type="unnatural_cut",
                        detail=f"ピッチ{nat.pitch_direction}",
                        clip_index=i,
                    ))
        except Exception as e:
            logger.debug(f"ピッチ分析スキップ: {e}")

    # 3. テキスト自然さチェック（AIに判定させる）
    # → _apply_fixesの中で実行（API呼び出しなので問題がある場合のみ）

    return QualityCheckResult(
        is_ok=len(issues) == 0,
        issues=issues,
    )


def _apply_fixes(
    suggestion: ClipSuggestion,
    issues: list[QualityIssue],
    video_path: Path,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
    min_duration: float,
    max_duration: float,
) -> bool:
    """問題の種類に応じた修正を適用する。修正があればTrue。"""
    modified = False

    # 優先度順に処理

    # (A) 不自然なカット点 → AIにテキスト含めてレビューさせてextend
    unnatural_cuts = [i for i in issues if i.type == "unnatural_cut"]
    if unnatural_cuts or len(suggestion.time_ranges) >= 2:
        # 不自然カットがなくてもテキスト自然さをAIレビュー
        cut_issues = [
            {"index": i.clip_index, "direction": i.detail}
            for i in unnatural_cuts
        ]
        segments_text = _get_text_for_ranges(suggestion, transcription)

        reviews = gateway.review_naturalness(
            suggestion.title, segments_text, cut_issues
        )

        old_count = len(suggestion.time_ranges)
        suggestion.time_ranges = _apply_extend_reviews(
            suggestion.time_ranges, reviews
        )
        if len(suggestion.time_ranges) != old_count:
            modified = True
            suggestion.total_duration = sum(
                e - s for s, e in suggestion.time_ranges
            )
            logger.info(f"  extend: {old_count}→{len(suggestion.time_ranges)}クリップ")

    # (B) デュレーション超過 → 不要な文を削除
    duration_over = [i for i in issues if i.type == "duration_over"]
    if duration_over:
        excess = suggestion.total_duration - max_duration
        trimmed = _trim_redundant_segments(
            suggestion, transcription, gateway, excess
        )
        if trimmed:
            modified = True
            logger.info(f"  trim: {suggestion.total_duration:.0f}s → 目標{max_duration:.0f}s")

    return modified


def _trim_redundant_segments(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
    excess_seconds: float,
) -> bool:
    """デュレーション超過時に不要な文を末尾から削除する。

    AIに「どのクリップが最も省略可能か」を判断させる。
    """
    if not suggestion.time_ranges or len(suggestion.time_ranges) < 2:
        # クリップが1つしかない場合は末尾を機械的にカット
        if suggestion.time_ranges:
            start, end = suggestion.time_ranges[-1]
            new_end = end - excess_seconds
            if new_end > start + 1.0:
                suggestion.time_ranges[-1] = (start, new_end)
                suggestion.total_duration = sum(
                    e - s for s, e in suggestion.time_ranges
                )
                return True
        return False

    # AIに不要クリップを判定させる
    segments_text = _get_text_for_ranges(suggestion, transcription)

    import json
    try:
        prompt = f"""以下のクリップで合計{suggestion.total_duration:.0f}秒ありますが、最大秒数を超えています。
話の本筋を損なわずに省略できるクリップを選んでください。
繰り返し・補足説明・脱線が省略候補です。

{chr(10).join(f'クリップ{i+1}: {t}' for i, t in enumerate(segments_text))}

JSON: {{"remove_indices": [省略するクリップの番号(0始まり)]}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画編集担当。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        remove_indices = set(result.get("remove_indices", []))

        if remove_indices:
            new_ranges = [
                r for i, r in enumerate(suggestion.time_ranges)
                if i not in remove_indices
            ]
            if new_ranges:
                suggestion.time_ranges = new_ranges
                suggestion.total_duration = sum(
                    e - s for s, e in suggestion.time_ranges
                )
                logger.info(f"  不要クリップ{len(remove_indices)}個削除")
                return True
    except Exception as e:
        logger.warning(f"不要クリップ判定失敗: {e}")

    # フォールバック: 末尾クリップを削除
    if len(suggestion.time_ranges) > 1:
        suggestion.time_ranges = suggestion.time_ranges[:-1]
        suggestion.total_duration = sum(
            e - s for s, e in suggestion.time_ranges
        )
        return True

    return False


def _get_text_for_ranges(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
) -> list[str]:
    """各time_rangeに対応するテキストを取得する"""
    result = []
    for tr_start, tr_end in suggestion.time_ranges:
        texts = []
        for seg in transcription.segments:
            if seg.end > tr_start and seg.start < tr_end:
                texts.append(seg.text)
        clip_text = "".join(texts) if texts else ""
        result.append(f"({tr_start:.1f}s-{tr_end:.1f}s) {clip_text[:150]}")
    return result


def _apply_extend_reviews(
    time_ranges: list[tuple[float, float]],
    reviews: list[dict],
) -> list[tuple[float, float]]:
    """AIレビューのextendアクションを適用する"""
    if not reviews:
        return time_ranges

    extend_indices = set()
    for review in reviews:
        if review.get("action") == "extend":
            idx = review.get("index", -1)
            if 0 <= idx < len(time_ranges) - 1:
                extend_indices.add(idx)

    if not extend_indices:
        return time_ranges

    merged = []
    i = 0
    while i < len(time_ranges):
        start, end = time_ranges[i]
        while i in extend_indices and i + 1 < len(time_ranges):
            i += 1
            _, end = time_ranges[i]
        merged.append((start, end))
        i += 1

    return merged
