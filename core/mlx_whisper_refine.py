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
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


# --- Hallucination 検出閾値 ---
# 短い segment (<15 chars) は「はい」「うん」等の自然な短発話の可能性が高いので判定対象外。
# Whisper 内部で反復 hallucination に陥ると、30秒ウィンドウが「まあまあ…」×100 超のような
# 長大な繰り返しテキストで埋まるため、15 文字閾値でこれを十分拾える。
HALLUCINATION_MIN_CHARS = 15
# 最頻 bigram が全 bigram の 40% 超を占めれば明らかに異常反復。
# 実測では「まあ」×221 のような極端なケースで最頻 bigram 比率は ~99%。
HALLUCINATION_BIGRAM_RATIO = 0.40
# gzip 圧縮比が 4.0 超 = 同じパターンが繰り返されている強い指標 (通常の日本語文は ~2.0)。
HALLUCINATION_COMPRESSION_RATIO = 4.0

# --- 境界重複 dedup の閾値 ---
# Whisper の 30 秒ウィンドウ境界を跨いだ重複は end ≈ start なので、0.1s 以内の近接は
# 自然な発話 (通常はマイクロ pause が挟まる) と区別できる。
BOUNDARY_TOUCH_SEC = 0.1
# edited.json の 58 候補分析で、suffix-prefix 一致 ≥ 7 文字のケースは全て真の境界跨ぎ重複、
# 5-6 文字のケースは自然な発話の反復 (e.g. 「〜というのが」の連続発話) 混在。
# 7 文字を閾値にすると Type B 検出率を保ちつつ Type C 誤検出 0 を達成。
BOUNDARY_MATCH_MIN_CHARS = 7


# --- Silero VAD 前処理の閾値 (WhisperX "VAD Cut & Merge" 相当) ---
# 300ms 以上の silence を区間境界として採用。短すぎると発話間のマイクロ pause を過剰分割する。
_VAD_MIN_SILENCE_MS = 300
# 100ms 未満の speech は誤検出の可能性が高いのでまとめる。
_VAD_MIN_SPEECH_MS = 100
# Whisper の 30 秒ウィンドウに収まるよう chunk をマージする最大秒数。
# 30 秒ちょうどより少し短め (28s) にして余裕を持たせる。
_VAD_MAX_CHUNK_SEC = 28.0
# chunk 境界で word が分断されないよう前後に付ける padding。
_VAD_CHUNK_PADDING_SEC = 0.2


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
    max_len は O(cap^2) の探索を抑えるためのキャップ。実測最大一致は 16 文字なので
    30 は十分な安全マージン。
    """
    cap = min(len(a_text), len(b_text), max_len)
    for n in range(cap, 0, -1):
        if b_text.startswith(a_text[-n:]):
            return n
    return 0


_LEADING_PUNCT_TO_STRIP = "、。　 "  # 全角カンマ・全角句点・全角スペース・半角スペース


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

    Note:
        forced-aligner 適用前の (text のみの) segments を想定している。
        aligner 適用後に呼ばれた場合、Type B の切り詰めで b.text と b.words/chars が
        不整合になるため、そのような segments が来たら AssertionError で弾く。
    """
    if len(segments) < 2:
        return list(segments)

    # aligner 後の segments には words/chars が付く (長さ > 0)。Type B 切り詰めで
    # text と同期できないため、このモジュールは aligner 前に呼ぶ前提。
    for idx, seg in enumerate(segments[:5]):  # 先頭 5 個だけサンプルチェック
        if seg.get("words") or seg.get("chars"):
            raise AssertionError(
                f"dedupe_boundary_overlaps は aligner 前の segments を想定。"
                f"segment[{idx}] に words/chars が既にある。"
            )

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
            # a の end を b.end まで延長。これにより連続した同一セグメント群
            # (「まあ/まあ/まあ/まあ…」) の 3 つ目以降も次イテレーションで
            # a と boundary-touch 判定でき、チェーン削除が正しく働く。
            if float(b["end"]) > float(a["end"]):
                a["end"] = float(b["end"])
            removed += 1
            continue

        # Case 2: suffix-prefix 一致 (Type B)
        match_len = _longest_suffix_prefix_match(a_text, b_text)
        if match_len >= min_match_chars:
            new_b = b_text[match_len:].lstrip(_LEADING_PUNCT_TO_STRIP)
            if not new_b:
                logger.info(
                    f"境界重複削除 [Type B empty] at {a['end']:.1f}s: "
                    f"'{a_text[-match_len:]}'"
                )
                if float(b["end"]) > float(a["end"]):
                    a["end"] = float(b["end"])
                removed += 1
                continue
            logger.info(
                f"境界重複切り詰め [Type B {match_len}] at {a['end']:.1f}s: "
                f"'{a_text[-match_len:]}' を b 冒頭から削除"
            )
            b["text"] = new_b
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

        # retry 自体が失敗してもパイプライン全体を落とさないように例外を握る。
        # 失敗した場合は元のセグメント (hallucination あり) を保持し、警告だけ残す。
        try:
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
        except Exception as exc:
            logger.warning(
                f"  retry 失敗 [{retry_start:.1f}-{retry_end:.1f}]s: {exc}. 元セグメントを保持"
            )
            continue

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

# ------------------------------------------------------------
# Silero VAD 前処理 (WhisperX "VAD Cut & Merge")
# ------------------------------------------------------------


