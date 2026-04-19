#!/usr/bin/env python3
"""
SRT字幕 vs 元の文字起こし比較HTMLレポート生成スクリプト

fcpxml_B_quality_41/ の全SRTファイルについて:
- SRTの字幕テキスト（連結）
- 元の文字起こしの該当時間範囲のテキスト（連結）
を並べて表示し、意味が正しく伝わるか目視確認できるHTMLを生成する。

time_rangesの取得:
1. gpt-4.1.json と gpt-4.1-mini.json の suggestions を全てマージ
2. SRTファイル名のタイトルで完全一致 → 番号で一致 の順に照合
3. マッチしない場合はFCPXMLのasset-clipから直接time_rangesを復元
"""

import json
import re
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path
from html import escape

# ============================================================
# 設定
# ============================================================

VIDEOS_DIR = Path("/Users/naoki/myProject/TextffCut/videos")
OUTPUT_PATH = Path("/Users/naoki/myProject/TextffCut/logs/model_comparison/srt_comparison.html")

VIDEO_CONFIGS = [
    {
        "dir_name": "20260115_スピードが速くなった世界では煙に巻くのは逆効果_TextffCut",
        "label": "20260115 スピードが速くなった世界では煙に巻くのは逆効果",
    },
    {
        "dir_name": "20260129_生成AIの世界で情報収集が完結する人が増えている_TextffCut",
        "label": "20260129 生成AIの世界で情報収集が完結する人が増えている",
    },
    {
        "dir_name": "20260122_メタゲームの概念を持っておくと人生は楽かも_TextffCut",
        "label": "20260122 メタゲームの概念を持っておくと人生は楽かも",
    },
]


# ============================================================
# SRTパーサー
# ============================================================


def parse_srt(srt_path: Path) -> list[dict]:
    """SRTファイルを解析して、エントリのリストを返す"""
    content = srt_path.read_text(encoding="utf-8")
    entries = []
    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        ts_match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not ts_match:
            continue
        start_ts = ts_match.group(1)
        end_ts = ts_match.group(2)
        text = "\n".join(lines[2:])
        entries.append(
            {
                "start": srt_ts_to_seconds(start_ts),
                "end": srt_ts_to_seconds(end_ts),
                "text": text,
            }
        )
    return entries


def srt_ts_to_seconds(ts: str) -> float:
    """SRTタイムスタンプ (HH:MM:SS,mmm) を秒に変換"""
    h, m, rest = ts.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def format_time(seconds: float) -> str:
    """秒を MM:SS 形式に変換"""
    m = int(seconds) // 60
    s = seconds - m * 60
    return f"{m:02d}:{s:05.2f}"


# ============================================================
# FCPXML からtime_ranges抽出
# ============================================================


def parse_fcpxml_fraction(value: str) -> float:
    """FCPXMLの分数形式 (例: "1191/10s") を秒に変換"""
    value = value.rstrip("s")
    if "/" in value:
        return float(Fraction(value))
    return float(value)


def extract_time_ranges_from_fcpxml(fcpxml_path: Path, speed: float = 1.0) -> list[list[float]]:
    """
    FCPXMLファイルからメインのasset-clipのtime_ranges（元動画の時間位置）を抽出する。
    spine直下のasset-clipで、lane属性がないもの（メイン映像）を対象とする。
    speedが1.0でない場合、start値をspeedで割って元動画の時間に変換する。
    """
    try:
        tree = ET.parse(fcpxml_path)
    except ET.ParseError:
        return []

    root = tree.getroot()
    time_ranges = []

    # spine直下のasset-clipを探す
    for spine in root.iter("spine"):
        for clip in spine:
            if clip.tag != "asset-clip":
                continue
            # lane属性があるもの(BGM, SE等)はスキップ
            if clip.get("lane") is not None:
                continue

            start_str = clip.get("start", "0/1s")
            duration_str = clip.get("duration", "0/1s")

            start = parse_fcpxml_fraction(start_str)
            duration = parse_fcpxml_fraction(duration_str)

            # speed補正: source_1.2x.mp4 等の場合、
            # FCPXMLのstartはスピード変換後のファイル上の位置
            # 元動画の位置に戻すには speed を掛ける
            orig_start = start * speed
            orig_end = (start + duration) * speed

            time_ranges.append([orig_start, orig_end])

    return time_ranges


