"""
機械的クリップ編集エンジン

AIが指定した話題範囲に対して、原文のみを使用した編集パターンを生成する。
1. フィラー削除（正規表現）
2. 話題境界でのトリミングパターン生成
3. 品質スコア計算
"""

from __future__ import annotations

import logging
import re

from domain.entities.clip_suggestion import ClipVariant, TopicRange
from domain.entities.transcription import TranscriptionResult, TranscriptionSegment

logger = logging.getLogger(__name__)

# セグメント全体がフィラーのみかを判定する
# （これらのセグメントはtime_rangesから完全に除外される）
FILLER_ONLY_TEXTS = {
    "はい", "うん", "まあ", "あの", "で", "なんか", "えー", "えーと", "えっと",
    "うーん", "んー", "ね", "そう", "そうですね", "まあまあ", "ちょっと",
    "!", "っていう", "多分", "なので", "ただ", "別に", "普通に",
    "まあそうですね", "そうそう", "そうそうそう", "なるほど", "確かに",
    "なんかその", "あれなんですけれども", "なのでね",
}

# 純粋なフィラー（wordsタイムスタンプでスキップする対象）
# テキスト内の任意の位置でマッチさせる
# 長い順にマッチさせる（「まあまあ」→「まあ」の順）
FILLER_WORDS = sorted([
    "えーっと", "えっとね", "えっと", "えーと", "あのー", "まあまあ",
    "まあその", "まあね", "なんかその", "なんかこう", "なんか",
    "そうですね", "あのね",
    "えー", "あの", "まあ", "まぁ", "うーん", "んー",
    "でまあ", "でなんか", "であの", "でその",
    "やっぱ", "やっぱり",
], key=len, reverse=True)

# 注: 以前ここに含まれていた「冗長な接続・修飾」（「っていうのが」「みたいな」
# 「結構」「ちょっとした」等）は、文中でwordsレベルカットすると音声が
# 不自然に途切れるため削除。これらはセグメント単位のAI判定で対処する。

# 廃止: ハードコードパターンの代わりにAI判定を使用する（suggest_and_export.pyで実行）
# SKIP_SEGMENT_PATTERNS は削除済み


def generate_clip_variants(
    topic: TopicRange,
    transcription: TranscriptionResult,
    min_duration: float = 30.0,
    max_duration: float = 60.0,
) -> list[ClipVariant]:
    """話題範囲から複数のクリップパターンを機械的に生成する。

    Args:
        topic: AIが指定した話題範囲
        transcription: 文字起こし結果
        min_duration: 最小秒数
        max_duration: 最大秒数

    Returns:
        品質スコア降順のClipVariantリスト
    """
    segments = transcription.segments
    start_idx = topic.segment_start_index
    end_idx = topic.segment_end_index

    if start_idx < 0 or end_idx >= len(segments) or start_idx > end_idx:
        logger.warning(f"Invalid segment range [{start_idx}-{end_idx}]")
        return []

    scoped = segments[start_idx : end_idx + 1]

    # Step 1: フィラー削除してセグメントを分類
    cleaned_segments = _clean_segments(scoped)

    # Step 2: トリミングパターンを生成
    variants = []

    # パターンA: フルレンジ（フィラー削除のみ）
    full = _build_variant(topic.id, cleaned_segments, "フル版")
    if full:
        variants.append(full)

    # パターンB: 冒頭トリム（最初の挨拶/前置きを削除）
    trimmed_start = _trim_start(cleaned_segments)
    if trimmed_start and len(trimmed_start) < len(cleaned_segments):
        v = _build_variant(topic.id, trimmed_start, "冒頭トリム")
        if v:
            variants.append(v)

    # パターンC: 末尾トリム（締めの余談を削除）
    trimmed_end = _trim_end(cleaned_segments)
    if trimmed_end and len(trimmed_end) < len(cleaned_segments):
        v = _build_variant(topic.id, trimmed_end, "末尾トリム")
        if v:
            variants.append(v)

    # パターンD: 両端トリム
    if trimmed_start and trimmed_end:
        both_trimmed = _trim_end(_trim_start(cleaned_segments))
        if both_trimmed and len(both_trimmed) < len(cleaned_segments):
            v = _build_variant(topic.id, both_trimmed, "両端トリム")
            if v:
                variants.append(v)

    # パターンE: デュレーションフィット（max_durationに収まるようにカット）
    if full and full.total_duration > max_duration:
        fitted = _fit_duration(cleaned_segments, max_duration)
        if fitted:
            v = _build_variant(topic.id, fitted, f"デュレーションフィット({max_duration:.0f}秒)")
            if v:
                variants.append(v)

    # 重複除去（同じtime_rangesのバリアントを除去）
    variants = _deduplicate(variants)

    # 品質スコア計算
    for v in variants:
        v.quality_score = _calculate_quality_score(v, min_duration, max_duration)

    # スコア降順
    variants.sort(key=lambda v: v.quality_score, reverse=True)

    return variants


