"""動画内テキスト塗りつぶし: 1 clip = 1 合成 PNG オーバーレイ方式 (v2.5.0)。

旧 AutoBlurUseCase は元動画 73 分すべてを再エンコードして source_blurred.mp4 を生成
していたが、ファイルサイズが元の 12 倍 (4.2GB) になる問題があった。

本 use case は元動画を一切再エンコードせず、clip 候補の time_ranges だけ OCR + track
して、**全 track の bbox を 1 枚の合成 PNG に OR 合成** する。FCPXML 出力時に asset-clip
として動画 (V1) の直上 (V2) に重ねることで、視覚的には同じ塗りつぶしを実現する。

メリット:
- ファイルサイズ削減 (4.2GB → 数十 KB / clip)
- OCR 範囲削減 (73 分 → 切り抜き候補 15 件 × 30-60 秒のみ)
- DaVinci 上で塗りつぶしを移動・削除・色変更できる
- 元動画は無加工

制約 (1 PNG 方式):
- clip 全範囲で常時表示 (時間切替なし) — 同じ lane=1 に複数 PNG を時間重複で
  並べると DaVinci で 1 枚しか描画されないため
- 各 bbox は周囲色サンプリングで個別の色で塗る (左下テキストと右上 UI で別色 OK)
- 流れるテロップなど位置が大きく動く UI には追従不可
  (配信動画のコメント欄/UI など固定位置 UI が主用途)

使用例:
    use_case = BlurOverlayUseCase()
    result = use_case.execute(
        video_path=Path("source.mp4"),
        clip_id="01_AIは道具",
        time_ranges=[(10.0, 40.0), (60.0, 90.0)],
        output_dir=Path("./blur_overlays"),
    )
    # result.overlays は 0 件 (track なし) または 1 件 (合成 PNG)
    for ov in result.overlays:
        print(f"  {ov.png_path.name}: {ov.start_sec:.1f}-{ov.end_sec:.1f}s")
"""

from __future__ import annotations

import json
import logging
import platform
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


def is_apple_silicon() -> bool:
    """Apple Silicon Mac (= ocrmac が使える環境) か判定。"""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


@dataclass
class BlurOverlayParams:
    """OCR + tracker のパラメータ。"""

    detect_scale: float = 0.5
    base_interval: float = 1.0  # OCR 検出間隔 (秒)。範囲狭いので短め
    padding: int = 12
    merge_gap_x: int = 60
    merge_gap_y: int = 40
    iou_threshold: float = 0.3
    # base_interval の数倍以上にしないと同一 UI を別 track として扱ってしまう
    max_gap_seconds: float = 8.0
    min_track_duration: float = 0.5  # この秒数より短い track は無視
    color_sample_border: int = 10
    languages: list[str] = field(default_factory=lambda: ["ja", "en"])
    # フレーム差分による検出スキップ (前フレームと変化なければ前回 bbox を再利用)
    skip_threshold: float = 0.02
    max_skip_streak: int = 15

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BlurOverlay:
    """1 clip 分の合成塗りつぶしオーバーレイ (v2 = 1 clip = 1 PNG)。

    Attributes:
        png_path: フルサイズ透過 PNG (動画解像度と同じ、複数 bbox を各々の色で OR 合成)。
            動画と同じ <adjust-conform type="fit"/> + scale/anchor を適用して配置する.
        start_sec: 元動画上の表示開始時刻 (= clip 候補の time_ranges 最小値)
        end_sec: 元動画上の表示終了時刻 (= clip 候補の time_ranges 最大値)
        union_x1, union_y1, union_x2, union_y2: 全 track の bbox を OR した外接矩形
            (記録/デバッグ用、PNG 描画では各 bbox を個別に塗っている)
    """

    png_path: Path
    start_sec: float
    end_sec: float
    union_x1: int
    union_y1: int
    union_x2: int
    union_y2: int

    def to_dict(self) -> dict:
        return {
            "png_path": str(self.png_path),
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "union_x1": self.union_x1,
            "union_y1": self.union_y1,
            "union_x2": self.union_x2,
            "union_y2": self.union_y2,
        }


@dataclass
class BlurOverlayResult:
    """clip 1 件分の塗りつぶしオーバーレイ生成結果。"""

    clip_id: str
    overlays: list[BlurOverlay]
    cached: bool
    duration_sec: float


