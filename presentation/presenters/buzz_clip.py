"""
バズクリップ生成のPresenter
"""

import logging
from typing import List, Dict, Any, Optional, Callable

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.presenters.base import BasePresenter
from presentation.view_models.buzz_clip import BuzzClipViewModel
from use_cases.ai.generate_buzz_clips import (
    GenerateBuzzClipsUseCase,
    GenerateBuzzClipsRequest,
)

logger = logging.getLogger(__name__)


class BuzzClipPresenter(BasePresenter[BuzzClipViewModel]):
    """
    バズクリップ生成のPresenter
    
    バズクリップ生成機能のビジネスロジックとViewの橋渡しを行います。
    """
    
    def __init__(
        self,
        view_model: BuzzClipViewModel,
        generate_buzz_clips_use_case: GenerateBuzzClipsUseCase,
        session_manager: Any = None
    ):
        """
        初期化
        
        Args:
            view_model: ViewModel
            generate_buzz_clips_use_case: バズクリップ生成ユースケース
            session_manager: セッション管理
        """
        super().__init__(view_model)
        self.generate_buzz_clips_use_case = generate_buzz_clips_use_case
        self.session_manager = session_manager
    
    def initialize(self) -> None:
        """初期化処理"""
        logger.info("BuzzClipPresenter initialized")
        
        # セッションから状態を復元
        if self.session_manager:
            saved_state = self.session_manager.get("buzz_clip_state")
            if saved_state:
                self._restore_state(saved_state)
    
    def set_generation_params(
        self,
        num_candidates: int,
        min_duration: int,
        max_duration: int,
        categories: List[str]
    ) -> None:
        """
        生成パラメータを設定
        
        Args:
            num_candidates: 候補数
            min_duration: 最小時間（秒）
            max_duration: 最大時間（秒）
            categories: カテゴリリスト
        """
        self.view_model.num_candidates = num_candidates
        self.view_model.min_duration = min_duration
        self.view_model.max_duration = max_duration
        self.view_model.selected_categories = categories
        
        # セッションに保存
        if self.session_manager:
            self._save_state()
    
    def generate_buzz_clips(
        self,
        transcription_segments: List[Dict[str, Any]],
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """
        バズクリップを生成
        
        Args:
            transcription_segments: 文字起こしセグメント
            progress_callback: 進捗コールバック
            
        Returns:
            成功したかどうか
        """
        logger.info(f"Starting buzz clip generation with {len(transcription_segments)} segments")
        
        try:
            # 生成開始
            self.view_model.start_generation()
            
            if progress_callback:
                progress_callback(0.1, "文字起こし結果を準備中...")
            
            # 全テキストを結合
            full_text = "\n".join([seg["text"] for seg in transcription_segments])
            
            # リクエストを作成
            request = GenerateBuzzClipsRequest(
                transcription_text=full_text,
                transcription_segments=transcription_segments,
                num_candidates=self.view_model.num_candidates,
                min_duration=self.view_model.min_duration,
                max_duration=self.view_model.max_duration,
                categories=self.view_model.selected_categories or None
            )
            
            if progress_callback:
                progress_callback(0.2, "AIによる分析を実行中...")
            
            # ユースケースを実行
            response = self.generate_buzz_clips_use_case.execute(request)
            
            if not response.success:
                logger.error(f"Buzz clip generation failed: {response.error_message}")
                self.view_model.set_error(response.error_message or "生成に失敗しました")
                return False
            
            if progress_callback:
                progress_callback(0.9, "結果を処理中...")
            
            # 結果を設定
            self.view_model.complete_generation(
                candidates=response.candidates,
                processing_time=response.processing_time,
                model_used=response.model_used,
                token_usage=response.usage
            )
            
            # セッションに保存
            if self.session_manager:
                self._save_state()
            
            if progress_callback:
                progress_callback(1.0, "完了")
            
            logger.info(f"Generated {len(response.candidates)} buzz clip candidates")
            return True
            
        except Exception as e:
            logger.error(f"Error generating buzz clips: {e}")
            self.view_model.set_error(str(e))
            return False
    
    def toggle_candidate_selection(self, candidate_id: str) -> None:
        """
        候補の選択状態を切り替え
        
        Args:
            candidate_id: 候補ID
        """
        self.view_model.toggle_candidate_selection(candidate_id)
        
        # セッションに保存
        if self.session_manager:
            self._save_state()
    
    def select_all_candidates(self) -> None:
        """すべての候補を選択"""
        self.view_model.select_all_candidates()
        
        # セッションに保存
        if self.session_manager:
            self._save_state()
    
    def deselect_all_candidates(self) -> None:
        """すべての候補の選択を解除"""
        self.view_model.deselect_all_candidates()
        
        # セッションに保存
        if self.session_manager:
            self._save_state()
    
    def get_selected_candidates(self) -> List[BuzzClipCandidate]:
        """
        選択された候補を取得
        
        Returns:
            選択された候補のリスト
        """
        selected = []
        for candidate_id in self.view_model.selected_candidates:
            candidate = self.view_model.get_candidate_by_id(candidate_id)
            if candidate:
                selected.append(candidate)
        return selected
    
    def reset(self) -> None:
        """状態をリセット"""
        self.view_model.reset()
        
        # セッションからも削除
        if self.session_manager:
            self.session_manager.set("buzz_clip_state", None)
    
    def _save_state(self) -> None:
        """状態をセッションに保存"""
        if not self.session_manager:
            return
        
        state = {
            "num_candidates": self.view_model.num_candidates,
            "min_duration": self.view_model.min_duration,
            "max_duration": self.view_model.max_duration,
            "selected_categories": self.view_model.selected_categories,
            "candidates": [c.to_dict() for c in self.view_model.candidates],
            "selected_candidates": self.view_model.selected_candidates,
            "total_processing_time": self.view_model.total_processing_time,
            "model_used": self.view_model.model_used,
            "token_usage": self.view_model.token_usage,
        }
        
        self.session_manager.set("buzz_clip_state", state)
    
    def _restore_state(self, state: Dict[str, Any]) -> None:
        """セッションから状態を復元"""
        self.view_model.num_candidates = state.get("num_candidates", 5)
        self.view_model.min_duration = state.get("min_duration", 30)
        self.view_model.max_duration = state.get("max_duration", 40)
        self.view_model.selected_categories = state.get("selected_categories", [])
        self.view_model.selected_candidates = state.get("selected_candidates", [])
        self.view_model.total_processing_time = state.get("total_processing_time", 0.0)
        self.view_model.model_used = state.get("model_used", "")
        self.view_model.token_usage = state.get("token_usage", {})
        
        # 候補を復元
        candidates = []
        for candidate_dict in state.get("candidates", []):
            candidate = BuzzClipCandidate(
                id=candidate_dict["id"],
                title=candidate_dict["title"],
                text=candidate_dict["text"],
                start_time=candidate_dict["start_time"],
                end_time=candidate_dict["end_time"],
                duration=candidate_dict["duration"],
                score=candidate_dict["score"],
                category=candidate_dict["category"],
                reasoning=candidate_dict["reasoning"],
                keywords=candidate_dict["keywords"],
                created_at=candidate_dict.get("created_at")
            )
            candidates.append(candidate)
        
        if candidates:
            self.view_model.candidates = candidates
            self.view_model.show_results = True