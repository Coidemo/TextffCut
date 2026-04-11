"""
アンカーポイント自動検出モジュール

Vision AI（GPT-4o）で動画フレームを分析し、
縦型（vertical）タイムラインでのズーム・回転の中心点を検出する。
"""

from __future__ import annotations

import base64
import json
import logging
import re
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
  "anchor_y": 0.5,
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


def _extract_json(text: str) -> str:
    """AIレスポンスからJSON文字列を抽出する。"""
    # ```json ... ``` または ``` ... ``` ブロックを探す
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # 直接JSONを探す
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    raise ValueError(f"AIレスポンスからJSONを抽出できません: {text[:200]}")


def _extract_frame(video_path: Path, time_sec: float = 5.0) -> bytes:
    """動画から指定時刻のフレームをJPEGとして抽出する。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(time_sec),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(tmp_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        data = tmp_path.read_bytes()
        if not data:
            raise RuntimeError(f"フレーム抽出に失敗: {video_path} の {time_sec}秒地点にフレームがありません")
        return data
    finally:
        tmp_path.unlink(missing_ok=True)


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
    logger.info("アンカー検出開始: %s (%.1f秒)", video_path.name, frame_time)
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
    logger.info("アンカー検出APIレスポンス: %s", text[:200])
    try:
        json_str = _extract_json(text)
        data = json.loads(json_str)
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning("アンカー検出JSON解析失敗: %s — レスポンス: %s", e, text[:200])
        return AnchorResult(anchor_x=0.5, anchor_y=0.5, description="解析失敗、デフォルト使用")

    ax = float(data.get("anchor_x", 0.5))
    ay = float(data.get("anchor_y", 0.5))
    ax = max(0.0, min(1.0, ax))
    ay = max(0.0, min(1.0, ay))

    result = AnchorResult(
        anchor_x=ax,
        anchor_y=ay,
        description=str(data.get("description", "")),
    )
    logger.info("アンカー検出結果: (%.2f, %.2f) — %s", ax, ay, result.description)
    return result


def anchor_to_fcpxml(
    anchor_x: float,
    anchor_y: float,
    src_w: int,
    src_h: int,
    scale: tuple[float, float],
) -> tuple[float, float]:
    """正規化座標(0-1)をFCPXMLアンカー座標系に変換する。

    Args:
        anchor_x: 正規化X座標 (0.0=左端, 1.0=右端)
        anchor_y: 正規化Y座標 (0.0=上端, 1.0=下端)
        src_w: ソース動画の幅(px)
        src_h: ソース動画の高さ(px)
        scale: ズーム倍率 (x, y)

    Returns:
        FCPXML座標系の (anchor_x, anchor_y)
    """
    sx = scale[0] if scale[0] > 0 else 1.0
    sy = scale[1] if scale[1] > 0 else 1.0
    return (
        (anchor_x - 0.5) * 100 / sx,
        -(anchor_y - 0.5) * 100 * src_w / src_h / sy,
    )
