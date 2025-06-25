"""
SRT字幕タイミング調整モジュール

字幕のタイミングを最適化し、読みやすさを向上させる。
"""

from dataclasses import dataclass
from typing import Any

from utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TimingConfig:
    """タイミング調整設定"""

    # 基本設定
    min_duration: float = 0.5  # 最小表示時間（秒）
    max_duration: float = 7.0  # 最大表示時間（秒）
    min_gap: float = 0.1  # 字幕間の最小間隔（秒）

    # 読みやすさ設定
    chars_per_second: float = 15.0  # 1秒あたりの文字数（読取速度）
    words_per_minute: int = 180  # 1分あたりの単語数

    # スナップ設定
    snap_to_shot_change: bool = True  # ショット変更にスナップ
    shot_change_threshold: float = 0.1  # ショット変更の許容範囲（秒）

    # 分割設定
    prefer_sentence_breaks: bool = True  # 文の区切りで分割を優先
    max_chars_per_line: int = 42  # 1行の最大文字数
    max_lines_per_subtitle: int = 2  # 1つの字幕の最大行数


class SRTTimingAdjuster:
    """SRT字幕タイミング調整クラス"""

    def __init__(self, config: TimingConfig | None = None):
        """初期化

        Args:
            config: タイミング調整設定
        """
        self.config = config or TimingConfig()

    def adjust_timing(
        self,
        segments: list[Any],  # TranscriptionSegment
        shot_changes: list[float] | None = None,
    ) -> list[Any]:
        """タイミングを調整

        Args:
            segments: 文字起こしセグメントのリスト
            shot_changes: ショット変更タイムスタンプのリスト

        Returns:
            調整後のセグメントリスト
        """
        if not segments:
            return segments

        # 1. 基本的なタイミング調整
        adjusted = self._adjust_basic_timing(segments)

        # 2. 読みやすさに基づく調整
        adjusted = self._adjust_for_readability(adjusted)

        # 3. ショット変更へのスナップ
        if shot_changes and self.config.snap_to_shot_change:
            adjusted = self._snap_to_shot_changes(adjusted, shot_changes)

        # 4. オーバーラップの解決
        adjusted = self._resolve_overlaps(adjusted)

        # 5. ギャップの調整
        adjusted = self._adjust_gaps(adjusted)

        return adjusted

    def _adjust_basic_timing(self, segments: list[Any]) -> list[Any]:
        """基本的なタイミング調整

        Args:
            segments: セグメントリスト

        Returns:
            調整後のセグメントリスト
        """
        adjusted = []

        for segment in segments:
            # 空のテキストはスキップ
            if not segment.text or not segment.text.strip():
                continue

            # コピーを作成（元のセグメントを変更しない）
            new_segment = self._copy_segment(segment)

            # 最小時間の確保
            duration = new_segment.end - new_segment.start
            if duration < self.config.min_duration:
                new_segment.end = new_segment.start + self.config.min_duration

            # 最大時間の制限
            elif duration > self.config.max_duration:
                # 長すぎる場合は分割を検討
                split_segments = self._split_long_segment(new_segment)
                adjusted.extend(split_segments)
                continue

            adjusted.append(new_segment)

        return adjusted

    def _adjust_for_readability(self, segments: list[Any]) -> list[Any]:
        """読みやすさに基づく調整

        Args:
            segments: セグメントリスト

        Returns:
            調整後のセグメントリスト
        """
        adjusted = []

        for segment in segments:
            # テキストの長さから適切な表示時間を計算
            text_length = len(segment.text)
            ideal_duration = text_length / self.config.chars_per_second

            # 最小・最大時間の範囲内で調整
            ideal_duration = max(self.config.min_duration, min(ideal_duration, self.config.max_duration))

            # 現在の表示時間
            current_duration = segment.end - segment.start

            # 差が大きい場合は調整
            if abs(current_duration - ideal_duration) > 0.5:
                # 中央値を取る
                new_duration = (current_duration + ideal_duration) / 2
                segment.end = segment.start + new_duration

            adjusted.append(segment)

        return adjusted

    def _snap_to_shot_changes(self, segments: list[Any], shot_changes: list[float]) -> list[Any]:
        """ショット変更にスナップ

        Args:
            segments: セグメントリスト
            shot_changes: ショット変更タイムスタンプ

        Returns:
            調整後のセグメントリスト
        """
        adjusted = []
        threshold = self.config.shot_change_threshold

        for segment in segments:
            new_segment = self._copy_segment(segment)

            # 開始時刻の近くにショット変更があるか確認
            for shot_time in shot_changes:
                if abs(segment.start - shot_time) <= threshold:
                    new_segment.start = shot_time
                    break

            # 終了時刻の近くにショット変更があるか確認
            for shot_time in shot_changes:
                if abs(segment.end - shot_time) <= threshold:
                    new_segment.end = shot_time
                    break

            # 最小時間を維持
            if new_segment.end - new_segment.start < self.config.min_duration:
                new_segment.end = new_segment.start + self.config.min_duration

            adjusted.append(new_segment)

        return adjusted

    def _resolve_overlaps(self, segments: list[Any]) -> list[Any]:
        """オーバーラップを解決

        Args:
            segments: セグメントリスト

        Returns:
            調整後のセグメントリスト
        """
        if not segments:
            return segments

        adjusted = [segments[0]]

        for i in range(1, len(segments)):
            current = self._copy_segment(segments[i])
            previous = adjusted[-1]

            # オーバーラップがある場合
            if current.start < previous.end:
                # 中点で分割
                midpoint = (previous.end + current.start) / 2

                # 最小ギャップを確保
                previous.end = midpoint - self.config.min_gap / 2
                current.start = midpoint + self.config.min_gap / 2

                # 最小時間を維持
                if current.end - current.start < self.config.min_duration:
                    current.end = current.start + self.config.min_duration

            adjusted.append(current)

        return adjusted

    def _adjust_gaps(self, segments: list[Any]) -> list[Any]:
        """ギャップを調整

        Args:
            segments: セグメントリスト

        Returns:
            調整後のセグメントリスト
        """
        if not segments:
            return segments

        adjusted = []

        for i, segment in enumerate(segments):
            new_segment = self._copy_segment(segment)

            if i > 0:
                previous = adjusted[-1]
                gap = new_segment.start - previous.end

                # ギャップが小さすぎる場合
                if gap < self.config.min_gap:
                    # 均等に調整
                    adjustment = (self.config.min_gap - gap) / 2
                    previous.end -= adjustment
                    new_segment.start += adjustment

                # ギャップが大きすぎる場合（1秒以上）
                elif gap > 1.0:
                    # 少し縮める
                    new_segment.start = previous.end + 0.5

            adjusted.append(new_segment)

        return adjusted

    def _split_long_segment(self, segment: Any) -> list[Any]:
        """長いセグメントを分割

        Args:
            segment: 分割するセグメント

        Returns:
            分割されたセグメントのリスト
        """
        text = segment.text
        duration = segment.end - segment.start

        # 文で分割を試みる
        if self.config.prefer_sentence_breaks:
            sentences = self._split_by_sentences(text)
            if len(sentences) > 1:
                return self._create_segments_from_sentences(sentences, segment.start, segment.end)

        # 文字数で均等分割
        max_chars = self.config.max_chars_per_line * self.config.max_lines_per_subtitle
        num_parts = max(2, (len(text) + max_chars - 1) // max_chars)

        parts = []
        part_duration = duration / num_parts

        words = text.split()
        words_per_part = len(words) // num_parts

        for i in range(num_parts):
            start_idx = i * words_per_part
            end_idx = (i + 1) * words_per_part if i < num_parts - 1 else len(words)

            part_text = " ".join(words[start_idx:end_idx])
            part_start = segment.start + i * part_duration
            part_end = segment.start + (i + 1) * part_duration

            new_segment = self._copy_segment(segment)
            new_segment.text = part_text
            new_segment.start = part_start
            new_segment.end = part_end

            parts.append(new_segment)

        return parts

    def _split_by_sentences(self, text: str) -> list[str]:
        """文で分割

        Args:
            text: 分割するテキスト

        Returns:
            文のリスト
        """
        # 簡単な文分割（日本語対応）
        import re

        # 句読点で分割
        sentences = re.split(r"[。！？\.!?]+", text)

        # 空の文を除去し、句読点を戻す
        result = []
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                # 元の句読点を探して追加
                if i < len(sentences) - 1:
                    match = re.search(r"[。！？\.!?]+", text[text.find(sentence) + len(sentence) :])
                    if match:
                        sentence += match.group()
                result.append(sentence.strip())

        return result if result else [text]

    def _create_segments_from_sentences(self, sentences: list[str], start: float, end: float) -> list[Any]:
        """文からセグメントを作成

        Args:
            sentences: 文のリスト
            start: 開始時刻
            end: 終了時刻

        Returns:
            セグメントのリスト
        """
        segments = []
        total_chars = sum(len(s) for s in sentences)
        current_time = start

        for sentence in sentences:
            # 文の長さに応じて時間を配分
            sentence_ratio = len(sentence) / total_chars
            sentence_duration = (end - start) * sentence_ratio

            # 最小時間を確保
            sentence_duration = max(self.config.min_duration, sentence_duration)

            segment = type(
                "Segment",
                (),
                {
                    "text": sentence,
                    "start": current_time,
                    "end": min(current_time + sentence_duration, end),
                    "words": [],
                },
            )()

            segments.append(segment)
            current_time = segment.end

        return segments

    def _copy_segment(self, segment: Any) -> Any:
        """セグメントをコピー

        Args:
            segment: コピー元のセグメント

        Returns:
            コピーされたセグメント
        """
        # 簡易的なコピー（属性をコピー）
        new_segment = type(
            "Segment",
            (),
            {"text": segment.text, "start": segment.start, "end": segment.end, "words": getattr(segment, "words", [])},
        )()

        return new_segment


# テスト用関数
def test_timing_adjuster():
    """タイミング調整のテスト"""
    print("=== SRT Timing Adjuster Test ===")

    # テスト用セグメント
    segments = [
        type("Segment", (), {"text": "短い", "start": 0.0, "end": 0.2, "words": []})(),  # 0.2秒（短すぎる）
        type(
            "Segment",
            (),
            {
                "text": "これは非常に長いテキストで、" * 5,  # 長いテキスト
                "start": 0.3,
                "end": 15.0,  # 14.7秒（長すぎる）
                "words": [],
            },
        )(),
        type(
            "Segment",
            (),
            {"text": "オーバーラップ", "start": 14.5, "end": 16.0, "words": []},  # 前のセグメントとオーバーラップ
        )(),
    ]

    # 調整器を作成
    config = TimingConfig(min_duration=0.5, max_duration=7.0, min_gap=0.1, chars_per_second=15.0)
    adjuster = SRTTimingAdjuster(config)

    # 調整実行
    adjusted = adjuster.adjust_timing(segments)

    print("\n--- Original Segments ---")
    for i, seg in enumerate(segments):
        print(f"{i+1}: {seg.start:.2f} - {seg.end:.2f} ({seg.end-seg.start:.2f}s) : {seg.text[:30]}...")

    print("\n--- Adjusted Segments ---")
    for i, seg in enumerate(adjusted):
        print(f"{i+1}: {seg.start:.2f} - {seg.end:.2f} ({seg.end-seg.start:.2f}s) : {seg.text[:30]}...")

    # ショット変更へのスナップテスト
    print("\n--- Shot Change Snap Test ---")
    shot_changes = [2.0, 5.0, 10.0]

    test_segments = [
        type("Segment", (), {"text": "ショット変更の近く", "start": 1.95, "end": 3.0, "words": []})(),  # 2.0の近く
    ]

    adjusted_with_shots = adjuster.adjust_timing(test_segments, shot_changes)

    for seg in adjusted_with_shots:
        print(f"Start: {seg.start:.2f} (snapped to shot change at 2.0)")

    print("\n✓ Timing adjustment test completed!")


if __name__ == "__main__":
    test_timing_adjuster()