def detect_speed_from_fcpxml(fcpxml_path: Path) -> float:
    """FCPXMLのソースファイル名からスピード倍率を検出する"""
    try:
        tree = ET.parse(fcpxml_path)
    except ET.ParseError:
        return 1.0

    root = tree.getroot()
    for asset in root.iter("asset"):
        name = asset.get("name", "")
        # source_1.2x.mp4 のようなパターン
        match = re.search(r"source_(\d+\.?\d*)x", name)
        if match:
            return float(match.group(1))
        # 元の動画ファイル名の場合はspeed=1.0
        if name.endswith(".mp4") and "source_" not in name:
            return 1.0
    return 1.0


# ============================================================
# Transcription からテキスト抽出
# ============================================================


def load_transcription(trans_path: Path) -> list[dict]:
    """文字起こしJSONを読み込み、セグメントリストを返す"""
    data = json.loads(trans_path.read_text(encoding="utf-8"))
    return data.get("segments", [])


def extract_text_for_time_range_with_boundaries(segments: list[dict], time_ranges: list[list[float]]) -> list[dict]:
    """
    time_rangesに該当するセグメントをまとめて返す（重複排除）。
    各セグメントの start, end, text を含む。
    """
    seen = set()
    result = []
    for tr_start, tr_end in time_ranges:
        for seg in segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            if seg_start < tr_end and seg_end > tr_start:
                key = (seg_start, seg_end)
                if key not in seen:
                    seen.add(key)
                    result.append(seg)
    result.sort(key=lambda s: s["start"])
    return result


# ============================================================
# Suggestion照合
# ============================================================


def load_all_suggestions(video_dir: Path) -> list[dict]:
    """gpt-4.1.json と gpt-4.1-mini.json の suggestions を全てマージして返す。
    gpt-4.1.json を優先する（先頭に配置）。
    """
    suggestions = []
    seen_titles = set()

    for json_name in ["gpt-4.1.json", "gpt-4.1-mini.json"]:
        json_path = video_dir / "clip_suggestions" / json_name
        if not json_path.exists():
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        model_name = json_name.replace(".json", "")
        for sug in data.get("suggestions", []):
            title = sug["title"]
            if title not in seen_titles:
                seen_titles.add(title)
                sug["_source_model"] = model_name
                suggestions.append(sug)

    return suggestions


def find_suggestion_for_srt(
    srt_filename: str,
    all_suggestions: list[dict],
    suggestion_index_map: dict[int, list[dict]],
) -> dict | None:
    """
    SRTファイル名からsuggestionを特定する。
    1. タイトル完全一致
    2. 同じ番号のsuggestionから選択
    """
    stem = Path(srt_filename).stem
    match = re.match(r"(\d+)_(.*)", stem)
    if not match:
        return None
    clip_num = int(match.group(1))
    srt_title = match.group(2)

    # 1. タイトル完全一致
    for sug in all_suggestions:
        if sug["title"] == srt_title:
            return sug

    # 2. 同じ番号のsuggestionから（最初のものを使用）
    if clip_num in suggestion_index_map:
        return suggestion_index_map[clip_num][0]

    return None


def build_suggestion_index_map(suggestions: list[dict]) -> dict[int, list[dict]]:
    """suggestionsを番号順にインデックス化する。
    suggestionsは順序通りに1,2,3...と番号が振られる想定。
    """
    result = {}
    for i, sug in enumerate(suggestions):
        num = i + 1
        result.setdefault(num, []).append(sug)
    return result


# ============================================================
# メイン処理
# ============================================================


