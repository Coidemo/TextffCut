"""mlx_whisper 推論の後処理 (boundary dedup + hallucination retry)。

mlx_whisper.transcribe のデフォルト出力には 2 つの課題:
  1. 30 秒ウィンドウ境界で発話が跨ぐと両方のウィンドウに同じ単語が出る
     (boundary duplication)
  2. LoRA 適用時など一部条件で「まあまあまあ…」等の反復 hallucination が起きる

本モジュールは以下の流れで緩和する:
  A. まず通常の mlx_whisper.transcribe で全音声を 1 発推論 (セグメント粒度を保つため)
  B. 隣接 segment で境界跨ぎの重複パターンを検出して文字列レベルで dedup
  C. それでも残った hallucinated なセグメントだけ保守的設定で再 transcribe

sliding-window は検討したが、mlx_whisper は 30 秒ちょうどの入力に対して segment
分割が極端に粗くなる挙動 (1-2 segments/30s) だったため不採用。

base / LoRA 両モデルに適用して問題なし。
"""

from __future__ import annotations

import gzip
import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)


# Hallucination 検出閾値
HALLUCINATION_MIN_CHARS = 15
HALLUCINATION_BIGRAM_RATIO = 0.40
HALLUCINATION_COMPRESSION_RATIO = 4.0

# 境界重複 dedup の閾値
BOUNDARY_TOUCH_SEC = 0.1          # |a.end - b.start| がこれ以下なら「boundary touch」
BOUNDARY_MATCH_MIN_CHARS = 7      # suffix-prefix 一致が何文字以上で重複とみなすか


# ------------------------------------------------------------
# Hallucination 検出
# ------------------------------------------------------------

def _compression_ratio(text: str) -> float:
    encoded = text.encode("utf-8")
    if not encoded:
        return 0.0
    compressed = gzip.compress(encoded)
    return len(encoded) / max(len(compressed), 1)


def detect_hallucination(text: str) -> bool:
    """反復 hallucination かを判定。

    2 指標のどちらかが異常値なら True:
      - 連続 bigram の反復率 (最頻 bigram / 全 bigram 数)
      - gzip 圧縮比 (反復が多いと極端に圧縮が効く)
    """
    text = text.strip()
    if len(text) < HALLUCINATION_MIN_CHARS:
        return False
    bigrams = [text[i : i + 2] for i in range(len(text) - 1)]
    if bigrams:
        top_count = Counter(bigrams).most_common(1)[0][1]
        if top_count / len(bigrams) > HALLUCINATION_BIGRAM_RATIO:
            return True
    if _compression_ratio(text) > HALLUCINATION_COMPRESSION_RATIO:
        return True
    return False


# ------------------------------------------------------------
# 境界重複 dedup (Type A: 完全重複, Type B: 単語跨ぎ)
# ------------------------------------------------------------

def _longest_suffix_prefix_match(a_text: str, b_text: str, max_len: int = 30) -> int:
    """a の末尾が b の冒頭に完全一致する最長文字数を返す。

    戻り値は一致文字数 (0 なら一致なし)。
    """
    cap = min(len(a_text), len(b_text), max_len)
    for n in range(cap, 0, -1):
        if b_text.startswith(a_text[-n:]):
            return n
    return 0


def dedupe_boundary_overlaps(
    segments: list[dict],
    boundary_touch: float = BOUNDARY_TOUCH_SEC,
    min_match_chars: int = BOUNDARY_MATCH_MIN_CHARS,
) -> list[dict]:
    """隣接 segment 間で 30s ウィンドウ境界由来の重複を検出して削除/切り詰め。

    判定条件 (両方満たす):
      (i) boundary touch: |a.end - b.start| < boundary_touch (0.1s)
          → 自然な発話の繰り返しは通常 start に隙間があるので除外できる
      (ii) a.text == b.text OR suffix-prefix 一致 >= min_match_chars
           → Type A (完全一致) と Type B (単語跨ぎ) の両方を拾う

    処理:
      - Type A: b を削除 (a 側に timing を残す)
      - Type B: b の先頭を切り詰め
    """
    if len(segments) < 2:
        return list(segments)

    out: list[dict] = [dict(segments[0])]
    removed = 0
    trimmed = 0

    for b_orig in segments[1:]:
        a = out[-1]
        b = dict(b_orig)

        # boundary touch 判定
        if abs(float(a["end"]) - float(b["start"])) >= boundary_touch:
            out.append(b)
            continue

        a_text = a["text"].strip()
        b_text = b["text"].strip()

        # Case 1: 完全重複 (Type A)
        if a_text and a_text == b_text:
            logger.info(
                f"境界重複削除 [Type A full] at {a['end']:.1f}s: '{a_text[:30]}'"
            )
            removed += 1
            continue

        # Case 2: suffix-prefix 一致 (Type B)
        match_len = _longest_suffix_prefix_match(a_text, b_text)
        if match_len >= min_match_chars:
            new_b = b_text[match_len:].lstrip("、。 、 ")
            if not new_b:
                logger.info(
                    f"境界重複削除 [Type B empty] at {a['end']:.1f}s: "
                    f"'{a_text[-match_len:]}'"
                )
                removed += 1
                continue
            logger.info(
                f"境界重複切り詰め [Type B {match_len}] at {a['end']:.1f}s: "
                f"'{a_text[-match_len:]}' を b 冒頭から削除"
            )
            b["text"] = new_b
            # words/chars は forced-aligner 前なので (通常未設定) 文字列のみ補正
            trimmed += 1
            out.append(b)
        else:
            out.append(b)

    logger.info(
        f"境界重複 dedup: {removed} 削除 + {trimmed} 切り詰め, "
        f"{len(out)} 残 (元 {len(segments)})"
    )
    return out


