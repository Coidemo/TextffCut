"""
テキスト編集View

StreamlitのUIコンポーネントを使用してテキスト編集画面を表示します。
"""

from pathlib import Path
from typing import Any

import streamlit as st

from domain.entities import TranscriptionResult
from presentation.presenters.text_editor import TextEditorPresenter
from presentation.view_models.text_editor import TextEditorViewModel
from ui.components import show_diff_viewer, show_edited_text_with_highlights, show_red_highlight_modal, show_text_editor
from utils.logging import get_logger
from utils.test_ids import TestIds

logger = get_logger(__name__)


class TextEditorView:
    """
    テキスト編集のView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: TextEditorPresenter, container: Any | None = None):
        """
        初期化

        Args:
            presenter: テキスト編集Presenter
            container: DIコンテナ（バズクリップ機能で使用）
        """
        self.presenter = presenter
        self.view_model = presenter.view_model
        self.container = container

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: TextEditorViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(self, transcription_result: TranscriptionResult, video_path: Path) -> dict[str, Any]:
        """
        UIをレンダリング

        Args:
            transcription_result: 文字起こし結果
            video_path: 動画ファイルパス

        Returns:
            処理結果の辞書
        """
        # 動画パスが変わった場合はキャッシュチェックをリセット
        current_video_path = str(video_path)
        if st.session_state.get("last_video_path_for_buzz") != current_video_path:
            st.session_state["last_video_path_for_buzz"] = current_video_path
            if "buzz_clip_cache_checked" in st.session_state:
                del st.session_state["buzz_clip_cache_checked"]
            if "buzz_clip_cache_exists" in st.session_state:
                del st.session_state["buzz_clip_cache_exists"]

        # 初期化
        self.presenter.initialize(transcription_result)

        # モーダル表示（最優先）
        if st.session_state.get("show_modal", False):
            with st.container():
                st.markdown("### ⚠️ 元動画に存在しない文字が検出されました")
                edited_text = st.session_state.get("current_edited_text", "")
                diff = st.session_state.get("current_diff")
                show_red_highlight_modal(edited_text, diff)
                # モーダルが表示されているときは他の処理をスキップ
                return {}

        # エラー表示（2カラムの上に表示）
        if st.session_state.get("show_error_and_delete", False):
            st.error("⚠️ 元動画に存在しない文字が切り抜き箇所に入力されています。削除してください。")

        # 2カラムレイアウト
        col1, col2 = st.columns([1, 1])

        # 左カラム: 文字起こし結果
        with col1:
            st.markdown("#### 文字起こし結果")
            st.caption("切り抜き箇所に指定した箇所が緑色でハイライトされます")
            # 文字起こし結果を表示
            self._render_transcription_result()

            # バズクリップ機能を表示
            self._render_buzz_clip_section()

        # 右カラム: テキスト編集
        with col2:
            st.markdown("#### 切り抜き箇所")
            st.caption("文字起こし結果から切り抜く箇所を入力してください")

            # テキストエディタ
            edited_text = self._render_text_editor()

            # 文字数と時間の表示
            if self.view_model.edited_text:
                self._render_text_stats()

            # アクションボタン
            self._render_action_buttons()

        # 境界調整マーカー検出時の表示
        if self.view_model.has_boundary_markers:
            self._render_boundary_markers_info()

        # セクション分割時の表示
        if self.view_model.has_separator:
            self._render_sections_info()

        # 時間範囲の計算結果表示
        if self.view_model.has_time_ranges:
            self._render_time_ranges_info()

        # エラー表示
        if self.view_model.error_message:
            st.error(f"❌ {self.view_model.error_message}")

        # マーカー位置エラーの表示
        if st.session_state.get("show_marker_error", False):
            st.error("⚠️ 境界調整マーカーの位置が不適切です。マーカーは各行の先頭と末尾にのみ配置してください。")
            marker_errors = st.session_state.get("marker_position_errors", [])
            for error in marker_errors:
                st.error(f"❌ {error}")

        # AI自動切り抜きセクション
        self._render_ai_clip_section()

        # 処理データを返す
        return self.presenter.get_processed_data()

    def _render_transcription_result(self) -> None:
        """文字起こし結果を表示"""
        if self.view_model.full_text:
            # 編集テキストがある場合は差分を表示
            if self.view_model.edited_text and self.view_model.differences:
                show_diff_viewer(self.view_model.full_text, self.view_model.differences)
            else:
                # 差分がない場合は元のテキストのみ表示
                show_diff_viewer(self.view_model.full_text)
        else:
            st.info("文字起こし結果がありません")

    def _render_text_editor(self) -> str:
        """テキストエディタを表示"""
        # セッション状態から初期値を取得
        initial_text = st.session_state.get("text_editor_value", self.view_model.edited_text)

        # テキストエディタ表示
        edited_text = st.text_area(
            "編集エリア", value=initial_text, height=400, key="text_editor", label_visibility="collapsed"
        )

        # テキストが変更されたら更新
        if edited_text != self.view_model.edited_text:
            self.presenter.update_edited_text(edited_text)

        return edited_text

    def _render_buzz_clip_navigation(self) -> None:
        """バズクリップ候補のナビゲーションUIを表示"""
        candidates = st.session_state.buzz_clip_all_candidates
        current_index = st.session_state.get("buzz_clip_current_index", 0)

        # ナビゲーションコントロール
        nav_col1, nav_col2, nav_col3 = st.columns([1, 8, 1])

        with nav_col1:
            # 前の候補ボタン
            if st.button("◀", key="buzz_prev", disabled=current_index == 0, use_container_width=True):
                new_index = current_index - 1
                st.session_state.buzz_clip_current_index = new_index
                # 候補を切り替え
                self._switch_to_candidate(candidates[new_index])
                st.rerun()

        with nav_col2:
            # 現在の候補情報
            candidate = candidates[current_index]
            st.info(f"候補 {current_index + 1}/{len(candidates)}: {candidate.title}")

        with nav_col3:
            # 次の候補ボタン
            if st.button("▶", key="buzz_next", disabled=current_index >= len(candidates) - 1, use_container_width=True):
                new_index = current_index + 1
                st.session_state.buzz_clip_current_index = new_index
                # 候補を切り替え
                self._switch_to_candidate(candidates[new_index])
                st.rerun()

        # 追加取得ボタン
        if st.button("🔄 新しい候補を追加取得 （API使用）", key="generate_more_buzz_clips", use_container_width=True):
            # 追加生成フラグを設定してrerun
            st.session_state["buzz_clip_append_generation_requested"] = True
            st.rerun()

        # 予想コストを表示
        self._render_estimated_cost()

    def _switch_to_candidate(self, candidate) -> None:
        """指定された候補に切り替え"""
        # テキストエディタに候補のテキストを設定
        st.session_state.text_editor_value = candidate.text
        # ビューモデルも更新
        self.presenter.update_edited_text(candidate.text)

    def _render_estimated_cost(self) -> None:
        """予想コストを表示"""
        # 文字起こし結果から概算トークン数を計算
        if self.view_model.full_text:
            # 日本語の場合、1文字≒1トークンとして概算
            # 英語の場合、4文字≒1トークンだが、安全側に見積もる
            estimated_input_tokens = len(self.view_model.full_text) * 1.2  # 余裕を持たせる
            estimated_output_tokens = 2500  # 生成される候補の平均的なトークン数

            # GPT-4oの料金で計算
            input_cost = (estimated_input_tokens / 1000000) * 5.0
            output_cost = (estimated_output_tokens / 1000000) * 20.0
            total_cost = input_cost + output_cost

            # 円換算
            total_cost_jpy = total_cost * 150

            st.caption(f"💰 予想コスト: 約{total_cost_jpy:.0f}円（GPT-4o使用）")

    def _check_buzz_clip_cache(self) -> bool:
        """バズクリップのキャッシュが存在するか確認"""
        try:
            from infrastructure.ui.session_manager import SessionManager
            from pathlib import Path
            import os

            session_manager = SessionManager()
            video_path = session_manager.get_video_path()
            transcription_result = session_manager.get_transcription_result()

            logger.info(f"[_check_buzz_clip_cache] video_path: {video_path}")
            logger.info(f"[_check_buzz_clip_cache] transcription_result exists: {transcription_result is not None}")

            if not video_path or not transcription_result:
                logger.info("[_check_buzz_clip_cache] No video_path or transcription_result")
                return False

            # TranscriptionResultAdapterの処理
            from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter

            if isinstance(transcription_result, TranscriptionResultAdapter):
                actual_result = transcription_result.domain_result
                logger.info("[_check_buzz_clip_cache] Using domain_result from adapter")
            else:
                actual_result = transcription_result
                logger.info("[_check_buzz_clip_cache] Using transcription_result directly")

            # 文字起こしモデル情報を取得
            transcription_model = None
            if hasattr(actual_result, "model_size"):
                transcription_model = actual_result.model_size
                logger.info(f"[_check_buzz_clip_cache] transcription_model: {transcription_model}")
            else:
                logger.info("[_check_buzz_clip_cache] No model_size attribute")

            # キャッシュパスを構築
            video_path_obj = Path(video_path)
            textffcut_dir = video_path_obj.parent / f"{video_path_obj.stem}_TextffCut"

            # textffcut_dirが存在しない場合はFalse
            if not textffcut_dir.exists():
                logger.info(f"[_check_buzz_clip_cache] TextffCut directory does not exist: {textffcut_dir}")
                return False

            cache_dir = textffcut_dir / "buzz_clips"

            # キャッシュファイルパスを作成
            if transcription_model:
                cache_file = cache_dir / f"{transcription_model}.json"
            else:
                cache_file = cache_dir / "default.json"

            logger.info(f"[_check_buzz_clip_cache] Looking for cache file: {cache_file}")
            exists = cache_file.exists()
            logger.info(f"[_check_buzz_clip_cache] Cache exists: {exists}")

            return exists

        except Exception as e:
            logger.error(f"[_check_buzz_clip_cache] Error: {e}", exc_info=True)
            return False

    def _generate_buzz_clips(self, force_new: bool = False, append_to_existing: bool = False) -> None:
        """バズクリップを生成"""
        logger.info(f"_generate_buzz_clips called with force_new={force_new}, append_to_existing={append_to_existing}")

        # APIキーの確認
        from infrastructure.ui.session_manager import SessionManager

        session_manager = SessionManager()
        api_key = session_manager.get("api_key")
        logger.info(f"API key exists: {bool(api_key)}")

        if not api_key:
            st.error("⚠️ この機能を使用するには、サイドバーでOpenAI APIキーを設定してください")
            return

        # 文字起こし結果を取得
        transcription_result = session_manager.get_transcription_result()
        video_path = session_manager.get_video_path()
        logger.info(f"Transcription result exists: {bool(transcription_result)}")
        logger.info(f"Video path: {video_path}")

        if not transcription_result or not video_path:
            st.error("文字起こし結果が必要です")
            return

        # AI GatewayとUseCaseを作成
        try:
            from infrastructure.external.gateways.openai_gateway import OpenAIGateway
            from use_cases.ai.generate_buzz_clips import GenerateBuzzClipsUseCase
            from presentation.presenters.buzz_clip import BuzzClipPresenter
            from presentation.view_models.buzz_clip import BuzzClipViewModel

            ai_gateway = OpenAIGateway(api_key=api_key)
            generate_buzz_clips_use_case = GenerateBuzzClipsUseCase(ai_gateway=ai_gateway)

            # BuzzClipPresenterを作成
            buzz_clip_view_model = BuzzClipViewModel()
            buzz_clip_presenter = BuzzClipPresenter(
                view_model=buzz_clip_view_model,
                generate_buzz_clips_use_case=generate_buzz_clips_use_case,
                session_manager=session_manager,
            )

            # Presenterを初期化
            buzz_clip_presenter.initialize()

            # 追加生成モードの場合、既存の候補を設定
            if append_to_existing and "buzz_clip_all_candidates" in st.session_state:
                existing_candidates = st.session_state["buzz_clip_all_candidates"]
                logger.info(f"Setting {len(existing_candidates)} existing candidates for append mode")
                buzz_clip_presenter.view_model.candidates = existing_candidates

            # TranscriptionResultAdapterの処理
            from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter

            if isinstance(transcription_result, TranscriptionResultAdapter):
                actual_result = transcription_result.domain_result
            else:
                actual_result = transcription_result

            # 文字起こしモデル情報を取得
            transcription_model = None
            if hasattr(actual_result, "model_size"):
                transcription_model = actual_result.model_size

            # キャッシュから読み込みを試行（force_newかつappend_to_existingでない場合のみ）
            logger.info(f"Checking cache with force_new={force_new}, append_to_existing={append_to_existing}")
            if not force_new and not append_to_existing:
                if buzz_clip_presenter.load_from_cache(video_path, transcription_model):
                    # キャッシュから読み込み成功
                    logger.info("Loaded from cache successfully")
                    candidates = buzz_clip_presenter.view_model.candidates
                    if candidates:
                        st.session_state["buzz_clip_all_candidates"] = candidates
                        st.session_state["buzz_clip_current_index"] = 0
                        # 最初の候補を表示
                        self._switch_to_candidate(candidates[0])
                        st.success(f"✅ {len(candidates)}個のバズクリップ候補を読み込みました")
                        st.rerun()
                else:
                    logger.info("No cache found, proceeding with API generation")
            else:
                logger.info(f"force_new={force_new} or append_to_existing={append_to_existing}, skipping cache check")
                # APIで新規生成
                logger.info("Starting API generation")
                progress_bar = st.progress(0, text="🔍 AIが文字起こし結果を分析中...")
                status_text = st.empty()

                try:
                    import time

                    start_time = time.time()

                    # 進捗コールバック
                    def progress_callback(progress: float, status: str):
                        elapsed_time = time.time() - start_time
                        # APIレスポンス待ちの場合は経過時間を表示
                        if "API" in status or "分析" in status:
                            progress_bar.progress(progress, text=f"{status} （{elapsed_time:.1f}秒経過）")
                        else:
                            progress_bar.progress(progress, text=status)

                        if progress >= 1.0:
                            status_text.success("✅ 生成完了")
                        else:
                            # API待ちの場合は詳細を表示
                            if elapsed_time > 5:
                                status_text.warning(f"⏳ APIレスポンス待ち... {elapsed_time:.0f}秒経過")
                            else:
                                status_text.info(f"🤖 {status}")

                    # セグメントを辞書形式に変換
                    segments = []
                    for seg in actual_result.segments:
                        segments.append({"text": seg.text, "start": seg.start, "end": seg.end})

                    # 生成パラメータを表示
                    status_text.info(
                        f"📈 生成設定: {buzz_clip_presenter.view_model.num_candidates}個の候補 / {buzz_clip_presenter.view_model.min_duration}-{buzz_clip_presenter.view_model.max_duration}秒 / OpenAI GPT-4o"
                    )

                    # 生成実行
                    progress_callback(0.1, "APIへ接続中...")
                    logger.info(
                        f"Calling generate_buzz_clips with {len(segments)} segments, force_new={force_new}, append_to_existing={append_to_existing}"
                    )
                    success = buzz_clip_presenter.generate_buzz_clips(
                        transcription_segments=segments,
                        video_path=video_path,
                        transcription_model=transcription_model,
                        progress_callback=progress_callback,
                        save_cache=True,  # 常にキャッシュに保存（追加の場合も更新）
                        append_to_existing=append_to_existing,
                    )
                    logger.info(f"generate_buzz_clips returned: {success}")

                    logger.info(
                        f"After generation: success={success}, candidates count={len(buzz_clip_presenter.view_model.candidates)}"
                    )

                    if success and buzz_clip_presenter.view_model.candidates:
                        candidates = buzz_clip_presenter.view_model.candidates
                        logger.info(f"Saving {len(candidates)} candidates to session state")

                        # コスト情報を計算
                        cost_info = ""
                        if buzz_clip_presenter.view_model.token_usage:
                            # GPT-4oの料金（2025年7月時点）
                            # 入力: $5/1M tokens, 出力: $20/1M tokens
                            input_cost = (
                                buzz_clip_presenter.view_model.token_usage.get("prompt_tokens", 0) / 1000000
                            ) * 5.0
                            output_cost = (
                                buzz_clip_presenter.view_model.token_usage.get("completion_tokens", 0) / 1000000
                            ) * 20.0
                            total_cost = input_cost + output_cost

                            # 円換算（1ドル = 150円として）
                            total_cost_jpy = total_cost * 150

                            cost_info = f"💰 API使用料: ${total_cost:.3f} (約{total_cost_jpy:.0f}円)"
                            logger.info(
                                f"API cost: ${total_cost:.3f}, tokens: {buzz_clip_presenter.view_model.token_usage}"
                            )

                        if append_to_existing:
                            # 追加生成の場合は結果を表示するだけ
                            progress_bar.empty()
                            status_text.empty()
                            new_count = len(candidates) - len(st.session_state.get("buzz_clip_all_candidates", []))
                            st.success(f"✅ {new_count}個の新しい候補を追加しました（合計{len(candidates)}個）")
                            if cost_info:
                                st.info(cost_info)
                            st.session_state["buzz_clip_all_candidates"] = candidates
                        else:
                            st.session_state["buzz_clip_all_candidates"] = candidates
                            st.session_state["buzz_clip_current_index"] = 0
                            # 最初の候補を表示
                            self._switch_to_candidate(candidates[0])
                            progress_bar.empty()
                            status_text.empty()
                            st.success(f"✅ {len(candidates)}個のバズクリップ候補を生成しました（API使用）")
                            if cost_info:
                                st.info(cost_info)
                        st.rerun()
                    else:
                        progress_bar.empty()
                        status_text.empty()
                        logger.error(
                            f"Generation failed or no candidates. success={success}, candidates={buzz_clip_presenter.view_model.candidates}"
                        )
                        st.error("バズクリップの生成に失敗しました")
                        # エラーの詳細を表示
                        if buzz_clip_presenter.view_model.error_message:
                            st.error(f"エラー詳細: {buzz_clip_presenter.view_model.error_message}")
                except TimeoutError:
                    progress_bar.empty()
                    status_text.empty()
                    st.error("⚠️ APIレスポンスがタイムアウトしました。しばらくしてから再度お試しください。")
                except Exception as api_error:
                    progress_bar.empty()
                    status_text.empty()
                    error_type = type(api_error).__name__
                    if "RateLimitError" in error_type:
                        st.error("🚫 APIのレート制限に達しました。少し待ってから再度お試しください。")
                    elif "AuthenticationError" in error_type:
                        st.error("🔒 APIキーが無効です。サイドバーで正しいAPIキーを設定してください。")
                    else:
                        st.error(f"❌ エラーが発生しました: {str(api_error)}")
                    logger.error(f"API call error: {api_error}", exc_info=True)
                finally:
                    # 進捗バーをクリア
                    if "progress_bar" in locals():
                        progress_bar.empty()
                    if "status_text" in locals():
                        status_text.empty()

        except Exception as e:
            error_type = type(e).__name__
            if "APIError" in str(e) or "openai" in str(e).lower():
                st.error("📡 APIとの通信に問題が発生しました。ネットワーク接続を確認してください。")
            else:
                st.error(f"エラーが発生しました: {str(e)}")
            logger.error(f"Buzz clip generation error: {e}", exc_info=True)

    def _render_buzz_clip_section(self) -> None:
        """バズクリップセクションを表示"""
        # 新しい外部AIサービス版のバズクリップ機能を表示
        from presentation.views.buzz_clip import show_buzz_clip_generation
        from infrastructure.ui.session_manager import SessionManager

        session_manager = SessionManager()
        transcription_result = session_manager.get_transcription_result()

        if transcription_result:
            # TranscriptionResultAdapterの処理
            from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter

            if isinstance(transcription_result, TranscriptionResultAdapter):
                actual_result = transcription_result.domain_result
            else:
                actual_result = transcription_result

            # セグメントを辞書形式に変換
            segments = []
            if hasattr(actual_result, "segments"):
                for seg in actual_result.segments:
                    segments.append({"text": seg.text, "start": seg.start, "end": seg.end})

            # プロンプト生成UI（横並び表示）
            if segments and self.container:
                col1, col2 = st.columns(2)

                with col1:
                    # バズクリップ生成UI
                    show_buzz_clip_generation(self.container, segments)

                with col2:
                    # タイトル生成プロンプト
                    self._render_title_generation_prompt()

                # 両方のプロンプトに対する説明を中央に配置
                st.caption("上記のプロンプトをChatGPT/Claude/Geminiなどにコピー&ペーストして使用してください")

    def _render_ai_clip_section(self) -> None:
        """AI自動切り抜きセクションを表示"""
        from textffcut_cli.setup_command import get_config_value
        from infrastructure.ui.session_manager import SessionManager

        st.markdown("---")
        st.markdown("### 🤖 AI自動切り抜き")
        st.caption("AIが話題を検出し、最適な切り抜きを自動生成します（FCPXML+SRT出力）")

        # APIキーチェック（api_key_manager → config.json → 環境変数）
        from utils.api_key_manager import api_key_manager
        api_key = api_key_manager.load_api_key()
        if not api_key:
            api_key = get_config_value("openai_api_key")
        if not api_key:
            import os

            api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")

        if not api_key:
            st.warning(
                "⚠️ OpenAI APIキーが必要です。\n\n"
                "CLIで設定: `textffcut setup`\n"
                "またはサイドバーのAPIキー設定から入力してください。"
            )
            return

        session_manager = SessionManager()
        video_path = session_manager.get_video_path()
        transcription_result = session_manager.get_transcription_result()

        if not video_path or not transcription_result:
            st.info("動画の文字起こしが完了してから使用できます。")
            return

        # 保存された設定を読み込み
        from utils import settings_manager

        saved_num = settings_manager.get("ai_clip_num", 5)
        saved_min = settings_manager.get("ai_clip_min_duration", 30)
        saved_max = settings_manager.get("ai_clip_max_duration", 60)
        saved_srt = settings_manager.get("ai_clip_srt", True)
        saved_silence = settings_manager.get("ai_clip_silence", True)
        saved_speed = settings_manager.get("ai_clip_speed", 1.0)
        saved_zoom = settings_manager.get("ai_clip_zoom", 100)
        saved_anchor_x = settings_manager.get("ai_clip_anchor_x", 0.0)
        saved_anchor_y = settings_manager.get("ai_clip_anchor_y", 0.0)
        saved_timeline = settings_manager.get("ai_clip_timeline", "horizontal")

        # 設定UI
        col1, col2, col3 = st.columns(3)
        with col1:
            num_candidates = st.number_input("候補数", min_value=1, max_value=10, value=saved_num, key="ai_clip_num")
        with col2:
            min_duration = st.number_input("最小秒数", min_value=10, max_value=120, value=saved_min, key="ai_clip_min")
        with col3:
            max_duration = st.number_input("最大秒数", min_value=10, max_value=120, value=saved_max, key="ai_clip_max")

        col_opts1, col_opts2, col_opts3 = st.columns(3)
        with col_opts1:
            generate_srt = st.checkbox("SRT字幕を生成", value=saved_srt, key="ai_clip_srt")
        with col_opts2:
            remove_silence = st.checkbox("無音削除", value=saved_silence, key="ai_clip_silence")
        with col_opts3:
            speed = st.number_input("再生速度", min_value=0.5, max_value=2.0, value=saved_speed, step=0.1, key="ai_clip_speed")

        # ズーム・アンカー・タイムライン設定
        col_zoom1, col_zoom2, col_zoom3, col_zoom4 = st.columns(4)
        with col_zoom1:
            zoom_percent = st.number_input(
                "ズーム (%)", min_value=50, max_value=300, value=saved_zoom, step=10,
                help="100% = 元のサイズ、200% = 2倍拡大", key="ai_clip_zoom",
            )
        with col_zoom2:
            anchor_x = st.number_input(
                "アンカー X", min_value=-100.0, max_value=100.0, value=float(saved_anchor_x), step=0.1,
                help="横方向の位置調整（0 = 中央）", key="ai_clip_anchor_x",
            )
        with col_zoom3:
            anchor_y = st.number_input(
                "アンカー Y", min_value=-100.0, max_value=100.0, value=float(saved_anchor_y), step=0.1,
                help="縦方向の位置調整（0 = 中央）", key="ai_clip_anchor_y",
            )
        with col_zoom4:
            timeline_options = ["横（16:9）", "縦（9:16）"]
            timeline_index = 1 if saved_timeline == "vertical" else 0
            timeline_orientation = st.selectbox(
                "タイムライン", options=timeline_options,
                index=timeline_index, key="ai_clip_timeline",
            )
            timeline_resolution = "vertical" if "縦" in timeline_orientation else "horizontal"

        # 設定値を保存
        settings_manager.set("ai_clip_num", int(num_candidates))
        settings_manager.set("ai_clip_min_duration", int(min_duration))
        settings_manager.set("ai_clip_max_duration", int(max_duration))
        settings_manager.set("ai_clip_srt", generate_srt)
        settings_manager.set("ai_clip_silence", remove_silence)
        settings_manager.set("ai_clip_speed", round(float(speed), 1))
        settings_manager.set("ai_clip_zoom", int(zoom_percent))
        settings_manager.set("ai_clip_anchor_x", float(anchor_x))
        settings_manager.set("ai_clip_anchor_y", float(anchor_y))
        settings_manager.set("ai_clip_timeline", timeline_resolution)

        # メディア素材検出・ON/OFF
        enable_frame = True
        enable_bgm = True
        enable_se = True
        from utils.media_asset_detector import detect_media_assets

        video_path_obj = Path(video_path).resolve()
        detected = detect_media_assets(video_path_obj)
        if detected.has_any:
            st.markdown("##### 🎨 メディア素材")
            if detected.overlay_settings:
                enable_frame = st.checkbox("フレーム画像を適用", value=True, key="ai_clip_frame")
            if detected.bgm_settings:
                enable_bgm = st.checkbox("BGMを適用", value=True, key="ai_clip_bgm")
            if detected.additional_audio_settings:
                n = len(detected.additional_audio_settings["audio_files"])
                enable_se = st.checkbox(f"効果音を適用（{n}個）", value=True, key="ai_clip_se")

        # タイトル画像
        saved_title_img = settings_manager.get("ai_clip_title_image", True)
        enable_title_image = st.checkbox("タイトル画像", value=saved_title_img, key="ai_clip_title")
        settings_manager.set("ai_clip_title_image", enable_title_image)

        # 入力検証
        if int(min_duration) > int(max_duration):
            st.warning("⚠️ 最小秒数が最大秒数より大きくなっています")

        st.caption("💰 コスト目安: 約2-5円/回（GPT-4.1-mini使用）")

        # 実行ボタン
        if st.button(
            "🚀 AI自動切り抜きを実行",
            type="primary",
            use_container_width=True,
            key="run_ai_clip",
            disabled=int(min_duration) > int(max_duration),
        ):
            self._execute_ai_clip(
                api_key=api_key,
                video_path=video_path,
                transcription_result=transcription_result,
                num_candidates=int(num_candidates),
                min_duration=int(min_duration),
                max_duration=int(max_duration),
                generate_srt=generate_srt,
                remove_silence=remove_silence,
                enable_frame=enable_frame,
                enable_bgm=enable_bgm,
                enable_se=enable_se,
                speed=float(speed),
                scale=(zoom_percent / 100.0, zoom_percent / 100.0),
                anchor=(float(anchor_x), float(anchor_y)),
                timeline_resolution=timeline_resolution,
                enable_title_image=enable_title_image,
            )

        # 結果表示
        if "ai_clip_result" in st.session_state and st.session_state["ai_clip_result"]:
            result = st.session_state["ai_clip_result"]

            for i, s in enumerate(result["suggestions"], 1):
                st.markdown(f"**{i}. {s['title']}**　{s['duration']:.0f}秒")

            st.caption(f"📁 {result['output_dir']}")

    def _execute_ai_clip(
        self,
        api_key: str,
        video_path: str,
        transcription_result,
        num_candidates: int,
        min_duration: int,
        max_duration: int,
        generate_srt: bool,
        remove_silence: bool,
        enable_frame: bool = True,
        enable_bgm: bool = True,
        enable_se: bool = True,
        speed: float = 1.0,
        scale: tuple[float, float] = (1.0, 1.0),
        anchor: tuple[float, float] = (0.0, 0.0),
        timeline_resolution: str = "horizontal",
        enable_title_image: bool = True,
    ) -> None:
        """AI自動切り抜きを実行"""
        from pathlib import Path
        from presentation.adapters.transcription_result_adapter import TranscriptionResultAdapter

        # TranscriptionResultAdapterの処理
        if isinstance(transcription_result, TranscriptionResultAdapter):
            actual_result = transcription_result.domain_result
        else:
            actual_result = transcription_result

        # TranscriptionResult（ドメインエンティティ）に変換
        from domain.entities.transcription import TranscriptionResult as DomainTranscriptionResult

        if not isinstance(actual_result, DomainTranscriptionResult):
            # レガシー形式からドメインエンティティに変換
            segments = []
            if hasattr(actual_result, "segments"):
                for seg in actual_result.segments:
                    if isinstance(seg, dict):
                        segments.append(seg)
                    else:
                        segments.append({"text": seg.text, "start": seg.start, "end": seg.end})
            actual_result = DomainTranscriptionResult(
                id=f"gui_{Path(video_path).stem}",
                video_id=video_path,
                language="ja",
                segments=segments,
                duration=segments[-1]["end"] if segments else 0.0,
                original_audio_path="",
                model_size=getattr(actual_result, "model_size", "unknown"),
                processing_time=0.0,
            )

        video_path_obj = Path(video_path).resolve()

        try:
            from infrastructure.external.gateways.openai_clip_suggestion_gateway import (
                OpenAIClipSuggestionGateway,
            )
            from use_cases.ai.suggest_and_export import (
                SuggestAndExportRequest,
                SuggestAndExportUseCase,
            )
            from use_cases.ai.generate_clip_suggestions import GenerateClipSuggestionsUseCase
            from use_cases.ai.word_level_filler_polish import polish_fillers

            gateway = OpenAIClipSuggestionGateway(api_key=api_key, model="gpt-4.1-mini")

            use_case = SuggestAndExportUseCase(gateway=gateway)

            with st.status("AI自動切り抜きを実行中...", expanded=True) as status:
                progress_text = st.empty()

                # Phase 1: 話題検出
                progress_text.write("🔍 話題を検出中...")
                gen_use_case = GenerateClipSuggestionsUseCase(gateway)
                suggestions = gen_use_case.execute(
                    transcription=actual_result,
                    video_path=video_path_obj,
                    num_candidates=num_candidates,
                    min_duration=min_duration,
                    max_duration=max_duration,
                )
                detection = gen_use_case.last_detection_result
                total = len(suggestions)

                if total == 0:
                    status.update(label="⚠️ 切り抜き候補が見つかりませんでした", state="error", expanded=False)
                    return

                progress_text.write(f"✅ {total}件の話題を検出")

                # Phase 2: フィラー仕上げ
                for i, suggestion in enumerate(suggestions):
                    progress_text.write(f"🧹 フィラー除去中... ({i + 1}/{total})")
                    suggestions[i] = polish_fillers(suggestion, actual_result, video_path_obj)

                # Phase 3: 無音削除
                if remove_silence:
                    video_name = video_path_obj.stem
                    base_dir = video_path_obj.parent / f"{video_name}_TextffCut"
                    for i, suggestion in enumerate(suggestions):
                        progress_text.write(f"🔇 無音削除中... ({i + 1}/{total})")
                        use_case._apply_silence_removal(suggestion, video_path_obj, base_dir)

                # Phase 3.5: 速度変更
                actual_video_path = video_path_obj
                if speed != 1.0:
                    from config import Config
                    from core.video import VideoProcessor

                    speed_label = f"{round(speed, 1)}x"
                    progress_text.write(f"⚡ {speed_label}速度変更中...")
                    video_name = video_path_obj.stem
                    base_dir = video_path_obj.parent / f"{video_name}_TextffCut"
                    vp = VideoProcessor(Config())
                    speed_path = base_dir / f"source_{speed_label}.mp4"
                    vp.create_speed_changed_video(str(video_path_obj), str(speed_path), round(speed, 2))
                    actual_video_path = speed_path

                    # 全候補のtime_rangesを速度に合わせて調整（FFmpegと同じ丸め値を使用）
                    actual_speed = round(speed, 2)
                    for suggestion in suggestions:
                        suggestion.time_ranges = [
                            (s / actual_speed, e / actual_speed)
                            for s, e in suggestion.time_ranges
                        ]
                        suggestion.total_duration = sum(e - s for s, e in suggestion.time_ranges)
                    progress_text.write(f"✅ {speed_label}速度変更完了")

                video_name = video_path_obj.stem
                base_dir = video_path_obj.parent / f"{video_name}_TextffCut"

                # Phase 4: FCPXML + SRT 生成
                fcpxml_dir = base_dir / "fcpxml"
                fcpxml_dir.mkdir(parents=True, exist_ok=True)

                # メディア素材検出（タイトル画像のframe色抽出でも再利用）
                from utils.media_asset_detector import detect_media_assets as _detect

                media_config = _detect(
                    video_path_obj,
                    enable_frame=enable_frame,
                    enable_bgm=enable_bgm,
                    enable_se=enable_se,
                )
                if media_config.has_any:
                    progress_text.write(f"🎨 {media_config.summary()}")

                # Phase 3.7: タイトル画像生成（バッチ1回のAI呼び出し）
                from use_cases.ai.suggest_and_export import _sanitize_filename

                title_image_paths: dict[int, Path] = {}
                if enable_title_image:
                    from use_cases.ai.title_image_generator import generate_title_images_batch

                    titles_dir = base_dir / "title_images"

                    frame_path_for_title = None
                    if media_config.overlay_settings:
                        fp = media_config.overlay_settings.get("frame_path")
                        if fp:
                            frame_path_for_title = Path(fp)

                    font_dir = video_path_obj.parent / "preset" / "fonts"
                    if not font_dir.exists():
                        font_dir = None

                    progress_text.write(f"🖼 タイトル画像生成中... ({total}件)")
                    title_image_paths = generate_title_images_batch(
                        suggestions=suggestions,
                        output_dir=titles_dir,
                        orientation=timeline_resolution,
                        client=gateway.client,
                        model=gateway.model,
                        font_dir=font_dir,
                        frame_path=frame_path_for_title,
                        sanitize_fn=_sanitize_filename,
                    )
                    failed_count = total - len(title_image_paths)
                    if failed_count > 0:
                        progress_text.write(
                            f"⚠️ タイトル画像: {len(title_image_paths)}枚成功、{failed_count}枚失敗"
                        )
                    else:
                        progress_text.write(f"✅ タイトル画像: {len(title_image_paths)}枚生成完了")

                exported_files: list[Path] = []
                for i, suggestion in enumerate(suggestions, 1):
                    progress_text.write(f"📄 FCPXML生成中... ({i}/{total})")
                    sanitized = _sanitize_filename(suggestion.title)

                    title_path = title_image_paths.get(i)
                    title_settings = {"title_path": str(title_path)} if title_path else None
                    fcpxml_path = fcpxml_dir / f"{i:02d}_{sanitized}.fcpxml"
                    success = use_case._export_fcpxml(
                        suggestion, actual_video_path, fcpxml_path, media_config,
                        scale=scale, anchor=anchor,
                        timeline_resolution=timeline_resolution,
                        title_settings=title_settings,
                    )
                    if success:
                        exported_files.append(fcpxml_path)

                    if generate_srt:
                        from use_cases.ai.srt_subtitle_generator import generate_srt as gen_srt

                        srt_path = fcpxml_dir / f"{i:02d}_{sanitized}.srt"
                        gen_srt(
                            suggestion=suggestion,
                            transcription=actual_result,
                            output_path=srt_path,
                            video_path=actual_video_path,
                        )

                # キャッシュ保存
                cache_dir = base_dir / "clip_suggestions"
                cache_dir.mkdir(parents=True, exist_ok=True)
                use_case._save_cache(suggestions, detection, cache_dir / f"{detection.model_used}.json")

                status.update(label=f"✅ {total}件の切り抜きを生成完了", state="complete", expanded=False)

            # 結果をセッションに保存
            cost_jpy = detection.estimated_cost_usd * 150
            st.session_state["ai_clip_result"] = {
                "suggestions": [
                    {
                        "title": s.title,
                        "duration": s.total_duration,
                    }
                    for s in suggestions
                ],
                "output_dir": str(fcpxml_dir),
            }
            st.rerun()

        except Exception as e:
            logger.error(f"AI clip generation error: {e}", exc_info=True)
            # エラー時はセッションの古い結果をクリア
            st.session_state.pop("ai_clip_result", None)
            st.error(f"❌ AI切り抜き生成中にエラーが発生しました: {e}")

    def _render_text_stats(self) -> None:
        """文字数と時間の統計を表示"""
        # デバッグ: 文字数を確認
        char_count = self.view_model.char_count
        if char_count == 0 and self.view_model.edited_text:
            # edited_textがあるのに文字数が0の場合は再計算
            char_count = len(self.view_model.edited_text)
            logger.warning(f"[_render_text_stats] char_count was 0 but edited_text exists. Recalculated: {char_count}")

        stats_parts = [f"文字数: {char_count}文字"]

        if self.view_model.total_duration > 0:
            stats_parts.append(f"時間: {self.view_model.duration_text}（無音削除前）")

        if self.view_model.section_count > 1:
            stats_parts.append(f"セクション数: {self.view_model.section_count}")

        st.caption(" / ".join(stats_parts))

    def _render_action_buttons(self) -> None:
        """アクションボタンを表示"""
        button_col1, button_col2 = st.columns([1, 3])

        with button_col1:
            # 更新ボタン
            if st.button("更新", type="primary", use_container_width=True, key=TestIds.TEXT_UPDATE_BUTTON):
                # 編集されたテキストを取得（text_editorウィジェットの値）
                current_text = st.session_state.get("text_editor", "")

                if current_text:
                    # テキストをそのまま処理（マーカーが含まれていても自動的に処理される）
                    self.presenter.update_edited_text(current_text)

                # セッション状態に保存（既存コードとの互換性）
                st.session_state.edited_text = current_text
                st.session_state.text_editor_value = current_text
                st.session_state.preview_update_requested = True

                # 時間範囲をセッション状態に保存
                if self.view_model.time_ranges:
                    time_ranges_tuples = [(tr.start, tr.end) for tr in self.view_model.time_ranges]
                    st.session_state.time_ranges = time_ranges_tuples
                    st.session_state.has_boundary_adjustments = self.view_model.has_boundary_markers

                    # 時間範囲が計算されたらナビゲーションを有効にするためのフラグ
                    st.session_state.text_edit_has_time_ranges = True
                    # text_edit_completedは「エクスポートへ進む」ボタンを押した時のみ設定

                # 差分に追加された文字がある場合はモーダル表示フラグを設定
                if self.view_model.has_added_chars:
                    st.session_state.show_modal = True
                    st.session_state.current_edited_text = self.view_model.edited_text
                    st.session_state.current_diff = self.view_model.differences
                    st.session_state.original_edited_text = current_text

                st.rerun()

        with button_col2:
            # 音声プレビュー（更新ボタンクリック時に生成・表示）
            if st.session_state.get("preview_update_requested", False) and self.view_model.time_ranges:
                # 音声を生成
                try:
                    # セッション状態から動画パスを取得（SessionManagerが設定する複数のキーを確認）
                    video_path = (
                        st.session_state.get("video_path")
                        or st.session_state.get("current_video_path")
                        or st.session_state.get("selected_video")
                    )
                    if not video_path:
                        # デバッグ情報を表示
                        import logging

                        logger = logging.getLogger(__name__)
                        logger.error(
                            f"動画パスが見つかりません。セッション状態: video_path={st.session_state.get('video_path')}, current_video_path={st.session_state.get('current_video_path')}, selected_video={st.session_state.get('selected_video')}"
                        )
                        st.error("動画が選択されていません。動画を選択してから文字起こしを実行してください。")
                    else:
                        # Presenter経由で音声プレビューを生成
                        # プレビュー用の時間範囲を準備
                        time_ranges = [(tr.start, tr.end) for tr in self.view_model.time_ranges]

                        # Presenter経由で音声プレビューを生成
                        audio_path = self.presenter.generate_audio_preview(
                            str(video_path), time_ranges, max_duration=60.0
                        )

                        if audio_path:
                            # 音声プレイヤーを表示
                            with open(audio_path, "rb") as audio_file:
                                audio_bytes = audio_file.read()
                                st.audio(audio_bytes, format="audio/wav")

                            # 一時ファイルを削除
                            import os

                            os.unlink(audio_path)

                            # プレビュー情報を表示
                            st.caption("音声プレビューを生成しました（最大60秒）")
                        else:
                            st.warning("音声プレビューの生成に失敗しました")

                except Exception as e:
                    st.error(f"音声プレビューの生成に失敗しました: {e}")

                # フラグをリセット
                st.session_state.preview_update_requested = False

    def _render_boundary_markers_info(self) -> None:
        """境界調整マーカー情報を表示"""
        with st.expander("🎯 境界調整マーカーが検出されました", expanded=True):
            st.info(
                "境界調整マーカーを使用してクリップの開始・終了位置を調整できます。\n\n"
                "**使用方法:**\n"
                "- `[数値<]` = 前のクリップを縮める\n"
                "- `[数値>]` = 前のクリップを延ばす\n"
                "- `[<数値]` = 後のクリップを早める\n"
                "- `[>数値]` = 後のクリップを遅らせる"
            )

            # ハイライト表示
            if self.view_model.differences:
                st.markdown("**マーカー適用後のプレビュー:**")
                show_edited_text_with_highlights(self.view_model.edited_text, self.view_model.differences, height=200)

    def _render_sections_info(self) -> None:
        """セクション分割情報を表示"""
        with st.expander(f"📑 {self.view_model.section_count}個のセクションに分割されています", expanded=True):
            st.info(f"区切り文字 `{self.view_model.separator}` で分割されました")

            # 各セクションの情報
            for i, section in enumerate(self.view_model.sections):
                st.markdown(f"**セクション {i + 1}:**")
                st.text(section[:100] + "..." if len(section) > 100 else section)

    def _render_time_ranges_info(self) -> None:
        """時間範囲の計算結果を表示"""
        # 時間範囲が計算されたことを示すだけ（特に表示なし）
        pass

    def _render_title_generation_prompt(self) -> None:
        """タイトル生成プロンプトを表示"""
        from utils.prompt_loader import PromptLoader

        if not self.view_model.edited_text:
            # 編集テキストがない場合は空のエリアを表示
            st.text_area(
                "🎯 タイトル生成プロンプト",
                value="（切り抜き箇所を入力すると表示されます）",
                height=68,
                key="title_generation_prompt",
                disabled=True,
            )
            return

        try:
            loader = PromptLoader()
            prompt = loader.load_title_generation_prompt(self.view_model.edited_text)

            # プロンプトを表示（最小高さ）
            st.text_area(
                "🎯 タイトル生成プロンプト",
                value=prompt,
                height=68,
                key="title_generation_prompt",
                help="Ctrl+A (Windows) / Cmd+A (Mac) で全選択してコピー",
            )
        except Exception as e:
            logger.error(f"タイトル生成プロンプトの読み込みエラー: {e}")


def show_text_editor_section(
    transcription_result: TranscriptionResult, video_path: Path, container: Any | None = None
) -> dict[str, Any]:
    """
    テキスト編集セクション（既存のUI関数との互換性のため）

    Args:
        transcription_result: 文字起こし結果
        video_path: 動画ファイルパス
        container: DIコンテナ

    Returns:
        処理結果の辞書
    """
    if not container:
        # 互換性のため、コンテナなしでは空の結果を返す
        return {}

    if not transcription_result:
        st.error("文字起こし結果がありません")
        return {}

    # PresenterとViewを作成
    presenter = container.presentation.text_editor_presenter()
    view = TextEditorView(presenter, container)

    # UIをレンダリングして結果を返す
    return view.render(transcription_result, video_path)


def show_text_editor(container: Any) -> None:
    """
    テキスト編集セクションを表示

    Args:
        container: Streamlitコンテナ
    """
    container.subheader("✏️ テキスト編集")
    container.info("ここにテキスト編集UIが表示されます")
    # TODO: 実際のテキスト編集UIを実装
