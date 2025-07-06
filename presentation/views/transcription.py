"""
文字起こしView

StreamlitのUIコンポーネントを使用して文字起こし画面を表示します。
"""

import logging
from pathlib import Path
from typing import Any

import streamlit as st

from presentation.presenters.transcription import TranscriptionPresenter
from presentation.view_models.transcription import TranscriptionViewModel

logger = logging.getLogger(__name__)


class TranscriptionView:
    """
    文字起こしのView

    MVPパターンのView部分を担当し、UI表示とユーザーイベントの収集を行います。
    """

    def __init__(self, presenter: TranscriptionPresenter):
        """
        初期化

        Args:
            presenter: 文字起こしPresenter
        """
        self.presenter = presenter
        self.view_model = presenter.view_model

        # ViewModelの変更を監視
        self.view_model.subscribe(self)

    def update(self, view_model: TranscriptionViewModel) -> None:
        """
        ViewModelの変更通知を受け取る

        Args:
            view_model: 変更されたViewModel
        """
        # Streamlitは自動的に再描画されるため、特別な処理は不要
        pass

    def render(self) -> None:
        """
        UIをレンダリング
        """
        # Presenterから動画パスを取得
        video_path = self.presenter.get_video_path()
        if not video_path:
            st.error("❌ 動画が選択されていません")
            return

        # 動画情報で初期化
        self.presenter.initialize_with_video(video_path)

        # 処理フラグ
        use_cache = False
        run_new = False

        # デバッグ情報を表示
        from utils.logging import get_logger

        logger = get_logger(__name__)
        logger.info(
            f"TranscriptionView.render - 利用可能なキャッシュ数: {len(self.view_model.available_caches) if self.view_model.available_caches else 0}"
        )
        logger.info(f"has_result: {self.view_model.has_result}, should_run: {self.view_model.should_run}")

        # キャッシュ選択UI（結果がない場合のみ表示）
        if self.view_model.available_caches and not self.view_model.has_result:
            with st.container(border=True):
                st.markdown("#### 📝 過去の文字起こし結果を利用する")

                # キャッシュ選択
                cache_options = []
                cache_map = {}

                for cache in self.view_model.available_caches:
                    from datetime import datetime

                    modified_date = datetime.fromtimestamp(cache.modified_time).strftime("%Y-%m-%d %H:%M")

                    # デバッグ: cacheオブジェクトの内容を確認
                    logger.info(
                        f"Cache object: mode={getattr(cache, 'mode', 'NONE')}, model_size={cache.model_size}, is_api={cache.is_api}"
                    )

                    # modeフィールドが存在しない場合のフォールバック
                    cache_mode = getattr(cache, "mode", None)
                    if cache_mode is None:
                        cache_mode = "API" if cache.is_api else "ローカル"
                        logger.warning(f"modeフィールドが見つかりません。is_apiから推測: {cache_mode}")

                    option_text = f"{cache_mode}モード - {cache.model_size} | {modified_date}"
                    cache_options.append(option_text)
                    cache_map[option_text] = cache

                selected_option = st.selectbox(
                    "保存済みの文字起こし結果",
                    cache_options,
                    index=None,  # デフォルトで何も選択しない
                    placeholder="キャッシュを選択してください",
                    help="使用する文字起こし結果を選択してください",
                )

                if selected_option:
                    selected_cache = cache_map[selected_option]
                    self.presenter.select_cache(selected_cache)

                # キャッシュ使用ボタン
                if st.button(
                    "💾 選択した結果を使用",
                    type="primary",
                    use_container_width=True,
                    disabled=selected_option is None,  # 選択されていない場合は無効
                ):
                    if self.presenter.load_selected_cache():
                        use_cache = True
                        st.success("✅ キャッシュから文字起こし結果を読み込みました")
                        # バズクリップのキャッシュチェックをリセット
                        if "buzz_clip_cache_checked" in st.session_state:
                            del st.session_state["buzz_clip_cache_checked"]
                        if "buzz_clip_cache_exists" in st.session_state:
                            del st.session_state["buzz_clip_cache_exists"]
                        # SessionManagerが内部で状態を管理
                        st.rerun()

        # 既存の結果がある場合の処理
        if self.view_model.has_result:
            # 文字起こし結果からモード情報を判断
            if self.view_model.transcription_result:
                # TranscriptionResultAdapterの場合は内部のドメインオブジェクトを取得
                result = self.view_model.transcription_result
                if hasattr(result, "domain_result"):
                    result = result.domain_result

                # model_sizeからモードを判断
                if hasattr(result, "model_size"):
                    model_size = result.model_size
                    mode_text = "API" if model_size == "whisper-1" else "ローカル"
                    st.success(f"✅ 文字起こし結果が読み込まれています ({mode_text}モード - {model_size})")
                else:
                    st.success("✅ 文字起こし結果が読み込まれています")
            else:
                st.success("✅ 文字起こし結果が読み込まれています")
            st.divider()
            st.markdown("#### 🔄 新規文字起こし")
            st.info("新規に文字起こしを実行すると、現在の結果は上書きされます")

        # 新規実行UI（結果の有無に関わらず表示）
        if not use_cache:
            # 処理モード・モデル選択・動画時間・料金を4カラムで横並び表示
            mode_col, model_col, time_col, price_col = st.columns(4)

            with mode_col:
                st.markdown("**⚙️ 処理モード**")
                mode_options = ["🖥️ ローカル", "🌐 API"]
                default_index = 1 if self.view_model.use_api else 0

                selected_mode = st.radio(
                    "処理モード",
                    mode_options,
                    index=default_index,
                    key="transcription_mode_radio",
                    label_visibility="collapsed",
                    horizontal=True,
                )
                use_api = selected_mode == "🌐 API"
                self.presenter.set_processing_mode(use_api)

            with model_col:
                st.markdown("**🤖 モデル**")
                st.markdown(self.view_model.model_text)

            with time_col:
                st.markdown("**📊 動画時間**")
                st.markdown(f"{self.view_model.video_duration_minutes:.1f}分 ({self.view_model.video_duration_text})")

            with price_col:
                st.markdown("**💰 推定料金**")
                st.markdown(self.view_model.cost_text)

            # API利用時の注意事項
            if self.view_model.use_api:
                st.caption("⚠️ API料金: $0.006/分 | 為替変動あり | [最新料金](https://openai.com/pricing)を確認")

            # エラー表示
            if self.view_model.error_message:
                st.error(f"❌ {self.view_model.error_message}")
                if self.view_model.error_details:
                    with st.expander("詳細"):
                        st.json(self.view_model.error_details)

            # 実行ボタン
            button_text = self._get_button_text()
            button_type = "secondary" if self.view_model.available_caches else "primary"

            # 過去の結果がある場合は上書き警告
            if self.view_model.available_caches:
                st.warning("⚠️ 同じ設定の過去の文字起こし結果は上書きされます")

            logger.info(f"実行ボタン表示 - text: {button_text}, has_result: {self.view_model.has_result}")
            if st.button(button_text, type=button_type, use_container_width=True):
                logger.info(f"文字起こしボタンクリック - APIモード: {self.view_model.use_api}")

                # APIモードでAPIキーチェック
                if self.view_model.use_api and not self.view_model.api_key:
                    logger.warning("APIキーが設定されていません")
                    st.error("⚠️ APIキーが設定されていません。サイドバーのAPIキー設定で設定してください。")
                    return

                logger.info("実行フラグを設定")

                # 既存の結果をクリア
                if self.view_model.has_result:
                    logger.info("既存の結果をクリア")
                    self.presenter.clear_result()

                # 実行フラグを設定（SessionManagerに保存）
                self.presenter.session_manager.set("transcription_should_run", True)
                run_new = True
                self.view_model.should_run = True
                logger.info(f"should_run設定完了: {self.view_model.should_run}")
                
                # バズクリップのキャッシュチェックをリセット
                if "buzz_clip_cache_checked" in st.session_state:
                    del st.session_state["buzz_clip_cache_checked"]
                if "buzz_clip_cache_exists" in st.session_state:
                    del st.session_state["buzz_clip_cache_exists"]
                    
                st.rerun()

        # 処理中の表示
        logger.info(
            f"処理中の表示チェック - should_run: {self.view_model.should_run}, has_result: {self.view_model.has_result}"
        )
        if self.view_model.should_run and not self.view_model.has_result:
            logger.info("処理中UIを表示")
            self._show_processing_ui()

    def _get_button_text(self) -> str:
        """実行ボタンのテキストを取得"""
        if self.view_model.available_caches:
            if self.view_model.use_api:
                return "💳 新たにAPIで文字起こしを実行する"
            else:
                return "🖥️ 新たにローカルで文字起こしを実行する"
        else:
            if self.view_model.use_api:
                return "💳 APIで文字起こしを実行する"
            else:
                return "🖥️ ローカルで文字起こしを実行する"

    def _show_processing_ui(self) -> None:
        """処理中のUIを表示"""
        # キャンセルボタン
        if st.button("❌ 処理を中止", type="secondary", use_container_width=True):
            self.presenter.cancel_transcription()
            st.warning("文字起こし処理を中止しました。")
            return

        # プログレス表示
        with st.spinner("文字起こし中..."):
            # プログレスバーとステータステキスト
            progress_bar = st.progress(self.view_model.progress)
            status_text = st.empty()

            if self.view_model.progress >= 1.0:
                status_text.success(self.view_model.status_message)
            else:
                status_text.info(self.view_model.status_message)

            # 実際の処理実行
            def progress_callback(progress: float, status: str) -> None:
                progress_bar.progress(min(progress, 1.0))
                status_text.info(status)

            # 文字起こし実行
            logger.info("start_transcription呼び出し開始")
            if self.presenter.start_transcription(progress_callback):
                # SessionManagerが内部で状態を管理
                logger.info("文字起こし完了")
                st.success("✅ 文字起こし完了！")
                st.rerun()
            else:
                logger.error(f"文字起こし失敗 - is_cancelled: {self.view_model.is_cancelled}")
                if self.view_model.is_cancelled:
                    st.warning("⚠️ 処理がキャンセルされました")
                else:
                    st.error(f"❌ {self.view_model.error_message}")


