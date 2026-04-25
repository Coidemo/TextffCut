"""文字起こし修正ツールの HTTP サーバ。

用途:
    transcribe_for_lora.py で生成した JSON + 原動画を入力に、
    ブラウザ上でセグメント毎に音声を再生しながらテキスト修正できる UI を提供する。

実行:
    python server.py /path/to/data.json /path/to/video.mp4
    → http://localhost:8000/ を開く

保存:
    編集結果は {json_path の stem}.edited.json に保存される。
    auto-save が 30 秒毎に走るほか、UI 上の保存ボタンと Cmd+S でも保存できる。

依存:
    Python 標準ライブラリのみ + ffmpeg (音声抽出に使用)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

STATIC_DIR = Path(__file__).parent / "static"
AUDIO_CACHE = Path(__file__).parent / ".audio_cache"

# グローバルに持つ（HTTPServer のシンプルな実装のため）
_json_path: Path | None = None
_audio_path: Path | None = None


def extract_audio(video_path: Path) -> Path:
    """動画から MP3 を抽出してキャッシュに置く。既に存在すればスキップ。"""
    AUDIO_CACHE.mkdir(exist_ok=True)
    out_path = AUDIO_CACHE / f"{video_path.stem}.mp3"
    if out_path.exists():
        return out_path
    print(f"音声抽出中: {video_path.name} -> {out_path.name}")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(out_path),
        ],
        check=True,
        capture_output=True,
    )
    return out_path


def send_file_with_range(handler: BaseHTTPRequestHandler, path: Path, content_type: str) -> None:
    """Range リクエスト対応のファイル送信（音声シーク用）。"""
    if not path.exists():
        handler.send_error(404, f"Not found: {path}")
        return
    total = path.stat().st_size
    range_header = handler.headers.get("Range", "")
    m = re.match(r"bytes=(\d*)-(\d*)", range_header)

    if m:
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else total - 1
        end = min(end, total - 1)
        length = end - start + 1
        handler.send_response(206)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Range", f"bytes {start}-{end}/{total}")
        handler.send_header("Content-Length", str(length))
        handler.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            handler.wfile.write(f.read(length))
    else:
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Accept-Ranges", "bytes")
        handler.send_header("Content-Length", str(total))
        handler.end_headers()
        handler.wfile.write(path.read_bytes())


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        routes = {
            "/": (STATIC_DIR / "index.html", "text/html; charset=utf-8"),
            "/app.js": (STATIC_DIR / "app.js", "application/javascript; charset=utf-8"),
            "/styles.css": (STATIC_DIR / "styles.css", "text/css; charset=utf-8"),
            "/data": (_json_path, "application/json; charset=utf-8"),
        }
        if parsed.path in routes:
            path, ctype = routes[parsed.path]
            send_file_with_range(self, path, ctype)
        elif parsed.path == "/audio":
            send_file_with_range(self, _audio_path, "audio/mpeg")
        else:
            self.send_error(404, f"Unknown path: {parsed.path}")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/save":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        assert _json_path is not None
        out_path = _json_path.with_name(f"{_json_path.stem}.edited.json")
        out_path.write_bytes(body)
        print(f"保存: {out_path}")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"ok": True, "path": str(out_path)}).encode("utf-8"))

    def log_message(self, *args: object) -> None:
        # アクセスログは抑制（音声シークで大量発生するため）
        pass


def main() -> None:
    global _json_path, _audio_path

    parser = argparse.ArgumentParser()
    parser.add_argument("json", type=Path, help="transcribe_for_lora.py が出力した JSON")
    parser.add_argument("video", type=Path, help="動画 or 音声ファイル")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="自動でブラウザを開かない")
    args = parser.parse_args()

    if not args.json.exists():
        print(f"JSON が見つかりません: {args.json}", file=sys.stderr)
        sys.exit(1)
    if not args.video.exists():
        print(f"動画/音声が見つかりません: {args.video}", file=sys.stderr)
        sys.exit(1)

    _json_path = args.json.resolve()
    _audio_path = extract_audio(args.video.resolve())

    edited_path = _json_path.with_name(f"{_json_path.stem}.edited.json")

    print()
    print("=" * 64)
    print(f"  URL:       http://localhost:{args.port}/")
    print(f"  JSON:      {_json_path}")
    print(f"  Audio:     {_audio_path}")
    print(f"  保存先:    {edited_path}")
    print("=" * 64)
    print("  Ctrl-C で停止")
    print()

    if not args.no_browser:
        webbrowser.open(f"http://localhost:{args.port}/")

    try:
        HTTPServer(("localhost", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")


if __name__ == "__main__":
    main()