# --- Internal functions ---


def _clean_segments(
    segments: list[TranscriptionSegment],
) -> list[_CleanedSegment]:
    """セグメントにフィラー判定を付与する"""
    result = []
    for seg in segments:
        is_filler = _is_filler_only(seg.text)
        result.append(_CleanedSegment(original=seg, is_filler_only=is_filler))
    return result


class _CleanedSegment:
    """フィラー判定済みセグメント"""

    __slots__ = ("original", "is_filler_only")

    def __init__(self, original: TranscriptionSegment, is_filler_only: bool):
        self.original = original
        self.is_filler_only = is_filler_only

    @property
    def start(self) -> float:
        return self.original.start

    @property
    def end(self) -> float:
        return self.original.end

    @property
    def duration(self) -> float:
        return self.end - self.start


def _build_ranges_skipping_fillers(
    segment: TranscriptionSegment,
) -> list[tuple[float, float, str]]:
    """セグメント内のフィラーをwordsタイムスタンプでスキップし、
    残す部分のtime_rangesとテキストを返す。

    Returns:
        [(start, end, text), ...] フィラーをスキップした区間リスト
    """
    text = segment.text
    words = getattr(segment, 'words', None) or []

    if not words:
        return [(segment.start, segment.end, text)]

    # wordsから文字位置→時間のマッピングを構築
    # words は1文字ずつ: [{word: "あ", start: 0.1, end: 0.2}, ...]
    char_times: list[tuple[float, float]] = []  # (start, end) per character
    for w in words:
        w_start = w.start if hasattr(w, 'start') else w.get('start', 0)
        w_end = w.end if hasattr(w, 'end') else w.get('end', 0)
        w_text = w.word if hasattr(w, 'word') else w.get('word', '')
        for _ in w_text:
            char_times.append((w_start, w_end))

    if len(char_times) != len(text):
        # words とテキストの長さが合わない場合はフォールバック
        return [(segment.start, segment.end, text)]

    # テキスト内のフィラー位置を検出
    filler_chars = set()  # フィラーに該当する文字インデックス
    pos = 0
    while pos < len(text):
        matched = False
        for filler in FILLER_WORDS:
            if text[pos:pos + len(filler)] == filler:
                for j in range(pos, pos + len(filler)):
                    filler_chars.add(j)
                pos += len(filler)
                matched = True
                break
        if not matched:
            pos += 1

    if not filler_chars:
        return [(segment.start, segment.end, text)]

    # フィラーでない連続区間を抽出
    ranges = []
    in_keep = False
    range_start = 0.0
    range_text = []

    for i in range(len(text)):
        if i not in filler_chars:
            if not in_keep:
                range_start = char_times[i][0]
                in_keep = True
            range_text.append(text[i])
        else:
            if in_keep:
                range_end = char_times[i - 1][1]
                ranges.append((range_start, range_end, "".join(range_text)))
                range_text = []
                in_keep = False

    if in_keep:
        range_end = char_times[len(text) - 1][1]
        ranges.append((range_start, range_end, "".join(range_text)))

    return ranges if ranges else [(segment.start, segment.end, text)]


def _is_filler_only(text: str) -> bool:
    """セグメント全体が純粋なフィラーかを判定する。
    文脈依存の判定（独り言・前置き等）はAI判定に任せる。
    """
    text = text.strip()
    if not text:
        return True
    return text in FILLER_ONLY_TEXTS


