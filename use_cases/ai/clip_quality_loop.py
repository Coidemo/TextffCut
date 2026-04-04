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
            suggestion, video_path, transcription, min_duration, max_duration, gateway
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
    gateway: ClipSuggestionGatewayInterface | None = None,
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

    # 3. 冒頭・末尾のテキスト自然さチェック（機械的）
    if transcription:
        texts_per_range = _get_text_for_ranges(suggestion, transcription)
        # 末尾チェック
        if texts_per_range:
            last_text = texts_per_range[-1]
            BAD_ENDINGS = ["ので", "けど", "から", "って", "のが", "みたいな",
                           "けれども", "とか", "んですけど", "ですけど", "んですが"]
            for bad in BAD_ENDINGS:
                if last_text.rstrip("。、 ").endswith(bad):
                    issues.append(QualityIssue(
                        type="bad_ending",
                        detail=f"末尾が「{bad}」で終わっている",
                        clip_index=len(suggestion.time_ranges) - 1,
                    ))
                    break
        # 冒頭チェック
        if texts_per_range:
            first_text = texts_per_range[0]
            # 時間情報を除去してテキスト部分だけ取得
            text_part = first_text.split(") ", 1)[-1] if ") " in first_text else first_text
            BAD_STARTS = ["なのかな", "ちょっとわかんない", "まあ、"]
            for bad in BAD_STARTS:
                if text_part.startswith(bad):
                    issues.append(QualityIssue(
                        type="bad_start",
                        detail=f"冒頭が「{bad}」で始まっている（前の話題の混入）",
                        clip_index=0,
                    ))
                    break

    # 4. 内容の完結性チェック（AIに判定させる）
    # time_rangesに対応する実際のテキストで判定する
    if gateway and transcription and suggestion.time_ranges:
        actual_texts = _get_text_for_ranges(suggestion, transcription)
        actual_text = " ".join(
            t.split(") ", 1)[-1] if ") " in t else t for t in actual_texts
        )
        completeness_issue = _check_content_completeness(
            actual_text, suggestion.title, gateway
        )
        if completeness_issue:
            issues.append(completeness_issue)

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

    # (A) 不自然なカット点 → AIレビューでextend or truncate
    unnatural_cuts = [i for i in issues if i.type == "unnatural_cut"]
    if unnatural_cuts or len(suggestion.time_ranges) >= 2:
        cut_issues = [
            {"index": i.clip_index, "direction": i.detail}
            for i in unnatural_cuts
        ]
        segments_text = _get_text_for_ranges(suggestion, transcription)

        reviews = gateway.review_naturalness(
            suggestion.title, segments_text, cut_issues
        )

        old_count = len(suggestion.time_ranges)
        old_ranges = list(suggestion.time_ranges)

        # extend適用
        suggestion.time_ranges = _apply_extend_reviews(
            suggestion.time_ranges, reviews
        )

        # remove適用（不要クリップ削除）
        remove_indices = {r.get("index") for r in reviews if r.get("action") == "remove"}
        if remove_indices:
            suggestion.time_ranges = [
                r for i, r in enumerate(suggestion.time_ranges)
                if i not in remove_indices
            ]

        if len(suggestion.time_ranges) != old_count:
            modified = True
            suggestion.total_duration = sum(
                e - s for s, e in suggestion.time_ranges
            )
            logger.info(f"  extend/remove: {old_count}→{len(suggestion.time_ranges)}クリップ")

        # extend後もunnatural_cutが残る場合、末尾を大胆にカット
        # （伸ばしてダメなら短くする）
        if not modified and unnatural_cuts:
            truncated = _truncate_to_natural_end(
                suggestion, transcription, gateway
            )
            if truncated:
                modified = True

    # (A2) 末尾が不自然 → 末尾クリップを削除して自然な文末まで戻す
    bad_endings = [i for i in issues if i.type == "bad_ending"]
    if bad_endings and len(suggestion.time_ranges) > 1:
        # 末尾から「です」「ます」「よね」等で終わるクリップを探す
        GOOD_ENDINGS = ["です", "ます", "ですね", "ますね", "ですよね", "ますよね",
                        "ました", "思います", "よね", "んですよ", "んです",
                        "ください", "しょう", "ません", "ないです"]
        texts = _get_text_for_ranges(suggestion, transcription)
        good_end_idx = None
        for idx in range(len(texts) - 2, -1, -1):
            text_part = texts[idx].split(") ", 1)[-1] if ") " in texts[idx] else texts[idx]
            if any(text_part.rstrip("。、 ").endswith(g) for g in GOOD_ENDINGS):
                good_end_idx = idx
                break
        if good_end_idx is not None and good_end_idx < len(suggestion.time_ranges) - 1:
            candidate_ranges = suggestion.time_ranges[:good_end_idx + 1]
            candidate_dur = sum(e - s for s, e in candidate_ranges)
            # 短くなりすぎないようにガード（min_durationの80%以上）
            if candidate_dur >= min_duration * 0.8:
                old = len(suggestion.time_ranges)
                suggestion.time_ranges = candidate_ranges
                suggestion.total_duration = candidate_dur
                modified = True
                logger.info(f"  bad_ending fix: {old}→{len(suggestion.time_ranges)}クリップ ({suggestion.total_duration:.0f}s)")
            else:
                logger.info(f"  bad_ending: 切り詰めると{candidate_dur:.0f}sで短すぎるためスキップ")

    # (A3) 冒頭が不自然 → 冒頭クリップを削除
    bad_starts = [i for i in issues if i.type == "bad_start"]
    if bad_starts and len(suggestion.time_ranges) > 1:
        suggestion.time_ranges = suggestion.time_ranges[1:]
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        modified = True
        logger.info(f"  bad_start fix: 冒頭クリップ削除")

    # (A4) 内容が完結していない → 修正不可（スキップされる）
    # incomplete_contentは構造的に修正できないため、何もしない
    # （ループが終了し、final_checkで不合格→Noneが返る）

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