class BlurOverlayUseCase:
    """clip 候補の time_ranges から塗りつぶし PNG を生成する。

    キャッシュは clip 単位で `{output_dir}/{clip_id}.overlays.json` に PNG パスと
    時刻範囲を保存する。同じ time_ranges + params + sidecar version で再呼び出し
    すると cache hit。
    """

    SIDECAR_SUFFIX = ".overlays.json"
    # v1: 1 track = 1 PNG (track ごと別 PNG, 時間範囲で出し分け) — 同時刻に複数 track
    #     が存在する場合 DaVinci で 1 枚しか描画されないバグがあった
    # v2: 1 clip = 1 合成 PNG (全 track の bbox を 1 枚に OR 合成、clip 全範囲で常時表示)
    SIDECAR_VERSION = 3  # v3: PNG ファイル名を {clip_id}_blur.png に変更
    # (旧 v1=track 1 PNG, v2={clip_id}.png, v3={clip_id}_blur.png — title PNG との
    # name 衝突を avoid)

    def __init__(self, params: BlurOverlayParams | None = None) -> None:
        self.params = params or BlurOverlayParams()

    def get_sidecar_path(self, output_dir: Path, clip_id: str) -> Path:
        return output_dir / f"{clip_id}{self.SIDECAR_SUFFIX}"

    def is_cached(
        self,
        video_path: Path,
        clip_id: str,
        time_ranges: list[tuple[float, float]],
        output_dir: Path,
    ) -> bool:
        """cache が有効か (params + time_ranges + 動画 mtime/size 一致) チェック。"""
        sidecar = self.get_sidecar_path(output_dir, clip_id)
        if not sidecar.exists():
            return False
        try:
            data = json.loads(sidecar.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        # 旧スキーマ (v1: 1 track = 1 PNG) のキャッシュは無効化
        if data.get("version") != self.SIDECAR_VERSION:
            return False
        if data.get("params") != self.params.to_dict():
            return False
        cached_ranges = data.get("time_ranges", [])
        if cached_ranges != [list(r) for r in time_ranges]:
            return False
        try:
            stat = video_path.stat()
        except OSError:
            return False
        if (
            abs(data.get("source_mtime", 0) - stat.st_mtime) > 1.0
            or data.get("source_size", 0) != stat.st_size
        ):
            return False
        # PNG ファイルが全部存在するか
        for ov_dict in data.get("overlays", []):
            if not Path(ov_dict["png_path"]).exists():
                return False
        return True

    def load_from_cache(
        self, output_dir: Path, clip_id: str
    ) -> list[BlurOverlay]:
        """cache 済 sidecar から overlays を復元。"""
        sidecar = self.get_sidecar_path(output_dir, clip_id)
        data = json.loads(sidecar.read_text())
        return [
            BlurOverlay(
                png_path=Path(ov["png_path"]),
                start_sec=float(ov["start_sec"]),
                end_sec=float(ov["end_sec"]),
                union_x1=int(ov["union_x1"]),
                union_y1=int(ov["union_y1"]),
                union_x2=int(ov["union_x2"]),
                union_y2=int(ov["union_y2"]),
            )
            for ov in data.get("overlays", [])
        ]

    def execute(
        self,
        video_path: Path,
        clip_id: str,
        time_ranges: list[tuple[float, float]],
        output_dir: Path,
    ) -> BlurOverlayResult:
        """指定 time_ranges で OCR + track → 各 track の塗りつぶし PNG を生成。

        Args:
            video_path: 元動画 (無加工)
            clip_id: ファイル名プレフィクス (e.g. "01_AIは道具")
            time_ranges: 元動画上の時刻範囲リスト [(start_sec, end_sec), ...]
            output_dir: PNG 出力ディレクトリ ({video}_TextffCut/blur_overlays/)

        Returns:
            BlurOverlayResult
        """
        if not is_apple_silicon():
            logger.warning(
                "Apple Silicon Mac 以外では ocrmac が使えないため塗りつぶし生成をスキップ"
            )
            return BlurOverlayResult(clip_id=clip_id, overlays=[], cached=False, duration_sec=0.0)

        output_dir.mkdir(parents=True, exist_ok=True)

        if self.is_cached(video_path, clip_id, time_ranges, output_dir):
            overlays = self.load_from_cache(output_dir, clip_id)
            return BlurOverlayResult(
                clip_id=clip_id, overlays=overlays, cached=True, duration_sec=0.0
            )

        t0 = time.time()

        # AI 切り抜き候補の time_ranges は細切れ (~0.5s) になることがあるため、
        # 全体の min/max で 1 つの大きな range として OCR + track 化する。
        # UI は飛び飛びの time_range をまたいで連続的に映るので、これで track が成立する。
        if not time_ranges:
            big_start, big_end = 0.0, 0.0
        else:
            big_start = min(r[0] for r in time_ranges)
            big_end = max(r[1] for r in time_ranges)

        tracks = _detect_and_track_in_range(
            video_path=video_path,
            start_sec=big_start,
            end_sec=big_end,
            params=self.params,
        )

        # **1 clip = 1 合成 PNG 方式 (v2.5.0)**:
        # 全 track の bbox を 1 枚の PNG に OR 合成して clip 全範囲 [big_start, big_end]
        # で常時表示する. 同じ lane=1 に複数 PNG を時刻重複で並べると DaVinci 上で
        # 1 枚しか表示されないため. 時間で出したり消したりはしない.
        all_overlays: list[BlurOverlay] = []
        if tracks:
            # title_images/{clip_id}.png と同名にならないよう "_blur" suffix を付ける
            # (DaVinci の <asset name="..."> 衝突回避、PR #151)
            png_path = output_dir / f"{clip_id}_blur.png"
            bboxes_with_colors: list[tuple[int, int, int, int, tuple[int, int, int]]] = []
            for track in tracks:
                ux1, uy1, ux2, uy2 = _track_union_bbox(track, self.params.padding)
                bboxes_with_colors.append((ux1, uy1, ux2, uy2, track.fill_color))

            _render_composite_overlay_png(
                png_path=png_path,
                video_path=video_path,
                bboxes_with_colors=bboxes_with_colors,
            )

            # 合成 PNG の bbox = 全 track の OR (sidecar 記録用)
            comp_x1 = min(b[0] for b in bboxes_with_colors)
            comp_y1 = min(b[1] for b in bboxes_with_colors)
            comp_x2 = max(b[2] for b in bboxes_with_colors)
            comp_y2 = max(b[3] for b in bboxes_with_colors)
            all_overlays.append(
                BlurOverlay(
                    png_path=png_path,
                    start_sec=big_start,
                    end_sec=big_end,
                    union_x1=comp_x1, union_y1=comp_y1, union_x2=comp_x2, union_y2=comp_y2,
                )
            )

        elapsed = time.time() - t0

        # sidecar 保存
        try:
            stat = video_path.stat()
            sidecar_data = {
                "version": self.SIDECAR_VERSION,
                "params": self.params.to_dict(),
                "time_ranges": [list(r) for r in time_ranges],
                "source_video": str(video_path),
                "source_size": stat.st_size,
                "source_mtime": stat.st_mtime,
                "overlays": [ov.to_dict() for ov in all_overlays],
                "track_count": len(tracks),
            }
            self.get_sidecar_path(output_dir, clip_id).write_text(
                json.dumps(sidecar_data, ensure_ascii=False, indent=2)
            )
        except OSError as e:
            logger.warning(f"sidecar 保存失敗: {e}")

        logger.info(
            f"塗りつぶし overlay 生成: {clip_id} ({len(tracks)} tracks → "
            f"{len(all_overlays)} 合成 PNG, {elapsed:.1f}s)"
        )
        return BlurOverlayResult(
            clip_id=clip_id, overlays=all_overlays, cached=False, duration_sec=elapsed
        )


def _track_union_bbox(track, padding: int) -> tuple[int, int, int, int]:
    """track 内全 bbox を OR 結合した最大エリア (padding 適用後)。"""
    x1 = min(p.box.x1 for p in track.points)
    y1 = min(p.box.y1 for p in track.points)
    x2 = max(p.box.x2 for p in track.points)
    y2 = max(p.box.y2 for p in track.points)
    return (
        max(0, x1 - padding),
        max(0, y1 - padding),
        x2 + padding,
        y2 + padding,
    )


def _detect_and_track_in_range(
    video_path: Path,
    start_sec: float,
    end_sec: float,
    params: BlurOverlayParams,
) -> list:
    """指定 time_range で OCR + track。chunk_worker.process_full_chunk の Step 1-5 相当。"""
    import cv2

    from core.text_blur.detector import OcrmacDetector, merge_boxes, sample_edge_color
    from core.text_blur.tracker import build_tracks, filter_short_tracks

    duration = end_sec - start_sec
    if duration <= 0:
        return []

    # サンプリング時刻 (= start_sec 起点でローカル時刻、最後に start_sec を加算)
    edge_offset = 0.1
    timestamps: set[float] = {edge_offset}
    t = params.base_interval
    while t < duration:
        timestamps.add(round(t, 4))
        t += params.base_interval
    timestamps.add(round(max(0.0, duration - edge_offset), 4))
    timestamps_sorted = sorted(timestamps)

    detector = OcrmacDetector(
        languages=params.languages, detect_scale=params.detect_scale
    )

    cap = cv2.VideoCapture(str(video_path))
    src_fps = cap.get(cv2.CAP_PROP_FPS)

    detections: list[tuple[float, list]] = []
    last_small = None
    last_boxes = None
    skip_streak = 0
    diff_resize = (320, 180)

    for t_local in timestamps_sorted:
        if t_local < 0 or t_local >= duration:
            continue
        t_abs = start_sec + t_local
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_abs * src_fps)))
        ret, frame = cap.read()
        if not ret:
            continue

        # 前フレーム差分でスキップ判定
        if (
            params.skip_threshold > 0.0
            and last_small is not None
            and last_boxes is not None
            and skip_streak < params.max_skip_streak
        ):
            current_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            diff = float(cv2.absdiff(current_small, last_small).mean()) / 255.0
            if diff < params.skip_threshold:
                detections.append((t_local, last_boxes))
                skip_streak += 1
                continue

        raw_boxes = detector.detect(frame)
        merged = merge_boxes(raw_boxes, gap_x=params.merge_gap_x, gap_y=params.merge_gap_y)
        detections.append((t_local, merged))
        if params.skip_threshold > 0.0:
            last_small = cv2.resize(frame, diff_resize, interpolation=cv2.INTER_AREA)
            last_boxes = merged
            skip_streak = 0

    # tracking
    tracks = build_tracks(
        detections,
        iou_threshold=params.iou_threshold,
        max_gap_seconds=params.max_gap_seconds,
    )
    if params.min_track_duration > 0:
        tracks = filter_short_tracks(tracks, params.min_track_duration)

    # 各 track の代表 frame で fill_color サンプリング
    for tr in tracks:
        t_mid_local = (tr.t_start + tr.t_end) / 2
        t_mid_abs = start_sec + t_mid_local
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t_mid_abs * src_fps)))
        ret, frame = cap.read()
        if not ret:
            continue
        ub = _track_union_bbox(tr, params.padding)
        h, w = frame.shape[:2]
        # bbox は元動画座標系。frame と同じサイズなのでそのまま渡す
        from core.text_blur.detector import Box

        ub_box = Box(ub[0], ub[1], min(ub[2], w), min(ub[3], h))
        tr.fill_color = sample_edge_color(
            frame, ub_box, border_width=params.color_sample_border
        )

    cap.release()
    return tracks


