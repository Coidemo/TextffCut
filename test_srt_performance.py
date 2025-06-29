#!/usr/bin/env python3
"""
SRT字幕機能のパフォーマンステスト

処理時間、メモリ使用量、大規模データの処理能力を測定
"""

import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from core.srt_diff_exporter import SRTDiffExporter
from core.text_processor import TextDifference, TextPosition
from core.transcription import TranscriptionResult, TranscriptionSegment
from utils.logging import get_logger

logger = get_logger(__name__)


def create_large_transcription(segment_count: int = 1000, words_per_segment: int = 20) -> TranscriptionResult:
    """大規模な文字起こしデータを生成"""
    segments = []
    current_time = 0.0

    for i in range(segment_count):
        words = []
        segment_text = ""
        word_start = current_time

        for j in range(words_per_segment):
            word = f"単語{i}_{j}"
            word_duration = 0.3
            words.append({"word": word, "start": word_start, "end": word_start + word_duration})
            segment_text += word
            word_start += word_duration

        segment = TranscriptionSegment(start=current_time, end=word_start, text=segment_text, words=words)
        segments.append(segment)
        current_time = word_start + 0.5  # セグメント間のギャップ

    return TranscriptionResult(
        segments=segments, language="ja", original_audio_path="test_large.wav", model_size="base", processing_time=1.0
    )


def measure_performance(func, *args, **kwargs) -> tuple[Any, float, float]:
    """関数の実行時間とメモリ使用量を測定"""
    # メモリ測定開始
    tracemalloc.start()

    # 実行時間測定
    start_time = time.time()
    result = func(*args, **kwargs)
    end_time = time.time()

    # メモリ使用量取得
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    execution_time = end_time - start_time
    peak_memory_mb = peak / 1024 / 1024

    return result, execution_time, peak_memory_mb


def test_basic_performance() -> None:
    """基本的なパフォーマンステスト"""
    print("\n=== 基本パフォーマンステスト ===")

    config = Config()
    exporter = SRTDiffExporter(config)

    # テスト設定
    srt_settings = {
        "max_line_length": 11,
        "max_lines": 2,
        "min_duration": 0.5,
        "max_duration": 7.0,
        "gap_threshold": 0.1,
        "fps": 30.0,
    }

    # 小規模データ（10セグメント）
    print("\n1. 小規模データ（10セグメント）:")
    small_transcription = create_large_transcription(10, 10)
    small_text = "".join(seg.text for seg in small_transcription.segments)

    small_diff = TextDifference(
        original_text=small_text,
        edited_text=small_text,
        common_positions=[TextPosition(0, len(small_text), small_text)],
        added_chars=set(),
    )

    _, exec_time, memory = measure_performance(
        exporter.export_from_diff,
        diff=small_diff,
        transcription_result=small_transcription,
        output_path="test_small_perf.srt",
        srt_settings=srt_settings,
    )

    print(f"  実行時間: {exec_time:.3f}秒")
    print(f"  ピークメモリ: {memory:.2f}MB")

    # 中規模データ（100セグメント）
    print("\n2. 中規模データ（100セグメント）:")
    medium_transcription = create_large_transcription(100, 15)
    medium_text = "".join(seg.text for seg in medium_transcription.segments)

    medium_diff = TextDifference(
        original_text=medium_text,
        edited_text=medium_text,
        common_positions=[TextPosition(0, len(medium_text), medium_text)],
        added_chars=set(),
    )

    _, exec_time, memory = measure_performance(
        exporter.export_from_diff,
        diff=medium_diff,
        transcription_result=medium_transcription,
        output_path="test_medium_perf.srt",
        srt_settings=srt_settings,
    )

    print(f"  実行時間: {exec_time:.3f}秒")
    print(f"  ピークメモリ: {memory:.2f}MB")

    # 大規模データ（1000セグメント）
    print("\n3. 大規模データ（1000セグメント）:")
    large_transcription = create_large_transcription(1000, 20)
    large_text = "".join(seg.text for seg in large_transcription.segments[:500])  # 半分だけ選択

    large_diff = TextDifference(
        original_text="".join(seg.text for seg in large_transcription.segments),
        edited_text=large_text,
        common_positions=[TextPosition(0, len(large_text), large_text)],
        added_chars=set(),
    )

    _, exec_time, memory = measure_performance(
        exporter.export_from_diff,
        diff=large_diff,
        transcription_result=large_transcription,
        output_path="test_large_perf.srt",
        srt_settings=srt_settings,
    )

    print(f"  実行時間: {exec_time:.3f}秒")
    print(f"  ピークメモリ: {memory:.2f}MB")

    # クリーンアップ
    for file in ["test_small_perf.srt", "test_medium_perf.srt", "test_large_perf.srt"]:
        Path(file).unlink(missing_ok=True)


