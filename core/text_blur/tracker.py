"""P3: bbox 時系列を IoU マッチングで track にまとめ、短時間ギャップを補間.

入力: [(timestamp, [Box,...]), ...]
出力: list of Track. 各 Track は連続時間範囲で同一物体の bbox 系列.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from core.text_blur.detector import Box


@dataclass
class TrackPoint:
    timestamp: float
    box: Box


@dataclass
class Track:
    points: list[TrackPoint] = field(default_factory=list)
    # solid fill mode で使う: 周囲のサンプリング色 (BGR). デフォルトはグレー.
    fill_color: tuple[int, int, int] = (128, 128, 128)

    @property
    def t_start(self) -> float:
        return self.points[0].timestamp

    @property
    def t_end(self) -> float:
        return self.points[-1].timestamp

    @property
    def duration(self) -> float:
        return self.t_end - self.t_start

    def latest_box(self) -> Box:
        return self.points[-1].box

    def box_at(self, t: float) -> Box:
        """指定時刻の bbox を線形補間で返す.

        範囲外は端点をそのまま返す.
        """
        if t <= self.points[0].timestamp:
            return self.points[0].box
        if t >= self.points[-1].timestamp:
            return self.points[-1].box

        for i in range(len(self.points) - 1):
            p0, p1 = self.points[i], self.points[i + 1]
            if p0.timestamp <= t <= p1.timestamp:
                if p1.timestamp == p0.timestamp:
                    return p0.box
                ratio = (t - p0.timestamp) / (p1.timestamp - p0.timestamp)
                return Box(
                    int(round(p0.box.x1 + (p1.box.x1 - p0.box.x1) * ratio)),
                    int(round(p0.box.y1 + (p1.box.y1 - p0.box.y1) * ratio)),
                    int(round(p0.box.x2 + (p1.box.x2 - p0.box.x2) * ratio)),
                    int(round(p0.box.y2 + (p1.box.y2 - p0.box.y2) * ratio)),
                )

        return self.points[-1].box


def build_tracks(
    detections: list[tuple[float, list[Box]]],
    iou_threshold: float = 0.3,
    max_gap_seconds: float = 1.0,
) -> list[Track]:
    """検出時系列を IoU で結びつけて Track のリストにする.

    Args:
        detections: [(timestamp, [Box, ...]), ...] の時系列 (timestamp 昇順).
        iou_threshold: 同一物体と判定する IoU の下限.
        max_gap_seconds: この時間以上欠損があれば Track を切断.

    Returns:
        Track のリスト.
    """
    tracks: list[Track] = []
    active: list[Track] = []

    for timestamp, boxes in detections:
        # 古すぎる active track を確定済みへ移す
        still_active: list[Track] = []
        for tr in active:
            if timestamp - tr.t_end > max_gap_seconds:
                tracks.append(tr)
            else:
                still_active.append(tr)
        active = still_active

        # 各 box を最も IoU の高い active track に割当
        used_tracks: set[int] = set()
        for box in boxes:
            best_iou = iou_threshold
            best_idx = -1
            for idx, tr in enumerate(active):
                if idx in used_tracks:
                    continue
                iou = tr.latest_box().iou(box)
                if iou > best_iou:
                    best_iou = iou
                    best_idx = idx
            if best_idx >= 0:
                active[best_idx].points.append(TrackPoint(timestamp, box))
                used_tracks.add(best_idx)
            else:
                new_track = Track(points=[TrackPoint(timestamp, box)])
                active.append(new_track)

    tracks.extend(active)
    return tracks


def filter_short_tracks(tracks: list[Track], min_duration: float = 0.0) -> list[Track]:
    """短すぎる track はノイズとして除去."""
    return [t for t in tracks if t.duration >= min_duration]


def collect_active_boxes(
    tracks: list[Track],
    timestamp: float,
    persistence: float = 0.0,
) -> list[Box]:
    """指定時刻に active な track の bbox を収集.

    Args:
        persistence: track が終わってからもこの秒数だけ bbox を保持して flicker 抑制.
    """
    result: list[Box] = []
    for tr in tracks:
        if tr.t_start - persistence <= timestamp <= tr.t_end + persistence:
            result.append(tr.box_at(timestamp))
    return result