def _render_composite_overlay_png(
    png_path: Path,
    video_path: Path,
    bboxes_with_colors: list[tuple[int, int, int, int, tuple[int, int, int]]],
) -> None:
    """動画解像度と同じサイズの透過 PNG を生成し、複数 bbox を各々の fill_color で塗る.

    各 bbox は (x1, y1, x2, y2, fill_color_bgr) のタプル. 重なりがあれば後の bbox の
    色で上書きする (現状 track 同士は merge_boxes/IoU で分離済みなので通常重ならない).

    DaVinci 上で配置時は動画と同じ <adjust-conform type="fit"/> + scale/anchor を
    適用するため、座標変換は呼び出し側で行う.
    """
    import cv2
    import numpy as np

    cap = cv2.VideoCapture(str(video_path))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    # RGBA 透過画像 (height, width, 4)
    img = np.zeros((height, width, 4), dtype=np.uint8)

    for x1, y1, x2, y2, fill_color_bgr in bboxes_with_colors:
        b, g, r = fill_color_bgr
        cx1 = max(0, x1)
        cy1 = max(0, y1)
        cx2 = min(width, x2)
        cy2 = min(height, y2)
        if cx2 > cx1 and cy2 > cy1:
            img[cy1:cy2, cx1:cx2] = [b, g, r, 255]

    png_path.parent.mkdir(parents=True, exist_ok=True)
    # cv2.imwrite は BGRA 順で書く
    cv2.imwrite(str(png_path), img)