def _vad_speech_ranges(audio_path: str) -> list[tuple[float, float]]:
    """Silero VAD で speech 区間を検出。戻り値は秒単位の (start, end) リスト。"""
    from silero_vad import get_speech_timestamps, load_silero_vad, read_audio

    model = load_silero_vad()
    audio = read_audio(audio_path, sampling_rate=16000)
    ranges = get_speech_timestamps(
        audio,
        model,
        sampling_rate=16000,
        return_seconds=True,
        min_silence_duration_ms=_VAD_MIN_SILENCE_MS,
        min_speech_duration_ms=_VAD_MIN_SPEECH_MS,
    )
    return [(r["start"], r["end"]) for r in ranges]


def _merge_vad_into_chunks(
    speech_ranges: list[tuple[float, float]],
    max_chunk_sec: float = _VAD_MAX_CHUNK_SEC,
) -> list[tuple[float, float]]:
    """speech 区間を max_chunk_sec 以下になるよう隣接ランをマージする。

    Whisper は 30 秒ウィンドウで内部処理するので、各 chunk を 30 秒以下に収める。
    短い speech 区間を詰めて chunk を作ることで chunk 数を減らし、呼び出し回数を削減。
    """
    if not speech_ranges:
        return []
    merged: list[list[float]] = [list(speech_ranges[0])]
    for s, e in speech_ranges[1:]:
        last = merged[-1]
        if e - last[0] <= max_chunk_sec:
            last[1] = e
        else:
            merged.append([s, e])
    return [(m[0], m[1]) for m in merged]


def _extract_audio_range(audio_path: str, start: float, end: float, out_path: str) -> None:
    """ffmpeg で音声ファイルの [start, end] を 16kHz mono WAV として抽出。"""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(start),
        "-i", audio_path,
        "-t", str(end - start),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        out_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def transcribe_refined(
    audio_path: str,
    model_path: str,
    language: str = "ja",
    initial_prompt: str | None = None,
    **mlx_kwargs: Any,
) -> dict[str, Any]:
    """Silero VAD cut → chunk 分割 → Whisper → 境界 dedup → hallucination retry。

    処理の流れ:
      1. Silero VAD で speech 区間検出
      2. max 28s の chunk にマージ (WhisperX VAD Cut & Merge 相当)
      3. 各 chunk に padding 0.2s を付けて個別に mlx_whisper.transcribe
      4. 元時刻に timestamp をオフセットして統合
      5. 境界重複 dedup + hallucination retry

    VAD 前処理により Whisper が「長無音を 1 segment に巻き込む」問題 (長 segment
    化 + 発話の認識漏れ) を構造的に防ぐ。

    VAD がライブラリ不在で失敗した場合は従来の一発 transcribe にフォールバック。

    Args:
        audio_path:     音声 / 動画ファイルパス
        model_path:     mlx_whisper が認識する model id または local path
        language:       言語コード
        initial_prompt: Whisper に渡す初期 prompt
        **mlx_kwargs:   mlx_whisper.transcribe に追加で渡したいパラメータ

    戻り値は mlx_whisper.transcribe 互換 ({"segments": [...], "language": "..."})。
    """
    import mlx_whisper

    # Step 1-2: VAD で speech 区間検出 → chunk マージ
    try:
        speech_ranges = _vad_speech_ranges(audio_path)
        chunks = _merge_vad_into_chunks(speech_ranges)
        logger.info(f"Silero VAD: {len(speech_ranges)} speech ranges → {len(chunks)} chunks")
    except Exception as e:
        logger.warning(f"Silero VAD 失敗、通常モードにフォールバック: {e}")
        chunks = []

    if not chunks:
        # フォールバック: VAD 不使用の従来動作
        logger.info("mlx_whisper.transcribe を実行 (通常モード)")
        result = mlx_whisper.transcribe(
            audio_path,
            path_or_hf_repo=model_path,
            language=language,
            initial_prompt=initial_prompt,
            **mlx_kwargs,
        )
        segments = list(result.get("segments", []))
    else:
        # Step 3-4: 各 chunk を個別 transcribe し、元時刻にオフセット
        segments = []
        with tempfile.TemporaryDirectory(prefix="vad_chunks_") as tmpdir:
            for i, (c_start, c_end) in enumerate(chunks):
                padded_start = max(0.0, c_start - _VAD_CHUNK_PADDING_SEC)
                padded_end = c_end + _VAD_CHUNK_PADDING_SEC
                chunk_wav = str(Path(tmpdir) / f"chunk_{i:03d}.wav")
                _extract_audio_range(audio_path, padded_start, padded_end, chunk_wav)

                logger.info(f"  chunk {i+1}/{len(chunks)}: {padded_start:.2f}-{padded_end:.2f}s")
                chunk_result = mlx_whisper.transcribe(
                    chunk_wav,
                    path_or_hf_repo=model_path,
                    language=language,
                    initial_prompt=initial_prompt,
                    **mlx_kwargs,
                )
                # 元音声の時刻にオフセット補正
                for seg in chunk_result.get("segments", []):
                    if not seg.get("text", "").strip():
                        continue
                    seg["start"] = float(seg["start"]) + padded_start
                    seg["end"] = float(seg["end"]) + padded_start
                    segments.append(seg)

    logger.info(f"  初期セグメント数: {len(segments)}")

    # Step 5a: 境界重複を削除
    segments = dedupe_boundary_overlaps(segments)

    # Step 5b: hallucination を検出して再試行 (元音声に対して実行)
    segments = retry_hallucinated_segments(
        audio_path=audio_path,
        model_path=model_path,
        segments=segments,
        language=language,
        initial_prompt=initial_prompt,
    )

    return {
        "segments": segments,
        "language": language,
    }
