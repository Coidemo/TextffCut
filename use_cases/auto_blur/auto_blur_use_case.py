"""動画内テキスト自動ぼかしのユースケース.

役割:
- パラメータベースのキャッシュ層 ({video}_TextffCut/source_blurred.mp4 + sidecar)
- 内部で full-chunk 並列パイプラインを起動
- 速度変更は適用しない (生のぼかし版を保存し、後段の clip step で speed 適用)

使用例:
    use_case = AutoBlurUseCase()
    if not use_case.is_cached(video_path):
        result = use_case.execute(video_path)
        print(f"ぼかし完了: {result.blurred_path} ({result.duration_sec:.1f}s)")
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import json
import platform
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable


def is_apple_silicon() -> bool:
    """Apple Silicon Mac (M1/M2/M3/M4 etc.) かどうか判定.

    auto_blur は ocrmac (Apple Vision API) に依存するため Apple Silicon Mac 専用.
    Intel Mac / Linux / Windows 等では機能しない.
    """
    return platform.system() == "Darwin" and platform.machine() == "arm64"


@dataclass
class AutoBlurParams:
    """ぼかし処理のパラメータ. cache invalidation key として使う."""

    detect_scale: float = 0.5
    scene_detect: bool = True
    scene_threshold: float = 0.1
    base_interval: float = 10.0
    blur_sigma: float = 40.0
    padding: int = 12
    merge_gap_x: int = 60
    merge_gap_y: int = 40
    iou_threshold: float = 0.3
    max_gap_seconds: float = 15.0
    persistence: float = 8.0
    skip_threshold: float = 0.02
    max_skip_streak: int = 15
    encoder: str = "h264_videotoolbox"
    bitrate: str = "8M"
    full_chunks: int = 4
    languages: list[str] = field(default_factory=lambda: ["ja", "en"])
    # 色サンプリング: bbox 縁のサンプリング幅 (px)
    color_sample_border: int = 10
    # フレーム差分計算用 resize サイズ (cv2.resize の (width, height))
    diff_resize_w: int = 320
    diff_resize_h: int = 180
    # ffmpeg subprocess timeout (秒). チャンクごとの処理時間上限
    ffmpeg_timeout_sec: int = 1200  # 20 分

    def to_dict(self) -> dict:
        return asdict(self)

    def hash_key(self) -> str:
        """sha256 を 16 桁に切り詰めた cache key."""
        s = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(s.encode()).hexdigest()[:16]


@dataclass
class AutoBlurResult:
    blurred_path: Path
    cached: bool
    duration_sec: float


class AutoBlurUseCase:
    """動画内テキストの自動ぼかし.

    結果は {video_name}_TextffCut/source_blurred.mp4 にキャッシュされる.
    再実行で同パラメータならスキップ (cached=True).
    """

    OUTPUT_FILENAME = "source_blurred.mp4"
    SIDECAR_FILENAME = "source_blurred.params.json"

    def __init__(self, params: AutoBlurParams | None = None) -> None:
        self.params = params or AutoBlurParams()

    def get_cache_paths(self, video_path: Path) -> tuple[Path, Path]:
        """({video}_TextffCut/source_blurred.mp4, sidecar params.json) を返す."""
        base_dir = video_path.parent / f"{video_path.stem}_TextffCut"
        return (
            base_dir / self.OUTPUT_FILENAME,
            base_dir / self.SIDECAR_FILENAME,
        )

    def is_cached(self, video_path: Path) -> bool:
        """cache が有効か (params 一致 + ファイル存在 + 元動画 mtime 一致) チェック.

        Apple Silicon 非依存: 別マシン (Intel Mac 等) で生成された cache でも
        ファイル整合性が取れていれば True を返す. cache を「読むだけ」なら
        ocrmac は不要なので、この設計で意図的に platform 非依存.
        """
        out_path, sidecar_path = self.get_cache_paths(video_path)
        if not out_path.exists() or not sidecar_path.exists():
            return False
        try:
            cached = json.loads(sidecar_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        if cached.get("hash_key") != self.params.hash_key():
            return False
        # 元動画が更新されていたら無効化
        try:
            current_mtime = video_path.stat().st_mtime
            current_size = video_path.stat().st_size
        except OSError:
            return False
        if (
            abs(cached.get("source_mtime", 0) - current_mtime) > 1.0
            or cached.get("source_size", 0) != current_size
        ):
            return False
        return True

    def execute(
        self,
        video_path: Path,
        progress_callback: Callable[[int, int, dict], None] | None = None,
    ) -> AutoBlurResult:
        """ぼかし動画を生成 (or cache hit でスキップ).

        Args:
            video_path: 元動画ファイルパス
            progress_callback: (done_chunks, total_chunks, stats) を受け取る進捗コールバック

        Returns:
            AutoBlurResult (blurred_path, cached, duration_sec)
        """
        out_path, sidecar_path = self.get_cache_paths(video_path)

        if self.is_cached(video_path):
            return AutoBlurResult(blurred_path=out_path, cached=True, duration_sec=0.0)

        out_path.parent.mkdir(parents=True, exist_ok=True)

        t0 = time.time()
        try:
            _run_full_chunk_pipeline(
                input_path=video_path,
                output_path=out_path,
                params=self.params,
                speed=1.0,  # speed 変更はここでは適用しない
                progress_callback=progress_callback,
            )
        except Exception:
            # 失敗時に破損 mp4 や前回中途終了で残った古い sidecar を一掃する.
            # (この時点で sidecar はまだ未書き込みだが、防御的にクリーンアップ)
            out_path.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)
            raise
        elapsed = time.time() - t0

        # sidecar 保存
        try:
            stat = video_path.stat()
            sidecar_data = {
                "hash_key": self.params.hash_key(),
                "params": self.params.to_dict(),
                "source_video": str(video_path),
                "source_size": stat.st_size,
                "source_mtime": stat.st_mtime,
                "duration_sec": elapsed,
            }
            sidecar_path.write_text(json.dumps(sidecar_data, ensure_ascii=False, indent=2))
        except OSError:
            pass

        return AutoBlurResult(blurred_path=out_path, cached=False, duration_sec=elapsed)


def _run_full_chunk_pipeline(
    input_path: Path,
    output_path: Path,
    params: AutoBlurParams,
    speed: float,
    progress_callback: Callable[[int, int, dict], None] | None,
) -> None:
    """full-chunk 並列パイプラインを実行.

    各 chunk が独立に scene_detect + detect + ffmpeg blur を走らせ、最後に concat.
    """
    import cv2

    from core.text_blur.chunk_worker import process_full_chunk

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        raise RuntimeError(f"動画を開けません: {input_path}")
    src_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / src_fps
    cap.release()

    n_chunks = max(1, params.full_chunks)
    chunk_dur = duration / n_chunks

    with tempfile.TemporaryDirectory() as tmpdir_s:
        tmpdir = Path(tmpdir_s)
        chunk_paths: list[Path] = []
        worker_args: list[dict] = []

        for i in range(n_chunks):
            abs_start = i * chunk_dur
            this_dur = (duration - abs_start) if i == n_chunks - 1 else chunk_dur
            chunk_path = tmpdir / f"chunk_{i:04d}.mp4"
            chunk_paths.append(chunk_path)
            worker_args.append(
                {
                    "chunk_idx": i,
                    "input_video": str(input_path),
                    "output_path": str(chunk_path),
                    "abs_start": abs_start,
                    "abs_dur": this_dur,
                    "scene_threshold": params.scene_threshold,
                    "scene_detect": params.scene_detect,
                    "base_interval": params.base_interval,
                    "detector_backend": "ocrmac",
                    "languages": params.languages,
                    "detect_scale": params.detect_scale,
                    "merge_gap_x": params.merge_gap_x,
                    "merge_gap_y": params.merge_gap_y,
                    "iou_threshold": params.iou_threshold,
                    "max_gap_seconds": params.max_gap_seconds,
                    "persistence": params.persistence,
                    "min_track_duration": 0.0,
                    "padding": params.padding,
                    "skip_threshold": params.skip_threshold,
                    "max_skip_streak": params.max_skip_streak,
                    "speed": speed,
                    "encoder": params.encoder,
                    "crf": 20,
                    "preset": "medium",
                    "bitrate": params.bitrate,
                    "color_sample_border": params.color_sample_border,
                    "diff_resize_w": params.diff_resize_w,
                    "diff_resize_h": params.diff_resize_h,
                    "ffmpeg_timeout_sec": params.ffmpeg_timeout_sec,
                }
            )

        with futures.ProcessPoolExecutor(max_workers=n_chunks) as pool:
            done = 0
            for fut in futures.as_completed(
                [pool.submit(process_full_chunk, a) for a in worker_args]
            ):
                stats = fut.result()
                done += 1
                if progress_callback is not None:
                    progress_callback(done, n_chunks, stats)

        # concat (再エンコードなし)
        list_file = tmpdir / "concat_list.txt"
        with list_file.open("w") as f:
            for cp in chunk_paths:
                f.write(f"file '{cp}'\n")
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-loglevel",
            "error",
            str(output_path),
        ]
        # concat は -c copy なので 60 秒程度で十分 (4 chunk なら数秒)
        subprocess.run(cmd, check=True, timeout=300)
