"""
Phase 3.5: 吃音（言い淀み）除去

AI選定後のクリップに残る「ない人はない人はない人は」のような
連続反復パターンを検出し、最後の1回だけ残して除去する。
wordsレベルのタイムスタンプを使ってtime_rangesを再構築する。
"""

from __future__ import annotations

import logging

from domain.entities.transcription import TranscriptionSegment
from use_cases.ai.early_filler_detection import expand_words_to_chars

logger = logging.getLogger(__name__)

# 連続とみなすギャップ閾値（秒）
_GAP_MERGE_THRESHOLD = 0.5

# 日本語の畳語（正当な反復語）— 吃音として誤検出しない
_REDUPLICATION_WORDS: frozenset[str] = frozenset(
    {
        # 副詞系
        "たまたま",
        "いろいろ",
        "だんだん",
        "ますます",
        "わざわざ",
        "ときどき",
        "なかなか",
        "そろそろ",
        "どんどん",
        "もともと",
        "じわじわ",
        "めきめき",
        "ぎりぎり",
        "ころころ",
        "ずるずる",
        "ぼちぼち",
        "こつこつ",
        # オノマトペ系
        "ばらばら",
        "ぼろぼろ",
        "めちゃめちゃ",
        "ぐちゃぐちゃ",
        "ごちゃごちゃ",
        "ばたばた",
        "がたがた",
        "べたべた",
        "きらきら",
        "ふわふわ",
        "ぐるぐる",
        "ぱらぱら",
        "にこにこ",
        "はらはら",
        "ぴかぴか",
        "ぽつぽつ",
        "ぞくぞく",
        "びくびく",
        "のろのろ",
        "さらさら",
        "すべすべ",
        "ぬるぬる",
        "へとへと",
        "ぺらぺら",
        "もやもや",
        "よちよち",
        "むらむら",
        "わくわく",
        "どきどき",
        "うろうろ",
        "おろおろ",
        "だらだら",
        "ぐだぐだ",
        "ぶつぶつ",
        "くどくど",
        "ぐずぐず",
        "のびのび",
        "うじうじ",
        "しぶしぶ",
        "つくづく",
        "ぞろぞろ",
        "めそめそ",
        "いちいち",
        # カタカナ系
        "バラバラ",
        "ボロボロ",
        "メチャメチャ",
        "グチャグチャ",
        "ゴチャゴチャ",
        "バタバタ",
        "ガタガタ",
        "ベタベタ",
        "キラキラ",
        "フワフワ",
        "グルグル",
        "パラパラ",
        "ニコニコ",
        "ハラハラ",
        "ピカピカ",
        "ポツポツ",
        "ドンドン",
        "ギリギリ",
        "ヌルヌル",
        "ペラペラ",
        # 応答・呼びかけ系
        "まあまあ",
        "もしもし",
        "はいはい",
        "いやいや",
        "ねえねえ",
        "おいおい",
        "なになに",
        # カタカナ追加
        "ゾクゾク",
        "ビクビク",
        "ノロノロ",
        "サラサラ",
        "スベスベ",
        "ヘトヘト",
        "モヤモヤ",
        "ヨチヨチ",
        "ムラムラ",
        "コロコロ",
        "ズルズル",
        "ボチボチ",
        "コツコツ",
        "ジワジワ",
        "メキメキ",
        "ワクワク",
        "ドキドキ",
        "ウロウロ",
        "オロオロ",
        "ダラダラ",
        "グダグダ",
        "ブツブツ",
        "クドクド",
        "グズグズ",
        "ノビノビ",
        "ウジウジ",
        "シブシブ",
        "ツクヅク",
        "ゾロゾロ",
        "メソメソ",
        "イチイチ",
    }
)