def show_transcription_controls(
    has_cache: bool = False,
    available_caches: list[dict[str, Any]] = None,
    video_path: Path | None = None,
    api_key: str | None = None,
    container: Any | None = None,
) -> tuple[bool, bool, dict[str, Any] | None]:
    """
    文字起こしコントロールUI（既存のUI関数との互換性のため）

    Args:
        has_cache: キャッシュが存在するか（非推奨）
        available_caches: 利用可能なキャッシュのリスト（非推奨）
        video_path: 動画ファイルパス
        api_key: APIキー
        container: DIコンテナ

    Returns:
        (use_cache, run_new, selected_cache_or_result)
    """
    if not container:
        # 互換性のため、コンテナなしでは従来の動作を返す
        return False, False, None

    if not video_path:
        st.error("動画ファイルが指定されていません")
        return False, False, None

    # PresenterとViewを作成
    presenter = container.presentation.transcription_presenter()

    # APIキーを設定
    if api_key:
        presenter.set_api_key(api_key)

    view = TranscriptionView(presenter)

    # UIをレンダリング
    use_cache, run_new, result = view.render(video_path)

    # 結果を辞書形式で返す（互換性のため）
    if result:
        return use_cache, run_new, {"result": result}

    return use_cache, run_new, None


def show_transcription(container: st.container) -> None:
    """
    文字起こしセクションを表示

    Args:
        container: Streamlitコンテナ
    """
    with container:
        st.subheader("📝 文字起こし")
        st.info("ここに文字起こしUIが表示されます")
        # TODO: 実際の文字起こしUIを実装
