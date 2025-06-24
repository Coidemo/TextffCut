"""
モデル定義（型ヒント強化版）

データモデルの定義。すべての型が明示的に定義されている。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Union

from core.types import (
    ModelSize,
    ProcessingMode,
    ProcessingStatus,
    SegmentDict,
    TimeSeconds,
    ValidationResult,
    VideoPath,
    WordInfo,
)


@dataclass
class WordInfo:
    """単語情報（型安全版）"""

    word: str
    start: TimeSeconds | None = None
    end: TimeSeconds | None = None
    confidence: float | None = None

    def is_valid(self) -> bool:
        """有効な単語情報かチェック"""
        return self.start is not None and self.end is not None

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {"word": self.word, "start": self.start, "end": self.end, "confidence": self.confidence}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WordInfo":
        """辞書から生成"""
        return cls(word=data["word"], start=data.get("start"), end=data.get("end"), confidence=data.get("confidence"))


@dataclass
class TranscriptionSegmentV2:
    """
    改良版セグメントデータ構造（型ヒント強化版）
    """

    id: str
    text: str
    start: TimeSeconds
    end: TimeSeconds
    words: list[WordInfo | dict[str, Any]] | None = None
    chars: list[Union["CharInfo", dict[str, Any]]] | None = None
    confidence: float | None = None
    language: str | None = None
    speaker: str | None = None

    # 処理状態
    transcription_completed: bool = False
    alignment_completed: bool = False
    alignment_error: str | None = None

    # メタデータ
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_valid_alignment(self) -> bool:
        """有効なアライメント情報を持つかチェック"""
        if not self.alignment_completed:
            return False

        if self.words:
            return any(self._is_word_valid(w) for w in self.words)

        if self.chars:
            return any(self._is_char_valid(c) for c in self.chars)

        return False

    def _is_word_valid(self, word: WordInfo | dict[str, Any]) -> bool:
        """単語情報が有効かチェック"""
        if isinstance(word, WordInfo):
            return word.is_valid()
        elif isinstance(word, dict):
            return word.get("start") is not None and word.get("end") is not None
        return False

    def _is_char_valid(self, char: Union["CharInfo", dict[str, Any]]) -> bool:
        """文字情報が有効かチェック"""
        if hasattr(char, "is_valid"):
            return char.is_valid()
        elif isinstance(char, dict):
            return char.get("start") is not None and char.get("end") is not None
        return False

    def validate_for_search(self) -> ValidationResult:
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
        invalid_words: list[int] = []
        for i, word in enumerate(self.words):
            if not self._is_word_valid(word):
                invalid_words.append(i)

        if invalid_words:
            return False, f"{len(invalid_words)}個のwordでタイムスタンプが欠落しています"

        return True, None

    def get_word_at_position(self, char_position: int) -> WordInfo | dict[str, Any] | None:
        """指定された文字位置の単語情報を取得"""
        if not self.words:
            return None

        current_pos: int = 0
        for word in self.words:
            word_text: str = ""
            if isinstance(word, WordInfo):
                word_text = word.word
            elif isinstance(word, dict):
                word_text = word.get("word", "")

            word_len: int = len(word_text)
            if current_pos <= char_position < current_pos + word_len:
                return word
            current_pos += word_len

        return None

    def to_dict(self) -> SegmentDict:
        """辞書形式に変換"""
        result: SegmentDict = {
            "id": self.id,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "words": self._convert_words_to_dict() if self.words else None,
            "confidence": self.confidence,
            "language": self.language,
            "speaker": self.speaker,
        }

        # 追加フィールド
        additional_fields = {
            "chars": self._convert_chars_to_dict() if self.chars else None,
            "transcription_completed": self.transcription_completed,
            "alignment_completed": self.alignment_completed,
            "alignment_error": self.alignment_error,
            "metadata": self.metadata,
        }

        # 型安全性のため、明示的に追加
        for key, value in additional_fields.items():
            result[key] = value  # type: ignore

        return result

    def _convert_words_to_dict(self) -> list[dict[str, Any]]:
        """wordsを辞書形式に変換"""
        if not self.words:
            return []

        result: list[dict[str, Any]] = []
        for w in self.words:
            if isinstance(w, dict):
                result.append(w)
            elif hasattr(w, "to_dict"):
                result.append(w.to_dict())
            else:
                # WordInfoオブジェクトの場合
                result.append(
                    {"word": w.word, "start": w.start, "end": w.end, "confidence": getattr(w, "confidence", None)}
                )
        return result

    def _convert_chars_to_dict(self) -> list[dict[str, Any]]:
        """charsを辞書形式に変換"""
        if not self.chars:
            return []

        result: list[dict[str, Any]] = []
        for c in self.chars:
            if isinstance(c, dict):
                result.append(c)
            elif hasattr(c, "to_dict"):
                result.append(c.to_dict())
            else:
                # CharInfoオブジェクトの場合
                result.append(
                    {
                        "char": getattr(c, "char", ""),
                        "start": getattr(c, "start", None),
                        "end": getattr(c, "end", None),
                        "confidence": getattr(c, "confidence", None),
                    }
                )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscriptionSegmentV2":
        """辞書から生成"""
        return cls(
            id=data["id"],
            text=data["text"],
            start=data["start"],
            end=data["end"],
            words=data.get("words"),
            chars=data.get("chars"),
            confidence=data.get("confidence"),
            language=data.get("language"),
            speaker=data.get("speaker"),
            transcription_completed=data.get("transcription_completed", False),
            alignment_completed=data.get("alignment_completed", False),
            alignment_error=data.get("alignment_error"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ProcessingMetadata:
    """処理に関するメタデータ（型ヒント強化版）"""

    video_path: VideoPath
    video_duration: TimeSeconds
    processing_mode: ProcessingMode
    model_size: ModelSize
    language: str

    # 処理時間の記録
    started_at: datetime = field(default_factory=datetime.now)
    transcription_started_at: datetime | None = None
    transcription_completed_at: datetime | None = None
    alignment_started_at: datetime | None = None
    alignment_completed_at: datetime | None = None
    completed_at: datetime | None = None

    # リソース使用状況
    peak_memory_mb: float | None = None
    total_processing_time: TimeSeconds | None = None

    # エラー情報
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, stage: str, error: str, details: dict[str, Any] | None = None) -> None:
        """エラーを記録"""
        self.errors.append(
            {"stage": stage, "error": error, "details": details or {}, "timestamp": datetime.now().isoformat()}
        )

    def add_warning(self, stage: str, warning: str, details: dict[str, Any] | None = None) -> None:
        """警告を記録"""
        self.warnings.append(
            {"stage": stage, "warning": warning, "details": details or {}, "timestamp": datetime.now().isoformat()}
        )

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "video_path": str(self.video_path),
            "video_duration": self.video_duration,
            "processing_mode": self.processing_mode,
            "model_size": self.model_size,
            "language": self.language,
            "started_at": self.started_at.isoformat(),
            "transcription_started_at": (
                self.transcription_started_at.isoformat() if self.transcription_started_at else None
            ),
            "transcription_completed_at": (
                self.transcription_completed_at.isoformat() if self.transcription_completed_at else None
            ),
            "alignment_started_at": self.alignment_started_at.isoformat() if self.alignment_started_at else None,
            "alignment_completed_at": self.alignment_completed_at.isoformat() if self.alignment_completed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "peak_memory_mb": self.peak_memory_mb,
            "total_processing_time": self.total_processing_time,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class TranscriptionResultV2:
    """
    文字起こし結果全体を表すデータ構造（型ヒント強化版）
    """

    segments: list[TranscriptionSegmentV2]
    metadata: ProcessingMetadata

    # 処理状態
    transcription_status: ProcessingStatus = "pending"
    alignment_status: ProcessingStatus = "pending"

    # 統計情報
    total_segments: int = 0
    transcribed_segments: int = 0
    aligned_segments: int = 0
    failed_segments: int = 0

    def __post_init__(self) -> None:
        """初期化後の処理"""
        self.update_statistics()

    def update_statistics(self) -> None:
        """統計情報を更新"""
        self.total_segments = len(self.segments)
        self.transcribed_segments = sum(1 for s in self.segments if s.transcription_completed)
        self.aligned_segments = sum(1 for s in self.segments if s.alignment_completed)
        self.failed_segments = sum(1 for s in self.segments if s.alignment_error is not None)

    def get_valid_segments(self) -> list[TranscriptionSegmentV2]:
        """有効なアライメント情報を持つセグメントのみ取得"""
        return [s for s in self.segments if s.has_valid_alignment()]

    def get_failed_segments(self) -> list[TranscriptionSegmentV2]:
        """アライメントに失敗したセグメントを取得"""
        return [s for s in self.segments if s.alignment_error is not None]

    def is_complete(self) -> bool:
        """処理が完了しているかチェック"""
        return self.transcription_status == "completed" and self.alignment_status == "completed"

    def has_valid_words(self) -> bool:
        """有効なwords情報を持つかチェック"""
        return any(s.has_valid_alignment() for s in self.segments)

    def validate_for_processing(self) -> tuple[bool, list[str]]:
        """
        処理（検索・切り抜き）に必要な情報が揃っているか厳密に検証

        Returns:
            (有効かどうか, エラーメッセージのリスト)
        """
        errors: list[str] = []

        # セグメントの存在チェック
        if not self.segments:
            errors.append("セグメントが存在しません")
            return False, errors

        # 各セグメントの検証
        invalid_segments: list[str] = []
        for i, segment in enumerate(self.segments):
            is_valid, error = segment.validate_for_search()
            if not is_valid:
                invalid_segments.append(f"セグメント{i+1}: {error}")

        if invalid_segments:
            errors.extend(invalid_segments[:5])  # 最初の5件のみ
            if len(invalid_segments) > 5:
                errors.append(f"...他{len(invalid_segments)-5}件のエラー")

        # メタデータの検証
        if not self.metadata:
            errors.append("メタデータが存在しません")

        return len(errors) == 0, errors
