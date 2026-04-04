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

    for iteration in range(MAX_ITERATIONS):
        # 出来上がり音声を文字起こし
        transcribed = _transcribe_output(suggestion, video_path)
        if not transcribed:
            logger.warning(f"文字起こし失敗: {suggestion.title}")
            break

        # デュレーションチェック
        total = suggestion.total_duration
        if total > max_duration:
            logger.info(f"duration_over ({total:.0f}s > {max_duration:.0f}s): {suggestion.title}")
            _trim_duration(suggestion, transcription, max_duration, gateway, video_path)
            continue
        if total < min_duration:
            logger.info(f"duration_under ({total:.0f}s < {min_duration:.0f}s): {suggestion.title}")
            extended = _extend_range(suggestion, transcription, min_duration)
            if not extended:
                break
            continue

        # AI品質判定（出来上がりテキストで判断）
        result = _ai_quality_check(
            suggestion.title, transcribed, gateway
        )

        if result.is_ok:
            logger.info(f"品質OK (iteration {iteration}): {suggestion.title}")
            return suggestion

        logger.info(f"品質問題 (iteration {iteration}): {result.issues}")

        # AI修正提案に基づいて修正
        modified = _apply_ai_fixes(
            suggestion, transcription, result, gateway, video_path, max_duration
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
    transcribed = _transcribe_output(suggestion, video_path)
    if transcribed:
        final = _ai_quality_check(suggestion.title, transcribed, gateway)
        if not final.is_ok and "incomplete" in str(final.issues).lower():
            logger.warning(f"内容不完結でスキップ: {suggestion.title}")
            return None

    return suggestion


def _transcribe_output(
    suggestion: ClipSuggestion,
    video_path: Path,
) -> str | None:
    """出来上がり音声をffmpegで結合→Whisper文字起こし。"""
    if not suggestion.time_ranges:
        return None

    try:
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
                subprocess.run(
                    ["ffmpeg", "-y", "-ss", str(start), "-t", str(end - start),
                     "-i", str(video_path), "-vn", "-ar", "16000", "-ac", "1", part_path],
                    capture_output=True, timeout=15,
                )
                parts.append(part_path)

            list_path = f"{tmpdir}/list.txt"
            with open(list_path, "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")

            combined_path = f"{tmpdir}/combined.wav"
            subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                 "-i", list_path, "-c", "copy", combined_path],
                capture_output=True, timeout=15,
            )

            with open(combined_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1", file=f, language="ja",
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
) -> QualityCheckResult:
    """出来上がりテキストをAIに判定させる。"""
    try:
        prompt = f"""以下はショート動画「{title}」の出来上がり音声を文字起こししたテキストです。
品質を厳しく判定してください。

テキスト:
{transcribed_text}

以下の問題がある場合は不合格です:
1. 末尾が途中で切れている（「〜とか」「〜ので」「〜けど」で終わって話が続きそう）
2. 冒頭に文脈がなく何の話かわからない（質問の途中から始まっている等）
3. 内容が前置きだけで結論がない（視聴者が「で、結論は？」と思う）
4. 独り言や脱線が残っている（「何話そうと思ったんだっけ」等）
5. 冗長なやり取りがある（同じことの繰り返し、なくても伝わる補足説明、回りくどい言い回し）

特に5について: たとえ時間内に収まっていても、もっとシンプルにできる部分があれば指摘してください。
言いたいことがわかる部分だけ残して、それ以外はバッサリ切るべきです。

JSON: {{"ok": true/false, "issues": ["問題1", "問題2"], "fix_suggestions": ["末尾を○○の後で切る", "冒頭の○○を削除", "中間の○○は冗長なので削除"]}}
問題がなければ {{"ok": true, "issues": [], "fix_suggestions": []}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "ショート動画の品質管理担当。厳しく判定。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)

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
) -> bool:
    """AI判定の問題に基づいて修正する。"""
    issues_str = " ".join(check_result.issues).lower()

    has_ending_issue = any(w in issues_str for w in ["末尾", "途中で切れ", "続きそう"])
    has_start_issue = any(w in issues_str for w in ["冒頭", "文脈", "何の話", "わからない"])
    has_conclusion_issue = any(w in issues_str for w in ["結論", "前置き", "incomplete"])
    has_redundancy = any(w in issues_str for w in ["冗長", "繰り返し", "シンプル", "回りくどい", "不要", "削除"])

    # 冒頭に文脈がない → 前方に延長（AIに必要なセグメントを判断させる）
    if has_start_issue:
        extended = _extend_range_backward(suggestion, transcription, gateway)
        if extended:
            logger.info(f"  前方延長: → {suggestion.total_duration:.0f}s")
            return True

    # 結論がない or 末尾で切れている → 後方に延長
    if has_conclusion_issue or has_ending_issue:
        target = min(suggestion.total_duration + 15, max_duration)
        extended = _extend_range(suggestion, transcription, target)
        if extended:
            logger.info(f"  後方延長: → {suggestion.total_duration:.0f}s")
            return True

        # 延長できなかった場合のみ末尾トリム
        if has_ending_issue and len(suggestion.time_ranges) > 2:
            old = len(suggestion.time_ranges)
            suggestion.time_ranges = suggestion.time_ranges[:-1]
            suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
            logger.info(f"  末尾トリム: {old}→{len(suggestion.time_ranges)}クリップ")
            return True

    # 冗長 → 中間カット（duration内でもシンプルにする）
    if has_redundancy and len(suggestion.time_ranges) > 3:
        _trim_duration(suggestion, transcription,
                       suggestion.total_duration,  # 現在のdurationをtargetに
                       gateway, video_path)
        # 実際にクリップ数が減ったか確認
        return True  # 常にTrue（AIが何も削除しなくても再チェックは行う）

    return False


def _trim_duration(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    max_duration: float,
    gateway: ClipSuggestionGatewayInterface | None = None,
    video_path: Path | None = None,
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
    transcribed = _transcribe_output(suggestion, video_path)
    if not transcribed:
        # フォールバック
        while suggestion.total_duration > max_duration and len(suggestion.time_ranges) > 1:
            suggestion.time_ranges = suggestion.time_ranges[:-1]
            suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        return

    # 各クリップのテキストを取得
    clip_texts = []
    for i, (tr_start, tr_end) in enumerate(suggestion.time_ranges):
        texts = [seg.text for seg in transcription.segments
                 if seg.end > tr_start and seg.start < tr_end]
        clip_texts.append(f"[{i}] ({tr_end - tr_start:.1f}s) {''.join(texts)[:80]}")

    excess = suggestion.total_duration - max_duration

    try:
        prompt = f"""以下はショート動画のクリップ一覧です。