# ------------------------------------------------------------
# Hallucination retry
# ------------------------------------------------------------

def retry_hallucinated_segments(
    audio_path: str,
    model_path: str,
    segments: list[dict],
    language: str = "ja",
    initial_prompt: str | None = None,
    buffer: float = 1.0,
    sample_rate: int = 16000,
) -> list[dict]:
    """hallucination 判定された範囲を保守的設定で再 transcribe。

    保守的設定:
      - condition_on_previous_text=False (反復ループの主因)
      - compression_ratio_threshold=1.6 (厳しめで温度フォールバック促進)
      - temperature=(0.2, 0.4, 0.6, 0.8) (多様化)

    再試行後も hallucination 判定なら元セグメントを保持する (悪化防止)。
    """
    import librosa
    import mlx_whisper

    bad_indices = [i for i, s in enumerate(segments) if detect_hallucination(s.get("text", ""))]
    if not bad_indices:
        return segments

    logger.info(f"hallucination 検出: {len(bad_indices)} / {len(segments)} セグメント")

    # 近接 bad ranges をマージ (間隔 2 秒以内なら 1 つの retry 範囲に)
    merged: list[tuple[float, float, list[int]]] = []
    for idx in bad_indices:
        s = segments[idx]
        s_start = float(s["start"])
        s_end = float(s["end"])
        if merged and s_start - merged[-1][1] <= 2.0:
            prev_start, prev_end, prev_idx = merged[-1]
            merged[-1] = (prev_start, max(prev_end, s_end), prev_idx + [idx])
        else:
            merged.append((s_start, s_end, [idx]))

    audio_full, sr = librosa.load(audio_path, sr=sample_rate, mono=True)

    indices_to_drop: set[int] = set()
    replacements: list[tuple[int, list[dict]]] = []

    for r_start, r_end, r_indices in merged:
        retry_start = max(0.0, r_start - buffer)
        retry_end = r_end + buffer
        logger.info(
            f"  retry [{retry_start:.1f}-{retry_end:.1f}]s "
            f"(元セグメント {len(r_indices)} 個)"
        )
        start_sample = int(retry_start * sr)
        end_sample = int(retry_end * sr)
        audio_slice = audio_full[start_sample:end_sample]

        retry_result = mlx_whisper.transcribe(
            audio_slice,
            path_or_hf_repo=model_path,
            language=language,
            initial_prompt=initial_prompt,
            condition_on_previous_text=False,
            compression_ratio_threshold=1.6,
            temperature=(0.2, 0.4, 0.6, 0.8),
            verbose=False,
        )
        retry_segs: list[dict] = []
        for seg in retry_result.get("segments", []):
            seg = dict(seg)
            seg["start"] = float(seg["start"]) + retry_start
            seg["end"] = float(seg["end"]) + retry_start
            for key in ("words", "chars"):
                if key in seg and seg[key]:
                    seg[key] = [
                        {**w, "start": float(w["start"]) + retry_start, "end": float(w["end"]) + retry_start}
                        for w in seg[key]
                    ]
            retry_segs.append(seg)

        still_bad = any(detect_hallucination(s.get("text", "")) for s in retry_segs)
        if still_bad or not retry_segs:
            logger.info("  retry 後も hallucination → 元セグメントを保持")
            continue
        indices_to_drop.update(r_indices)
        replacements.append((r_indices[0], retry_segs))

    rebuilt: list[dict] = []
    insert_map: dict[int, list[dict]] = {idx: segs for idx, segs in replacements}
    for i, seg in enumerate(segments):
        if i in insert_map:
            rebuilt.extend(insert_map[i])
        if i not in indices_to_drop:
            rebuilt.append(seg)
    return rebuilt


# ------------------------------------------------------------
# メインエントリ
# ------------------------------------------------------------

def transcribe_refined(
    audio_path: str,
    model_path: str,
    language: str = "ja",
    initial_prompt: str | None = None,
) -> dict[str, Any]:
    """通常 transcribe → 境界 dedup → hallucination retry の一連を実行。

    戻り値は mlx_whisper.transcribe 互換 ({"segments": [...], "language": "..."})。
    """
    import mlx_whisper

    logger.info("mlx_whisper.transcribe を実行 (通常モード)")
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=model_path,
        language=language,
        initial_prompt=initial_prompt,
    )
    segments = list(result.get("segments", []))
    logger.info(f"  初期セグメント数: {len(segments)}")

    # 境界重複を削除
    segments = dedupe_boundary_overlaps(segments)

    # hallucination を検出して再試行
    segments = retry_hallucinated_segments(
        audio_path=audio_path,
        model_path=model_path,
        segments=segments,
        language=language,
        initial_prompt=initial_prompt,
    )

    return {
        "segments": segments,
        "language": result.get("language", language),
    }
