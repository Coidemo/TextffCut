"""
モデル比較テスト結果の集計・比較スクリプト

Usage:
    python scripts/compare_model_results.py [--log-dir logs/model_comparison]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ClipResult:
    title: str = ""
    is_ok: bool = False
    final_iteration: int = 0
    scores: dict[str, int] = field(default_factory=dict)
    total_score: int = 0
    skipped: bool = False


@dataclass
class PatternResult:
    video_name: str = ""
    pattern: str = ""
    clips: list[ClipResult] = field(default_factory=list)
    skip_count: int = 0
    total_iterations: int = 0
    pipeline_time: float = 0.0
    fcpxml_count: int = 0


# ログからスコア情報を抽出する正規表現
RE_QUALITY_OK = re.compile(r"品質OK \(iteration (\d+)\): (.+?) \| scores: (.+?) total=(\d+)")
RE_QUALITY_NG = re.compile(r"品質問題 \(iteration (\d+)\): (.+?) \| scores: (.+?) total=(\d+)")
RE_SKIP = re.compile(r"品質ループでスキップ: (.+)")
RE_DURATION_SKIP = re.compile(r"デュレーション基準未達でスキップ: (.+?) \(")
RE_INCOMPLETE_SKIP = re.compile(r"内容不完結でスキップ: (.+)")
RE_PIPELINE_TOTAL = re.compile(r"合計: ([\d.]+)s")
RE_FCPXML = re.compile(r"✓ (.+\.fcpxml)")
RE_COST = re.compile(r"約([\d.]+)円")


def parse_scores(scores_str: str) -> dict[str, int]:
    """'hook=4 completeness=3 ...' 形式のスコア文字列をパース"""
    scores = {}
    for item in scores_str.strip().split():
        if "=" in item:
            key, val = item.split("=", 1)
            try:
                scores[key] = int(val)
            except ValueError:
                pass
    return scores


def parse_log(log_path: Path) -> PatternResult:
    """ログファイルからテスト結果を抽出"""
    result = PatternResult()
    result.video_name = log_path.stem.rsplit("_", 1)[0] if "_" in log_path.stem else log_path.stem

    # パターン名を抽出（ファイル名末尾）
    parts = log_path.stem.split("_")
    if len(parts) >= 2:
        # 末尾2-3パーツがパターン名（A_all_mini, B_quality_41, C_all_41）
        for i, p in enumerate(parts):
            if p in ("A", "B", "C"):
                result.pattern = "_".join(parts[i:])
                result.video_name = "_".join(parts[:i])
                break

    text = log_path.read_text(encoding="utf-8", errors="replace")

    # クリップ単位の結果を追跡
    clip_iterations: dict[str, list[int]] = defaultdict(list)
    clip_last_scores: dict[str, dict[str, int]] = {}
    clip_ok: dict[str, bool] = {}
    skipped_titles: set[str] = set()

    for line in text.splitlines():
        # 品質OK
        m = RE_QUALITY_OK.search(line)
        if m:
            iteration, title, scores_str, total = m.groups()
            clip_iterations[title].append(int(iteration))
            clip_last_scores[title] = parse_scores(scores_str)
            clip_ok[title] = True
            result.total_iterations += int(iteration) + 1
            continue

        # 品質問題
        m = RE_QUALITY_NG.search(line)
        if m:
            iteration, title, scores_str, total = m.groups()
            clip_iterations[title].append(int(iteration))
            clip_last_scores[title] = parse_scores(scores_str)
            continue

        # スキップ
        m = RE_SKIP.search(line)
        if m:
            title = m.group(1)
            skipped_titles.add(title)
            result.skip_count += 1
            continue

        m = RE_DURATION_SKIP.search(line)
        if m:
            title = m.group(1)
            skipped_titles.add(title)
            result.skip_count += 1
            continue

        m = RE_INCOMPLETE_SKIP.search(line)
        if m:
            title = m.group(1)
            skipped_titles.add(title)
            result.skip_count += 1
            continue

        # パイプライン合計時間
        m = RE_PIPELINE_TOTAL.search(line)
        if m:
            result.pipeline_time = float(m.group(1))
            continue

        # FCPXML出力数
        m = RE_FCPXML.search(line)
        if m:
            result.fcpxml_count += 1
            continue

    # クリップ結果を構築
    all_titles = set(clip_iterations.keys()) | skipped_titles
    for title in all_titles:
        clip = ClipResult(title=title)
        if title in skipped_titles:
            clip.skipped = True
        if title in clip_ok:
            clip.is_ok = True
        if title in clip_iterations:
            clip.final_iteration = max(clip_iterations[title])
        if title in clip_last_scores:
            clip.scores = clip_last_scores[title]
            clip.total_score = sum(clip.scores.values())
        result.clips.append(clip)

    return result


def print_comparison(results_by_video: dict[str, dict[str, PatternResult]]) -> None:
    """比較テーブルを出力"""
    patterns = ["A_all_mini", "B_quality_41", "C_all_41"]
    pattern_labels = {
        "A_all_mini": "A(全mini)",
        "B_quality_41": "B(品質4.1)",
        "C_all_41": "C(全4.1)",
    }
    score_axes = ["hook", "completeness", "compactness", "ending", "title_relevance"]

    for video_name, pattern_results in sorted(results_by_video.items()):
        # 動画名を短縮表示
        short_name = video_name[:40] + "..." if len(video_name) > 40 else video_name
        print(f"\n{'=' * 70}")
        print(f"  {short_name}")
        print(f"{'=' * 70}")

        # ヘッダー
        col_width = 16
        header = f"{'':24s}"
        for p in patterns:
            label = pattern_labels.get(p, p)
            header += f"{label:>{col_width}s}"
        print(header)
        print("-" * (24 + col_width * len(patterns)))

        # 候補数
        row = f"{'候補数':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r:
                ok_count = sum(1 for c in r.clips if c.is_ok and not c.skipped)
                total = len(r.clips)
                row += f"{f'{ok_count}/{total}':>{col_width}s}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

        # FCPXML数
        row = f"{'FCPXML出力':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r:
                row += f"{str(r.fcpxml_count):>{col_width}s}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

        # 各スコア軸の平均
        for axis in score_axes:
            row = f"{f'平均{axis}':24s}"
            for p in patterns:
                r = pattern_results.get(p)
                if r:
                    vals = [c.scores.get(axis, 0) for c in r.clips if c.scores]
                    if vals:
                        avg = sum(vals) / len(vals)
                        row += f"{avg:>{col_width}.1f}"
                    else:
                        row += f"{'N/A':>{col_width}s}"
                else:
                    row += f"{'N/A':>{col_width}s}"
            # compactnessに注目マーク
            if axis == "compactness":
                row += "  <-- 注目"
            print(row)

        # 合計スコア平均
        row = f"{'合計スコア平均':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r:
                totals = [c.total_score for c in r.clips if c.scores]
                if totals:
                    avg = sum(totals) / len(totals)
                    row += f"{avg:>{col_width}.1f}"
                else:
                    row += f"{'N/A':>{col_width}s}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

        # スキップ数
        row = f"{'スキップ数':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r:
                row += f"{str(r.skip_count):>{col_width}s}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

        # 修正iteration平均
        row = f"{'修正iteration合計':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r:
                row += f"{str(r.total_iterations):>{col_width}s}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

        # 処理時間
        row = f"{'処理時間(秒)':24s}"
        for p in patterns:
            r = pattern_results.get(p)
            if r and r.pipeline_time > 0:
                row += f"{r.pipeline_time:>{col_width}.0f}"
            else:
                row += f"{'N/A':>{col_width}s}"
        print(row)

    # サマリー（全動画合計）
    print(f"\n{'=' * 70}")
    print("  全動画サマリー")
    print(f"{'=' * 70}")

    col_width = 16
    header = f"{'':24s}"
    for p in patterns:
        label = pattern_labels.get(p, p)
        header += f"{label:>{col_width}s}"
    print(header)
    print("-" * (24 + col_width * len(patterns)))

    for axis in score_axes:
        row = f"{f'平均{axis}':24s}"
        for p in patterns:
            all_vals = []
            for video_results in results_by_video.values():
                r = video_results.get(p)
                if r:
                    all_vals.extend(c.scores.get(axis, 0) for c in r.clips if c.scores)
            if all_vals:
                avg = sum(all_vals) / len(all_vals)
                row += f"{avg:>{col_width}.1f}"
            else:
                row += f"{'N/A':>{col_width}s}"
        if axis == "compactness":
            row += "  <-- 注目"
        print(row)

    row = f"{'合計スコア平均':24s}"
    for p in patterns:
        all_totals = []
        for video_results in results_by_video.values():
            r = video_results.get(p)
            if r:
                all_totals.extend(c.total_score for c in r.clips if c.scores)
        if all_totals:
            avg = sum(all_totals) / len(all_totals)
            row += f"{avg:>{col_width}.1f}"
        else:
            row += f"{'N/A':>{col_width}s}"
    print(row)

    row = f"{'スキップ合計':24s}"
    for p in patterns:
        total_skip = sum(
            video_results.get(p, PatternResult()).skip_count for video_results in results_by_video.values()
        )
        row += f"{str(total_skip):>{col_width}s}"
    print(row)

    row = f"{'処理時間合計(秒)':24s}"
    for p in patterns:
        total_time = sum(
            video_results.get(p, PatternResult()).pipeline_time for video_results in results_by_video.values()
        )
        if total_time > 0:
            row += f"{total_time:>{col_width}.0f}"
        else:
            row += f"{'N/A':>{col_width}s}"
    print(row)

    # 判断基準の出力
    print(f"\n{'=' * 70}")
    print("  判断基準")
    print(f"{'=' * 70}")
    print("  B > A (compactness改善)  → 品質モデルアップグレード有効。現在のデフォルト維持")
    print("  B ≈ A (差なし)          → モデル変更では不十分。compactness critical化を検討")
    print("  C >> B (大差)           → 全タスク4.1の価値あり。コスト許容なら全4.1推奨")
    print("  B でスキップ激増         → 品質基準の閾値調整が必要（15点→13点等）")


def main():
    parser = argparse.ArgumentParser(description="モデル比較テスト結果の集計")
    parser.add_argument(
        "--log-dir",
        default="logs/model_comparison",
        help="ログディレクトリ（デフォルト: logs/model_comparison）",
    )
    args = parser.parse_args()

    log_dir = Path(args.log_dir)
    if not log_dir.exists():
        print(f"エラー: ログディレクトリが見つかりません: {log_dir}")
        print("  先に scripts/model_comparison_test.sh を実行してください")
        sys.exit(1)

    log_files = sorted(log_dir.glob("*.log"))
    if not log_files:
        print(f"エラー: ログファイルが見つかりません: {log_dir}/*.log")
        sys.exit(1)

    print(f"ログファイル: {len(log_files)}件 ({log_dir}/)")

    # ログをパース
    results_by_video: dict[str, dict[str, PatternResult]] = defaultdict(dict)
    for log_file in log_files:
        result = parse_log(log_file)
        results_by_video[result.video_name][result.pattern] = result

    # 比較テーブル出力
    print_comparison(results_by_video)


if __name__ == "__main__":
    main()
