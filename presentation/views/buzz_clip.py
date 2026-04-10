"""
バズクリップ生成View

StreamlitのUIコンポーネントを使用してバズクリップ生成画面を表示します。
"""

import logging
from typing import Any

import streamlit as st

from domain.entities.buzz_clip import BuzzClipCandidate
from presentation.presenters.buzz_clip import BuzzClipPresenter
from presentation.view_models.buzz_clip import BuzzClipViewModel
from utils.test_ids import TestIds

logger = logging.getLogger(__name__)


class BuzzClipView:
    """
    バズクリップ生成のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: BuzzClipPresenter):
        """
        初期化

        Args:
            presenter: バズクリップPresenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: BuzzClipViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(
        self,
        transcription_segments: list[dict[str, Any]] | None = None,
        video_path: str | None = None,
        transcription_model: str | None = None,
    ) -> None:
        """
        UIをレンダリング

        Args:
            transcription_segments: 文字起こしセグメント（結果がある場合）
            video_path: 動画ファイルパス（キャッシュ用）
            transcription_model: 文字起こしモデル名（キャッシュ紐付け用）
        """
        # 文字起こし結果がない場合
        if not transcription_segments:
            return

        # 自動的にプロンプトを表示
        self._show_prompt_for_copy(transcription_segments)

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")

    def _show_prompt_for_copy(self, transcription_segments: list[dict[str, Any]]) -> None:
        """プロンプトを表示してコピーできるようにする"""
        # プロンプトを生成
        prompt = self.presenter.generate_prompt_for_external_ai(transcription_segments)

        # プロンプトを表示（最小高さに設定）
        st.text_area(
            "💡 切り抜き生成プロンプト",
            value=prompt,
            height=68,
            key=TestIds.BUZZ_CLIP_PROMPT_AREA,
            help="Ctrl+A (Windows) / Cmd+A (Mac) で全選択してコピー",
        )


def show_buzz_clip_generation(container: Any, transcription_segments: list[dict[str, Any]] | None = None) -> None:
    """
    バズクリップ生成セクションを表示

    Args:
        container: DIコンテナ
        transcription_segments: 文字起こしセグメント
    """
    # PresenterとViewを作成
    presenter = container.presentation.buzz_clip_presenter()
    view = BuzzClipView(presenter)

    # 初期化
    presenter.initialize()

    # UIをレンダリング
    view.render(transcription_segments)