def _build_variant(
    topic_id: str,
    segments: list[_CleanedSegment],
    label: str,
) -> ClipVariant | None:
    """セグメントリストからClipVariantを構築する"""
    # フィラーのみのセグメントを除外し、残りのセグメントでは
    # wordsレベルでフィラーをスキップしたtime_rangesを構築
    time_ranges = []
    texts = []
    for seg in segments:
        if seg.is_filler_only:
            continue
        for rng_start, rng_end, rng_text in _build_ranges_skipping_fillers(seg.original):
            if rng_start < rng_end and rng_text.strip():
                time_ranges.append((rng_start, rng_end))
                texts.append(rng_text)

    if not time_ranges:
        return None

    # 隣接するtime_rangesをマージ（0.5秒以内のギャップ）
    merged = _merge_time_ranges(time_ranges, max_gap=0.5)

    return ClipVariant.create(
        topic_id=topic_id,
        text="".join(texts),
        time_ranges=merged,
        label=label,
    )


def _merge_time_ranges(
    ranges: list[tuple[float, float]], max_gap: float = 0.5
) -> list[tuple[float, float]]:
    """近接するtime_rangesをマージする"""
    if not ranges:
        return []
    merged = [ranges[0]]
    for start, end in ranges[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= max_gap:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def _trim_start(segments: list[_CleanedSegment]) -> list[_CleanedSegment]:
    """冒頭の挨拶・前置きセグメントを削除する"""
    # 最初の数セグメントが短い挨拶の場合はカット
    start_patterns = {"はい", "おはようございます", "こんにちは", "どうも", "はいここから本編です"}
    trim_count = 0
    for seg in segments:
        text = seg.original.text.strip()
        if text in start_patterns or seg.is_filler_only or len(text) <= 5:
            trim_count += 1
        else:
            break

    if trim_count > 0 and trim_count < len(segments):
        return segments[trim_count:]
    return segments


def _trim_end(segments: list[_CleanedSegment]) -> list[_CleanedSegment]:
    """末尾の余談・締めセグメントを削除する"""
    end_patterns = {"はい", "ありがとうございます", "以上です", "次の話題"}
    trim_count = 0
    for seg in reversed(segments):
        text = seg.original.text.strip()
        if text in end_patterns or seg.is_filler_only or len(text) <= 3:
            trim_count += 1
        else:
            break

    if trim_count > 0 and trim_count < len(segments):
        return segments[: len(segments) - trim_count]
    return segments


def _fit_duration(
    segments: list[_CleanedSegment], max_duration: float
) -> list[_CleanedSegment]:
    """max_durationに収まるようにセグメントを前から選択する"""
    result = []
    total = 0.0
    for seg in segments:
        if seg.is_filler_only:
            continue
        seg_dur = seg.duration
        if total + seg_dur > max_duration:
            break
        result.append(seg)
        total += seg_dur
    return result if result else None


def _deduplicate(variants: list[ClipVariant]) -> list[ClipVariant]:
    """同じtime_rangesのバリアントを除去する"""
    seen = set()
    result = []
    for v in variants:
        key = tuple(v.time_ranges)
        if key not in seen:
            seen.add(key)
            result.append(v)
    return result


def _calculate_quality_score(
    variant: ClipVariant,
    min_duration: float,
    max_duration: float,
) -> float:
    """クリップの機械的な品質スコアを計算する（0-100）"""
    score = 50.0  # ベーススコア

    # デュレーションが範囲内かどうか（最大±20点）
    if min_duration <= variant.total_duration <= max_duration:
        # 範囲内 → ボーナス
        # 中央値に近いほど高スコア
        center = (min_duration + max_duration) / 2
        deviation = abs(variant.total_duration - center) / center
        score += 20.0 * (1.0 - deviation)
    elif variant.total_duration < min_duration:
        ratio = variant.total_duration / min_duration
        score -= 20.0 * (1.0 - ratio)
    else:
        ratio = max_duration / variant.total_duration
        score -= 20.0 * (1.0 - ratio)

    # テキスト密度（フィラー除去後の文字数 / 秒）
    if variant.total_duration > 0:
        density = len(variant.text) / variant.total_duration
        # 5-7文字/秒が理想
        if 5.0 <= density <= 7.0:
            score += 10.0
        elif 3.0 <= density <= 9.0:
            score += 5.0

    # time_rangesの数（少ないほど自然 — 連続した映像が良い）
    num_ranges = len(variant.time_ranges)
    if num_ranges == 1:
        score += 10.0
    elif num_ranges <= 3:
        score += 5.0
    else:
        score -= 5.0

    # テキストの長さ（短すぎるのはダメ）
    if len(variant.text) < 50:
        score -= 20.0

    return max(0.0, min(100.0, score))
