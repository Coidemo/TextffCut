"""動画内テキスト塗りつぶし機能のコアモジュール.

公開 API:
- OcrmacDetector: Apple Vision API ベースのテキスト bbox 検出器
- Box / merge_boxes / sample_edge_color: bbox ユーティリティ
- Track / build_tracks: track 構築

V2.5.0 で drawbox 方式 (filter_complex を組んで再エンコード) を廃止し、
PNG オーバーレイ方式 (use_cases.auto_blur.blur_overlay_use_case) に統合された。
"""

from core.text_blur.detector import (
    Box,
    OcrmacDetector,
    merge_boxes,
    sample_edge_color,
)
from core.text_blur.tracker import (
    Track,
    TrackPoint,
    build_tracks,
    collect_active_boxes,
    filter_short_tracks,
)

__all__ = [
    "Box",
    "OcrmacDetector",
    "Track",
    "TrackPoint",
    "build_tracks",
    "collect_active_boxes",
    "filter_short_tracks",
    "merge_boxes",
    "sample_edge_color",
]
