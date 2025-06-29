"""
ゲートウェイインターフェース

外部システムとのやり取りを抽象化するインターフェース。
これらのインターフェースはアダプター層で実装されます。
"""

from .transcription_gateway import ITranscriptionGateway
from .text_processor_gateway import ITextProcessorGateway
from .video_processor_gateway import IVideoProcessorGateway
from .export_gateway import (
    IExportGateway,
    IFCPXMLExportGateway,
    IPremiereXMLExportGateway,
    ISRTExportGateway,
)
from .file_gateway import IFileGateway

__all__ = [
    "ITranscriptionGateway",
    "ITextProcessorGateway",
    "IVideoProcessorGateway",
    "IExportGateway",
    "IFCPXMLExportGateway",
    "IPremiereXMLExportGateway",
    "ISRTExportGateway",
    "IFileGateway",
]