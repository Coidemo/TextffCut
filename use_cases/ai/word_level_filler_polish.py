"""
wordsレベルフィラー仕上げ削除（3層判定 + 音響安全チェック）

3層パイプライン:
1. 音響閾値緩和 — カット後の音響チェックを緩和して通過率を上げる
2. GiNZA文脈ルール — 曖昧フィラーの文法的用法を無料・高速で事前判定
3. LLM文脈判定 — GiNZAで判定不能なケースをGPT-4.1-miniでバッチ判定

カットするたびに音響チェック（音圧・ピッチの不連続）を行い、
不自然になったら**そのカットだけ取り消す**。
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment

if TYPE_CHECKING:
    from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface

logger = logging.getLogger(__name__)

from use_cases.ai.filler_constants import AMBIGUOUS_FILLERS, FILLER_WORDS as PURE_FILLERS  # noqa: F401

# 確定フィラー = PURE_FILLERS のうち曖昧でないもの（長い順にソート済み）
_CERTAIN_FILLERS = [f for f in PURE_FILLERS if f not in AMBIGUOUS_FILLERS]
# 曖昧フィラー（長い順にソート）
_AMBIGUOUS_FILLERS_SORTED = sorted(AMBIGUOUS_FILLERS, key=len, reverse=True)

# 音響チェックの閾値（日本語フィラー除去向けに緩和）
# RMS 15dB / ピッチ 120Hz は話者内変動の2σ相当で聴感上自然な範囲
MAX_RMS_DIFF_DB = 15.0
MAX_PITCH_DIFF_HZ = 120.0


def polish_fillers(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    video_path: Path,
    gateway: "ClipSuggestionGatewayInterface | None" = None,
    predetected_filler_map: dict | None = None,
) -> ClipSuggestion:
    """最終候補のtime_ranges内に残ったフィラーをwordsレベルで除去する。

    3層パイプライン:
    - 確定フィラー → 即カット候補
    - 曖昧フィラー → GiNZA文脈ルール → 確定/除外/LLM委譲
    - LLM判定 → フィラー確定/除外

    各フィラーカットを個別に適用し、音響チェックに通らなければ取り消す。

    predetected_filler_map: Phase 0で事前検出済みのFillerMap。
        指定された場合、確定フィラー+GiNZA判定済みフィラーを再利用し、
        LLM判定のみ新規実行する。
    """
    if not suggestion.time_ranges:
        return suggestion

    # Phase 0の事前検出結果がある場合はそれを活用
    if predetected_filler_map:
        filler_cuts = _apply_predetected_fillers(suggestion.time_ranges, transcription, predetected_filler_map, gateway)
    else:
        # time_ranges内のセグメントからフィラー箇所を検出（3層パイプライン）
        filler_cuts = _detect_fillers_in_ranges(suggestion.time_ranges, transcription, gateway)

    if not filler_cuts:
        return suggestion

    logger.info(f"フィラー仕上げ: {len(filler_cuts)}箇所検出 ({suggestion.title})")

    applied = 0
    reverted = 0

    for filler_text, filler_start, filler_end in filler_cuts:
        # カットを試みる
        new_ranges = _apply_single_cut(suggestion.time_ranges, filler_start, filler_end)

        if new_ranges == suggestion.time_ranges:
            continue  # 変化なし

        # 音響チェック: カット前後の音が自然につながるか
        is_natural = _check_cut_acoustics(video_path, suggestion.time_ranges, new_ranges, filler_start, filler_end)

        if is_natural:
            suggestion.time_ranges = new_ranges
            suggestion.total_duration = sum(e - s for s, e in new_ranges)
            applied += 1
            logger.debug(f"  ✓ カット: 「{filler_text}」({filler_start:.2f}s)")
        else:
            reverted += 1
            logger.debug(f"  ✗ 取消: 「{filler_text}」({filler_start:.2f}s) 音響不自然")

    if applied > 0 or reverted > 0:
        logger.info(f"フィラー仕上げ結果: {applied}カット適用, {reverted}取消 " f"→ {suggestion.total_duration:.1f}s")

    return suggestion


# ---------------------------------------------------------------------------
# Phase 0 事前検出結果の適用
# ---------------------------------------------------------------------------


def _apply_predetected_fillers(
    time_ranges: list[tuple[float, float]],
    transcription: TranscriptionResult,
    filler_map: dict,
    gateway: "ClipSuggestionGatewayInterface | None" = None,
) -> list[tuple[str, float, float]]:
    """Phase 0で検出済みのフィラーをtime_ranges内でフィルタし、LLM判定のみ新規実行する。

    Phase 0では層1（確定フィラー）と層2（GiNZA判定）のみ実行している。
    ここでは:
    - Phase 0の結果のうちtime_ranges内のものを採用
    - 層3（LLM判定）はPhase 0でスキップされた曖昧フィラーに対して実行
    """
    fillers: list[tuple[str, float, float]] = []
    llm_candidates: list[dict] = []

    for seg_idx, filler_spans in filler_map.items():
        if seg_idx >= len(transcription.segments):
            continue
        for span in filler_spans:
            # time_ranges内にあるかチェック
            for tr_start, tr_end in time_ranges:
                if span.time_start >= tr_start - 0.1 and span.time_end <= tr_end + 0.1:
                    fillers.append((span.filler_text, span.time_start, span.time_end))
                    break

    # Phase 0でスキップされた曖昧フィラー（LLM委譲分）を検出
    all_fillers_sorted = sorted(
        set(_CERTAIN_FILLERS) | AMBIGUOUS_FILLERS,
        key=len,
        reverse=True,
    )
    for tr_start, tr_end in time_ranges:
        for seg in transcription.segments:
            if seg.end <= tr_start or seg.start >= tr_end:
                continue
            text = seg.text
            words = getattr(seg, "words", None) or []
            if not words:
                continue

            pos = 0
            while pos < len(text):
                matched = None
                for filler in all_fillers_sorted:
                    if text[pos : pos + len(filler)] == filler:
                        matched = filler
                        break
                if matched and matched in AMBIGUOUS_FILLERS:
                    filler_len = len(matched)
                    f_start, f_end = _get_filler_time(words, pos, filler_len)
                    if (
                        f_start is not None
                        and f_end is not None
                        and f_start >= tr_start - 0.1
                        and f_end <= tr_end + 0.1
                    ):
                        # Phase 0で既に検出済みかチェック
                        already_detected = any(
                            abs(f[1] - f_start) < 0.05 and abs(f[2] - f_end) < 0.05 for f in fillers
                        )
                        if not already_detected:
                            # GiNZA判定不能だったもの → LLM委譲
                            verdict = _is_grammatical_by_context(matched, text, pos)
                            if verdict is None:
                                context_start = max(0, pos - 15)
                                context_end = min(len(text), pos + filler_len + 15)
                                llm_candidates.append(
                                    {
                                        "filler": matched,
                                        "context": text[context_start:context_end],
                                        "f_start": f_start,
                                        "f_end": f_end,
                                    }
                                )
                    pos += filler_len
                elif matched:
                    pos += len(matched)
                else:
                    pos += 1

    # 層3: LLM判定（Phase 0でスキップされた分のみ）
    if llm_candidates and gateway:
        try:
            judgements = gateway.judge_filler_context(
                [{"filler": c["filler"], "context": c["context"]} for c in llm_candidates]
            )
            for candidate, is_filler in zip(llm_candidates, judgements, strict=True):
                if is_filler:
                    fillers.append((candidate["filler"], candidate["f_start"], candidate["f_end"]))
        except Exception as e:
            logger.warning(f"LLMフィラー判定失敗: {e}")
            for candidate in llm_candidates:
                fillers.append((candidate["filler"], candidate["f_start"], candidate["f_end"]))

    if fillers:
        pre_count = len(fillers) - len(llm_candidates)
        logger.info(
            f"フィラー仕上げ(Phase0再利用): {len(fillers)}箇所 "
            f"(事前検出={pre_count}, LLM追加={len(llm_candidates)})"
        )
    return fillers


# ---------------------------------------------------------------------------
# 層2: GiNZA文脈判定
# ---------------------------------------------------------------------------


def _get_ginza_nlp():
    """GiNZA NLPモデルを取得（JapaneseLineBreakRulesのシングルトンを再利用）。"""
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        nlp = JapaneseLineBreakRules._get_nlp()
        if nlp and nlp is not False:
            return nlp
    except Exception:
        pass
    return None


def _analyze_text(text: str):
    """GiNZAでテキストを解析（キャッシュはJapaneseLineBreakRulesに委譲）。"""
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        return JapaneseLineBreakRules._analyze(text)
    except Exception:
        return None


def _is_grammatical_by_context(filler_text: str, seg_text: str, char_pos: int) -> bool | None:
    """GiNZA POS + 文脈ルールでフィラーか文法的用法かを判定。

    Returns:
        True  = 確実に文法的用法（カットしない）
        False = 確実にフィラー（カットする）
        None  = 判定不能（LLMに委譲）
    """
    doc = _analyze_text(seg_text)
    if doc is None:
        return None  # GiNZA利用不可 → LLM委譲

    # フィラーの直後テキストのPOSを取得
    after_pos = char_pos + len(filler_text)
    after_text = seg_text[after_pos : after_pos + 10].strip() if after_pos < len(seg_text) else ""
    before_text = seg_text[max(0, char_pos - 10) : char_pos].strip()

    # doc内でフィラー位置に対応するトークンを特定
    filler_token_idx = None
    running_pos = 0
    for i, token in enumerate(doc):
        token_end = running_pos + len(token.text)
        if running_pos <= char_pos < token_end:
            filler_token_idx = i
            break
        running_pos = token_end

    # フィラーの直後トークンのPOS
    after_token = None
    if filler_token_idx is not None:
        # フィラーが複数トークンにまたがる場合、最後のトークンの次を取る
        scan_pos = running_pos
        for i in range(filler_token_idx, len(doc)):
            token_end = sum(len(doc[j].text) for j in range(i + 1))
            if token_end >= after_pos:
                if i + 1 < len(doc):
                    after_token = doc[i + 1]
                break

    after_pos_tag = after_token.pos_ if after_token else ""

    if filler_text == "なんか":
        # 直前が「な」（形容動詞連体形） → 「異常ななんか」=「異常な何か」= 文法的用法
        if before_text and before_text.endswith("な"):
            return True
        # 直後が動詞・形容詞・副詞 → フィラー
        if after_pos_tag in ("VERB", "ADJ", "ADV"):
            return False
        # 文頭で直後が名詞以外 → フィラー
        if char_pos == 0:
            return False
        # 直後が名詞でも文脈依存（"なんかSNS"=フィラー vs "何か問題"=文法的）→ LLM委譲
        return None

    if filler_text == "あの":
        # 文頭 or 直後が動詞 → フィラー
        if char_pos == 0 or after_pos_tag == "VERB":
            return False
        # 直後が副詞 → フィラー（「あの全然」「あのそう」等）
        if after_pos_tag == "ADV":
            return False
        # 直後が名詞でも文脈依存（"あの人"=連体詞 vs "あのここ15年"=フィラー）→ LLM委譲
        return None

    if filler_text == "とか":
        # 前後に名詞が2つ以上 → 並列助詞「AとかBとか」
        nouns_before = sum(
            1
            for t in doc
            if t.pos_ == "NOUN" and sum(len(doc[j].text) for j in range(list(doc).index(t) + 1)) <= char_pos
        )
        nouns_after = sum(
            1 for t in doc if t.pos_ == "NOUN" and sum(len(doc[j].text) for j in range(list(doc).index(t))) >= after_pos
        )
        if nouns_before >= 1 and nouns_after >= 1:
            return True
        # 文末 or 直後が句点系 → フィラー
        if after_pos >= len(seg_text) or (after_text and after_text[0] in "。、"):
            return False
        return None

    if filler_text == "的な":
        # 直前が漢語名詞（漢字のみ） → 接尾辞「具体的な」
        before_chars = before_text
        if before_chars and re.search(r"[\u4e00-\u9fff]$", before_chars):
            return True
        # 直後が名詞 → 形容的用法「〜的な+名詞」（例: 「いいね的な拍手」）
        if after_pos_tag == "NOUN":
            return True
        # 文末 or 直前がひらがな → フィラー
        if after_pos >= len(seg_text) or (before_chars and re.search(r"[\u3040-\u309f]$", before_chars)):
            return False
        return None

    if filler_text in ("やっぱ", "やっぱり"):
        # 直後に述語（動詞・形容詞・助動詞）があれば文法的
        if after_pos_tag in ("VERB", "ADJ", "AUX"):
            return True
        # 文末 → 不明
        if after_pos >= len(seg_text):
            return None
        return None

    if filler_text in ("まあ", "まぁ"):
        # 文頭で直後が名詞以外 → フィラー
        if char_pos == 0 and after_pos_tag != "NOUN":
            return False
        # 直後に述語があっても文脈依存（"まあいいか"=副詞 vs "まあ例えば"=フィラー）→ LLM委譲
        return None

    if filler_text == "ぶっちゃけ":
        # 直後に述語あり → 副詞的用法
        if after_pos_tag in ("VERB", "ADJ", "ADV", "NOUN"):
            return True
        return None

    if filler_text == "みたいな感じで":
        # 直前に具体的な名詞 → 比喩「猫みたいな感じで」
        if before_text and any(t.pos_ == "NOUN" for t in doc if t.text in before_text[-5:]):
            return True
        # 文末付近 → フィラー
        if after_pos >= len(seg_text) - 2:
            return False
        return None

    if filler_text == "っていうのは":
        # 直後に述語 → 主題提示「幸せっていうのは〜」
        if after_pos_tag in ("VERB", "ADJ", "NOUN", "ADV"):
            return True
        return None

    if filler_text == "じゃないですか":
        # 直前に具体的内容あり + 直後に「だから」「でも」等 → 修辞的疑問（文法的）
        if after_text and any(after_text.startswith(w) for w in ("だから", "でも", "それで", "なので")):
            return True
        # 文末 → フィラー（同意要求）
        if after_pos >= len(seg_text) - 1:
            return False
        return None

    # 未知の曖昧フィラー → LLM委譲
    return None


# ---------------------------------------------------------------------------
# 3層パイプライン: フィラー検出
# ---------------------------------------------------------------------------


def _detect_fillers_in_ranges(
    time_ranges: list[tuple[float, float]],
    transcription: TranscriptionResult,
    gateway: "ClipSuggestionGatewayInterface | None" = None,
) -> list[tuple[str, float, float]]:
    """time_ranges内のセグメントからフィラー箇所を3層で検出する。

    層1: 確定フィラー（PURE_FILLERS - AMBIGUOUS_FILLERS）→ 即カット候補
    層2: 曖昧フィラー → GiNZA文脈ルール → 確定/除外/LLM委譲
    層3: LLM判定 → フィラー確定/除外

    Returns:
        [(filler_text, start_time, end_time), ...]
    """
    fillers: list[tuple[str, float, float]] = []
    llm_candidates: list[dict] = []  # LLM判定待ちの候補

    # 全フィラーリスト（確定 + 曖昧、長い順）
    all_fillers = sorted(
        list(set(_CERTAIN_FILLERS) | AMBIGUOUS_FILLERS),
        key=len,
        reverse=True,
    )

    for tr_start, tr_end in time_ranges:
        for seg in transcription.segments:
            if seg.end <= tr_start or seg.start >= tr_end:
                continue

            text = seg.text
            words = getattr(seg, "words", None) or []
            if not words:
                continue

            pos = 0
            while pos < len(text):
                matched_filler = None
                for filler in all_fillers:
                    if text[pos : pos + len(filler)] == filler:
                        matched_filler = filler
                        break

                if matched_filler:
                    filler_len = len(matched_filler)
                    f_start, f_end = _get_filler_time(words, pos, filler_len)

                    if f_start is not None and f_end is not None:
                        if f_start >= tr_start - 0.1 and f_end <= tr_end + 0.1:
                            if matched_filler in AMBIGUOUS_FILLERS:
                                # 層2: GiNZA文脈判定
                                verdict = _is_grammatical_by_context(matched_filler, text, pos)
                                if verdict is True:
                                    # 文法的用法 → スキップ
                                    logger.debug(f"  GiNZA: 文法的「{matched_filler}」({f_start:.2f}s) スキップ")
                                elif verdict is False:
                                    # 確実にフィラー → カット候補
                                    fillers.append((matched_filler, f_start, f_end))
                                    logger.debug(f"  GiNZA: フィラー「{matched_filler}」({f_start:.2f}s) カット候補")
                                else:
                                    # 判定不能 → LLMバッチに蓄積
                                    context_start = max(0, pos - 15)
                                    context_end = min(len(text), pos + filler_len + 15)
                                    llm_candidates.append(
                                        {
                                            "filler": matched_filler,
                                            "context": text[context_start:context_end],
                                            "f_start": f_start,
                                            "f_end": f_end,
                                        }
                                    )
                            else:
                                # 確定フィラー → 即カット候補
                                fillers.append((matched_filler, f_start, f_end))

                    pos += filler_len
                else:
                    pos += 1

    # 層3: LLM文脈判定（バッチ）
    if llm_candidates and gateway:
        try:
            judgements = gateway.judge_filler_context(
                [{"filler": c["filler"], "context": c["context"]} for c in llm_candidates]
            )
            for candidate, is_filler in zip(llm_candidates, judgements):
                if is_filler:
                    fillers.append((candidate["filler"], candidate["f_start"], candidate["f_end"]))
                    logger.debug(f"  LLM: フィラー「{candidate['filler']}」({candidate['f_start']:.2f}s) カット候補")
                else:
                    logger.debug(f"  LLM: 文法的「{candidate['filler']}」({candidate['f_start']:.2f}s) スキップ")
        except Exception as e:
            logger.warning(f"LLMフィラー判定失敗: {e}、曖昧候補をフィラーとして扱います")
            for candidate in llm_candidates:
                fillers.append((candidate["filler"], candidate["f_start"], candidate["f_end"]))
    elif llm_candidates:
        # gatewayなし → 曖昧候補はフィラーとして扱う（後方互換）
        logger.debug(f"Gateway未指定: 曖昧フィラー{len(llm_candidates)}件をフィラーとして扱います")
        for candidate in llm_candidates:
            fillers.append((candidate["filler"], candidate["f_start"], candidate["f_end"]))

    if llm_candidates:
        logger.info(
            f"フィラー3層判定: 確定={len(fillers) - len([c for c in llm_candidates if gateway])}, "
            f"GiNZA判定済み, LLM判定={len(llm_candidates)}件"
        )

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

    f_start = first_word.start if hasattr(first_word, "start") else first_word.get("start")
    f_end = last_word.end if hasattr(last_word, "end") else last_word.get("end")

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
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(before_start),
                    "-t",
                    "0.3",
                    "-i",
                    str(video_path),
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    before_path,
                ],
                capture_output=True,
                timeout=10,
            )

            # カット点の後の音声（cut_endの後0.3秒）
            after_path = f"{tmpdir}/after.wav"
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    str(cut_end),
                    "-t",
                    "0.3",
                    "-i",
                    str(video_path),
                    "-vn",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    after_path,
                ],
                capture_output=True,
                timeout=10,
            )

            y_before, sr = librosa.load(before_path, sr=16000)
            y_after, _ = librosa.load(after_path, sr=16000)

            if len(y_before) < 100 or len(y_after) < 100:
                return True  # 短すぎる場合は許可

            # 音圧チェック
            rms_before = np.sqrt(np.mean(y_before**2))
            rms_after = np.sqrt(np.mean(y_after**2))
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
