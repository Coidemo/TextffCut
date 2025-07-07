"""
テキスト編集のPresenter

テキスト編集のビジネスロジックを処理します。
"""

from typing import Any, Protocol

from domain.entities import TranscriptionResult
from domain.interfaces.error_handler import IErrorHandler
from presentation.presenters.base import BasePresenter
from presentation.view_models.text_editor import TextEditorViewModel
from use_cases.interfaces import ITextProcessorGateway, IVideoProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class TextEditorPresenter(BasePresenter[TextEditorViewModel]):
    """
    テキスト編集のPresenter

    テキスト編集、差分検出、時間計算などの処理を行います。
    """

    def __init__(
        self,
        view_model: TextEditorViewModel,
        text_processor_gateway: ITextProcessorGateway,
        video_processor_gateway: IVideoProcessorGateway,
        error_handler: IErrorHandler,
        session_manager: Any = None,  # TODO: SessionManagerProtocolに置き換え
    ):
        """
        初期化

        Args:
            view_model: ViewModel
            text_processor_gateway: テキスト処理ゲートウェイ
            video_processor_gateway: 動画処理ゲートウェイ
            error_handler: エラーハンドラー
            session_manager: セッション管理（オプション）
        """
        super().__init__(view_model)
        self.text_processor_gateway = text_processor_gateway
        self.video_processor_gateway = video_processor_gateway
        self.error_handler = error_handler
        self.session_manager = session_manager

    def initialize(self, transcription_result: TranscriptionResult) -> None:
        """
        文字起こし結果で初期化

        Args:
            transcription_result: 文字起こし結果
        """
        try:
            logger.info("TextEditorPresenter.initialize called")
            logger.debug(f"Type of transcription_result: {type(transcription_result)}")

            # セッション状態のデバッグ情報
            import streamlit as st

            if hasattr(st, "session_state"):
                logger.debug(f"use_buzz_clips: {st.session_state.get('use_buzz_clips', False)}")
                logger.debug(
                    f"_skip_initial_text_processing: {st.session_state.get('_skip_initial_text_processing', False)}"
                )
                logger.debug(f"edited_text in session: {'edited_text' in st.session_state}")

            # TranscriptionResultAdapterの場合は、ドメインエンティティを取得
            from domain.entities.transcription import TranscriptionResult
            from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter

            actual_result = transcription_result
            if isinstance(transcription_result, TranscriptionResultAdapter):
                logger.debug("TranscriptionResultAdapterが渡されました。ドメインエンティティを取得します。")
                actual_result = transcription_result.domain_result
                if actual_result:
                    self.view_model.transcription_result = actual_result
                else:
                    logger.error("TranscriptionResultAdapterにドメインエンティティがありません")
                    raise ValueError("TranscriptionResultAdapter has no domain entity")
            elif isinstance(transcription_result, TranscriptionResult):
                logger.debug("ドメインエンティティのTranscriptionResultが直接渡されました。")
                self.view_model.transcription_result = transcription_result
                actual_result = transcription_result
            else:
                # その他の形式の場合（後方互換性）
                logger.warning(f"未知の形式のtranscription_resultが渡されました: {type(transcription_result)}")
                self.view_model.transcription_result = transcription_result
                actual_result = transcription_result

            # actual_resultから full_text を取得
            try:
                # デバッグ情報を追加
                logger.debug(f"actual_result type: {type(actual_result)}")
                logger.debug(f"actual_result has get_full_text: {hasattr(actual_result, 'get_full_text')}")
                logger.debug(f"actual_result has text: {hasattr(actual_result, 'text')}")

                if hasattr(actual_result, "get_full_text"):
                    full_text = actual_result.get_full_text()
                else:
                    # プロパティとしてアクセス
                    full_text = actual_result.text
            except Exception as e:
                # get_full_text()がエラーを投げた場合（words情報がない場合など）
                logger.warning(f"get_full_text() failed: {e}. Falling back to segment text concatenation.")
                # セグメントのテキストを結合（スペースなしで）
                if hasattr(actual_result, "segments"):
                    full_text = "".join(seg.text for seg in actual_result.segments)
                else:
                    logger.error("No segments found in transcription result")
                    full_text = ""

            logger.info(f"[TextEditorPresenter.initialize] Full text length: {len(full_text) if full_text else 0}")
            if not full_text:
                logger.error("[TextEditorPresenter.initialize] full_textが空です！")
            self.view_model.full_text = full_text

            # セッション状態から編集済みテキストを読み込む
            import streamlit as st

            if hasattr(st, "session_state") and st.session_state is not None:
                # 初期処理をスキップするフラグがある場合は処理しない
                if not st.session_state.get("_skip_initial_text_processing", False):
                    if "edited_text" in st.session_state and st.session_state.edited_text:
                        self.view_model.edited_text = st.session_state.edited_text
                        # 保存された差分があれば復元
                        if "text_differences" in st.session_state:
                            self.view_model.differences = st.session_state.text_differences
                        # 編集済みテキストがある場合は処理を実行して差分を計算
                        self._process_edited_text()

            # 初期テキストがあれば設定（初期処理スキップフラグがない場合のみ）
            if self.view_model.edited_text and not st.session_state.get("_skip_initial_text_processing", False):
                self._process_edited_text()

            self.view_model.notify()

        except Exception as e:
            self.handle_error(e, "初期化")

    def update_edited_text(self, text: str) -> None:
        """
        編集テキストを更新して処理

        Args:
            text: 新しいテキスト
        """
        try:
            # ViewModelを更新
            self.view_model.update_edited_text(text)
            
            # SessionManagerも更新
            if self.session_manager:
                self.session_manager.set_edited_text(text)

            # テキストが空でなければ処理
            if text.strip():
                self._process_edited_text()
            else:
                # 空の場合はリセット
                self.view_model.time_ranges = []
                self.view_model.sections = []
                self.view_model.separator = None
                self.view_model.total_duration = 0.0
                self.view_model.duration_text = ""
                self.view_model.notify()

        except Exception as e:
            self.handle_error(e, "テキスト更新")

    def _process_edited_text(self) -> None:
        """編集テキストを処理"""
        if not self.view_model.transcription_result:
            logger.warning("transcription_result is not set, skipping text processing")
            return

        edited_text = self.view_model.edited_text

        if not edited_text:
            logger.info("No edited text to process")
            return

        logger.info(f"Processing edited text with length: {len(edited_text)}")

        # 境界調整マーカーの存在をチェック
        has_markers = any(marker in edited_text for marker in ["[<", "[>", "<]", ">]"])
        self.view_model.has_boundary_markers = has_markers

        # 境界調整マーカーを除去
        if has_markers:
            cleaned_text = self.text_processor_gateway.remove_boundary_markers(edited_text)
            self.view_model.cleaned_text = cleaned_text
        else:
            cleaned_text = edited_text
            self.view_model.cleaned_text = cleaned_text

        # 区切り文字を検出
        separator = self._detect_separator(cleaned_text)

        if separator:
            # セクション分割モード
            self._process_with_separator(cleaned_text, separator)
        else:
            # 単一セクションモード
            self._process_single_section(cleaned_text)

    def _detect_separator(self, text: str) -> str | None:
        """区切り文字を検出"""
        separator_patterns = ["---", "——", "－－－"]

        for pattern in separator_patterns:
            if pattern in text:
                return pattern

        return None

    def _process_with_separator(self, text: str, separator: str) -> None:
        """区切り文字でセクション分割して処理"""
        try:
            logger.info(f"Processing with separator: '{separator}'")
            # セクションに分割
            sections = self.text_processor_gateway.split_text_by_separator(text, separator)
            logger.info(f"Split into {len(sections)} sections")
            self.view_model.update_sections(sections, separator)

            # 差分検出（セパレータ付き）
            logger.info("Finding differences with separator...")
            result = self.text_processor_gateway.find_differences_with_separator(
                source_text=self.view_model.full_text,
                target_text=text,
                transcription_result=self.view_model.transcription_result,
                separator=separator,
                skip_normalization=self.view_model.has_boundary_markers,
            )

            if result:
                # 差分情報を保存
                self.view_model.differences = result

                # 追加文字のチェック（differencesリストから検出）
                self._check_added_chars(result)

                if not self.view_model.has_added_chars:
                    # 追加文字がない場合は通常処理
                    logger.info("追加文字なし、時間範囲の計算を実行")
                    self._update_time_ranges_from_diff(result)
            else:
                logger.warning("No differences found")

        except Exception as e:
            logger.error(f"セクション分割処理エラー: {e}", exc_info=True)
            # エラーメッセージをより詳細に
            error_msg = str(e)
            if "追加された文字があります" in error_msg or "added characters" in error_msg.lower():
                self.view_model.set_error(
                    "切り抜き箇所のテキストが元の文字起こし結果と一致しません。AIが生成したテキストに誤りがある可能性があります。"
                )
            else:
                # エラーの詳細情報を含める
                import traceback

                detailed_error = f"テキスト処理でエラーが発生しました: {error_msg}\n\n詳細: {traceback.format_exc()}"
                logger.error(detailed_error)
                self.view_model.set_error(f"テキスト処理でエラーが発生しました: {error_msg}")

    def _process_single_section(self, text: str) -> None:
        """単一セクションとして処理"""
        try:
            # full_textが空または未設定の場合のチェック
            if not self.view_model.full_text:
                logger.error("full_textが空または未設定です")
                self.view_model.set_error("文字起こし結果が正しく読み込まれていません。")
                return

            logger.info(
                f"[_process_single_section] full_text長さ: {len(self.view_model.full_text)}, edited_text長さ: {len(text)}"
            )

            # 差分検出（境界調整マーカーがある場合は正規化をスキップ）
            result = self.text_processor_gateway.find_differences(
                original_text=self.view_model.full_text,
                edited_text=text,
                skip_normalization=self.view_model.has_boundary_markers,
            )

            if result:
                # 差分情報を保存
                self.view_model.differences = result

                # 追加文字のチェック（differencesリストから検出）
                self._check_added_chars(result)

                if not self.view_model.has_added_chars:
                    # 追加文字がない場合は通常処理
                    logger.info("追加文字なし、時間範囲の計算を実行")
                    self._update_time_ranges_from_diff(result)

                # 差分をセッション状態に保存（rerun後も保持するため）
                import streamlit as st

                if hasattr(st, "session_state") and st.session_state is not None:
                    st.session_state["text_differences"] = result

                # セクション情報を更新（単一）
                self.view_model.update_sections([text], None)

        except Exception as e:
            logger.error(f"単一セクション処理エラー: {e}", exc_info=True)
            # エラーメッセージをより詳細に
            error_msg = str(e)
            if "追加された文字があります" in error_msg or "added characters" in error_msg.lower():
                self.view_model.set_error(
                    "切り抜き箇所のテキストが元の文字起こし結果と一致しません。AIが生成したテキストに誤りがある可能性があります。"
                )
            else:
                self.view_model.set_error(f"テキスト処理でエラーが発生しました: {error_msg}")

    def _check_added_chars(self, diff_result: Any) -> None:
        """差分結果から追加文字をチェック"""
        added_texts = []

        logger.info(f"[_check_added_chars] 差分結果の型: {type(diff_result)}")

        if hasattr(diff_result, "differences"):
            from domain.entities.text_difference import DifferenceType

            logger.info(
                f"[_check_added_chars] differences数: {len(diff_result.differences) if diff_result.differences else 0}"
            )

            for diff_type, text, _ in diff_result.differences:
                logger.debug(f"[_check_added_chars] 差分タイプ: {diff_type}, テキスト長: {len(text)}")
                if diff_type == DifferenceType.ADDED:
                    added_texts.append(text)
                    logger.info(f"追加されたテキスト検出: '{text}'")

        # ViewModelに状態を設定
        self.view_model.has_added_chars = len(added_texts) > 0
        self.view_model.added_chars_info = added_texts

        if added_texts:
            logger.info(f"追加文字検出のため時間範囲計算をスキップ: {added_texts}")
        else:
            logger.info("[_check_added_chars] 追加文字なし")

    def _update_time_ranges_from_diff(self, diff_result: Any) -> None:
        """差分結果から時間範囲を更新"""
        if not self.view_model.transcription_result:
            return

        # TextDifferenceから時間範囲を取得
        time_ranges = self.text_processor_gateway.get_time_ranges(diff_result, self.view_model.transcription_result)

        # デバッグ情報を出力
        logger.info("=== 時間範囲デバッグ情報 ===")
        logger.info(f"取得した時間範囲数: {len(time_ranges)}")
        for i, tr in enumerate(time_ranges):
            logger.info(f"範囲 {i+1}: {tr.start:.2f}秒 - {tr.end:.2f}秒 (長さ: {tr.duration:.2f}秒)")
            
            # 該当するテキストも表示（最初の50文字）
            if hasattr(diff_result, 'differences'):
                # 該当する部分のテキストを探す
                from domain.entities.text_difference import DifferenceType
                unchanged_texts = []
                for diff_type, text, _ in diff_result.differences:
                    if diff_type == DifferenceType.UNCHANGED:
                        unchanged_texts.append(text)
                if i < len(unchanged_texts):
                    preview_text = unchanged_texts[i][:50] + "..." if len(unchanged_texts[i]) > 50 else unchanged_texts[i]
                    logger.info(f"  対応テキスト: {preview_text}")
        logger.info("=== デバッグ情報終了 ===")

        self.view_model.update_time_ranges(time_ranges)
        
        # SessionManagerも更新
        if self.session_manager and time_ranges:
            self.session_manager.set_time_ranges(time_ranges)

    def remove_boundary_markers(self, text: str) -> str:
        """
        境界調整マーカーを削除

        Args:
            text: マーカーを削除するテキスト

        Returns:
            マーカーを削除したテキスト
        """
        return self.text_processor_gateway.remove_boundary_markers(text)

    def apply_boundary_adjustment_markers(self, text: str) -> None:
        """
        境界調整マーカーを適用

        Args:
            text: マーカーを適用するテキスト
        """
        try:
            if not self.view_model.transcription_result:
                return

            # 既存のマーカー情報を抽出
            existing_markers = self.text_processor_gateway.extract_existing_markers(text)

            # マーカーを除去したテキストで処理
            cleaned_text = self.text_processor_gateway.remove_boundary_markers(text)

            # 区切り文字の確認
            separator_patterns = ["---", "——", "－－－"]
            found_separator = None
            for pattern in separator_patterns:
                if pattern in cleaned_text:
                    found_separator = pattern
                    break

            if found_separator:
                # 区切り文字がある場合：各セクションを処理
                sections = self.text_processor_gateway.split_text_by_separator(cleaned_text, found_separator)
                processed_sections = []

                for section in sections:
                    # 各セクションの差分を検出
                    diff = self.text_processor_gateway.find_differences(
                        original_text=self.view_model.full_text, edited_text=section
                    )

                    # 共通部分を抽出してマーカーを挿入
                    section_with_markers = self._add_markers_to_section(diff, section, existing_markers)
                    processed_sections.append(section_with_markers)

                # セクションを区切り文字で結合
                processed_text = f"\n{found_separator}\n".join(processed_sections)
            else:
                # 区切り文字がない場合：全体を処理
                diff = self.text_processor_gateway.find_differences(
                    original_text=self.view_model.full_text, edited_text=cleaned_text
                )
                processed_text = self._add_markers_to_section(diff, cleaned_text, existing_markers)

            # 処理後のテキストを設定
            self.view_model.edited_text = processed_text
            self.view_model.has_boundary_markers = True
            self.view_model.notify()

            # 境界調整値をセッション状態に保存
            import streamlit as st

            if hasattr(st, "session_state") and st.session_state is not None:
                if existing_markers:
                    st.session_state.boundary_adjustments = existing_markers

            # 再処理してtime_rangesなどを更新
            self._process_edited_text()

        except Exception as e:
            logger.error(f"境界調整マーカー適用エラー: {e}")
            self.view_model.set_error("境界調整マーカーの適用でエラーが発生しました")

    def _add_markers_to_section(self, diff: Any, section: str, existing_markers: dict) -> str:
        """
        セクションにマーカーを追加

        Args:
            diff: 差分情報
            section: セクションテキスト
            existing_markers: 既存のマーカー情報

        Returns:
            マーカーを追加したテキスト
        """
        from domain.entities.text_difference import DifferenceType

        section_with_markers = ""
        common_parts = []

        # ドメインエンティティから共通部分を抽出
        if hasattr(diff, "differences"):
            for diff_type, text, _ in diff.differences:
                if diff_type == DifferenceType.UNCHANGED:
                    common_parts.append(text)

        # 共通部分にマーカーを追加
        for i, text in enumerate(common_parts):
            if i > 0:
                section_with_markers += "\n"

            # 既存マーカーがあればその値を使用、なければ初期値
            if text in existing_markers:
                start_val = existing_markers[text]["start"]
                end_val = existing_markers[text]["end"]
            else:
                start_val = 0.0
                end_val = 0.0

            section_with_markers += f"[<{start_val}]{text}[{end_val}>]"

        return section_with_markers if section_with_markers else section

    def get_processed_data(self) -> dict[str, Any]:
        """
        処理済みデータを取得

        Returns:
            処理結果の辞書
        """
        # 時間範囲をタプル形式に変換（元の実装との互換性のため）
        time_ranges = [(tr.start, tr.end) for tr in self.view_model.time_ranges]

        return {
            "edited_text": self.view_model.edited_text,
            "cleaned_text": self.view_model.cleaned_text,
            "time_ranges": time_ranges,
            "total_duration": self.view_model.total_duration,
            "has_boundary_markers": self.view_model.has_boundary_markers,
            "separator": self.view_model.separator,
            "sections": self.view_model.sections,
            "differences": self.view_model.differences,
        }

    def handle_error(self, error: Exception, context: str) -> None:
        """
        エラーを処理

        Args:
            error: エラー
            context: エラーが発生したコンテキスト
        """
        error_info = self.error_handler.handle_error(error, context=f"テキスト編集: {context}", raise_after=False)

        if error_info:
            self.view_model.set_error(error_info.get("user_message", str(error)))
        else:
            self.view_model.set_error(str(error))

    def generate_audio_preview(
        self, video_path: str, time_ranges: list[tuple], max_duration: float = 30.0
    ) -> str | None:
        """
        音声プレビューを生成

        Args:
            video_path: 動画ファイルパス
            time_ranges: 時間範囲のリスト
            max_duration: 最大プレビュー時間（秒）

        Returns:
            生成された音声ファイルのパス
        """
        try:
            import tempfile

            # 一時ファイルを作成
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                output_path = tmp_file.name

            # プレビュー用の時間範囲を調整（最大duration秒）
            preview_ranges = []
            total_duration = 0

            for start, end in time_ranges:
                segment_duration = end - start
                if total_duration + segment_duration <= max_duration:
                    preview_ranges.append((start, end))
                    total_duration += segment_duration
                else:
                    # 残り時間分だけ追加
                    remaining = max_duration - total_duration
                    if remaining > 0:
                        preview_ranges.append((start, start + remaining))
                    break

            if preview_ranges:
                # Gateway経由で音声を結合
                self.video_processor_gateway.extract_and_combine_audio(
                    video_path=video_path, time_ranges=preview_ranges, output_path=output_path
                )
                return output_path

            return None

        except Exception as e:
            logger.error(f"音声プレビュー生成エラー: {e}")
            return None