合計{suggestion.total_duration:.0f}秒ありますが、{max_duration:.0f}秒以内にする必要があります（{excess:.0f}秒超過）。

**主張と結論は必ず残してください。** 削除すべきは:
- 繰り返し・冗長な説明
- 本筋と関係ない例え話・脱線
- なくても主張が伝わる補足
- 質問の読み上げ部分（回答だけ残す）

冒頭（話の導入）と末尾（結論）は原則残してください。中間から削除するのが理想です。

クリップ:
{chr(10).join(clip_texts)}

出来上がりテキスト:
{transcribed[:400]}

JSON: {{"remove": [削除するクリップのindex番号], "reason": "理由"}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画編集の中間カット担当。主張と結論を残して不要部分を大胆に削除。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        remove_indices = set(result.get("remove", []))

        if remove_indices:
            new_ranges = [r for i, r in enumerate(suggestion.time_ranges) if i not in remove_indices]
            if new_ranges:
                old_dur = suggestion.total_duration
                suggestion.time_ranges = new_ranges
                suggestion.total_duration = sum(e - s for s, e in new_ranges)
                logger.info(
                    f"  中間カット: {old_dur:.0f}s→{suggestion.total_duration:.0f}s "
                    f"({len(remove_indices)}クリップ削除) reason: {result.get('reason','')}"
                )
                return

    except Exception as e:
        logger.warning(f"中間カット判定失敗: {e}")

    # フォールバック: 末尾削除
    while suggestion.total_duration > max_duration and len(suggestion.time_ranges) > 1:
        suggestion.time_ranges = suggestion.time_ranges[:-1]
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)


def _extend_range_backward(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    gateway: ClipSuggestionGatewayInterface | None = None,
    max_segments: int = 8,
) -> bool:
    """冒頭の前のセグメントを追加して文脈を補完する。

    前のセグメントの中から、この話題の文脈に必要なものだけをAIに選ばせる。
    前の話題のセグメントは追加しない。
    """
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

    import json
    try:
        cand_desc = "\n".join(
            f"[{i}] ({seg.start:.0f}s) {seg.text}"
            for i, seg in enumerate(candidates)
        )

        prompt = f"""ショート動画「{suggestion.title}」の冒頭に文脈が足りません。
現在の冒頭: 「{current_start}」

以下は現在の冒頭の前にあるセグメントです。
この話題の文脈を理解するために必要なセグメントだけを選んでください。
**前の別の話題のセグメントは選ばないでください。**

候補セグメント:
{cand_desc}

JSON: {{"include": [含めるべきセグメントのindex番号], "reason": "理由"}}
全部不要なら {{"include": [], "reason": "理由"}}"""

        response = gateway.client.chat.completions.create(
            model=gateway.model,
            messages=[
                {"role": "system", "content": "動画編集の文脈判断担当。JSON形式で回答。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        include_indices = result.get("include", [])

        if include_indices:
            prepend = [
                (candidates[i].start, candidates[i].end)
                for i in include_indices
                if 0 <= i < len(candidates)
            ]
            if prepend:
                suggestion.time_ranges = prepend + suggestion.time_ranges
                suggestion.total_duration = sum(
                    e - s for s, e in suggestion.time_ranges
                )
                logger.info(
                    f"  前方延長: {len(prepend)}セグメント追加 "
                    f"reason: {result.get('reason','')}"
                )
                return True

    except Exception as e:
        logger.warning(f"前方延長AI判定失敗: {e}")

    return False


def _extend_range(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    target_duration: float,
) -> bool:
    """トピック範囲外の隣接セグメントを追加して延長する。

    time_rangesの末尾ではなく、全time_rangesの最大endの後にある
    セグメントを探す（フィラー削除で細かく分割されていても正しく延長できる）。
    """
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
        if added_count >= 15:
            break

        suggestion.time_ranges.append((seg.start, seg.end))
        max_end = seg.end
        added = True
        added_count += 1
        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
        if suggestion.total_duration >= target_duration:
            break

    return added
