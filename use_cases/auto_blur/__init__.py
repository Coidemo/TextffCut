"""動画内テキスト塗りつぶしオーバーレイのユースケース層.

公開 API:
- BlurOverlayUseCase: clip 候補の time_ranges を OCR + track 化して塗りつぶし PNG を生成
- BlurOverlayParams: パラメータ
- BlurOverlay / BlurOverlayResult: 実行結果

V2.5.0 で drawbox 方式 (source_blurred.mp4 を再エンコード) から PNG オーバーレイ方式に
完全置換された (旧実装は元動画の 12 倍 = 4.2GB のサイズ問題があった)。
"""

from use_cases.auto_blur.blur_overlay_use_case import (
    BlurOverlay,
    BlurOverlayParams,
    BlurOverlayResult,
    BlurOverlayUseCase,
    is_apple_silicon,
)

__all__ = [
    "BlurOverlay",
    "BlurOverlayParams",
    "BlurOverlayResult",
    "BlurOverlayUseCase",
    "is_apple_silicon",
]
