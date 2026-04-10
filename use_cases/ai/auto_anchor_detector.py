"""
アンカーポイント自動検出モジュール

Vision AI（GPT-4o）で動画フレームを分析し、
縦型（vertical）タイムラインでのズーム・回転の中心点を検出する。
"""

from __future__ import annotations

import base64
import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPT_FILE = Path(__file__).parent.parent.parent / "prompts" / "anchor_detection.md"

DEFAULT_PROMPT = """\
この動画フレームを分析して、縦型ショート動画用のアンカーポイント（ズーム・回転の中心）を決定してください。

## 判定基準
- 話者の顔が映っている場合: 顔の中心付近
- 複数人の場合: メインの話者
- テロップや字幕がある場合: それらを避ける
- 話者がいない場合: 最も重要な被写体の中心

## 出力JSON
```json
{
  "anchor_x": 0.5,
  "anchor_y": 0.3,
  "description": "判定理由の簡潔な説明"
}
```

- anchor_x: 0.0（左端）〜 1.0（右端）
- anchor_y: 0.0（上端）〜 1.0（下端）
"""


@dataclass
class AnchorResult:
    """アンカー検出結果"""

    anchor_x: float
    anchor_y: float
    description: str


def _extract_frame(video_path: Path, time_sec: float = 5.0) -> bytes:
    """動画から指定時刻のフレームをJPEGとして抽出する。"""
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=True) as tmp:
        cmd = [
            "ffmpeg", "-y", "-ss", str(time_sec),
            "-i", str(video_path),
            "-frames:v", "1", "-q:v", "2",
            tmp.name,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return Path(tmp.name).read_bytes()


def _load_prompt() -> str:
    """プロンプトファイルを読み込む。存在しなければデフォルトを返す。"""
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    return DEFAULT_PROMPT


def detect_anchor(
    video_path: Path,
    client,
    model: str = "gpt-4o",
    frame_time: float = 5.0,
) -> AnchorResult:
    """
    動画フレームからアンカーポイントを検出する。

    Args:
        video_path: 動画ファイルパス
        client: OpenAI クライアント
        model: 使用モデル（デフォルト: gpt-4o）
        frame_time: 分析するフレームの時刻（秒）

    Returns:
        AnchorResult: 検出結果
    """
    frame_bytes = _extract_frame(video_path, frame_time)
    b64 = base64.b64encode(frame_bytes).decode()
    prompt = _load_prompt()

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ],
        max_tokens=256,
        temperature=0.2,
    )

    text = response.choices[0].message.content or ""

    # JSON抽出（```json ... ``` ブロックまたは直接JSON）
    if "```" in text:
        json_str = text.split("```json")[-1].split("```")[0].strip()
    else:
        start = text.find("{")
        end = text.rfind("}") + 1
        json_str = text[start:end]

    data = json.loads(json_str)

    ax = float(data.get("anchor_x", 0.5))
    ay = float(data.get("anchor_y", 0.3))
    ax = max(0.0, min(1.0, ax))
    ay = max(0.0, min(1.0, ay))

    return AnchorResult(
        anchor_x=ax,
        anchor_y=ay,
        description=data.get("description", ""),
    )
