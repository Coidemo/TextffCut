"""
SRT字幕エクスポートモジュール

文字起こし結果をSRT（SubRip Text）形式で出力する。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import Config
from utils.logging import get_logger
from utils.time_utils import seconds_to_srt_time

logger = get_logger(__name__)


@dataclass
class SRTEntry:
    """SRT字幕エントリー"""

    index: int
    start_time: float
    end_time: float
    text: str

    def to_srt(self) -> str:
        """SRT形式の文字列に変換

        Returns:
            SRT形式の文字列（最後に空行を含む）
        """
        start_str = seconds_to_srt_time(self.start_time)
        end_str = seconds_to_srt_time(self.end_time)

        # テキストの整形（改行を維持）
        text = self.text.strip()

        # DaVinci Resolveで改行を認識させるため<b>タグで囲む
        # 他の編集ソフトでも問題なく動作することを確認済み
        formatted_text = f"<b>{text}</b>"

        # SRT仕様準拠: 各エントリの後に空行が必要
        return f"{self.index}\n{start_str} --> {end_str}\n{formatted_text}\n\n"


class SRTExporter:
    """SRT字幕エクスポータークラス"""

    def __init__(self, config: Config) -> None:
        """初期化

        Args:
            config: 設定オブジェクト
        """
        self.config = config
        self.max_line_length = 42  # 1行の最大文字数（一般的な推奨値）
        self.max_lines = 2  # 1つの字幕の最大行数
        self.min_duration = 0.5  # 最小表示時間（秒）
        self.max_duration = 7.0  # 最大表示時間（秒）
        self.gap_threshold = 0.1  # 字幕間の最小間隔（秒）

    def export(
        self,
        segments: list[Any],  # TranscriptionSegment
        output_path: str | Path,
        encoding: str = "utf-8",
        adjust_timing: bool = True,
    ) -> bool:
        """SRTファイルをエクスポート

        Args:
            segments: 文字起こしセグメントのリスト
            output_path: 出力ファイルパス
            encoding: 文字エンコーディング
            adjust_timing: タイミング調整を行うか

        Returns:
            成功したかどうか
        """
        try:
            # SRTエントリーを生成
            srt_entries = self._generate_srt_entries(segments, adjust_timing)

            if not srt_entries:
                logger.warning("No SRT entries generated")
                return False

            # SRTファイルに書き込み
            self._write_srt_file(srt_entries, output_path, encoding)

            logger.info(f"SRT exported successfully: {output_path} ({len(srt_entries)} entries)")
            return True

        except Exception as e:
            logger.error(f"SRT export failed: {e}")
            return False

    def _generate_srt_entries(self, segments: list[Any], adjust_timing: bool) -> list[SRTEntry]:
        """SRTエントリーを生成

        Args:
            segments: 文字起こしセグメント
            adjust_timing: タイミング調整を行うか

        Returns:
            SRTエントリーのリスト
        """
        srt_entries = []
        index = 1

        for segment in segments:
            if not segment.text or not segment.text.strip():
                continue

            # テキストを行に分割
            lines = self._split_text_into_lines(segment.text)

            if not lines:
                continue

            # タイミング調整
            start_time = segment.start
            end_time = segment.end

            if adjust_timing:
                # 表示時間の調整
                duration = end_time - start_time

                # 最小時間の確保
                if duration < self.min_duration:
                    end_time = start_time + self.min_duration

                # 最大時間の制限
                elif duration > self.max_duration:
                    # 長いセグメントは分割
                    words_per_second = len(segment.text.split()) / duration

                    current_start = start_time
                    for line_group in self._group_lines(lines, self.max_lines):
                        # 各グループの推定時間
                        group_text = "\n".join(line_group)
                        word_count = len(group_text.split())
                        group_duration = min(word_count / words_per_second, self.max_duration)

                        current_end = min(current_start + group_duration, end_time)

                        entry = SRTEntry(index=index, start_time=current_start, end_time=current_end, text=group_text)
                        srt_entries.append(entry)

                        index += 1
                        current_start = current_end

                    continue

            # 通常のエントリー作成
            text = "\n".join(lines[: self.max_lines])
            entry = SRTEntry(index=index, start_time=start_time, end_time=end_time, text=text)
            srt_entries.append(entry)
            index += 1

        # ギャップ調整
        if adjust_timing and len(srt_entries) > 1:
            srt_entries = self._adjust_gaps(srt_entries)

        return srt_entries

    def _split_text_into_lines(self, text: str) -> list[str]:
        """テキストを適切な行に分割

        Args:
            text: 分割するテキスト

        Returns:
            行のリスト
        """
        # 既存の改行を尊重
        lines = text.strip().split("\n")

        result = []
        for line in lines:
            if len(line) <= self.max_line_length:
                result.append(line)
            else:
                # 長い行は分割
                words = line.split()
                current_line = ""

                for word in words:
                    if not current_line:
                        current_line = word
                    elif len(current_line + " " + word) <= self.max_line_length:
                        current_line += " " + word
                    else:
                        result.append(current_line)
                        current_line = word

                if current_line:
                    result.append(current_line)

        return result

    def _group_lines(self, lines: list[str], max_lines: int) -> list[list[str]]:
        """行をグループ化

        Args:
            lines: 行のリスト
            max_lines: グループあたりの最大行数

        Returns:
            グループ化された行のリスト
        """
        groups = []
        for i in range(0, len(lines), max_lines):
            groups.append(lines[i : i + max_lines])
        return groups

    def _adjust_gaps(self, entries: list[SRTEntry]) -> list[SRTEntry]:
        """字幕間のギャップを調整

        Args:
            entries: SRTエントリーのリスト

        Returns:
            調整後のSRTエントリーのリスト
        """
        adjusted = []

        for i, entry in enumerate(entries):
            if i > 0:
                prev_entry = adjusted[-1]
                gap = entry.start_time - prev_entry.end_time

                # ギャップが小さすぎる場合
                if gap < self.gap_threshold:
                    # 前の字幕の終了時間を調整
                    mid_point = (prev_entry.end_time + entry.start_time) / 2
                    prev_entry.end_time = mid_point - self.gap_threshold / 2
                    entry.start_time = mid_point + self.gap_threshold / 2

            adjusted.append(entry)

        return adjusted

    def _write_srt_file(self, entries: list[SRTEntry], output_path: str | Path, encoding: str) -> None:
        """SRTファイルに書き込み（CRLF改行）

        Args:
            entries: SRTエントリーのリスト
            output_path: 出力ファイルパス
            encoding: 文字エンコーディング
        """
        # 出力ディレクトリを作成
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # SRTファイルに書き込み（newline=''でpythonの自動改行変換を無効化）
        with open(output_path, "w", encoding=encoding, newline="") as f:
            for entry in entries:
                # to_srt()メソッドが返す文字列のLFをCRLFに変換
                srt_text = entry.to_srt().replace("\n", "\r\n")
                f.write(srt_text)

    def export_with_style(
        self,
        segments: list[Any],  # TranscriptionSegment
        output_path: str | Path,
        style_options: dict[str, Any] | None = None,
    ) -> bool:
        """スタイル付きSRTをエクスポート（将来の拡張用）

        Args:
            segments: 文字起こしセグメント
            output_path: 出力ファイルパス
            style_options: スタイルオプション

        Returns:
            成功したかどうか
        """
        # 基本的なSRTはスタイルをサポートしないため、
        # 通常のエクスポートを実行
        return self.export(segments, output_path)


# テスト用関数
def test_srt_exporter() -> bool:
    """SRTエクスポーターのテスト"""
    from core.transcription import TranscriptionSegment

    print("=== SRT Exporter Test ===")

    # テスト用セグメント
    segments = [
        TranscriptionSegment(start=0.0, end=3.5, text="これはテスト用の字幕です。", words=[]),
        TranscriptionSegment(
            start=3.5,
            end=8.0,
            text="長いテキストの場合は自動的に複数行に分割されます。このように長い文章でも適切に処理されます。",
            words=[],
        ),
        TranscriptionSegment(start=8.5, end=12.0, text="短い字幕", words=[]),
    ]

    # エクスポーターを作成
    from config import Config

    config = Config()
    exporter = SRTExporter(config)

    # エクスポート実行
    output_path = "/tmp/test_subtitle.srt"
    success = exporter.export(segments, output_path)

    if success:
        print(f"✓ SRT exported to: {output_path}")

        # ファイル内容を表示
        with open(output_path, encoding="utf-8") as f:
            content = f.read()
            print("\n--- SRT Content ---")
            print(content)
    else:
        print("✗ SRT export failed")

    return success


if __name__ == "__main__":
    test_srt_exporter()