def process_video(config: dict) -> list[dict]:
    """1動画分の全SRTを処理"""
    video_dir = VIDEOS_DIR / config["dir_name"]
    fcpxml_dir = video_dir / "fcpxml_B_quality_41"
    trans_path = video_dir / "transcriptions" / "large-v3.json"

    if not fcpxml_dir.exists():
        print(f"  スキップ: {fcpxml_dir} が存在しません")
        return []

    # 文字起こしを読み込む
    segments = load_transcription(trans_path)
    print(f"  文字起こしセグメント数: {len(segments)}")

    # 全suggestionsをマージ
    all_suggestions = load_all_suggestions(video_dir)
    print(f"  マージ済みsuggestion数: {len(all_suggestions)}")

    # 番号→suggestionsのマッピングを構築
    # gpt-4.1.jsonのsuggestionsの順序を使う
    gpt41_path = video_dir / "clip_suggestions" / "gpt-4.1.json"
    if gpt41_path.exists():
        gpt41_data = json.loads(gpt41_path.read_text(encoding="utf-8"))
        primary_suggestions = gpt41_data.get("suggestions", [])
    else:
        gpt41_mini_path = video_dir / "clip_suggestions" / "gpt-4.1-mini.json"
        gpt41_mini_data = json.loads(gpt41_mini_path.read_text(encoding="utf-8"))
        primary_suggestions = gpt41_mini_data.get("suggestions", [])

    suggestion_index_map = build_suggestion_index_map(primary_suggestions)

    # SRTファイル一覧
    srt_files = sorted(fcpxml_dir.glob("*.srt"))
    print(f"  SRTファイル数: {len(srt_files)}")

    results = []
    for srt_path in srt_files:
        srt_filename = srt_path.name
        srt_entries = parse_srt(srt_path)

        # 対応するFCPXMLパス
        fcpxml_path = srt_path.with_suffix(".fcpxml")

        # SRTタイトルからsuggestionを特定
        suggestion = find_suggestion_for_srt(srt_filename, all_suggestions, suggestion_index_map)

        if suggestion is not None:
            time_ranges = suggestion["time_ranges"]
            source_info = f"suggestion ({suggestion.get('_source_model', '?')})"
            score = suggestion.get("score", "?")
            category = suggestion.get("category", "?")
            reasoning = suggestion.get("reasoning", "")
            variant_label = suggestion.get("variant_label", "")
            total_duration = suggestion.get("total_duration", sum(tr[1] - tr[0] for tr in time_ranges))
        elif fcpxml_path.exists():
            # FCPXMLからtime_rangesをフォールバック取得
            speed = detect_speed_from_fcpxml(fcpxml_path)
            time_ranges = extract_time_ranges_from_fcpxml(fcpxml_path, speed)
            source_info = f"FCPXML (speed={speed}x)"
            score = "?"
            category = "?"
            reasoning = "(suggestionに対応なし - FCPXMLから抽出)"
            variant_label = f"FCPXML解析"
            total_duration = sum(tr[1] - tr[0] for tr in time_ranges)
            print(f"    FCPXML解析: {srt_filename} (speed={speed}x, {len(time_ranges)}区間)")
        else:
            print(f"    スキップ: {srt_filename} (suggestionもFCPXMLも見つからず)")
            continue

        if not time_ranges:
            print(f"    スキップ: {srt_filename} (time_rangesが空)")
            continue

        # SRT字幕テキスト連結
        srt_text_parts = []
        for entry in srt_entries:
            text = entry["text"].replace("\n", "")
            srt_text_parts.append(text)
        srt_full_text = "".join(srt_text_parts)

        # 元の文字起こしの該当範囲テキスト
        matching_segs = extract_text_for_time_range_with_boundaries(segments, time_ranges)
        orig_full_text = "".join(seg["text"].strip() for seg in matching_segs)

        # time_rangesの情報
        total_start = min(tr[0] for tr in time_ranges)
        total_end = max(tr[1] for tr in time_ranges)

        results.append(
            {
                "srt_filename": srt_filename,
                "title": suggestion["title"] if suggestion else srt_filename.replace(".srt", ""),
                "score": score,
                "category": category,
                "reasoning": reasoning,
                "time_ranges": time_ranges,
                "total_start": total_start,
                "total_end": total_end,
                "total_duration": total_duration,
                "srt_text": srt_full_text,
                "orig_text": orig_full_text,
                "srt_entries": srt_entries,
                "matching_segs": matching_segs,
                "variant_label": variant_label,
                "source_info": source_info,
            }
        )

    return results


