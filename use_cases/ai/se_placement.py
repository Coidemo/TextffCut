"""
AI効果音（SE）配置モジュール

GPT-4.1-miniで字幕テキスト・タイミングを分析し、
効果音の配置タイミングをAI判定する。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "se_placement.md"

DEFAULT_PROMPT = """\
あなたはYouTubeショート動画の効果音（SE）配置の専門家です。
字幕データを分析し、最適な効果音の配置を決定してください。

## 字幕データ
{SUBTITLES}

## 利用可能なSEファイル
{SE_FILES}

## 配置ルール
1. 盛り上がりポイント・感情変化・場面転換に合わせて配置
2. 同一SEの連続配置は避ける（メリハリ重視）
3. 字幕の開始タイミングに合わせる
4. 多すぎず少なすぎず（全体の30-50%の字幕にSEを付ける）
5. SEの雰囲気と字幕の内容を合わせる

## 出力JSON
```json
{
  "placements": [
    {
      "se_file": "キュピーン1.mp3",
      "timestamp": 1.5,
      "reason": "配置理由"
    }
  ]
}
```
"""


@dataclass
class SEPlacement:
    """SE配置結果"""

    se_file: str
    timestamp: float
    reason: str = ""


def _load_prompt() -> str:
    """プロンプトファイルを読み込む。存在しなければデフォルトを返す。"""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return DEFAULT_PROMPT


def _format_subtitles(subtitle_entries) -> str:
    """字幕エントリをテキスト形式にフォーマットする。"""
    lines = []
    for e in subtitle_entries:
        lines.append(
            f"#{e.index} [{e.start_time:.1f}s - {e.end_time:.1f}s] {e.text}"
        )
    return "\n".join(lines)


def _format_se_files(se_files: list[Path]) -> str:
    """SEファイル一覧をテキスト形式にフォーマットする。"""
    return "\n".join(f"- {p.name}" for p in se_files)


def plan_se_placements(
    client,
    subtitle_entries: list,
    se_files: list[Path],
    model: str = "gpt-4.1-mini",
) -> list[SEPlacement]:
    """
    字幕データからAI SE配置を計算する。

    Args:
        client: OpenAI クライアント
        subtitle_entries: SubtitleEntry のリスト
        se_files: 利用可能なSEファイルパスのリスト
        model: 使用モデル

    Returns:
        SEPlacement のリスト
    """
    if not subtitle_entries or not se_files:
        return []

    prompt_template = _load_prompt()
    prompt = prompt_template.replace(
        "{SUBTITLES}", _format_subtitles(subtitle_entries)
    ).replace(
        "{SE_FILES}", _format_se_files(se_files)
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
            temperature=0.3,
        )
        text = response.choices[0].message.content or ""
    except Exception as e:
        logger.warning(f"AI SE配置API呼び出し失敗: {e}")
        return []

    # JSON抽出
    try:
        if "```" in text:
            json_str = text.split("```json")[-1].split("```")[0].strip()
        else:
            start = text.find("{")
            end = text.rfind("}") + 1
            json_str = text[start:end]
        data = json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"AI SE配置JSON解析失敗: {e}")
        return []

    # SEファイル名のセット（バリデーション用）
    valid_se_names = {p.name for p in se_files}
    se_path_map = {p.name: str(p) for p in se_files}

    placements = []
    for item in data.get("placements", []):
        se_name = item.get("se_file", "")
        if se_name not in valid_se_names:
            logger.debug(f"不明なSEファイルをスキップ: {se_name}")
            continue

        timestamp = float(item.get("timestamp", 0))
        if timestamp < 0:
            continue

        placements.append(
            SEPlacement(
                se_file=se_path_map.get(se_name, se_name),
                timestamp=timestamp,
                reason=item.get("reason", ""),
            )
        )

    # タイムスタンプ順にソート
    placements.sort(key=lambda p: p.timestamp)
    return placements
