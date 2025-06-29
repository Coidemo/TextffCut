"""
動画処理ゲートウェイ

既存の動画処理機能をクリーンアーキテクチャのインターフェースに適合させます。
"""

from .video_processor_gateway import VideoProcessorGatewayAdapter

__all__ = ["VideoProcessorGatewayAdapter"]