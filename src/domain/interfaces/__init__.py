"""
ドメイン層のインターフェース定義

各層で使用されるインターフェースを定義
"""

from .gateways import (
    IEDLExportGateway,
    IExportGateway,
    IFCPXMLExportGateway,
    IFileGateway,
    ISilenceDetectionGateway,
    ISRTExportGateway,
    ITextProcessorGateway,
    ITranscriptionGateway,
    IVideoGateway,
)
from .session import ISessionManager

__all__ = [
    # Gateway interfaces
    "IFileGateway",
    "ITranscriptionGateway",
    "IVideoGateway",
    "ISilenceDetectionGateway",
    "ITextProcessorGateway",
    "IExportGateway",
    "IFCPXMLExportGateway",
    "IEDLExportGateway",
    "ISRTExportGateway",
    # Session interface
    "ISessionManager",
]
