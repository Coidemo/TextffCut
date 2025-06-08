"""
サービス層パッケージ

ビジネスロジックを提供するサービスクラスを含む。
UI層（main.py）とCore層の間を仲介し、複雑な処理フローを管理する。
"""

from .base import (
    BaseService,
    ServiceResult,
    TypedServiceResult,
    ServiceError,
    ValidationError,
    ProcessingError
)

from .configuration_service import ConfigurationService
from .transcription_service import TranscriptionService
from .text_editing_service import TextEditingService
from .video_processing_service import VideoProcessingService
from .export_service import ExportService
from .workflow_service import WorkflowService, WorkflowSettings

__all__ = [
    # Base
    'BaseService',
    'ServiceResult',
    'TypedServiceResult',
    'ServiceError',
    'ValidationError',
    'ProcessingError',
    
    # Services
    'ConfigurationService',
    'TranscriptionService',
    'TextEditingService',
    'VideoProcessingService',
    'ExportService',
    'WorkflowService',
    
    # Settings
    'WorkflowSettings'
]