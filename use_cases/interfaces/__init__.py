"""
ゲートウェイインターフェース

外部システムとのやり取りを抽象化するインターフェース。
これらのインターフェースはアダプター層で実装されます。
"""

from .export_gateway import (
    ExportSegment,
    IExportGateway,
    IFCPXMLExportGateway,
    IPremiereXMLExportGateway,
    ISRTExportGateway,
    TimeMapper,
)
from .file_gateway import IFileGateway
from .text_processor_gateway import ITextProcessorGateway
from .transcription_gateway import ITranscriptionGateway
from .video_processor_gateway import IVideoProcessorGateway

__all__ = [
    "ITranscriptionGateway",
    "ITextProcessorGateway",
    "IVideoProcessorGateway",
    "IExportGateway",
    "IFCPXMLExportGateway",
    "IPremiereXMLExportGateway",
    "ISRTExportGateway",
    "IFileGateway",
    "ExportSegment",
    "TimeMapper",
]
