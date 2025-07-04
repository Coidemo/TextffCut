"""
文字起こし結果のドメインエンティティ

ビジネスロジックを含む文字起こし結果のエンティティ定義。
既存の実装との互換性を保ちながら、クリーンな設計を実現。
"""

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class Word:
    """単語エンティティ"""

    word: str
    start: float
    end: float
    confidence: float | None = None

    def __post_init__(self):
        """バリデーション"""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be greater than start time")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")

    @property
    def duration(self) -> float:
        """単語の継続時間"""
        return self.end - self.start

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Word":
        """辞書からWordインスタンスを作成（既存コードとの互換性）"""
        return cls(
            word=data["word"],
            start=data["start"],
            end=data["end"],
            confidence=data.get("confidence") or data.get("score"),
        )

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換（既存コードとの互換性）"""
        result = {"word": self.word, "start": self.start, "end": self.end}
        if self.confidence is not None:
            result["confidence"] = self.confidence
        return result


@dataclass
class Char:
    """文字エンティティ（日本語等）"""

    char: str
    start: float
    end: float
    confidence: float | None = None

    def __post_init__(self):
        """バリデーション"""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be greater than start time")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Char":
        """辞書からCharインスタンスを作成"""
        return cls(
            char=data["char"],
            start=data["start"],
            end=data["end"],
            confidence=data.get("confidence") or data.get("score"),
        )

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        result = {"char": self.char, "start": self.start, "end": self.end}
        if self.confidence is not None:
            result["confidence"] = self.confidence
        return result


@dataclass
class TranscriptionSegment:
    """文字起こしセグメントエンティティ"""

    id: str
    text: str
    start: float
    end: float
    words: list[Word | dict[str, Any]] | None = None
    chars: list[Char | dict[str, Any]] | None = None

    def __post_init__(self):
        """バリデーションと正規化"""
        if self.start < 0:
            raise ValueError("Start time cannot be negative")
        if self.end < self.start:
            raise ValueError("End time must be greater than start time")

        # wordsとcharsを正規化（辞書の場合はWordオブジェクトに変換）
        if self.words:
            normalized_words = []
            for w in self.words:
                if isinstance(w, dict):
                    normalized_words.append(Word.from_dict(w))
                else:
                    normalized_words.append(w)
            self.words = normalized_words

        if self.chars:
            normalized_chars = []
            for c in self.chars:
                if isinstance(c, dict):
                    normalized_chars.append(Char.from_dict(c))
                else:
                    normalized_chars.append(c)
            self.chars = normalized_chars

    @property
    def duration(self) -> float:
        """セグメントの継続時間"""
        return self.end - self.start

    @property
    def has_word_level_timestamps(self) -> bool:
        """単語レベルのタイムスタンプを持っているか"""
        return self.words is not None and len(self.words) > 0

    @property
    def has_char_level_timestamps(self) -> bool:
        """文字レベルのタイムスタンプを持っているか"""
        return self.chars is not None and len(self.chars) > 0

    def get_words_as_dicts(self) -> list[dict[str, Any]] | None:
        """wordsを辞書のリストとして取得（既存コードとの互換性）"""
        if not self.words:
            return None
        return [w.to_dict() if isinstance(w, Word) else w for w in self.words]

    def get_chars_as_dicts(self) -> list[dict[str, Any]] | None:
        """charsを辞書のリストとして取得（既存コードとの互換性）"""
        if not self.chars:
            return None
        return [c.to_dict() if isinstance(c, Char) else c for c in self.chars]

    @classmethod
    def from_legacy_format(cls, data: dict[str, Any]) -> "TranscriptionSegment":
        """レガシー形式から変換"""
        return cls(
            id=str(uuid4()),
            text=data["text"],
            start=data["start"],
            end=data["end"],
            words=data.get("words"),
            chars=data.get("chars"),
        )

    def to_legacy_format(self) -> dict[str, Any]:
        """レガシー形式に変換"""
        result = {"text": self.text, "start": self.start, "end": self.end}

        words_dicts = self.get_words_as_dicts()
        if words_dicts:
            result["words"] = words_dicts

        chars_dicts = self.get_chars_as_dicts()
        if chars_dicts:
            result["chars"] = chars_dicts

        return result


@dataclass
class TranscriptionResult:
    """文字起こし結果エンティティ"""

    id: str
    language: str
    segments: list[TranscriptionSegment]
    original_audio_path: str
    model_size: str
    processing_time: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """バリデーションとセグメントの正規化"""
        if not self.segments:
            raise ValueError("Transcription result must have at least one segment")
        if self.processing_time < 0:
            raise ValueError("Processing time cannot be negative")
        
        # segmentsが辞書のリストの場合、TranscriptionSegmentオブジェクトに変換
        normalized_segments = []
        for seg in self.segments:
            if isinstance(seg, dict):
                # 辞書からTranscriptionSegmentを作成
                normalized_segments.append(TranscriptionSegment.from_legacy_format(seg))
            else:
                normalized_segments.append(seg)
        self.segments = normalized_segments

    @property
    def duration(self) -> float:
        """全体の継続時間"""
        if not self.segments:
            return 0.0
        return max(seg.end for seg in self.segments)

    @property
    def text(self) -> str:
        """全セグメントのテキストを結合"""
        return " ".join(seg.text for seg in self.segments)

    @property
    def has_word_level_timestamps(self) -> bool:
        """単語レベルのタイムスタンプを持っているか"""
        return any(seg.has_word_level_timestamps for seg in self.segments)

    def get_segments_in_range(self, start: float, end: float) -> list[TranscriptionSegment]:
        """指定された時間範囲内のセグメントを取得"""
        return [seg for seg in self.segments if seg.start < end and seg.end > start]

    def validate_for_text_search(self) -> bool:
        """テキスト検索に必要な条件を満たしているか確認"""
        if not self.has_word_level_timestamps:
            return False

        # すべてのセグメントがwordsを持っているか確認
        for seg in self.segments:
            if not seg.words:
                return False

        return True

    @classmethod
    def from_legacy_format(cls, data: dict[str, Any]) -> "TranscriptionResult":
        """レガシー形式から変換（core.transcription.TranscriptionResult互換）"""
        segments = []
        for seg_data in data.get("segments", []):
            if isinstance(seg_data, dict):
                segments.append(TranscriptionSegment.from_legacy_format(seg_data))
            else:
                # TranscriptionSegmentオブジェクトの場合
                segments.append(
                    TranscriptionSegment.from_legacy_format(
                        {
                            "text": seg_data.text,
                            "start": seg_data.start,
                            "end": seg_data.end,
                            "words": getattr(seg_data, "words", None),
                            "chars": getattr(seg_data, "chars", None),
                        }
                    )
                )

        return cls(
            id=str(uuid4()),
            language=data["language"],
            segments=segments,
            original_audio_path=str(data["original_audio_path"]),
            model_size=data["model_size"],
            processing_time=data["processing_time"],
            metadata=data.get("metadata", {}),
        )

    def to_legacy_format(self) -> dict[str, Any]:
        """レガシー形式に変換"""
        return {
            "language": self.language,
            "segments": [seg.to_legacy_format() for seg in self.segments],
            "original_audio_path": self.original_audio_path,
            "model_size": self.model_size,
            "processing_time": self.processing_time,
        }
