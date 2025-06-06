"""
TextffCut 2段階処理アーキテクチャ用データモデル

このモジュールは、文字起こしとアライメントの2段階処理を
効率的に管理するためのデータ構造を定義します。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Union
from datetime import datetime
from enum import Enum
import json


class ProcessingStatus(Enum):
    """処理状態を表す列挙型"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProcessingStage(Enum):
    """処理段階を表す列挙型"""
    TRANSCRIPTION = "transcription"
    ALIGNMENT = "alignment"
    POST_PROCESSING = "post_processing"


@dataclass
class WordInfo:
    """単語レベルのタイムスタンプ情報"""
    word: str
    start: Optional[float] = None
    end: Optional[float] = None
    confidence: Optional[float] = None
    
    def is_valid(self) -> bool:
        """タイムスタンプが有効かチェック"""
        return self.start is not None and self.end is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "word": self.word,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WordInfo':
        """辞書から生成"""
        return cls(
            word=data["word"],
            start=data.get("start"),
            end=data.get("end"),
            confidence=data.get("confidence")
        )


@dataclass
class CharInfo:
    """文字レベルのタイムスタンプ情報（日本語対応）"""
    char: str
    start: Optional[float] = None
    end: Optional[float] = None
    confidence: Optional[float] = None
    
    def is_valid(self) -> bool:
        """タイムスタンプが有効かチェック"""
        return self.start is not None and self.end is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "char": self.char,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharInfo':
        """辞書から生成"""
        return cls(
            char=data["char"],
            start=data.get("start"),
            end=data.get("end"),
            confidence=data.get("confidence")
        )


@dataclass
class TranscriptionSegmentV2:
    """
    改良版セグメントデータ構造
    - 文字起こしとアライメントの段階的処理に対応
    - 部分的な処理状態の管理が可能
    """
    id: str
    text: str
    start: float
    end: float
    words: Optional[List[Union[WordInfo, Dict[str, Any]]]] = None
    chars: Optional[List[Union[CharInfo, Dict[str, Any]]]] = None
    confidence: Optional[float] = None
    language: Optional[str] = None
    speaker: Optional[str] = None
    
    # 処理状態
    transcription_completed: bool = False
    alignment_completed: bool = False
    alignment_error: Optional[str] = None
    
    # メタデータ
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def has_valid_alignment(self) -> bool:
        """有効なアライメント情報を持つかチェック"""
        if not self.alignment_completed:
            return False
        if self.words:
            for w in self.words:
                if isinstance(w, WordInfo):
                    if w.is_valid():
                        return True
                elif isinstance(w, dict):
                    if w.get('start') is not None and w.get('end') is not None:
                        return True
        if self.chars:
            for c in self.chars:
                if isinstance(c, CharInfo):
                    if c.is_valid():
                        return True
                elif isinstance(c, dict):
                    if c.get('start') is not None and c.get('end') is not None:
                        return True
        return False
    
    def validate_for_search(self) -> tuple[bool, Optional[str]]:
        """
        検索処理に必要な情報が揃っているか検証
        
        Returns:
            (有効かどうか, エラーメッセージ)
        """
        # テキストの検証
        if not self.text or not self.text.strip():
            return False, "テキストが空です"
        
        # タイムスタンプの検証
        if self.start is None or self.end is None:
            return False, "セグメントのタイムスタンプが欠落しています"
        
        # wordsフィールドの検証（必須）
        if not self.words or len(self.words) == 0:
            return False, "words情報が欠落しています（文字位置の特定に必須）"
        
        # 各wordの検証
        invalid_words = []
        for i, word in enumerate(self.words):
            is_valid = False
            if isinstance(word, WordInfo):
                is_valid = word.is_valid()
            elif isinstance(word, dict):
                is_valid = word.get('start') is not None and word.get('end') is not None
            
            if not is_valid:
                invalid_words.append(i)
        
        if invalid_words:
            return False, f"{len(invalid_words)}個のwordでタイムスタンプが欠落しています"
        
        return True, None
    
    def get_word_at_position(self, char_position: int) -> Optional[Union[WordInfo, Dict[str, Any]]]:
        """指定された文字位置の単語情報を取得"""
        if not self.words:
            return None
        
        current_pos = 0
        for word in self.words:
            if isinstance(word, WordInfo):
                word_text = word.word
            elif isinstance(word, dict):
                word_text = word.get('word', '')
            else:
                continue
            
            word_len = len(word_text)
            if current_pos <= char_position < current_pos + word_len:
                return word
            current_pos += word_len
        
        return None
    
    def _convert_words_to_dict(self) -> List[Dict[str, Any]]:
        """wordsを辞書形式に変換（WordInfoオブジェクトと辞書の両方に対応）"""
        result = []
        for w in self.words:
            if isinstance(w, dict):
                result.append(w)
            elif hasattr(w, 'to_dict'):
                result.append(w.to_dict())
            else:
                # WordInfoオブジェクトの場合
                result.append({
                    "word": w.word,
                    "start": w.start,
                    "end": w.end,
                    "confidence": w.confidence
                })
        return result
    
    def _convert_chars_to_dict(self) -> List[Dict[str, Any]]:
        """charsを辞書形式に変換（CharInfoオブジェクトと辞書の両方に対応）"""
        result = []
        for c in self.chars:
            if isinstance(c, dict):
                result.append(c)
            elif hasattr(c, 'to_dict'):
                result.append(c.to_dict())
            else:
                # CharInfoオブジェクトの場合
                result.append({
                    "char": c.char,
                    "start": c.start,
                    "end": c.end,
                    "confidence": c.confidence
                })
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "id": self.id,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "words": self._convert_words_to_dict() if self.words else None,
            "chars": self._convert_chars_to_dict() if self.chars else None,
            "confidence": self.confidence,
            "language": self.language,
            "speaker": self.speaker,
            "transcription_completed": self.transcription_completed,
            "alignment_completed": self.alignment_completed,
            "alignment_error": self.alignment_error,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionSegmentV2':
        """辞書から生成"""
        return cls(
            id=data["id"],
            text=data["text"],
            start=data["start"],
            end=data["end"],
            words=data.get("words"),  # 辞書形式のままで保持
            chars=data.get("chars"),  # 辞書形式のままで保持
            confidence=data.get("confidence"),
            language=data.get("language"),
            speaker=data.get("speaker"),
            transcription_completed=data.get("transcription_completed", False),
            alignment_completed=data.get("alignment_completed", False),
            alignment_error=data.get("alignment_error"),
            metadata=data.get("metadata", {})
        )
    
    def to_legacy_format(self) -> Dict[str, Any]:
        """旧形式との互換性のための変換"""
        legacy_words = None
        if self.words:
            legacy_words = []
            for w in self.words:
                if isinstance(w, WordInfo):
                    legacy_words.append({"word": w.word, "start": w.start, "end": w.end})
                elif isinstance(w, dict):
                    legacy_words.append({"word": w.get("word", ""), "start": w.get("start"), "end": w.get("end")})
        
        legacy_chars = None
        if self.chars:
            legacy_chars = []
            for c in self.chars:
                if isinstance(c, CharInfo):
                    legacy_chars.append({"char": c.char, "start": c.start, "end": c.end})
                elif isinstance(c, dict):
                    legacy_chars.append({"char": c.get("char", ""), "start": c.get("start"), "end": c.get("end")})
        
        return {
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "words": legacy_words,
            "chars": legacy_chars
        }