def _check_content_completeness(
    text: str,
    title: str,
    gateway: ClipSuggestionGatewayInterface,
) -> QualityIssue | None:
    """テキストが内容として完結しているかAIに判定させる。

    前置きだけで結論がない、途中で切れている等を検出。
    """
    import json

    try:
        prompt = f"""以下はショート動画「{title}」の書き起こしテキストです。
この動画を見た視聴者が「学びがあった」「保存したい」と思える内容かどうか厳しく判定してください。

テキスト:
{text[:500]}

以下のいずれかに該当する場合はfalse（不合格）としてください：
- テーマの紹介や前置きだけで、具体的な主張・結論・アドバイスがない
- 「〜とか」「〜ですよね」で終わって話が続きそうな印象がある
- 質問の読み上げが大部分を占め、回答が途中で切れている
- 例え話や脱線で終わっていて本題の結論に到達していない
- 視聴者が見終わった後に「で、結論は？」と思う

JSON: {{"complete": true/false, "reason": "理由"}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画コンテンツの品質評価担当。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)

        if not result.get("complete", True):
            reason = result.get("reason", "内容が完結していない")
            logger.info(f"  内容不完結: {reason}")
            return QualityIssue(
                type="incomplete_content",
                detail=reason,
            )
    except Exception as e:
        logger.warning(f"完結性チェック失敗: {e}")

    return None


def _truncate_to_natural_end(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface,
) -> bool:
    """末尾のクリップを自然な文末まで短縮する。

    「〜とか」「〜ので」「〜けど」等で終わっている場合、
    その前の自然な文末（「〜です」「〜ます」「〜よね」等）まで戻る。
    """
    if not suggestion.time_ranges:
        return False

    segments_text = _get_text_for_ranges(suggestion, transcription)

    import json
    try:
        prompt = f"""以下のクリップで構成される切り抜き動画があります。
末尾が不自然に切れている場合、どのクリップまでで終わるべきか判断してください。

{chr(10).join(f'クリップ{i+1}: {t}' for i, t in enumerate(segments_text))}

自然な終わり方の例: 「〜です」「〜ます」「〜ですね」「〜ますよね」「〜と思います」
不自然な終わり方の例: 「〜とか」「〜ので」「〜けど」「〜って」「〜のが」

JSON: {{"end_at_clip": 最後に含めるクリップ番号(1始まり), "reason": "理由"}}
全クリップで問題ない場合は現在のクリップ数をそのまま返してください。"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画編集の品質管理担当。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        end_at = result.get("end_at_clip", len(suggestion.time_ranges))

        if end_at < len(suggestion.time_ranges):
            old = len(suggestion.time_ranges)
            suggestion.time_ranges = suggestion.time_ranges[:end_at]
            suggestion.total_duration = sum(
                e - s for s, e in suggestion.time_ranges
            )
            logger.info(
                f"  truncate: {old}→{len(suggestion.time_ranges)}クリップ "
                f"({suggestion.total_duration:.0f}s) reason: {result.get('reason','')}"
            )
            return True
    except Exception as e:
        logger.warning(f"Truncate判定失敗: {e}")

    # 同様に冒頭もチェック
    try:
        prompt2 = f"""以下のクリップで構成される切り抜き動画の冒頭をチェックしてください。
最初のクリップが前の話題の末尾で始まっている場合、何番目のクリップから始めるべきか判断してください。

{chr(10).join(f'クリップ{i+1}: {t}' for i, t in enumerate(segments_text[:5]))}

JSON: {{"start_at_clip": 最初に含めるクリップ番号(1始まり), "reason": "理由"}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画編集の品質管理担当。JSON形式で回答。"},
                {"role": "user", "content": prompt2},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        start_at = result.get("start_at_clip", 1)

        if start_at > 1 and start_at <= len(suggestion.time_ranges):
            old = len(suggestion.time_ranges)
            suggestion.time_ranges = suggestion.time_ranges[start_at - 1:]
            suggestion.total_duration = sum(
                e - s for s, e in suggestion.time_ranges
            )
            logger.info(
                f"  trim_start: clip{start_at}から開始 "
                f"({suggestion.total_duration:.0f}s) reason: {result.get('reason','')}"
            )
            return True
    except Exception as e:
        logger.warning(f"冒頭トリム判定失敗: {e}")

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
