#!/usr/bin/env python3
"""
Phase 1 フォーマット比較実験スクリプト

5つのセグメントフォーマットで detect_topics() を実行し、
結果を比較テーブルで表示する。

Usage:
    python scripts/experiment_phase1_format.py \
        "/path/to/video.mp4" \
        --num 3
"""

import argparse
import json
import os
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from rich.console import Console
from rich.table import Table

from domain.entities.clip_suggestion import TopicDetectionRequest, TopicDetectionResult
from infrastructure.external.gateways.openai_clip_suggestion_gateway import (
    OpenAIClipSuggestionGateway,
)

console = Console()

FORMAT_MODES = [
    ("A", "chunk_30s", "30秒チャンク（現行）"),
    ("B", "individual", "セグメント個別表示"),
    ("C", "individual_gap", "個別 + 沈黙ギャップ"),
    ("D", "individual_noise", "個別 + ノイズタグ"),
    ("E", "individual_full", "全部入り（ギャップ+ノイズ+低conf）"),
]


def load_cache(video_path: Path) -> list[dict]:
    """文字起こしキャッシュを読み込み（wordsフィールド含む）"""
    cache_dir = video_path.parent / f"{video_path.stem}_TextffCut" / "transcriptions"

    if not cache_dir.exists():
        console.print(f"[red]キャッシュディレクトリが見つかりません: {cache_dir}[/]")
        sys.exit(1)

    # 利用可能なキャッシュファイルを探す
    cache_files = list(cache_dir.glob("*.json"))
    if not cache_files:
        console.print(f"[red]キャッシュファイルが見つかりません: {cache_dir}[/]")
        sys.exit(1)

    # 最新のキャッシュを使用
    cache_file = sorted(cache_files, key=lambda f: f.stat().st_mtime, reverse=True)[0]
    console.print(f"[cyan]キャッシュ読み込み: {cache_file.name}[/]")

    data = json.loads(cache_file.read_text(encoding="utf-8"))

    # v2.0 形式対応
    if "version" in data and "result" in data:
        segments = data["result"]["segments"]
    else:
        segments = data["segments"]

    # words フィールドを含む dict を構築
    result = []
    for seg in segments:
        entry = {
            "text": seg.get("text", ""),
            "start": seg.get("start", 0.0),
            "end": seg.get("end", 0.0),
        }
        # words があれば含める（confidence/score 両対応）
        if "words" in seg and seg["words"]:
            words = []
            for w in seg["words"]:
                word_entry = {
                    "word": w.get("word", w.get("char", "")),
                    "start": w.get("start", 0.0),
                    "end": w.get("end", 0.0),
                }
                # confidence or score
                conf = w.get("confidence", w.get("score", w.get("probability")))
                if conf is not None:
                    word_entry["probability"] = conf
                words.append(word_entry)
            entry["words"] = words
        result.append(entry)

    console.print(f"  セグメント数: {len(result)}")
    if result:
        duration = result[-1].get("end", 0.0) - result[0].get("start", 0.0)
        console.print(f"  動画長: {duration:.0f}秒")

    return result


def count_noise_segments(segments: list[dict], gateway: OpenAIClipSuggestionGateway) -> dict:
    """全セグメントのノイズ分布を集計"""
    counts: dict[str, int] = {}
    for seg in segments:
        tag = gateway._detect_noise_tag(seg)
        if tag:
            counts[tag] = counts.get(tag, 0) + 1
    return counts


def analyze_topic_noise(topics: list, segments: list[dict], gateway: OpenAIClipSuggestionGateway) -> list[dict]:
    """各話題範囲内のノイズセグメント数を分析"""
    results = []
    for topic in topics:
        start_idx = topic.segment_start_index
        end_idx = topic.segment_end_index
        topic_segs = segments[start_idx : end_idx + 1]

        noise_count = 0
        noise_tags = []
        for seg in topic_segs:
            tag = gateway._detect_noise_tag(seg)
            if tag:
                noise_count += 1
                noise_tags.append(tag)

        # 境界セグメントのノイズチェック
        start_noise = gateway._detect_noise_tag(segments[start_idx]) if start_idx < len(segments) else None
        end_noise = gateway._detect_noise_tag(segments[end_idx]) if end_idx < len(segments) else None

        results.append(
            {
                "title": topic.title,
                "range": f"[{start_idx}-{end_idx}]",
                "noise_count": noise_count,
                "total_segs": len(topic_segs),
                "noise_rate": noise_count / len(topic_segs) if topic_segs else 0,
                "start_noise": start_noise,
                "end_noise": end_noise,
                "noise_tags": noise_tags,
            }
        )
    return results