@dataclass
class ProcessingMetadata:
    """処理に関するメタデータ"""
    video_path: str
    video_duration: float
    processing_mode: str  # "api" or "local"
    model_size: str
    language: str
    
    # 処理時間の記録
    started_at: datetime = field(default_factory=datetime.now)
    transcription_started_at: Optional[datetime] = None
    transcription_completed_at: Optional[datetime] = None
    alignment_started_at: Optional[datetime] = None
    alignment_completed_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # リソース使用状況
    peak_memory_mb: Optional[float] = None
    total_processing_time: Optional[float] = None
    
    # エラー情報
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[Dict[str, Any]] = field(default_factory=list)
    
    def add_error(self, stage: str, error: str, details: Optional[Dict[str, Any]] = None):
        """エラーを記録"""
        self.errors.append({
            "stage": stage,
            "error": error,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
    
    def add_warning(self, stage: str, warning: str, details: Optional[Dict[str, Any]] = None):
        """警告を記録"""
        self.warnings.append({
            "stage": stage,
            "warning": warning,
            "details": details or {},
            "timestamp": datetime.now().isoformat()
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "video_path": self.video_path,
            "video_duration": self.video_duration,
            "processing_mode": self.processing_mode,
            "model_size": self.model_size,
            "language": self.language,
            "started_at": self.started_at.isoformat(),
            "transcription_started_at": self.transcription_started_at.isoformat() if self.transcription_started_at else None,
            "transcription_completed_at": self.transcription_completed_at.isoformat() if self.transcription_completed_at else None,
            "alignment_started_at": self.alignment_started_at.isoformat() if self.alignment_started_at else None,
            "alignment_completed_at": self.alignment_completed_at.isoformat() if self.alignment_completed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "peak_memory_mb": self.peak_memory_mb,
            "total_processing_time": self.total_processing_time,
            "errors": self.errors,
            "warnings": self.warnings
        }


@dataclass
class TranscriptionResultV2:
    """
    改良版文字起こし結果データ構造
    - 段階的な処理状態の管理
    - 部分的な成功/失敗の追跡
    - メタデータの充実
    """
    segments: List[TranscriptionSegmentV2]
    metadata: ProcessingMetadata
    
    # 処理状態
    transcription_status: ProcessingStatus = ProcessingStatus.PENDING
    alignment_status: ProcessingStatus = ProcessingStatus.PENDING
    
    # 統計情報
    total_segments: int = 0
    transcribed_segments: int = 0
    aligned_segments: int = 0
    failed_segments: int = 0
    
    def __post_init__(self):
        """初期化後の処理"""
        self.update_statistics()
    
    def update_statistics(self):
        """統計情報を更新"""
        self.total_segments = len(self.segments)
        self.transcribed_segments = sum(1 for s in self.segments if s.transcription_completed)
        self.aligned_segments = sum(1 for s in self.segments if s.alignment_completed)
        self.failed_segments = sum(1 for s in self.segments if s.alignment_error is not None)
    
    def get_valid_segments(self) -> List[TranscriptionSegmentV2]:
        """有効なアライメント情報を持つセグメントのみ取得"""
        return [s for s in self.segments if s.has_valid_alignment()]
    
    def get_failed_segments(self) -> List[TranscriptionSegmentV2]:
        """アライメントに失敗したセグメントを取得"""
        return [s for s in self.segments if s.alignment_error is not None]
    
    def is_complete(self) -> bool:
        """処理が完了しているかチェック"""
        return (self.transcription_status == ProcessingStatus.COMPLETED and
                self.alignment_status == ProcessingStatus.COMPLETED)
    
    def has_valid_words(self) -> bool:
        """有効なwords情報を持つかチェック"""
        return any(s.has_valid_alignment() for s in self.segments)
    
    def validate_for_processing(self) -> tuple[bool, List[str]]:
        """
        処理（検索・切り抜き）に必要な情報が揃っているか厳密に検証
        
        Returns:
            (有効かどうか, エラーメッセージのリスト)
        """
        errors = []
        
        # セグメントの存在チェック
        if not self.segments:
            errors.append("セグメントが存在しません")
            return False, errors
        
        # 各セグメントの検証
        invalid_segments = []
        segments_without_words = []
        segments_with_invalid_words = []
        
        for segment in self.segments:
            is_valid, error_msg = segment.validate_for_search()
            if not is_valid:
                invalid_segments.append({
                    "id": segment.id,
                    "text_preview": segment.text[:50] if segment.text else "(空)",
                    "error": error_msg
                })
                
                # エラータイプの分類
                if "words情報が欠落" in error_msg:
                    segments_without_words.append(segment)
                elif "wordでタイムスタンプが欠落" in error_msg:
                    segments_with_invalid_words.append(segment)
        
        # エラーサマリーの作成
        if segments_without_words:
            errors.append(
                f"{len(segments_without_words)}個のセグメントでwords情報が完全に欠落しています"
            )
        
        if segments_with_invalid_words:
            errors.append(
                f"{len(segments_with_invalid_words)}個のセグメントでタイムスタンプが不完全です"
            )
        
        if invalid_segments and not segments_without_words and not segments_with_invalid_words:
            # その他のエラー
            errors.append(f"{len(invalid_segments)}個のセグメントで検証エラーが発生しました")
        
        # 処理ステータスの確認
        if self.transcription_status != ProcessingStatus.COMPLETED:
            errors.append("文字起こし処理が完了していません")
        
        if self.alignment_status != ProcessingStatus.COMPLETED:
            errors.append("アライメント処理が完了していません")
        
        # 全体的な検証結果
        is_valid = len(errors) == 0
        
        # デバッグ情報の追加
        if not is_valid and invalid_segments:
            # 最初の3つのエラーを詳細に記録
            sample_errors = invalid_segments[:3]
            for sample in sample_errors:
                errors.append(f"  セグメント '{sample['text_preview']}...': {sample['error']}")
        
        return is_valid, errors
    
    def require_valid_words(self):
        """
        有効なwords情報を要求（なければ例外を発生）
        主にUI表示前のチェックポイントで使用
        """
        from .exceptions import WordsFieldMissingError, TranscriptionValidationError
        
        is_valid, errors = self.validate_for_processing()
        
        if not is_valid:
            # wordsフィールド欠落の特別処理
            segments_without_words = [
                s for s in self.segments 
                if not s.words or len(s.words) == 0
            ]
            
            if segments_without_words:
                # サンプルテキストの取得
                sample_texts = [
                    s.text[:50] + "..." if s.text and len(s.text) > 50 else s.text
                    for s in segments_without_words[:3]
                ]
                
                raise WordsFieldMissingError(
                    segment_count=len(segments_without_words),
                    sample_segments=sample_texts
                )
            else:
                # その他の検証エラー
                raise TranscriptionValidationError(
                    "文字起こし結果が処理要件を満たしていません",
                    invalid_segments=[s.id for s in self.segments if s.alignment_error]
                )
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "segments": [s.to_dict() for s in self.segments],
            "metadata": self.metadata.to_dict(),
            "transcription_status": self.transcription_status.value,
            "alignment_status": self.alignment_status.value,
            "total_segments": self.total_segments,
            "transcribed_segments": self.transcribed_segments,
            "aligned_segments": self.aligned_segments,
            "failed_segments": self.failed_segments
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionResultV2':
        """辞書から生成"""
        segments = [TranscriptionSegmentV2.from_dict(s) for s in data["segments"]]
        
        # メタデータの復元（簡略化）
        metadata_dict = data["metadata"]
        metadata = ProcessingMetadata(
            video_path=metadata_dict["video_path"],
            video_duration=metadata_dict["video_duration"],
            processing_mode=metadata_dict["processing_mode"],
            model_size=metadata_dict["model_size"],
            language=metadata_dict["language"]
        )
        
        result = cls(segments=segments, metadata=metadata)
        result.transcription_status = ProcessingStatus(data.get("transcription_status", "pending"))
        result.alignment_status = ProcessingStatus(data.get("alignment_status", "pending"))
        
        return result
    
    def to_legacy_format(self) -> Dict[str, Any]:
        """旧形式との互換性のための変換"""
        return {
            "language": self.metadata.language,
            "segments": [s.to_legacy_format() for s in self.segments],
            "original_audio_path": self.metadata.video_path,
            "model_size": self.metadata.model_size,
            "processing_time": self.metadata.total_processing_time or 0
        }


@dataclass
class ProcessingRequest:
    """処理リクエストのデータ構造"""
    video_path: str
    model_size: str
    language: str
    processing_mode: str  # "api" or "local"
    
    # オプション設定
    use_cache: bool = True
    save_cache: bool = True
    force_realignment: bool = False
    
    # APIモード用設定
    api_key: Optional[str] = None
    api_provider: str = "openai"
    
    # 処理パラメータ
    chunk_seconds: int = 30
    batch_size: int = 8
    num_workers: Optional[int] = None
    
    # コールバック
    progress_callback: Optional[Any] = None  # Callable[[float, str], None]
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "video_path": self.video_path,
            "model_size": self.model_size,
            "language": self.language,
            "processing_mode": self.processing_mode,
            "use_cache": self.use_cache,
            "save_cache": self.save_cache,
            "force_realignment": self.force_realignment,
            "api_provider": self.api_provider,
            "chunk_seconds": self.chunk_seconds,
            "batch_size": self.batch_size,
            "num_workers": self.num_workers
        }


@dataclass
class AlignmentRequest:
    """アライメント処理リクエスト"""
    segments: List[TranscriptionSegmentV2]
    audio_path: str
    language: str
    device: str = "cpu"
    
    # 処理オプション
    retry_on_failure: bool = True
    max_retries: int = 3
    fallback_to_estimation: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "segments": [s.to_dict() for s in self.segments],
            "audio_path": self.audio_path,
            "language": self.language,
            "device": self.device,
            "retry_on_failure": self.retry_on_failure,
            "max_retries": self.max_retries,
            "fallback_to_estimation": self.fallback_to_estimation
        }


@dataclass
class CacheEntry:
    """キャッシュエントリのデータ構造"""
    cache_key: str
    file_path: str
    created_at: datetime
    accessed_at: datetime
    
    # キャッシュ内容の情報
    processing_mode: str
    model_size: str
    language: str
    video_duration: float
    
    # キャッシュの状態
    has_transcription: bool = False
    has_alignment: bool = False
    is_complete: bool = False
    
    # ファイルサイズ
    file_size_bytes: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "cache_key": self.cache_key,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat(),
            "accessed_at": self.accessed_at.isoformat(),
            "processing_mode": self.processing_mode,
            "model_size": self.model_size,
            "language": self.language,
            "video_duration": self.video_duration,
            "has_transcription": self.has_transcription,
            "has_alignment": self.has_alignment,
            "is_complete": self.is_complete,
            "file_size_bytes": self.file_size_bytes
        }