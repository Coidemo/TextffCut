"""
タイムライン編集サービス
タイムライン編集機能のビジネスロジックを提供
"""

import tempfile
from typing import Any

import streamlit as st

from config import Config
from core.exceptions import ProcessingError
from core.timeline_processor import TimelineProcessor
from core.video import VideoProcessor, VideoInfo
from utils.logging import get_logger
from utils.settings import settings_manager

logger = get_logger(__name__)


class TimelineEditingService:
    """タイムライン編集サービスクラス"""

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self.timeline_processor = TimelineProcessor()
        self.video_processor = VideoProcessor(self.config)

    def initialize_timeline(
        self, time_ranges: list[tuple[float, float]], transcription_result: dict[str, Any], video_path: str
    ) -> dict[str, Any]:
        """
        タイムラインを初期化

        Args:
            time_ranges: 時間範囲のリスト
            transcription_result: 文字起こし結果
            video_path: 動画ファイルパス

        Returns:
            初期化結果
        """
        try:
            # 動画情報を取得
            video_info = VideoInfo.from_file(video_path)
            video_duration = video_info.duration
            fps = video_info.fps

            # TimelineSegmentを作成
            segments = self.timeline_processor.create_segments_from_ranges(
                time_ranges, transcription_result, video_duration
            )

            # セッション状態に保存
            if "timeline_data" not in st.session_state:
                st.session_state.timeline_data = {}

            st.session_state.timeline_data = {
                "segments": [seg.to_dict() for seg in segments],
                "video_duration": video_duration,
                "fps": fps,
                "video_path": video_path,
            }

            return {"success": True, "segments": segments, "video_duration": video_duration, "fps": fps}

        except Exception as e:
            logger.error(f"タイムライン初期化エラー: {e}")
            raise ProcessingError(f"タイムラインの初期化に失敗しました: {str(e)}")

    def adjust_segment_timing(self, segment_id: str, adjustment_type: str, adjustment_value: float) -> dict[str, Any]:
        """
        セグメントのタイミングを調整

        Args:
            segment_id: セグメントID
            adjustment_type: 調整タイプ ("start" or "end")
            adjustment_value: 調整値（秒）

        Returns:
            調整結果
        """
        try:
            # セッション状態から復元
            if "timeline_data" not in st.session_state:
                raise ProcessingError("タイムラインが初期化されていません")

            self.timeline_processor.from_dict(st.session_state.timeline_data)

            # 調整を実行
            if adjustment_type == "start":
                success = self.timeline_processor.adjust_segment_time(segment_id, start_delta=adjustment_value)
            elif adjustment_type == "end":
                success = self.timeline_processor.adjust_segment_time(segment_id, end_delta=adjustment_value)
            else:
                raise ValueError(f"不正な調整タイプ: {adjustment_type}")

            if not success:
                return {"success": False, "error": "調整値が無効です"}

            # 検証
            is_valid, errors = self.timeline_processor.validate_segments()
            if not is_valid:
                return {"success": False, "error": "セグメントの検証に失敗しました", "validation_errors": errors}

            # セッション状態を更新（video_pathを保持）
            current_video_path = st.session_state.timeline_data.get("video_path")
            st.session_state.timeline_data = self.timeline_processor.to_dict()
            if current_video_path:
                st.session_state.timeline_data["video_path"] = current_video_path

            return {"success": True, "segments": self.timeline_processor.segments}

        except Exception as e:
            logger.error(f"セグメント調整エラー: {e}")
            raise ProcessingError(f"セグメントの調整に失敗しました: {str(e)}")

    def set_segment_time_range(self, segment_id: str, start_time: float, end_time: float) -> dict[str, Any]:
        """
        セグメントの時間範囲を直接設定

        Args:
            segment_id: セグメントID
            start_time: 開始時間（秒）
            end_time: 終了時間（秒）

        Returns:
            設定結果
        """
        try:
            # セッション状態から復元
            if "timeline_data" not in st.session_state:
                raise ProcessingError("タイムラインが初期化されていません")

            self.timeline_processor.from_dict(st.session_state.timeline_data)

            # 時間範囲を設定
            success = self.timeline_processor.set_segment_time_range(segment_id, start_time, end_time)

            if not success:
                return {"success": False, "error": "時間範囲が無効です"}

            # 検証
            is_valid, errors = self.timeline_processor.validate_segments()
            if not is_valid:
                return {"success": False, "error": "セグメントの検証に失敗しました", "validation_errors": errors}

            # セッション状態を更新（video_pathを保持）
            current_video_path = st.session_state.timeline_data.get("video_path")
            st.session_state.timeline_data = self.timeline_processor.to_dict()
            if current_video_path:
                st.session_state.timeline_data["video_path"] = current_video_path

            return {"success": True, "segments": self.timeline_processor.segments}

        except Exception as e:
            logger.error(f"時間範囲設定エラー: {e}")
            raise ProcessingError(f"時間範囲の設定に失敗しました: {str(e)}")

    def generate_preview_audio(self, segment_id: str) -> str | None:
        """
        プレビュー用の音声ファイルを生成

        Args:
            segment_id: セグメントID

        Returns:
            プレビュー音声ファイルのパス
        """
        try:
            # セッション状態から復元
            if "timeline_data" not in st.session_state:
                raise ProcessingError("タイムラインが初期化されていません")

            # デバッグ: timeline_dataの内容を確認
            logger.debug(f"timeline_data keys: {list(st.session_state.timeline_data.keys())}")
            
            self.timeline_processor.from_dict(st.session_state.timeline_data)
            video_path = st.session_state.timeline_data.get("video_path")
            
            logger.debug(f"video_path from timeline_data: {video_path}")

            if not video_path:
                raise ProcessingError("動画パスが設定されていません")

            # セグメントを取得
            segment = self.timeline_processor.get_segment_by_id(segment_id)
            if not segment:
                raise ProcessingError(f"セグメントが見つかりません: {segment_id}")

            # プレビュー範囲を計算（フレーム境界に合わせる）
            fps = st.session_state.timeline_data.get("fps", 30.0)
            preview_start = round(segment.start * fps) / fps
            preview_end = round(segment.end * fps) / fps

            # 一時ファイルで音声を抽出
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                output_path = tmp_file.name

            # 音声抽出
            self.video_processor.extract_audio_segment(video_path, output_path, preview_start, preview_end)

            return output_path

        except Exception as e:
            logger.error(f"プレビュー音声生成エラー: {e}")
            raise ProcessingError(f"プレビュー音声の生成に失敗しました: {str(e)}")

    def get_adjusted_time_ranges(self) -> list[tuple[float, float]]:
        """
        調整後の時間範囲を取得

        Returns:
            時間範囲のリスト
        """
        try:
            # セッション状態から復元
            if "timeline_data" not in st.session_state:
                raise ProcessingError("タイムラインが初期化されていません")

            self.timeline_processor.from_dict(st.session_state.timeline_data)

            # 検証
            is_valid, errors = self.timeline_processor.validate_segments()
            if not is_valid:
                raise ProcessingError(f"セグメントが無効です: {', '.join(errors)}")

            return self.timeline_processor.get_time_ranges()

        except Exception as e:
            logger.error(f"時間範囲取得エラー: {e}")
            raise ProcessingError(f"時間範囲の取得に失敗しました: {str(e)}")

    def save_timeline_settings(self) -> bool:
        """
        タイムライン設定を保存

        Returns:
            保存成功フラグ
        """
        try:
            if "timeline_data" in st.session_state:
                settings_manager.set("last_timeline_data", st.session_state.timeline_data)
                return True
            return False

        except Exception as e:
            logger.error(f"設定保存エラー: {e}")
            return False

    def load_timeline_settings(self) -> dict[str, Any] | None:
        """
        保存されたタイムライン設定を読み込み

        Returns:
            タイムラインデータ
        """
        try:
            return settings_manager.get("last_timeline_data")

        except Exception as e:
            logger.error(f"設定読み込みエラー: {e}")
            return None

    def get_timeline_statistics(self) -> dict[str, Any]:
        """
        タイムラインの統計情報を取得

        Returns:
            統計情報
        """
        try:
            if "timeline_data" not in st.session_state:
                return {}

            self.timeline_processor.from_dict(st.session_state.timeline_data)

            total_duration = sum(seg.duration() for seg in self.timeline_processor.segments)

            return {
                "segment_count": len(self.timeline_processor.segments),
                "total_duration": total_duration,
                "video_duration": self.timeline_processor.video_duration,
                "coverage_percentage": (
                    (total_duration / self.timeline_processor.video_duration * 100)
                    if self.timeline_processor.video_duration > 0
                    else 0
                ),
            }

        except Exception as e:
            logger.error(f"統計情報取得エラー: {e}")
            return {}
