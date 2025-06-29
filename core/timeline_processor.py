"""
タイムライン編集処理モジュール
タイムラインセグメントの管理と調整機能を提供
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimelineSegment:
    """タイムラインセグメントのデータクラス"""

    id: str
    start: float  # 開始時間（秒）
    end: float  # 終了時間（秒）
    text: str  # 対応するテキスト
    waveform_data: list[float] = field(default_factory=list)  # 波形データ（オプション）

    def duration(self) -> float:
        """セグメントの長さ（秒）を返す"""
        return self.end - self.start

    def to_frames(self, fps: float = 30.0) -> tuple[int, int]:
        """フレーム番号に変換"""
        return int(self.start * fps), int(self.end * fps)

    def adjust_start(self, delta: float, min_duration: float = 0.1) -> bool:
        """
        開始時間を調整

        Args:
            delta: 調整量（秒）
            min_duration: 最小セグメント長（秒）

        Returns:
            調整が成功したかどうか
        """
        new_start = max(0, self.start + delta)
        # 最小長を保証
        if self.end - new_start >= min_duration:
            self.start = new_start
            return True
        return False

    def adjust_end(self, delta: float, max_duration: float, min_duration: float = 0.1) -> bool:
        """
        終了時間を調整

        Args:
            delta: 調整量（秒）
            max_duration: 動画の最大長（秒）
            min_duration: 最小セグメント長（秒）

        Returns:
            調整が成功したかどうか
        """
        new_end = min(max_duration, self.end + delta)
        # 最小長を保証
        if new_end - self.start >= min_duration:
            self.end = new_end
            return True
        return False

    def set_time_range(self, start: float, end: float, max_duration: float) -> bool:
        """
        時間範囲を直接設定

        Args:
            start: 開始時間（秒）
            end: 終了時間（秒）
            max_duration: 動画の最大長（秒）

        Returns:
            設定が成功したかどうか
        """
        # 範囲チェック
        if start < 0 or end > max_duration or start >= end:
            return False

        self.start = start
        self.end = end
        return True

    def to_dict(self) -> dict:
        """辞書形式に変換"""
        return {
            "id": self.id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "waveform_data": self.waveform_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineSegment":
        """辞書からインスタンスを作成"""
        return cls(
            id=data["id"],
            start=data["start"],
            end=data["end"],
            text=data["text"],
            waveform_data=data.get("waveform_data", []),
        )


class TimelineProcessor:
    """タイムライン処理クラス"""

    def __init__(self) -> None:
        self.segments: list[TimelineSegment] = []
        self.video_duration: float = 0.0
        self.fps: float = 30.0

    def create_segments_from_ranges(
        self, time_ranges: list[tuple[float, float]], transcription_result: dict | Any, video_duration: float
    ) -> list[TimelineSegment]:
        """
        時間範囲リストからTimelineSegmentを作成

        Args:
            time_ranges: [(start, end), ...] の時間範囲リスト
            transcription_result: 文字起こし結果
            video_duration: 動画の長さ（秒）

        Returns:
            TimelineSegmentのリスト
        """
        self.video_duration = video_duration
        self.segments = []

        for i, (start, end) in enumerate(time_ranges):
            # 該当範囲のテキストを抽出
            text = self._extract_text_for_range(start, end, transcription_result)

            segment = TimelineSegment(id=f"segment_{i + 1}", start=start, end=end, text=text)
            self.segments.append(segment)

        return self.segments

    def _extract_text_for_range(self, start: float, end: float, transcription_result: dict | Any) -> str:
        """指定範囲のテキストを抽出"""
        text_parts = []

        # TranscriptionResultオブジェクトの場合は辞書に変換
        if hasattr(transcription_result, "segments"):
            segments = transcription_result.segments
        elif isinstance(transcription_result, dict) and "segments" in transcription_result:
            segments = transcription_result["segments"]
        else:
            return ""

        for segment in segments:
            # segmentが辞書の場合
            if isinstance(segment, dict):
                words = segment.get("words", [])
            # segmentがオブジェクトの場合
            elif hasattr(segment, "words"):
                words = segment.words
            else:
                continue

            for word_info in words:
                # word_infoが辞書の場合
                if isinstance(word_info, dict):
                    word_start = word_info.get("start", 0)
                    word_end = word_info.get("end", 0)
                    word = word_info.get("word", "")
                # word_infoがオブジェクトの場合
                elif hasattr(word_info, "start") and hasattr(word_info, "end"):
                    word_start = word_info.start
                    word_end = word_info.end
                    word = getattr(word_info, "word", "")
                else:
                    continue

                # Noneチェック
                if word_start is None or word_end is None:
                    continue

                # 範囲内の単語を収集
                if word_start >= start and word_end <= end:
                    text_parts.append(word)

        return "".join(text_parts)

    def adjust_segment_time(
        self,
        segment_id: str,
        start_delta: float | None = None,
        end_delta: float | None = None,
        fps: float | None = None,
    ) -> bool:
        """
        セグメントの時間を調整

        Args:
            segment_id: セグメントID
            start_delta: 開始時間の調整量（秒）
            end_delta: 終了時間の調整量（秒）
            fps: フレームレート（指定時はフレーム単位で調整）

        Returns:
            調整が成功したかどうか
        """
        segment = self.get_segment_by_id(segment_id)
        if not segment:
            return False

        success = True

        if start_delta is not None:
            if fps:
                # フレーム単位の調整
                frame_delta = start_delta / fps
                success &= segment.adjust_start(frame_delta)
            else:
                success &= segment.adjust_start(start_delta)

        if end_delta is not None:
            if fps:
                # フレーム単位の調整
                frame_delta = end_delta / fps
                success &= segment.adjust_end(frame_delta, self.video_duration)
            else:
                success &= segment.adjust_end(end_delta, self.video_duration)

        return success

    def set_segment_time_range(self, segment_id: str, start: float, end: float) -> bool:
        """セグメントの時間範囲を直接設定"""
        segment = self.get_segment_by_id(segment_id)
        if not segment:
            return False

        return segment.set_time_range(start, end, self.video_duration)

    def get_segment_by_id(self, segment_id: str) -> TimelineSegment | None:
        """IDでセグメントを取得"""
        for segment in self.segments:
            if segment.id == segment_id:
                return segment
        return None

    def get_time_ranges(self) -> list[tuple[float, float]]:
        """全セグメントの時間範囲をタプルのリストで返す"""
        return [(seg.start, seg.end) for seg in self.segments]

    def validate_segments(self) -> tuple[bool, list[str]]:
        """
        セグメントの妥当性を検証

        Returns:
            (検証成功フラグ, エラーメッセージのリスト)
        """
        errors = []

        # 各セグメントの基本検証
        for segment in self.segments:
            if segment.start < 0:
                errors.append(f"{segment.id}: 開始時間が負の値です")
            if segment.end > self.video_duration:
                errors.append(f"{segment.id}: 終了時間が動画長を超えています")
            if segment.start >= segment.end:
                errors.append(f"{segment.id}: 開始時間が終了時間以降です")

        # セグメント間の重複チェック
        sorted_segments = sorted(self.segments, key=lambda s: s.start)
        for i in range(len(sorted_segments) - 1):
            current = sorted_segments[i]
            next_seg = sorted_segments[i + 1]

            if current.end > next_seg.start:
                errors.append(f"{current.id}と{next_seg.id}が重複しています")

        return len(errors) == 0, errors

    def merge_overlapping_segments(self) -> int:
        """
        重複するセグメントをマージ

        Returns:
            マージされたセグメント数
        """
        if not self.segments:
            return 0

        # 開始時間でソート
        sorted_segments = sorted(self.segments, key=lambda s: s.start)
        merged = [sorted_segments[0]]
        merge_count = 0

        for current in sorted_segments[1:]:
            last = merged[-1]

            # 重複または隣接している場合はマージ
            if current.start <= last.end:
                # 終了時間を更新
                last.end = max(last.end, current.end)
                # テキストを結合
                last.text += current.text
                merge_count += 1
            else:
                merged.append(current)

        # セグメントIDを再割り当て
        for i, segment in enumerate(merged):
            segment.id = f"segment_{i + 1}"

        self.segments = merged
        return merge_count

    def to_dict(self) -> dict:
        """全データを辞書形式に変換"""
        return {
            "segments": [seg.to_dict() for seg in self.segments],
            "video_duration": self.video_duration,
            "fps": self.fps,
        }

    def from_dict(self, data: dict) -> None:
        """辞書からデータを復元"""
        self.video_duration = data.get("video_duration", 0.0)
        self.fps = data.get("fps", 30.0)
        self.segments = [TimelineSegment.from_dict(seg_data) for seg_data in data.get("segments", [])]
