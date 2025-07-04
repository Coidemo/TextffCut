"""
Subtitle Entity

字幕関連のエンティティ
"""

from dataclasses import dataclass

from ..value_objects import TimeRange


@dataclass
class Subtitle:
    """字幕エントリ"""

    id: int
    time_range: TimeRange
    text: str

    def __post_init__(self):
        """バリデーション"""
        if self.id < 1:
            raise ValueError(f"Subtitle ID must be positive: {self.id}")
        if not self.text.strip():
            raise ValueError("Subtitle text cannot be empty")

    @property
    def start(self) -> float:
        """開始時刻"""
        return self.time_range.start

    @property
    def end(self) -> float:
        """終了時刻"""
        return self.time_range.end

    @property
    def duration(self) -> float:
        """表示時間"""
        return self.time_range.duration

    @property
    def line_count(self) -> int:
        """行数"""
        return len(self.text.strip().split("\n"))

    def format_srt_time(self, time: float) -> str:
        """
        SRT形式の時刻文字列にフォーマット

        Args:
            time: 時刻（秒）

        Returns:
            HH:MM:SS,mmm 形式の文字列
        """
        hours = int(time // 3600)
        minutes = int((time % 3600) // 60)
        seconds = int(time % 60)
        milliseconds = int((time % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def to_srt(self) -> str:
        """
        SRT形式の文字列に変換

        Returns:
            SRT形式の字幕エントリ
        """
        return f"{self.id}\n{self.format_srt_time(self.start)} --> {self.format_srt_time(self.end)}\n{self.text}\n"

    def split_by_max_length(self, max_line_length: int, max_lines: int) -> list["Subtitle"]:
        """
        最大文字数・行数に基づいて字幕を分割

        Args:
            max_line_length: 1行の最大文字数
            max_lines: 最大行数

        Returns:
            分割された字幕のリスト
        """
        if not self.needs_split(max_line_length, max_lines):
            return [self]

        # テキストを単語に分割
        words = self.text.split()
        if not words:
            return [self]

        # 字幕を分割
        subtitles = []
        current_lines = []
        current_line = ""
        subtitle_count = 0

        for word in words:
            # 現在の行に単語を追加できるか確認
            test_line = current_line + (" " if current_line else "") + word
            if len(test_line) <= max_line_length:
                current_line = test_line
            else:
                # 現在の行を確定して新しい行を開始
                if current_line:
                    current_lines.append(current_line)
                current_line = word

                # 最大行数に達したら新しい字幕を作成
                if len(current_lines) >= max_lines:
                    subtitle_count += 1
                    duration_per_subtitle = self.duration / len(words) * len(" ".join(current_lines).split())
                    start_time = self.start + (self.duration * subtitle_count / (len(words) / max_lines))

                    subtitles.append(
                        Subtitle(
                            id=self.id + subtitle_count - 1,
                            time_range=TimeRange(
                                start=start_time, end=min(start_time + duration_per_subtitle, self.end)
                            ),
                            text="\n".join(current_lines),
                        )
                    )
                    current_lines = []

        # 残りのテキストを処理
        if current_line:
            current_lines.append(current_line)
        if current_lines:
            subtitle_count += 1
            start_time = self.start + (self.duration * (subtitle_count - 1) / (len(words) / max_lines))
            subtitles.append(
                Subtitle(
                    id=self.id + subtitle_count - 1,
                    time_range=TimeRange(start=start_time, end=self.end),
                    text="\n".join(current_lines),
                )
            )

        return subtitles

    def needs_split(self, max_line_length: int, max_lines: int) -> bool:
        """
        分割が必要かどうか判定

        Args:
            max_line_length: 1行の最大文字数
            max_lines: 最大行数

        Returns:
            分割が必要な場合True
        """
        lines = self.text.strip().split("\n")
        if len(lines) > max_lines:
            return True

        for line in lines:
            if len(line) > max_line_length:
                return True

        return False