def test_line_break_performance() -> None:
    """日本語改行処理のパフォーマンステスト"""
    print("\n=== 日本語改行処理パフォーマンステスト ===")

    from core.japanese_line_break import JapaneseLineBreakRules

    # janomeの有無を確認
    try:
        import janome  # noqa: F401

        print("janomeモジュール: インストール済み")
    except ImportError:
        print("janomeモジュール: 未インストール（正規表現フォールバック）")

    # テストテキスト
    test_texts = [
        "これは短いテキストです。",
        "これは非常に長い日本語のテキストで、複数の文章が含まれています。改行処理のパフォーマンスを測定するために、様々な長さのテキストを用意しました。",
        "日本語と英語がmixedされたテキストも、適切にline breakできるかperformanceをチェックします。数字123や記号!?も含まれています。"
        * 10,
    ]

    max_line_length = 15

    for i, text in enumerate(test_texts):
        print(f"\n{i + 1}. テキスト長: {len(text)}文字")

        # extract_line のパフォーマンス測定
        remaining = text
        lines = []

        start_time = time.time()
        while remaining:
            line, remaining = JapaneseLineBreakRules.extract_line(remaining, max_line_length)
            lines.append(line)
        end_time = time.time()

        print(f"  生成行数: {len(lines)}")
        print(f"  処理時間: {(end_time - start_time) * 1000:.2f}ms")
        print(f"  1行あたり: {(end_time - start_time) * 1000 / len(lines):.2f}ms")


def test_edge_cases() -> None:
    """エッジケースのテスト"""
    print("\n=== エッジケーステスト ===")

    config = Config()
    exporter = SRTDiffExporter(config)

    # 1. 非常に短いセグメント
    print("\n1. 非常に短いセグメント（0.1秒）:")
    short_segments = []
    for i in range(10):
        short_segments.append(
            TranscriptionSegment(
                start=i * 0.1,
                end=(i + 1) * 0.1,
                text=f"短{i}",
                words=[{"word": f"短{i}", "start": i * 0.1, "end": (i + 1) * 0.1}],
            )
        )

    short_transcription = TranscriptionResult(
        segments=short_segments, language="ja", original_audio_path="test.wav", model_size="base", processing_time=1.0
    )

    short_text = "".join(seg.text for seg in short_segments)
    short_diff = TextDifference(
        original_text=short_text,
        edited_text=short_text,
        common_positions=[TextPosition(0, len(short_text), short_text)],
        added_chars=set(),
    )

    success = exporter.export_from_diff(
        diff=short_diff,
        transcription_result=short_transcription,
        output_path="test_short_segments.srt",
        srt_settings={"min_duration": 0.5, "gap_threshold": 0.1},
    )

    if success:
        with open("test_short_segments.srt", encoding="utf-8") as f:
            content = f.read()
            entry_count = content.count("\n\n") + 1
            print(f"  結果: {entry_count}エントリ生成（元: {len(short_segments)}セグメント）")

    # 2. 非常に長い単一セグメント
    print("\n2. 非常に長い単一セグメント（300文字）:")
    long_text = "これは非常に長いテキストです。" * 20
    long_segment = TranscriptionSegment(
        start=0.0, end=30.0, text=long_text, words=[{"word": long_text, "start": 0.0, "end": 30.0}]
    )

    long_transcription = TranscriptionResult(
        segments=[long_segment], language="ja", original_audio_path="test.wav", model_size="base", processing_time=1.0
    )

    long_diff = TextDifference(
        original_text=long_text,
        edited_text=long_text,
        common_positions=[TextPosition(0, len(long_text), long_text)],
        added_chars=set(),
    )

    _, exec_time, _ = measure_performance(
        exporter.export_from_diff,
        diff=long_diff,
        transcription_result=long_transcription,
        output_path="test_long_segment.srt",
        srt_settings={"max_line_length": 20, "max_lines": 2},
    )

    with open("test_long_segment.srt", encoding="utf-8") as f:
        content = f.read()
        entry_count = content.count("\n\n") + 1
        print(f"  結果: {entry_count}エントリに分割")
        print(f"  処理時間: {exec_time:.3f}秒")

    # クリーンアップ
    Path("test_short_segments.srt").unlink(missing_ok=True)
    Path("test_long_segment.srt").unlink(missing_ok=True)


def test_memory_efficiency() -> None:
    """メモリ効率性のテスト"""
    print("\n=== メモリ効率性テスト ===")

    config = Config()
    exporter = SRTDiffExporter(config)

    # 段階的にデータサイズを増やしてメモリ使用量を測定
    sizes = [10, 50, 100, 500, 1000]
    results = []

    for size in sizes:
        transcription = create_large_transcription(size, 20)
        text = "".join(seg.text for seg in transcription.segments[: size // 2])

        diff = TextDifference(
            original_text="".join(seg.text for seg in transcription.segments),
            edited_text=text,
            common_positions=[TextPosition(0, len(text), text)],
            added_chars=set(),
        )

        _, _, memory = measure_performance(
            exporter.export_from_diff,
            diff=diff,
            transcription_result=transcription,
            output_path=f"test_memory_{size}.srt",
        )

        results.append((size, memory))
        Path(f"test_memory_{size}.srt").unlink(missing_ok=True)

    print("\nセグメント数とメモリ使用量:")
    for size, memory in results:
        print(f"  {size:4d}セグメント: {memory:6.2f}MB")

    # メモリ使用量の増加率を計算
    if len(results) > 1:
        growth_rate = (results[-1][1] - results[0][1]) / (results[-1][0] - results[0][0])
        print(f"\nメモリ増加率: {growth_rate:.4f}MB/セグメント")


def run_all_tests() -> None:
    """すべてのパフォーマンステストを実行"""
    print("=== SRT機能パフォーマンステスト ===")
    print(f"開始時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    start_time = time.time()

    # 各テストを実行
    test_basic_performance()
    test_line_break_performance()
    test_edge_cases()
    test_memory_efficiency()

    total_time = time.time() - start_time

    print("\n=== テスト完了 ===")
    print(f"総実行時間: {total_time:.2f}秒")
    print(f"終了時刻: {time.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    run_all_tests()
