"""
E2Eテスト用のテストID定義

StreamlitコンポーネントのE2Eテストで使用するIDを一元管理します。
IDは機能別に整理され、わかりやすい命名規則に従っています。
"""


class TestIds:
    """E2Eテスト用のテストID定義クラス"""
    
    # ===================
    # 動画入力セクション
    # ===================
    # ローカルファイル選択
    VIDEO_SELECT_DROPDOWN = "video_select_dropdown"
    VIDEO_REFRESH_BUTTON = "video_refresh_button"
    VIDEO_PATH_CAPTION = "video_path_caption"
    
    # YouTube動画ダウンロード
    YOUTUBE_URL_INPUT = "youtube_url_input"
    YOUTUBE_INFO_BUTTON = "youtube_info_button"
    YOUTUBE_FORMAT_SELECT = "youtube_format_select"
    YOUTUBE_DOWNLOAD_BUTTON = "youtube_download_button"
    YOUTUBE_DOWNLOAD_PROGRESS = "youtube_download_progress"
    
    # ===================
    # 文字起こしセクション
    # ===================
    # コンテナ
    TRANSCRIPTION_RESULT_CONTAINER = "transcription_result_container"
    
    # 処理モード選択
    TRANSCRIPTION_MODE_RADIO = "transcription_mode_radio"
    
    # APIモード
    API_MODEL_SELECT = "api_model_select"
    API_BUZZ_CLIP_SELECT = "api_buzz_clip_select"
    
    # ローカルモード
    LOCAL_MODEL_SIZE_SELECT = "local_model_size_select"
    
    # 実行制御
    TRANSCRIPTION_EXECUTE_BUTTON = "transcription_execute_button"
    TRANSCRIPTION_CANCEL_BUTTON = "transcription_cancel_button"
    
    # キャッシュ関連
    TRANSCRIPTION_CACHE_SELECT = "transcription_cache_select"
    TRANSCRIPTION_USE_CACHE_BUTTON = "transcription_use_cache_button"
    TRANSCRIPTION_DELETE_CACHE_BUTTON = "transcription_delete_cache_button"
    
    # ===================
    # テキスト編集セクション
    # ===================
    # メインエディタ
    TEXT_EDITOR_AREA = "text_editor_area"
    TEXT_UPDATE_BUTTON = "text_update_button"
    TEXT_RESET_BUTTON = "text_reset_button"
    
    # 差分表示
    TEXT_DIFF_TOGGLE = "text_diff_toggle"
    TEXT_HIGHLIGHT_MODE_SELECT = "text_highlight_mode_select"
    TEXT_BOUNDARY_CHECKBOX = "text_boundary_checkbox"
    
    # バズクリップ関連
    BUZZ_CLIP_GENERATE_BUTTON = "buzz_clip_generate_button"
    BUZZ_CLIP_COST_CONFIRM = "buzz_clip_cost_confirm"
    BUZZ_CLIP_SELECT = "buzz_clip_select"
    BUZZ_CLIP_PROMPT_AREA = "buzz_clip_prompt_area"
    BUZZ_CLIP_EDIT_CHECKBOX = "buzz_clip_edit_checkbox"
    BUZZ_CLIP_APPLY_BUTTON = "buzz_clip_apply_button"
    BUZZ_CLIP_DELETE_BUTTON = "buzz_clip_delete_button"
    
    # タイトル生成
    TITLE_GENERATE_BUTTON = "title_generate_button"
    TITLE_PROMPT_AREA = "title_prompt_area"
    TITLE_SUGGESTIONS_SELECT = "title_suggestions_select"
    
    # タイムライン編集
    TIMELINE_EDIT_BUTTON = "timeline_edit_button"
    TIMELINE_SAVE_BUTTON = "timeline_save_button"
    TIMELINE_RESET_BUTTON = "timeline_reset_button"
    
    # モーダルダイアログ
    DELETE_HIGHLIGHTS_MODAL_BUTTON = "delete_highlights_modal_button"
    CONTINUE_EDITING_MODAL_BUTTON = "continue_editing_modal_button"
    
    # ===================
    # エクスポート設定セクション
    # ===================
    # 出力形式
    EXPORT_FORMAT_RADIO = "export_format_radio"
    
    # 出力オプション
    EXPORT_SILENCE_REMOVAL_ENABLED = "export_silence_removal_enabled"
    EXPORT_SRT_CHECKBOX = "export_srt_checkbox"
    EXPORT_XML_CHECKBOX = "export_xml_checkbox"
    
    # SRT字幕設定
    SRT_MAX_LINE_LENGTH = "srt_max_line_length"
    SRT_MAX_LINES = "srt_max_lines"
    
    # 実行制御
    EXPORT_EXECUTE_BUTTON = "export_execute_button"
    EXPORT_DOWNLOAD_BUTTON = "export_download_button"
    
    # ===================
    # サイドバー設定
    # ===================
    # タブ
    SIDEBAR_TAB_SILENCE = "sidebar_tab_silence"
    SIDEBAR_TAB_SRT = "sidebar_tab_srt"
    SIDEBAR_TAB_RECOVERY = "sidebar_tab_recovery"
    SIDEBAR_TAB_HISTORY = "sidebar_tab_history"
    SIDEBAR_TAB_HELP = "sidebar_tab_help"
    
    # APIキー管理
    SIDEBAR_API_KEY_INPUT = "sidebar_api_key_input"
    SIDEBAR_API_KEY_SAVE = "sidebar_api_key_save"
    SIDEBAR_API_KEY_DELETE = "sidebar_api_key_delete"
    
    # 無音検出設定
    SIDEBAR_SILENCE_THRESHOLD = "sidebar_silence_threshold"
    SIDEBAR_MIN_SILENCE_DURATION = "sidebar_min_silence_duration"
    SIDEBAR_MIN_SEGMENT_DURATION = "sidebar_min_segment_duration"
    SIDEBAR_SILENCE_PAD = "sidebar_silence_pad"
    
    # SRT字幕設定
    SIDEBAR_SRT_LINE_LENGTH = "sidebar_srt_line_length"
    SIDEBAR_SRT_MAX_LINES = "sidebar_srt_max_lines"
    
    # ===================
    # ユーティリティセクション
    # ===================
    # ダウンロード・保存
    DOWNLOAD_LINK = "download_link"
    SAVE_CONFIG_BUTTON = "save_config_button"
    LOAD_CONFIG_BUTTON = "load_config_button"
    
    # プログレス・ステータス
    PROGRESS_BAR = "progress_bar"
    STATUS_MESSAGE = "status_message"
    ERROR_MESSAGE = "error_message"
    SUCCESS_MESSAGE = "success_message"
    
    # ===================
    # ヘッダー・フッター
    # ===================
    HEADER_TITLE = "header_title"
    HEADER_VERSION = "header_version"
    FOOTER_CREDITS = "footer_credits"
    
    @classmethod
    def get_all_ids(cls) -> list[str]:
        """定義されている全てのテストIDを取得"""
        return [
            value for name, value in vars(cls).items()
            if not name.startswith('_') and isinstance(value, str)
        ]
    
    @classmethod
    def validate_id(cls, test_id: str) -> bool:
        """指定されたIDが定義されているか検証"""
        return test_id in cls.get_all_ids()