def generate_html(all_results: dict[str, list[dict]]) -> str:
    """HTMLレポートを生成"""

    total_clips = sum(len(v) for v in all_results.values())
    clip_sections = []

    for video_label, clips in all_results.items():
        clip_cards = []
        for clip in clips:
            # time_ranges を見やすくフォーマット
            tr_lines = []
            for i, (s, e) in enumerate(clip["time_ranges"]):
                tr_lines.append(f"{format_time(s)} - {format_time(e)} ({e-s:.1f}s)")
            tr_html = "<br>".join(escape(line) for line in tr_lines)

            # SRTテキスト（各エントリを段落で表示）
            srt_html_parts = []
            for entry in clip["srt_entries"]:
                ts = f'{format_time(entry["start"])} - {format_time(entry["end"])}'
                text = escape(entry["text"]).replace("\n", "<br>")
                srt_html_parts.append(
                    f'<div class="srt-entry">' f'<span class="ts">{escape(ts)}</span> ' f"{text}" f"</div>"
                )
            srt_html = "\n".join(srt_html_parts)

            # 元テキスト（セグメント単位で表示）
            orig_html_parts = []
            for seg in clip["matching_segs"]:
                ts = f'{format_time(seg["start"])} - {format_time(seg["end"])}'
                text = escape(seg["text"].strip())
                orig_html_parts.append(
                    f'<div class="orig-entry">' f'<span class="ts">{escape(ts)}</span> ' f"{text}" f"</div>"
                )
            orig_html = "\n".join(orig_html_parts)

            # テキスト差分の簡易比較（文字数）
            srt_len = len(clip["srt_text"])
            orig_len = len(clip["orig_text"])
            if orig_len > 0:
                ratio = srt_len / orig_len * 100
            else:
                ratio = 0

            # ソース情報のバッジ色
            source_class = "source-sug" if "suggestion" in clip["source_info"] else "source-fcpxml"

            clip_cards.append(
                f"""
            <div class="clip-card">
                <div class="clip-header">
                    <h3>{escape(clip["srt_filename"])}</h3>
                    <div class="clip-meta">
                        <span class="badge score">Score: {clip["score"]}</span>
                        <span class="badge category">{escape(str(clip["category"]))}</span>
                        <span class="badge variant">{escape(str(clip["variant_label"]))}</span>
                        <span class="badge duration">合計: {clip["total_duration"]:.1f}s</span>
                        <span class="badge range">{format_time(clip["total_start"])} - {format_time(clip["total_end"])}</span>
                        <span class="badge {source_class}">{escape(clip["source_info"])}</span>
                    </div>
                    <div class="reasoning">{escape(clip["reasoning"])}</div>
                </div>

                <div class="text-stats">
                    SRT文字数: {srt_len} / 元テキスト文字数: {orig_len} /
                    カバー率: {ratio:.1f}%
                </div>

                <div class="comparison">
                    <div class="col srt-col">
                        <h4>SRT字幕テキスト（切り抜き）</h4>
                        <div class="text-content">
                            {srt_html}
                        </div>
                        <div class="full-text">
                            <h5>連結テキスト:</h5>
                            <p>{escape(clip["srt_text"])}</p>
                        </div>
                    </div>
                    <div class="col orig-col">
                        <h4>元の文字起こし（該当範囲）</h4>
                        <div class="text-content">
                            {orig_html}
                        </div>
                        <div class="full-text">
                            <h5>連結テキスト:</h5>
                            <p>{escape(clip["orig_text"])}</p>
                        </div>
                    </div>
                </div>

                <details class="time-ranges-details">
                    <summary>time_ranges 詳細 ({len(clip["time_ranges"])}区間)</summary>
                    <div class="time-ranges">
                        {tr_html}
                    </div>
                </details>
            </div>
            """
            )

        clip_sections.append(
            f"""
        <section class="video-section">
            <h2>{escape(video_label)}</h2>
            <p class="clip-count">{len(clips)}クリップ</p>
            {"".join(clip_cards)}
        </section>
        """
        )

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <title>SRT vs 元文字起こし 比較レポート (Bパターン / gpt-4.1)</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
            background: #f5f5f5;
            color: #333;
            padding: 20px;
            line-height: 1.6;
        }}
        h1 {{
            text-align: center;
            margin-bottom: 10px;
            font-size: 1.5em;
            color: #1a1a1a;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 30px;
            font-size: 0.9em;
        }}
        .video-section {{
            margin-bottom: 40px;
        }}
        .video-section h2 {{
            background: #2c3e50;
            color: white;
            padding: 12px 20px;
            border-radius: 8px 8px 0 0;
            font-size: 1.1em;
        }}
        .clip-count {{
            background: #34495e;
            color: #bdc3c7;
            padding: 4px 20px;
            font-size: 0.85em;
        }}
        .clip-card {{
            background: white;
            border: 1px solid #ddd;
            border-radius: 0 0 8px 8px;
            margin-bottom: 20px;
            overflow: hidden;
        }}
        .clip-header {{
            padding: 15px 20px;
            border-bottom: 1px solid #eee;
            background: #fafafa;
        }}
        .clip-header h3 {{
            font-size: 1em;
            margin-bottom: 8px;
            color: #2c3e50;
        }}
        .clip-meta {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-bottom: 8px;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 500;
        }}
        .badge.score {{ background: #e8f5e9; color: #2e7d32; }}
        .badge.category {{ background: #e3f2fd; color: #1565c0; }}
        .badge.variant {{ background: #fff3e0; color: #e65100; }}
        .badge.duration {{ background: #f3e5f5; color: #7b1fa2; }}
        .badge.range {{ background: #e0f2f1; color: #00695c; }}
        .badge.source-sug {{ background: #e8eaf6; color: #283593; }}
        .badge.source-fcpxml {{ background: #fce4ec; color: #c62828; }}
        .reasoning {{
            font-size: 0.85em;
            color: #666;
            font-style: italic;
        }}
        .text-stats {{
            padding: 8px 20px;
            background: #f9f9f9;
            border-bottom: 1px solid #eee;
            font-size: 0.85em;
            color: #555;
        }}
        .comparison {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0;
        }}
        .col {{
            padding: 15px 20px;
        }}
        .srt-col {{
            border-right: 2px solid #e0e0e0;
            background: #fffde7;
        }}
        .orig-col {{
            background: #e8f5e9;
        }}
        .col h4 {{
            font-size: 0.9em;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 1px solid #ccc;
        }}
        .text-content {{
            max-height: 400px;
            overflow-y: auto;
        }}
        .srt-entry, .orig-entry {{
            margin-bottom: 4px;
            font-size: 0.88em;
            line-height: 1.5;
        }}
        .ts {{
            color: #999;
            font-size: 0.75em;
            font-family: "SF Mono", Menlo, monospace;
        }}
        .full-text {{
            margin-top: 12px;
            padding-top: 10px;
            border-top: 1px dashed #ccc;
        }}
        .full-text h5 {{
            font-size: 0.8em;
            color: #888;
            margin-bottom: 4px;
        }}
        .full-text p {{
            font-size: 0.85em;
            color: #444;
            line-height: 1.7;
            word-break: break-all;
        }}
        .time-ranges-details {{
            padding: 10px 20px;
            border-top: 1px solid #eee;
            font-size: 0.8em;
        }}
        .time-ranges-details summary {{
            cursor: pointer;
            color: #666;
            font-weight: 500;
        }}
        .time-ranges {{
            margin-top: 8px;
            color: #888;
            font-family: "SF Mono", Menlo, monospace;
            font-size: 0.9em;
            line-height: 1.8;
        }}
        @media (max-width: 900px) {{
            .comparison {{
                grid-template-columns: 1fr;
            }}
            .srt-col {{
                border-right: none;
                border-bottom: 2px solid #e0e0e0;
            }}
        }}
    </style>
</head>
<body>
    <h1>SRT字幕 vs 元の文字起こし 比較レポート</h1>
    <p class="subtitle">Bパターン (fcpxml_B_quality_41) / gpt-4.1 quality model / {total_clips}クリップ</p>

    {"".join(clip_sections)}

</body>
</html>"""
    return html


def main():
    all_results = {}

    for config in VIDEO_CONFIGS:
        label = config["label"]
        print(f"\n処理中: {label}")
        clips = process_video(config)
        all_results[label] = clips
        print(f"  完了: {len(clips)}クリップ")

    # HTML生成
    html = generate_html(all_results)

    # 出力
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nHTMLレポート生成完了: {OUTPUT_PATH}")
    print(f"合計クリップ数: {sum(len(v) for v in all_results.values())}")


if __name__ == "__main__":
    main()