def remove_stammering(
    text: str,
    segments: list[TranscriptionSegment],
    time_ranges: list[tuple[float, float]],
) -> tuple[str, list[tuple[float, float]], float]:
    """吃音（連続反復パターン）を検出・除去する。

    Args:
        text: クリップのテキスト
        segments: 対応するTranscriptionSegmentリスト
        time_ranges: クリップの時間範囲リスト

    Returns:
        (cleaned_text, cleaned_time_ranges, cleaned_duration)
        char_timesを構築できない場合は入力をそのまま返す
    """
    # Step 1: segments[].words から文字単位の (start, end) 配列を構築
    char_times: list[tuple[float, float]] = []
    for seg in segments:
        words = seg.words or []
        expanded = expand_words_to_chars(words)
        seg_text = seg.text
        for i in range(len(seg_text)):
            if i < len(expanded):
                w = expanded[i]
                w_start = w.start if hasattr(w, "start") else w.get("start", 0.0)
                w_end = w.end if hasattr(w, "end") else w.get("end", 0.0)
                char_times.append((w_start, w_end))
            elif char_times:
                last_end = char_times[-1][1]
                char_times.append((last_end, last_end))

    # 長さ不一致なら入力をそのまま返す
    if len(char_times) != len(text):
        logger.warning(f"char_times長不一致（{len(char_times)} vs {len(text)}）、吃音除去をスキップ")
        total_dur = sum(e - s for s, e in time_ranges)
        return text, time_ranges, total_dur

    # Step 2: パターン長15→2の降順で走査、連続反復を検出
    keep = [True] * len(text)

    for pat_len in range(15, 1, -1):
        i = 0
        while i <= len(text) - pat_len:
            if not keep[i]:
                i += 1
                continue

            pattern = text[i : i + pat_len]
            # 同一パターンが何回連続するか数える
            count = 1
            j = i + pat_len
            while j + pat_len <= len(text) and text[j : j + pat_len] == pattern:
                count += 1
                j += pat_len

            if count >= 2:
                # 畳語チェック: パターン自体が畳語、またはパターン×2が畳語
                is_reduplication = pattern in _REDUPLICATION_WORDS or (pattern * 2) in _REDUPLICATION_WORDS
                if is_reduplication:
                    if count == 2:
                        # 畳語そのもの（例: "たまたま"）→ 正常、スキップ
                        i = j
                        continue
                    # 3回以上 → 畳語1回分（2回）だけ残す
                    remove_end = i + pat_len * (count - 2)
                    for k in range(i, remove_end):
                        keep[k] = False
                    logger.debug(f"吃音検出（畳語含み）: 「{pattern}」×{count}回 → 2回に縮約")
                    i = j
                else:
                    # 通常の吃音 → 最後の1回だけ残す
                    remove_end = i + pat_len * (count - 1)
                    for k in range(i, remove_end):
                        keep[k] = False
                    logger.debug(f"吃音検出: 「{pattern}」×{count}回 → 1回に縮約")
                    i = j
            else:
                i += 1

    # 変化なしなら早期リターン
    if all(keep):
        total_dur = sum(e - s for s, e in time_ranges)
        return text, time_ranges, total_dur

    # Step 3: 残った文字のchar_timesからtime_rangesを再構築
    cleaned_text = "".join(c for c, k in zip(text, keep) if k)
    kept_times = [t for t, k in zip(char_times, keep) if k]

    if not kept_times:
        total_dur = sum(e - s for s, e in time_ranges)
        return text, time_ranges, total_dur

    cleaned_ranges = _rebuild_time_ranges(kept_times)
    cleaned_dur = sum(e - s for s, e in cleaned_ranges)

    return cleaned_text, cleaned_ranges, cleaned_dur


def _rebuild_time_ranges(
    kept_times: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """残った文字のタイムスタンプからtime_rangesを再構築する。

    0.5秒以内のギャップはマージする。
    """
    if not kept_times:
        return []

    ranges: list[tuple[float, float]] = []
    current_start = kept_times[0][0]
    current_end = kept_times[0][1]

    for t_start, t_end in kept_times[1:]:
        if t_start - current_end <= _GAP_MERGE_THRESHOLD:
            current_end = max(current_end, t_end)
        else:
            ranges.append((current_start, current_end))
            current_start = t_start
            current_end = t_end

    ranges.append((current_start, current_end))
    return ranges