def preview_format(segments: list[dict], gateway: OpenAIClipSuggestionGateway, mode: str, max_lines: int = 5) -> str:
    """フォーマットのプレビュー（先頭N行）"""
    text = gateway._format_segments(segments, format_mode=mode)
    lines = text.split("\n")
    preview = "\n".join(lines[:max_lines])
    if len(lines) > max_lines:
        preview += f"\n... (残り{len(lines) - max_lines}行)"
    return preview


def run_experiment(
    video_path: Path,
    num_candidates: int,
    min_duration: int,
    max_duration: int,
    modes: list[str] | None = None,
) -> None:
    """5フォーマットの比較実験を実行"""
    # APIキー読み込み（暗号化ファイル → config.json → 環境変数）
    from utils.api_key_manager import api_key_manager
    from textffcut_cli.setup_command import get_config_value

    api_key = api_key_manager.load_api_key()
    if not api_key:
        api_key = get_config_value("openai_api_key")
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        console.print("[red]OPENAI_API_KEY が設定されていません[/]")
        console.print("  textffcut setup で設定するか、環境変数を設定してください")
        sys.exit(1)

    gateway = OpenAIClipSuggestionGateway(api_key=api_key, model="gpt-4.1-mini")
    segments = load_cache(video_path)

    # フィルタリング
    if modes:
        run_formats = [f for f in FORMAT_MODES if f[0] in modes]
    else:
        run_formats = FORMAT_MODES

    # フォーマットプレビュー表示
    console.print("\n[bold]フォーマットプレビュー[/]\n")
    for fmt_id, mode, label in run_formats:
        console.print(f"[bold cyan]--- {fmt_id}: {label} ---[/]")
        preview = preview_format(segments, gateway, mode)
        console.print(preview)
        console.print()

    # ノイズ分布
    noise_dist = count_noise_segments(segments, gateway)
    if noise_dist:
        console.print("[bold]ノイズセグメント分布[/]")
        for tag, count in sorted(noise_dist.items(), key=lambda x: -x[1]):
            console.print(f"  {tag}: {count}個")
        console.print()

    # 各フォーマットで実行（レートリミット対応リトライ付き）
    results: list[tuple[str, str, str, TopicDetectionResult]] = []

    for fmt_id, mode, label in run_formats:
        console.print(f"[bold yellow]実行中: {fmt_id} ({label})...[/]", end=" ")

        request = TopicDetectionRequest(
            transcription_segments=segments,
            num_candidates=num_candidates,
            min_duration=min_duration,
            max_duration=max_duration,
        )

        # リトライロジック（レートリミット対応）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = gateway.detect_topics(request, format_mode=mode)
                break
            except Exception as e:
                error_msg = str(e)
                if "rate_limit" in error_msg.lower() or "429" in error_msg:
                    # レートリミットエラー: メッセージからウェイト時間を抽出
                    import re
                    import time as time_mod

                    wait_match = re.search(r"([\d.]+)\s*s", error_msg)
                    wait_time = float(wait_match.group(1)) + 1.0 if wait_match else 15.0
                    console.print(f"\n  [yellow]レートリミット、{wait_time:.0f}秒待機中...[/]", end=" ")
                    time_mod.sleep(wait_time)
                    if attempt == max_retries - 1:
                        console.print(f"[red]失敗（リトライ上限）[/]")
                        raise
                else:
                    raise

        results.append((fmt_id, mode, label, result))

        console.print(
            f"[green]完了[/] "
            f"({result.processing_time:.1f}s, "
            f"{result.token_usage.get('prompt_tokens', 0):,} prompt tokens, "
            f"${result.estimated_cost_usd:.4f})"
        )

    # 結果比較テーブル
    console.print("\n[bold]結果比較[/]\n")

    summary_table = Table(title="フォーマット比較サマリー")
    summary_table.add_column("ID", style="bold")
    summary_table.add_column("フォーマット")
    summary_table.add_column("話題数", justify="right")
    summary_table.add_column("Prompt tokens", justify="right")
    summary_table.add_column("コスト", justify="right")
    summary_table.add_column("時間", justify="right")

    for fmt_id, mode, label, result in results:
        summary_table.add_row(
            fmt_id,
            label,
            str(len(result.topics)),
            f"{result.token_usage.get('prompt_tokens', 0):,}",
            f"${result.estimated_cost_usd:.4f}",
            f"{result.processing_time:.1f}s",
        )
    console.print(summary_table)

    # 各フォーマットの話題詳細
    for fmt_id, mode, label, result in results:
        console.print(f"\n[bold cyan]--- {fmt_id}: {label} ---[/]")

        topic_table = Table()
        topic_table.add_column("#", justify="right")
        topic_table.add_column("タイトル", max_width=30)
        topic_table.add_column("範囲")
        topic_table.add_column("Score", justify="right")
        topic_table.add_column("カテゴリ")
        topic_table.add_column("ノイズ", justify="right")
        topic_table.add_column("境界ノイズ")

        noise_analysis = analyze_topic_noise(result.topics, segments, gateway)

        for i, (topic, noise) in enumerate(zip(result.topics, noise_analysis)):
            boundary_info = ""
            if noise["start_noise"]:
                boundary_info += f"先頭:{noise['start_noise']}"
            if noise["end_noise"]:
                if boundary_info:
                    boundary_info += " "
                boundary_info += f"末尾:{noise['end_noise']}"

            topic_table.add_row(
                str(i + 1),
                topic.title,
                f"[{topic.segment_start_index}-{topic.segment_end_index}]",
                str(topic.score),
                topic.category,
                f"{noise['noise_count']}/{noise['total_segs']}",
                boundary_info or "-",
            )
        console.print(topic_table)

    # フォーマット間の話題重複分析
    console.print("\n[bold]話題範囲の重複分析[/]\n")
    if len(results) >= 2:
        overlap_table = Table(title="フォーマット間の範囲重複")
        overlap_table.add_column("話題#", justify="right")
        for fmt_id, _, label, _ in results:
            overlap_table.add_column(f"{fmt_id}", max_width=25)

        max_topics = max(len(r[3].topics) for r in results)
        for i in range(max_topics):
            row = [str(i + 1)]
            for _, _, _, result in results:
                if i < len(result.topics):
                    t = result.topics[i]
                    row.append(f"{t.title[:15]}\n[{t.segment_start_index}-{t.segment_end_index}]")
                else:
                    row.append("-")
            overlap_table.add_row(*row)
        console.print(overlap_table)


def main():
    parser = argparse.ArgumentParser(description="Phase 1 フォーマット比較実験")
    parser.add_argument("video_path", type=Path, help="動画ファイルパス")
    parser.add_argument("--num", type=int, default=3, help="候補数 (default: 3)")
    parser.add_argument("--min-duration", type=int, default=30, help="最小秒数 (default: 30)")
    parser.add_argument("--max-duration", type=int, default=60, help="最大秒数 (default: 60)")
    parser.add_argument(
        "--modes",
        nargs="*",
        choices=["A", "B", "C", "D", "E"],
        help="実行するフォーマット (default: 全て)",
    )
    args = parser.parse_args()

    if not args.video_path.exists():
        console.print(f"[red]動画ファイルが見つかりません: {args.video_path}[/]")
        sys.exit(1)

    console.print(f"[bold]Phase 1 フォーマット比較実験[/]")
    console.print(f"動画: {args.video_path.name}")
    console.print(f"候補数: {args.num}, 範囲: {args.min_duration}-{args.max_duration}秒")

    run_experiment(
        video_path=args.video_path,
        num_candidates=args.num,
        min_duration=args.min_duration,
        max_duration=args.max_duration,
        modes=args.modes,
    )


if __name__ == "__main__":
    main()
