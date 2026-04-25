"""動画内テキスト自動ぼかし機能のコアモジュール.

公開 API:
- OcrmacDetector / TextDetector: テキスト bbox 検出器
- Box / merge_boxes / sample_edge_color: bbox ユーティリティ
- Track / build_tracks: track 構築
- ffmpeg.* : filter_complex 構築 + 実行ヘルパー
- chunk_worker.process_full_chunk: フルチャンク並列ワーカー
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
