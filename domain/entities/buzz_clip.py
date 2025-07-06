"""
バズる切り抜き候補のドメインエンティティ
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BuzzClipCandidate:
    """バズる切り抜き候補"""

    id: str
    title: str  # タイトル案
    text: str  # 切り抜きテキスト
    start_time: float  # 開始時間（秒）
    end_time: float  # 終了時間（秒）
    duration: float  # 長さ（秒）
    score: int  # バズスコア（0-20）
    category: str  # カテゴリ（感動系、驚き系等）
    reasoning: str  # 選定理由
    keywords: list[str]  # キーワード
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def create(
        cls,
        title: str,
        text: str,
        start_time: float,
        end_time: float,
        score: int,
        category: str,
        reasoning: str,
        keywords: list[str],
    ) -> "BuzzClipCandidate":
        """ファクトリメソッド"""
        return cls(
            id=str(uuid.uuid4()),
            title=title,
            text=text,
            start_time=start_time,
            end_time=end_time,
            duration=end_time - start_time,
            score=score,
            category=category,
            reasoning=reasoning,
            keywords=keywords,
        )

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        # created_atがdatetimeオブジェクトか文字列かを判定
        if isinstance(self.created_at, datetime):
            created_at_str = self.created_at.isoformat()
        else:
            # 既に文字列の場合はそのまま使用
            created_at_str = self.created_at

        return {
            "id": self.id,
            "title": self.title,
            "text": self.text,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "score": self.score,
            "category": self.category,
            "reasoning": self.reasoning,
            "keywords": self.keywords,
            "created_at": created_at_str,
        }


@dataclass
class BuzzClipGenerationRequest:
    """生成リクエスト"""

    transcription_text: str
    transcription_segments: list[dict]  # タイムスタンプ付きセグメント
    num_candidates: int = 5
    min_duration: int = 30
    max_duration: int = 40
    categories: list[str] | None = None  # 指定カテゴリ


@dataclass
class BuzzClipGenerationResult:
    """生成結果"""

    candidates: list[BuzzClipCandidate]
    total_processing_time: float
    model_used: str
    usage: dict  # トークン使用量
