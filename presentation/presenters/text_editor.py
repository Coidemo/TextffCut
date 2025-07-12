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
            if self.session_manager:
                logger.debug(f"use_buzz_clips: {self.session_manager.get('use_buzz_clips', False)}")
                logger.debug(
                    f"_skip_initial_text_processing: {self.session_manager.get('_skip_initial_text_processing', False)}"
                )
                logger.debug(f"edited_text exists: {bool(self.session_manager.get('edited_text'))}")

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
            # 文字起こし結果の全文を取得
            # 重要：words情報から再構築したテキストを使用する
            # これにより、CharacterArrayBuilderと同じテキストになり、位置が一致する
            try:
                from domain.use_cases.character_array_builder import CharacterArrayBuilder
                from adapters.converters.transcription_converter import TranscriptionConverter
                
                # ドメイン形式に変換（必要な場合）
                if hasattr(actual_result, 'segments') and not hasattr(actual_result, 'computed_duration'):
                    # レガシー形式の場合は変換
                    converter = TranscriptionConverter()
                    domain_result = converter.from_legacy(actual_result)
                else:
                    domain_result = actual_result
                
                # CharacterArrayBuilderで再構築
                builder = CharacterArrayBuilder()
                char_array, reconstructed_text = builder.build_from_transcription(domain_result)
                full_text = reconstructed_text
                logger.info(f"[TextEditorPresenter.initialize] Words情報から再構築: {len(full_text)}文字")
                
            except Exception as e:
                logger.warning(f"CharacterArrayBuilder failed: {e}. Falling back to segment text concatenation.")
                # フォールバック：セグメントのテキストを結合
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
            if self.session_manager:
                # 初期処理をスキップするフラグがある場合は処理しない
                if not self.session_manager.get("_skip_initial_text_processing", False):
                    edited_text = self.session_manager.get("edited_text")
                    if edited_text:
                        # ViewModelのupdate_edited_textメソッドを使用して、char_countも更新
                        self.view_model.update_edited_text(edited_text)
                        # 保存された差分があれば復元
                        text_differences = self.session_manager.get("text_differences")
                        if text_differences:
                            self.view_model.differences = text_differences
                        # 編集済みテキストがある場合は処理を実行して差分を計算
                        self._process_edited_text()

            # 初期テキストがあれば設定（初期処理スキップフラグがない場合のみ）
            if self.view_model.edited_text and self.session_manager and not self.session_manager.get("_skip_initial_text_processing", False):
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
        
        # SequenceMatcherTextProcessorGatewayの場合、TranscriptionResultを設定
        if hasattr(self.text_processor_gateway, 'set_transcription_result'):
            self.text_processor_gateway.set_transcription_result(self.view_model.transcription_result)

        # 区切り文字を検出
        separator = self._detect_separator(edited_text)

        if separator:
            # セクション分割モード（元のテキストを渡す）
            self._process_with_separator(edited_text, separator)
        else:
            # 単一セクションモード（元のテキストを渡す）
            self._process_single_section(edited_text)

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
                if self.session_manager:
                    self.session_manager.set("text_differences", result)

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

            for diff_item in diff_result.differences:
                # タプルの長さをチェック
                if len(diff_item) >= 3:
                    diff_type, text = diff_item[0], diff_item[1]
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
            if hasattr(diff_result, "differences"):
                # 該当する部分のテキストを探す
                from domain.entities.text_difference import DifferenceType

                unchanged_texts = []
                for diff_item in diff_result.differences:
                    if len(diff_item) >= 3 and diff_item[0] == DifferenceType.UNCHANGED:
                        unchanged_texts.append(diff_item[1])
                if i < len(unchanged_texts):
                    preview_text = (
                        unchanged_texts[i][:50] + "..." if len(unchanged_texts[i]) > 50 else unchanged_texts[i]
                    )
                    logger.info(f"  対応テキスト: {preview_text}")
        logger.info("=== デバッグ情報終了 ===")

        self.view_model.update_time_ranges(time_ranges)

        # SessionManagerも更新
        if self.session_manager and time_ranges:
            self.session_manager.set_time_ranges(time_ranges)




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
