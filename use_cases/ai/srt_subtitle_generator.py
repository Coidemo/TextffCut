"""
SRT字幕自動生成

Phase 1: 全テキストをDP探索で最小ブロックに分割（全単語境界）
Phase 2: 隣接ブロックをDPで結合して11文字以下の1行にまとめる
Phase 3: 隣接する1行を2行ブロックにまとめるかAIに判断させる
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from domain.entities.clip_suggestion import ClipSuggestion
from domain.entities.transcription import TranscriptionResult

logger = logging.getLogger(__name__)

DEFAULT_MAX_CHARS_PER_LINE = 11
DEFAULT_MAX_LINES = 2

# 事前並列化で文字起こし失敗を示すセンチネル値
_SRT_TRANSCRIPTION_FAILED: list[dict] = []


@dataclass
class TextBlock:
    text: str
    start_pos: int
    end_pos: int


@dataclass
class SRTEntry:
    index: int
    start_time: float
    end_time: float
    text: str


def generate_srt(
    suggestion: ClipSuggestion,
    transcription: TranscriptionResult,
    output_path: Path,
    video_path: Path | None = None,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
    speed: float = 1.0,
    precomputed_segments: list[dict] | None = None,
    api_key: str | None = None,
) -> Path | None:
    if not suggestion.time_ranges:
        return None

    # 元の文字起こしからpartsを構築（比較用）
    tmap = build_timeline_map(suggestion.time_ranges)
    original_parts = collect_parts(suggestion.time_ranges, tmap, transcription, speed=speed)

    # Whisper再文字起こし結果を取得
    whisper_segments = None
    if precomputed_segments is _SRT_TRANSCRIPTION_FAILED:
        whisper_segments = None  # 失敗済み
    elif precomputed_segments is not None:
        whisper_segments = precomputed_segments
    elif video_path:
        whisper_segments = _transcribe_output_audio(suggestion.time_ranges, video_path, api_key=api_key)

    # Phase 6a: Whisper再文字起こし vs 元文字起こしを比較
    if whisper_segments and original_parts:
        use_whisper = select_better_transcription(whisper_segments, original_parts)
        if use_whisper:
            logger.debug("SRT: Whisper再文字起こしを採用")
            return _generate_from_segments(whisper_segments, output_path, max_chars_per_line, max_lines)
        else:
            logger.debug("SRT: 元の文字起こしを採用（Whisperより高品質）")
    elif whisper_segments:
        # 元のpartsがない場合はWhisperを使用
        return _generate_from_segments(whisper_segments, output_path, max_chars_per_line, max_lines)

    # フォールバック / 元テキスト採用: 元の文字起こしを使用
    if not original_parts:
        return None

    full_text, char_times, seg_bounds = _build_char_time_map(original_parts)
    if not full_text:
        return None

    return _generate_from_char_times(
        full_text,
        char_times,
        seg_bounds,
        output_path,
        max_chars_per_line,
        max_lines,
    )


def select_better_transcription(
    whisper_segments: list[dict],
    original_parts: list[tuple],
) -> bool:
    """Whisper再文字起こしと元文字起こしを比較し、Whisperを使うべきかを返す。

    比較基準（機械的）:
    1. 文完結率: 末尾がis_sentence_complete()なセグメントの割合
    2. フィラー混入率: フィラー語の出現割合（少ないほうが良い）
    3. テキスト密度: 全文字数 / 全時間（異常に少ない = 認識漏れ）
    4. 全体の文字数差: 大きく減っている場合はWhisperの認識漏れ

    Returns:
        True: Whisperを採用, False: 元テキストを採用
    """
    from core.japanese_line_break import JapaneseLineBreakRules
    from use_cases.ai.filler_constants import FILLER_WORDS

    # Whisperテキスト構築
    whisper_text = "".join(s.get("text", "") for s in whisper_segments)
    whisper_duration = sum(s.get("end", 0) - s.get("start", 0) for s in whisper_segments) if whisper_segments else 1.0

    # 元テキスト構築
    original_text = "".join(p[0] for p in original_parts)
    original_duration = sum(p[2] - p[1] for p in original_parts) if original_parts else 1.0

    whisper_score = 0.0
    original_score = 0.0

    # 1. 文完結率
    whisper_ends = [s.get("text", "").rstrip() for s in whisper_segments if s.get("text", "").strip()]
    whisper_complete = sum(1 for t in whisper_ends if JapaneseLineBreakRules.is_sentence_complete(t))
    whisper_complete_rate = whisper_complete / max(len(whisper_ends), 1)

    original_ends = [p[0].rstrip() for p in original_parts if p[0].strip()]
    original_complete = sum(1 for t in original_ends if JapaneseLineBreakRules.is_sentence_complete(t))
    original_complete_rate = original_complete / max(len(original_ends), 1)

    whisper_score += whisper_complete_rate * 30
    original_score += original_complete_rate * 30

    # 2. フィラー混入率
    filler_set = set(FILLER_WORDS)

    def _count_fillers(text: str) -> int:
        count = 0
        for f in filler_set:
            count += text.count(f)
        return count

    whisper_fillers = _count_fillers(whisper_text)
    original_fillers = _count_fillers(original_text)
    whisper_filler_rate = whisper_fillers / max(len(whisper_text), 1)
    original_filler_rate = original_fillers / max(len(original_text), 1)

    # フィラーが少ないほうが良い
    whisper_score += (1 - whisper_filler_rate) * 20
    original_score += (1 - original_filler_rate) * 20

    # 3. テキスト密度
    whisper_density = len(whisper_text) / max(whisper_duration, 0.1)
    original_density = len(original_text) / max(original_duration, 0.1)

    # 正常範囲: 3-10文字/秒（日本語の発話速度）
    def _density_score(d: float) -> float:
        if 3.0 <= d <= 10.0:
            return 20.0
        elif d < 3.0:
            return d / 3.0 * 20.0  # 低密度ペナルティ
        else:
            return max(0, 20.0 - (d - 10.0) * 2)

    whisper_score += _density_score(whisper_density)
    original_score += _density_score(original_density)

    # 4. 文字数差: Whisperが元より大幅に少ない場合は認識漏れ
    if len(original_text) > 0:
        ratio = len(whisper_text) / len(original_text)
        if ratio < 0.7:
            whisper_score -= 20  # 30%以上減少はペナルティ
        elif ratio > 1.3:
            whisper_score -= 10  # 30%以上増加も疑わしい

    logger.debug(
        f"SRT比較: Whisper={whisper_score:.1f} vs Original={original_score:.1f} "
        f"(文完結: {whisper_complete_rate:.0%}/{original_complete_rate:.0%}, "
        f"フィラー: {whisper_fillers}/{original_fillers}, "
        f"密度: {whisper_density:.1f}/{original_density:.1f})"
    )

    return whisper_score >= original_score


def _extract_audio_parts_parallel(
    time_ranges: list[tuple[float, float]],
    video_path: Path,
    tmpdir: str,
    ffmpeg_timeout: int = 30,
) -> list[str] | None:
    """複数time_rangesの音声をThreadPoolExecutorで並列抽出する。

    Returns:
        抽出したWAVファイルパスのリスト。1つでも失敗したらNone。
    """
    import subprocess
    from concurrent.futures import ThreadPoolExecutor

    def _extract_one(args: tuple[int, float, float]) -> str | None:
        i, start, end = args
        p = f"{tmpdir}/p{i}.wav"
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
                p,
            ],
            capture_output=True,
            timeout=ffmpeg_timeout,
        )
        if proc.returncode != 0:
            logger.warning("ffmpeg extract failed (part %d)", i)
            return None
        return p

    with ThreadPoolExecutor(max_workers=min(len(time_ranges), 4)) as executor:
        results = list(executor.map(_extract_one, [(i, s, e) for i, (s, e) in enumerate(time_ranges)]))

    if any(r is None for r in results):
        return None
    return results


def _transcribe_output_audio(
    time_ranges: list[tuple[float, float]],
    video_path: Path,
    api_key: str | None = None,
) -> list[dict] | None:
    """切り抜き後の音声を結合し、Whisper APIで文字起こしする。

    APIキー解決の優先順位:
        1. 引数 api_key（明示的に渡された場合）
        2. 環境変数 OPENAI_API_KEY / TEXTFFCUT_API_KEY
        3. api_key_manager.load_api_key()（暗号化ストレージ）

    Returns:
        [{"text": str, "start": float, "end": float}, ...] セグメントリスト
        タイムスタンプは結合後の音声の時間（0始まり）
    """
    import subprocess
    import tempfile

    if not api_key:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")

    if not api_key:
        try:
            from utils.api_key_manager import api_key_manager

            api_key = api_key_manager.load_api_key()
        except Exception:
            pass

    if not api_key:
        logger.debug("APIキー未設定、元の文字起こしでフォールバック")
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)

        with tempfile.TemporaryDirectory() as tmpdir:
            # 各rangeの音声を並列抽出
            total_duration = sum(end - start for start, end in time_ranges)
            ffmpeg_timeout = max(30, int(total_duration * 2))

            parts = _extract_audio_parts_parallel(time_ranges, video_path, tmpdir, ffmpeg_timeout)
            if parts is None:
                return None

            # 結合
            with open(f"{tmpdir}/list.txt", "w") as f:
                for p in parts:
                    f.write(f"file '{p}'\n")
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    f"{tmpdir}/list.txt",
                    "-c",
                    "copy",
                    f"{tmpdir}/out.wav",
                ],
                capture_output=True,
                timeout=ffmpeg_timeout,
            )
            if proc.returncode != 0:
                logger.warning("ffmpeg concat failed")
                return None

            # Whisper APIでsegment-levelタイムスタンプ付き文字起こし
            with open(f"{tmpdir}/out.wav", "rb") as f:
                resp = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    language="ja",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )

            # SDKバージョンによりsegmentsの取得方法が異なる
            raw_segments = getattr(resp, "segments", None)
            if raw_segments is None:
                raw_segments = getattr(resp, "model_extra", {}).get("segments", [])
            if not raw_segments:
                return None

            segments = []
            for seg in raw_segments:
                text = seg.text if hasattr(seg, "text") else seg.get("text", "")
                text = (text or "").strip()
                start = seg.start if hasattr(seg, "start") else seg.get("start", 0)
                end = seg.end if hasattr(seg, "end") else seg.get("end", 0)
                if text and end > start:
                    # Whisperが音声長を超えるタイムスタンプを返すことがあるのでクランプ
                    start = min(start, total_duration)
                    end = min(end, total_duration)
                    if end > start:
                        segments.append({"text": text, "start": start, "end": end})

            logger.info(f"出力音声文字起こし: {len(segments)}セグメント")
            return segments

    except Exception as e:
        logger.warning(f"出力音声文字起こし失敗: {e}")
        return None


def _generate_from_segments(
    segments: list[dict],
    output_path: Path,
    max_chars_per_line: int,
    max_lines: int,
) -> Path | None:
    """Whisperセグメントから字幕を生成する。"""
    if not segments:
        return None

    # 全テキスト結合 + セグメントベースのchar_times
    full_text = ""
    char_times = []
    seg_bounds = set()

    for seg in segments:
        text = seg["text"]
        if not text:
            continue
        seg_bounds.add(len(full_text))
        start = seg["start"]
        end = seg["end"]
        dur = end - start
        n = max(len(text), 1)
        for i in range(len(text)):
            char_times.append((start + dur * i / n, start + dur * (i + 1) / n))
        full_text += text

    seg_bounds.add(len(full_text))
    seg_bounds.discard(0)

    if not full_text:
        return None

    return _generate_from_char_times(
        full_text,
        char_times,
        seg_bounds,
        output_path,
        max_chars_per_line,
        max_lines,
    )


def generate_srt_entries_from_segments(
    segments: list[dict],
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_lines: int = DEFAULT_MAX_LINES,
) -> list[SRTEntry]:
    """Whisperセグメントから字幕エントリーのリストを返す（ファイル書き出しなし）。

    Args:
        segments: [{"text": str, "start": float, "end": float}, ...] セグメントリスト
        max_chars_per_line: 1行あたり最大文字数
        max_lines: 最大行数

    Returns:
        SRTEntryのリスト
    """
    if not segments:
        return []

    full_text = ""
    char_times = []
    seg_bounds = set()

    for seg in segments:
        text = seg["text"]
        if not text:
            continue
        seg_bounds.add(len(full_text))
        start = seg["start"]
        end = seg["end"]
        dur = end - start
        n = max(len(text), 1)
        for i in range(len(text)):
            char_times.append((start + dur * i / n, start + dur * (i + 1) / n))
        full_text += text

    seg_bounds.add(len(full_text))
    seg_bounds.discard(0)

    if not full_text:
        return []

    return _entries_from_char_times(full_text, char_times, seg_bounds, max_chars_per_line, max_lines)


# 字幕内で除去する安全なフィラー（長い順）
SUBTITLE_FILLER_WORDS = sorted(
    [
        "やっぱり",
        "やっぱ",
        "えーっと",
        "えっとね",
        "えーと",
        "えっと",
        "あのー",
        "なんかその",
        "なんかこう",
        "なんか",
        "あのね",
        "えー",
    ],
    key=len,
    reverse=True,
)


def _remove_inline_fillers(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
) -> tuple[str, list[tuple[float, float]], set[int]]:
    """テキスト内のフィラーを除去し、char_timesとseg_boundsを調整する。

    Returns:
        (除去後テキスト, 調整後char_times, 調整後seg_bounds)
    """
    if not full_text:
        return full_text, char_times, seg_bounds

    # 除去する区間を収集 [(start_pos, end_pos), ...]
    remove_ranges: list[tuple[int, int]] = []

    # 1. GiNZA形態素解析でフィラーPOSを検出
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        doc = JapaneseLineBreakRules._analyze(full_text)
        if doc is not None:
            for token in doc:
                tag = JapaneseLineBreakRules._normalize_pos_tag(token.tag_)
                if tag == "フィラー":
                    remove_ranges.append((token.idx, token.idx + len(token.text)))
    except ImportError:
        pass

    # 2. SUBTITLE_FILLER_WORDSによる追加検出
    for filler in SUBTITLE_FILLER_WORDS:
        start = 0
        while True:
            idx = full_text.find(filler, start)
            if idx == -1:
                break
            filler_end = idx + len(filler)
            # 既にカバーされていなければ追加
            already_covered = any(rs <= idx and filler_end <= re for rs, re in remove_ranges)
            if not already_covered:
                remove_ranges.append((idx, filler_end))
            start = filler_end

    if not remove_ranges:
        return full_text, char_times, seg_bounds

    # 重複・重なりを統合してソート
    remove_ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in remove_ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    # 除去範囲に含まれる位置を集合化
    remove_set = set()
    for s, e in merged:
        for i in range(s, e):
            remove_set.add(i)

    # 新しいテキスト・char_timesを構築
    new_text_chars = []
    new_char_times = []
    # 位置マッピング: old_pos → new_pos
    pos_map = {}
    new_pos = 0
    for old_pos in range(len(full_text)):
        if old_pos not in remove_set:
            new_text_chars.append(full_text[old_pos])
            new_char_times.append(char_times[old_pos])
            pos_map[old_pos] = new_pos
            new_pos += 1

    # seg_boundsを調整
    new_seg_bounds = set()
    for bound in seg_bounds:
        # boundは「ここから新セグメント」の位置
        # bound以上で最初の残存位置を探す
        mapped = None
        for check_pos in range(bound, len(full_text)):
            if check_pos in pos_map:
                mapped = pos_map[check_pos]
                break
        if mapped is not None and mapped > 0:
            new_seg_bounds.add(mapped)
    # 末尾を追加
    new_len = len(new_text_chars)
    if new_len > 0:
        new_seg_bounds.add(new_len)
    new_seg_bounds.discard(0)

    new_text = "".join(new_text_chars)
    return new_text, new_char_times, new_seg_bounds


def _trim_incomplete_ending(entries: list[SRTEntry]) -> list[SRTEntry]:
    """SRT末尾が不完全文で終わる場合、最後の完結点まで切り詰める。

    パターン1: 最終エントリ内に完結点がある → テキストをその点で切り詰め
    パターン2: 最終エントリ全体が不完全 → 前のエントリに遡って完結点を探す（最大3エントリ）
    """
    if not entries:
        return entries

    from core.japanese_line_break import JapaneseLineBreakRules

    # 最終エントリのテキスト（改行除去して結合）
    last = entries[-1]
    flat = last.text.replace("\n", "")
    if JapaneseLineBreakRules.is_sentence_complete(flat):
        return entries

    # パターン1: 最終エントリ内を逆走して完結点を探す
    # 行単位でチェック（SRTは1-2行構成）
    lines = last.text.split("\n")
    if len(lines) >= 2:
        first_line = lines[0].rstrip()
        if first_line and JapaneseLineBreakRules.is_sentence_complete(first_line):
            # 1行目で完結 → 2行目以降をカット
            last.text = first_line
            logger.info(f"SRT末尾トリム: 最終エントリを1行目で切り詰め '{first_line[-15:]}'")
            return entries

    # パターン2: 最終エントリを丸ごと除去して前のエントリをチェック
    for drop_count in range(1, min(4, len(entries))):
        candidate_entries = entries[: len(entries) - drop_count]
        if not candidate_entries:
            break
        check = candidate_entries[-1]
        check_flat = check.text.replace("\n", "")
        if JapaneseLineBreakRules.is_sentence_complete(check_flat):
            logger.info(f"SRT末尾トリム: 末尾{drop_count}エントリ除去 → '{check_flat[-15:]}'")
            return candidate_entries

    # 完結点が見つからない場合はそのまま返す
    return entries


def _entries_from_char_times(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry]:
    """char_timesベースでSRTEntryリストを生成する（共通処理）。"""
    # フィラー除去
    full_text, char_times, seg_bounds = _remove_inline_fillers(full_text, char_times, seg_bounds)
    if not full_text:
        return []

    micro_blocks = _phase1_split(full_text, seg_bounds, max_chars_per_line)
    lines = _phase2_merge_to_lines(micro_blocks, max_chars_per_line, seg_bounds)
    entries = _phase3_dp_group(lines, char_times, max_chars_per_line, max_lines)

    if not entries:
        return []

    # 隣接エントリ間の隙間を埋める
    for i in range(len(entries) - 1):
        if entries[i + 1].start_time > entries[i].end_time:
            entries[i].end_time = entries[i + 1].start_time

    # 短すぎるエントリを前後と統合
    entries = _merge_short_entries(entries, max_chars_per_line, max_lines)

    # 末尾トリミング: 最後のエントリが不完全文で終わる場合、完結点まで切り詰める
    entries = _trim_incomplete_ending(entries)

    for i, e in enumerate(entries, 1):
        e.index = i

    return entries


def _generate_from_char_times(
    full_text: str,
    char_times: list[tuple[float, float]],
    seg_bounds: set[int],
    output_path: Path,
    max_chars_per_line: int,
    max_lines: int,
) -> Path | None:
    """char_timesベースで字幕を生成する（共通処理）。"""
    entries = _entries_from_char_times(full_text, char_times, seg_bounds, max_chars_per_line, max_lines)

    if not entries:
        return None

    _write_srt(entries, output_path)
    logger.info("SRT生成: %dエントリ → %s", len(entries), output_path.name)
    return output_path


# =============================================
# Phase 1: 全テキストをDP探索で最小ブロックに分割
# =============================================


def _tokenize(text: str) -> list[tuple[int, str, str]]:
    """GiNZAで形態素解析。

    Returns:
        [(boundary_pos, surface, pos_tag), ...]
    """
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        return JapaneseLineBreakRules.get_word_boundaries_with_pos(text)
    except ImportError:
        pass

    # フォールバック: 1文字ずつ
    return [(i + 1, text[i], "") for i in range(len(text))]


def _parse_pos(tag: str) -> tuple[str, str]:
    """品詞タグを (大分類, サブカテゴリ) に分解する。

    例: "助詞-格助詞" → ("助詞", "格助詞")
        "名詞" → ("名詞", "")
    """
    if "-" in tag:
        parts = tag.split("-", 1)
        return parts[0], parts[1]
    return tag, ""


def _phase1_split(full_text: str, seg_bounds: set[int], max_chars: int = DEFAULT_MAX_CHARS_PER_LINE) -> list[TextBlock]:
    n = len(full_text)
    if n == 0:
        return []

    # 統合API: 形態素境界と文節境界を1回の解析で取得
    try:
        from core.japanese_line_break import JapaneseLineBreakRules

        bp, bunsetu_bounds = JapaneseLineBreakRules.get_word_boundaries_and_bunsetu(full_text)
    except ImportError:
        bp = _tokenize(full_text)
        bunsetu_bounds = set()

    boundaries = sorted(set([b for b, _, _ in bp if 0 < b < n]))

    if not boundaries:
        boundaries = list(range(1, n))

    # 長すぎるギャップ（11文字超）にフォールバック境界を追加
    MAX_BLOCK = max_chars
    all_b = sorted(set([0] + boundaries + [n]))
    for idx in range(len(all_b) - 1):
        gap = all_b[idx + 1] - all_b[idx]
        if gap > MAX_BLOCK:
            for fill in range(all_b[idx] + 1, all_b[idx + 1]):
                boundaries.append(fill)
    boundaries = sorted(set(boundaries))

    # 分割点スコア（文節ベース）
    cut_scores = {}
    bp_dict = {pos: (surface, pos_tag) for pos, surface, pos_tag in bp}

    for b in boundaries:
        score = 0.0
        if b in seg_bounds:
            score += 50

        surface, pos_tag = bp_dict.get(b, ("", ""))
        pos_major, pos_sub = _parse_pos(pos_tag)

        if b in bunsetu_bounds:
            # 文節境界 = 自然な分割点
            score += 20
            # 品詞ボーナス
            if pos_major == "助詞" and pos_sub == "接続助詞" and surface not in ("て", "で"):
                score += 20  # から/けど/ので → 計40
            elif pos_major == "助詞" and pos_sub == "終助詞":
                score += 20  # な/ね/よ → 計40
            elif pos_major == "助詞" and pos_sub == "係助詞":
                score += 10  # は/も → 計30
            elif pos_major == "フィラー":
                score += 15
        else:
            # 文節内部 = 分割を強く抑制
            score -= 30
            # フィラーの後は文節内でも許容
            if pos_major == "フィラー":
                score += 45  # net: +15

        cut_scores[b] = score

    # DP（11文字以下で分割）
    MAX_BLOCK = max_chars
    dp = {0: (0.0, -1)}
    all_positions = sorted(set([0] + boundaries))

    for i in all_positions:
        if i not in dp or i >= n:
            continue
        for b in boundaries:
            if b <= i:
                continue
            if b - i > MAX_BLOCK:
                break
            if b - i < 2:
                continue
            new_score = dp[i][0] + cut_scores.get(b, 0)
            if b - i <= 2:
                new_score -= 20
            if b not in dp or new_score > dp[b][0]:
                dp[b] = (new_score, i)

        remaining = n - i
        if 2 <= remaining <= MAX_BLOCK:
            if n not in dp or dp[i][0] > dp.get(n, (-999, -1))[0]:
                dp[n] = (dp[i][0], i)

    if n not in dp:
        return [TextBlock(full_text, 0, n)]

    points = []
    pos = n
    while pos > 0:
        points.append(pos)
        pos = dp[pos][1]
    points.reverse()

    blocks = []
    prev = 0
    for sp in points:
        if sp > prev:
            blocks.append(TextBlock(full_text[prev:sp], prev, sp))
        prev = sp

    return blocks


# =============================================
# Phase 2: 隣接ブロックをDPで結合して11文字以下の1行に
# =============================================


def _phase2_merge_to_lines(
    blocks: list[TextBlock],
    max_chars: int,
    seg_bounds: set[int],
) -> list[TextBlock]:
    """隣接するmicro_blocksを結合して、各行がmax_chars以下になるようにする。

    DPで全体最適な結合を見つける。
    セグメント境界をまたぐ結合はペナルティ。
    """
    n = len(blocks)
    if n == 0:
        return []

    # dp[i] = (score, prev_group_start)
    # i = 次のグループの開始ブロックindex
    dp = {0: (0.0, -1)}

    for i in range(n):
        if i not in dp:
            continue
        current_score = dp[i][0]

        # i から j までのブロックを1行に結合
        combined_text = ""
        for j in range(i, n):
            combined_text += blocks[j].text
            combined_len = len(combined_text)
            if combined_len > max_chars:
                break

            # セグメント境界をまたぐ結合はペナルティ
            crosses = False
            if j > i:
                for k in range(i + 1, j + 1):
                    if blocks[k].start_pos in seg_bounds:
                        crosses = True
                        break

            score = current_score
            # 適度な長さにボーナス
            if combined_len >= 6:
                score += 5
            if combined_len >= 9:
                score += 3
            if crosses:
                score -= 10

            next_i = j + 1
            if next_i not in dp or score > dp[next_i][0]:
                dp[next_i] = (score, i)

    if n not in dp:
        return blocks

    # 逆順に復元
    group_starts = []
    pos = n
    while pos > 0:
        start = dp[pos][1]
        group_starts.append(start)
        pos = start
    group_starts.reverse()

    # グループからTextBlockを生成
    lines = []
    for idx, gs in enumerate(group_starts):
        ge = group_starts[idx + 1] if idx + 1 < len(group_starts) else n
        text = "".join(blocks[k].text for k in range(gs, ge))
        lines.append(TextBlock(text, blocks[gs].start_pos, blocks[ge - 1].end_pos))

    return lines


# =============================================
# Phase 3: 隣接1行を2行ブロックにまとめるかDPで判断
# =============================================

# 文の区切りパターン（これで終わる行は次の行と結合しない）
SENTENCE_ENDINGS = [
    "です",
    "ですよ",
    "ですね",
    "ですけど",
    "ですか",
    "ですかね",
    "ですよね",
    "ますよね",
    "ます",
    "ました",
    "ません",
    "ましたね",
    "のか",
    "のかとか",
    "いいな",
    "だな",
    "かな",
    "んですけど",
    "んですが",
    "ないので",
    "しょう",
    "ください",
    "だよ",
    "だよね",
    "よね",
    "んですけれども",
    "ですけれども",
    "んですけども",
    "ですけども",
    "けれども",
    "けども",
    "だけど",
    "からね",
    "しかない",
    "らしい",
]


def _phase3_dp_group(
    lines: list[TextBlock],
    char_times: list[tuple[float, float]],
    max_chars_per_line: int,
    max_lines: int = 2,
) -> list[SRTEntry]:
    """DPで隣接行を2行にまとめるかどうかを最適化する。"""
    if max_lines < 2:
        # 1行モード: 結合しない
        entries = []
        for i, line in enumerate(lines):
            entries.append(_make_srt_entry(i + 1, [line], char_times))
        return entries
    max_total = max_chars_per_line * 2
    n = len(lines)
    if n == 0:
        return []

    # dp[i] = (score, entries)
    dp = {0: (0.0, [])}

    for i in range(n):
        if i not in dp:
            continue
        prev_score, prev_entries = dp[i]

        # 選択肢A: 行iを単独エントリ
        entry_a = _make_srt_entry(len(prev_entries) + 1, [lines[i]], char_times)
        score_a = prev_score + _line_group_score(lines[i].text, None)
        next_a = i + 1
        if next_a not in dp or score_a > dp[next_a][0]:
            dp[next_a] = (score_a, prev_entries + [entry_a])

        # 選択肢B: 行iとi+1を結合
        if i + 1 < n:
            combined_len = len(lines[i].text) + len(lines[i + 1].text)
            if combined_len <= max_total:
                # 文末パターンで終わる場合は結合しない
                if _ends_with_sentence(lines[i].text):
                    pass  # 結合スキップ
                else:
                    entry_b = _make_srt_entry(
                        len(prev_entries) + 1,
                        [lines[i], lines[i + 1]],
                        char_times,
                    )
                    score_b = prev_score + _line_group_score(lines[i].text, lines[i + 1].text)
                    next_b = i + 2
                    if next_b not in dp or score_b > dp[next_b][0]:
                        dp[next_b] = (score_b, prev_entries + [entry_b])

    if n not in dp:
        return []

    _, best = dp[n]
    for idx, e in enumerate(best, 1):
        e.index = idx
    return best


def _ends_with_sentence(text: str) -> bool:
    """行が文の区切りで終わるかチェック。"""
    for ending in SENTENCE_ENDINGS:
        if text.endswith(ending):
            return True
    return False


def _line_group_score(line1: str, line2: str | None) -> float:
    """1エントリのスコア。"""
    score = 0.0

    if line2 is None:
        # 単独行
        if len(line1) >= 8:
            score += 3

        # 短い単独行はペナルティ（結合して2行にした方が読みやすい）
        if len(line1) <= 7:
            score -= 5

        # 助詞で終わる単独行は強ペナルティ
        if _ends_with_particle(line1):
            score -= 10

        return score

    # 2行結合
    score += 5  # 結合ボーナス

    # 1行目が助詞で終わる場合は結合を推奨（主語の途中）
    if _ends_with_particle(line1):
        score += 10

    # 2行目が「は」「が」等で終わる場合は強く結合（文頭〜主語が1ブロックに収まる）
    if line2.endswith(("のは", "には", "では", "とは", "は", "が")):
        score += 15

    # バランス
    balance = 1.0 - abs(len(line1) - len(line2)) / max(len(line1) + len(line2), 1)
    score += balance * 3

    # 表示文字数
    total = len(line1) + len(line2)
    if total >= 15:
        score += 2

    return score


def _ends_with_particle(text: str) -> bool:
    """行が助詞（は、が、を、に、で、から、の等）で終わるか。"""
    particles = ["のは", "には", "では", "とは", "から", "まで", "は", "が", "を", "に", "で", "と", "も", "の"]
    for p in particles:
        if text.endswith(p):
            return True
    return False


def _make_srt_entry(index, line_blocks, char_times):
    if len(line_blocks) == 1:
        text = line_blocks[0].text
    else:
        text = "\n".join(lb.text for lb in line_blocks)

    start_pos = line_blocks[0].start_pos
    end_pos = line_blocks[-1].end_pos
    tl_start = _char_time(start_pos, char_times, True)
    tl_end = _char_time(end_pos - 1, char_times, False)

    return SRTEntry(index=index, start_time=tl_start, end_time=tl_end, text=text)


MIN_ENTRY_DURATION = 0.7  # 最小表示時間（秒）


def _merge_short_entries(
    entries: list[SRTEntry],
    max_chars_per_line: int,
    max_lines: int,
) -> list[SRTEntry]:
    """短すぎるエントリを前後と統合する。"""
    if len(entries) <= 1:
        return entries

    max_total_chars = max_chars_per_line * max_lines

    def _text_lines(e: SRTEntry) -> list[str]:
        return e.text.split("\n")

    def _can_merge(a: SRTEntry, b: SRTEntry) -> bool:
        """2つのエントリを統合可能か（文字数制限チェック）"""
        a_lines = _text_lines(a)
        b_lines = _text_lines(b)
        combined_lines = a_lines + b_lines
        if len(combined_lines) > max_lines:
            # 行数超過 → 最終行同士を結合して収まるか
            merged_last = a_lines[-1] + b_lines[0]
            if len(merged_last) > max_chars_per_line:
                return False
            combined_lines = a_lines[:-1] + [merged_last] + b_lines[1:]
            if len(combined_lines) > max_lines:
                return False
        return all(len(line) <= max_chars_per_line for line in combined_lines)

    def _do_merge(a: SRTEntry, b: SRTEntry) -> SRTEntry:
        """2つのエントリを統合する"""
        a_lines = _text_lines(a)
        b_lines = _text_lines(b)
        combined_lines = a_lines + b_lines
        if len(combined_lines) > max_lines:
            merged_last = a_lines[-1] + b_lines[0]
            combined_lines = a_lines[:-1] + [merged_last] + b_lines[1:]
        return SRTEntry(
            index=0,
            start_time=a.start_time,
            end_time=b.end_time,
            text="\n".join(combined_lines),
        )

    changed = True
    max_iterations = 50
    iteration = 0
    while changed:
        iteration += 1
        if iteration > max_iterations:
            logger.warning("短エントリ統合ループが収束しません（%d回）。打ち切ります。", max_iterations)
            break
        changed = False
        new_entries = []
        i = 0
        while i < len(entries):
            e = entries[i]
            dur = e.end_time - e.start_time

            if dur < MIN_ENTRY_DURATION - 1e-3 and len(entries) > 1:
                # 前のエントリと統合を試みる
                if new_entries and _can_merge(new_entries[-1], e):
                    new_entries[-1] = _do_merge(new_entries[-1], e)
                    changed = True
                    i += 1
                    continue
                # 次のエントリと統合を試みる
                if i + 1 < len(entries) and _can_merge(e, entries[i + 1]):
                    merged = _do_merge(e, entries[i + 1])
                    new_entries.append(merged)
                    changed = True
                    i += 2
                    continue
                # 統合不可 → 表示時間を延長（前後から借りる）
                desired_end = e.start_time + MIN_ENTRY_DURATION
                if i + 1 < len(entries) and desired_end <= entries[i + 1].end_time:
                    # 次エントリの開始を後ろにずらす
                    entries[i + 1] = SRTEntry(
                        index=0,
                        start_time=desired_end,
                        end_time=entries[i + 1].end_time,
                        text=entries[i + 1].text,
                    )
                    e = SRTEntry(index=0, start_time=e.start_time, end_time=desired_end, text=e.text)
                    changed = True
                elif new_entries:
                    # 前エントリの終了を前にずらして自分を延長
                    desired_start = e.end_time - MIN_ENTRY_DURATION
                    if desired_start >= new_entries[-1].start_time:
                        new_entries[-1] = SRTEntry(
                            index=0,
                            start_time=new_entries[-1].start_time,
                            end_time=desired_start,
                            text=new_entries[-1].text,
                        )
                        e = SRTEntry(index=0, start_time=desired_start, end_time=e.end_time, text=e.text)
                        changed = True

            new_entries.append(e)
            i += 1
        entries = new_entries

    return entries


# =============================================
# ユーティリティ
# =============================================


def _char_time(pos, char_times, start):
    if not char_times:
        return 0.0
    if pos < 0:
        pos = 0
    if pos >= len(char_times):
        pos = len(char_times) - 1
    return char_times[pos][0] if start else char_times[pos][1]


def build_timeline_map(time_ranges):
    m = []
    tl = 0.0
    for s, e in time_ranges:
        m.append((s, e, tl))
        tl += e - s
    return m


def _to_tl(orig, tmap):
    for os_, oe, tl in tmap:
        if os_ - 0.1 <= orig <= oe + 0.1:
            return tl + max(0.0, orig - os_)
    return None


def collect_parts(time_ranges, tmap, transcription, speed=1.0):
    """word-levelタイムスタンプを使ってtime_rangesに含まれる発話を抽出する。

    各 transcription segment の word 単位で「最も重なりが大きい range」に1回だけ
    割り当て、その range 内の連続 word 群を1つの part として収集する。

    time_ranges は speed 除算済み、seg.start/end と seg.words の時間は元時間。

    Raises:
        ValueError: seg に word-level タイムスタンプが無い場合
            （旧キャッシュ対応。上流でキャッシュ無し扱いにしてもらう）
    """
    if speed <= 0:
        raise ValueError(f"speed must be > 0, got {speed}")
    from use_cases.ai.filler_constants import FILLER_ONLY_TEXTS

    def _orig_to_tl(orig_time: float) -> float | None:
        return _to_tl(orig_time / speed, tmap)

    # 各 range を元時間で事前計算
    orig_ranges = [(tr_s * speed, tr_e * speed) for tr_s, tr_e in time_ranges]

    def _best_range_idx(word) -> int | None:  # noqa: ANN001
        """word と最も重なりが大きい range のインデックスを返す。重なり0なら None。"""
        best_idx = None
        best_overlap = 0.0
        for idx, (orig_s, orig_e) in enumerate(orig_ranges):
            overlap = max(0.0, min(word.end, orig_e) - max(word.start, orig_s))
            if overlap > best_overlap:
                best_overlap = overlap
                best_idx = idx
        return best_idx

    parts = []
    for seg in transcription.segments:
        if seg.text.strip() in FILLER_ONLY_TEXTS:
            continue
        if not getattr(seg, "words", None):
            raise ValueError(
                f"segment at {seg.start:.2f}s has no word-level timestamps. "
                "Transcription cache is outdated; re-transcribe the video."
            )

        # 各 word を「最適な range」に割り当て、range ごとに連続 word を 1 part にまとめる
        current_range_idx: int | None = None
        current_words: list = []

        def _flush(range_idx: int, words_buf: list) -> None:
            if range_idx is None or not words_buf:
                return
            text = "".join(w.word for w in words_buf)
            if not text.strip():
                return
            orig_s, orig_e = orig_ranges[range_idx]
            clipped_s = max(words_buf[0].start, orig_s)
            clipped_e = min(words_buf[-1].end, orig_e)
            tl_s = _orig_to_tl(clipped_s)
            tl_e = _orig_to_tl(clipped_e)
            if tl_s is None or tl_e is None or tl_e <= tl_s:
                return
            parts.append((text, tl_s, tl_e))

        for w in seg.words:
            r_idx = _best_range_idx(w)
            if r_idx != current_range_idx:
                _flush(current_range_idx, current_words)
                current_range_idx = r_idx
                current_words = []
            if r_idx is not None:
                current_words.append(w)
        _flush(current_range_idx, current_words)

    return parts


def _build_char_time_map(parts):
    full = ""
    ctimes = []
    seg_bounds = set()
    for text, tl_s, tl_e in parts:
        seg_bounds.add(len(full))
        dur = tl_e - tl_s
        n = max(len(text), 1)
        for i in range(len(text)):
            ctimes.append((tl_s + dur * i / n, tl_s + dur * (i + 1) / n))
        full += text
    seg_bounds.add(len(full))
    seg_bounds.discard(0)
    return full, ctimes, seg_bounds


def _write_srt(entries, output_path):
    lines = []
    for e in entries:
        lines.append(str(e.index))
        lines.append(f"{_fmt(e.start_time)} --> {_fmt(e.end_time)}")
        lines.append(e.text)
        lines.append("")
    # BOMなし + LF改行（macOS + DaVinci Resolve推奨）
    output_path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(s):
    if s < 0:
        s = 0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = round((s % 1) * 1000)
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"
