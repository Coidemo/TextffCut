"""
バズクリップ生成のViewModel
"""

from dataclasses import dataclass, field
from typing import Any

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.view_models.base import BaseViewModel


@dataclass
class BuzzClipViewModel(BaseViewModel):
    """
    バズクリップ生成のViewModel

    バズクリップ生成機能の状態とUIデータを管理します。
    """

    # 生成設定
    num_candidates: int = 10
    min_duration: int = 30
    max_duration: int = 40
    selected_categories: list[str] = field(default_factory=list)

    # 利用可能なカテゴリ
    available_categories: list[str] = field(
        default_factory=lambda: ["仕事術", "人間関係", "ライフハック", "日常の疑問", "新しい視点", "その他"]
    )

    # 処理状態
    is_generating: bool = False
    generation_progress: float = 0.0
    generation_status: str = ""

    # 結果
    candidates: list[BuzzClipCandidate] = field(default_factory=list)

    # 統計情報
    total_processing_time: float = 0.0
    model_used: str = ""
    token_usage: dict = field(default_factory=dict)

    # エラー
    error_message: str | None = None

    # UI状態
    show_results: bool = False
    show_preview: bool = False
    preview_candidate_id: str | None = None

    @property
    def has_candidates(self) -> bool:
        """候補があるかどうか"""
        return len(self.candidates) > 0

    @property
    def duration_range_text(self) -> str:
        """時間範囲のテキスト表現"""
        return f"{self.min_duration}〜{self.max_duration}秒"

    @property
    def categories_text(self) -> str:
        """選択されたカテゴリのテキスト表現"""
        if not self.selected_categories:
            return "すべて"
        return "、".join(self.selected_categories)

    def get_candidate_by_id(self, candidate_id: str) -> BuzzClipCandidate | None:
        """IDで候補を取得"""
        for candidate in self.candidates:
            if candidate.id == candidate_id:
                return candidate
        return None

    def start_generation(self) -> None:
        """生成を開始"""
        self.is_generating = True
        self.generation_progress = 0.0
        self.generation_status = "AI分析を開始しています..."
        self.error_message = None
        self.candidates = []
        self.notify()

    def update_generation_progress(self, progress: float, status: str) -> None:
        """生成進捗を更新"""
        self.generation_progress = min(progress, 1.0)
        self.generation_status = status
        self.notify()

    def complete_generation(
        self, candidates: list[BuzzClipCandidate], processing_time: float, model_used: str, token_usage: dict
    ) -> None:
        """生成を完了"""
        self.is_generating = False
        self.generation_progress = 1.0
        self.generation_status = "生成完了"
        self.candidates = candidates
        self.total_processing_time = processing_time
        self.model_used = model_used
        self.token_usage = token_usage
        self.show_results = True
        self.notify()

    def set_error(self, message: str) -> None:
        """エラーを設定"""
        self.is_generating = False
        self.error_message = message
        self.notify()

    def reset(self) -> None:
        """状態をリセット"""
        self.candidates = []
        self.is_generating = False
        self.generation_progress = 0.0
        self.generation_status = ""
        self.error_message = None
        self.show_results = False
        self.show_preview = False
        self.preview_candidate_id = None
        self.notify()

    def to_dict(self) -> dict[str, Any]:
        """辞書形式に変換"""
        return {
            "num_candidates": self.num_candidates,
            "min_duration": self.min_duration,
            "max_duration": self.max_duration,
            "selected_categories": self.selected_categories,
            "is_generating": self.is_generating,
            "generation_progress": self.generation_progress,
            "generation_status": self.generation_status,
            "candidates": [c.to_dict() for c in self.candidates],
            "total_processing_time": self.total_processing_time,
            "model_used": self.model_used,
            "token_usage": self.token_usage,
            "error_message": self.error_message,
            "show_results": self.show_results,
            "show_preview": self.show_preview,
            "preview_candidate_id": self.preview_candidate_id,
        }

    def validate(self) -> bool:
        """検証"""
        if self.min_duration < 10 or self.min_duration > 60:
            return False

        if self.max_duration < 10 or self.max_duration > 60:
            return False

        if self.min_duration >= self.max_duration:
            return False

        if self.num_candidates < 1:
            return False

        return True
