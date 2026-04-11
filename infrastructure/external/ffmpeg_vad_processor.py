"""
FFmpegベースのVADプロセッサー実装

ffmpegのsilencedetectフィルターを使用した音声区間検出
"""

import re
import subprocess
from typing import List, Tuple

from infrastructure.interfaces.vad_processor import IVADProcessor
from utils.logging import get_logger

logger = get_logger(__name__)


class FFmpegVADProcessor(IVADProcessor):
    """FFmpegを使用したVADプロセッサー"""

    def __init__(self):
        """初期化"""
        self.preferred_segment_duration = 20.0  # 推奨セグメント長

    def detect_segments(
        self,
        audio_path: str,
        max_segment_duration: float = 30.0,
        min_segment_duration: float = 5.0,
        silence_threshold: float = -35.0,
        min_silence_duration: float = 0.3,
    ) -> List[Tuple[float, float]]:
        """
        FFmpegのsilencedetectを使用して音声区間を検出
        """
        try:
            # 音声の総時間を取得
            total_duration = self.get_audio_duration(audio_path)

            # 無音検出で音声区間を特定
            silence_cmd = [
                "ffmpeg",
                "-i",
                audio_path,
                "-af",
                f"silencedetect=noise={silence_threshold}dB:d={min_silence_duration}",
                "-f",
                "null",
                "-",
            ]
            result = subprocess.run(silence_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

            # 無音区間を解析して音声区間を抽出
            vad_segments = self._parse_silence_output(result.stdout, total_duration)

            # セグメントを適切なサイズに分割
            final_segments = self._split_segments(vad_segments, max_segment_duration, min_segment_duration)

            logger.info(f"VAD検出: {len(vad_segments)}個の音声区間 → " f"{len(final_segments)}個のセグメントに分割")

            return final_segments

        except Exception as e:
            logger.error(f"VADベース分割に失敗: {e}")
            # フォールバック：固定長分割
            return self._fallback_fixed_segments(audio_path, max_segment_duration, min_segment_duration)

    def get_audio_duration(self, audio_path: str) -> float:
        """音声ファイルの総時間を取得"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {result.stderr}")

        duration_str = result.stdout.strip()
        if not duration_str:
            raise RuntimeError("ffprobe returned empty duration")

        return float(duration_str)

    def _parse_silence_output(self, output: str, total_duration: float) -> List[Tuple[float, float]]:
        """FFmpegの出力から音声区間を解析"""
        silence_starts = re.findall(r"silence_start: ([\d.]+)", output)
        silence_ends = re.findall(r"silence_end: ([\d.]+)", output)

        vad_segments = []

        if silence_starts:
            # 最初の無音開始まで
            if float(silence_starts[0]) > 0.1:
                vad_segments.append((0.0, float(silence_starts[0])))

            # 無音区間の間の音声区間
            for i in range(len(silence_ends)):
                start = float(silence_ends[i])
                if i < len(silence_starts) - 1:
                    end = float(silence_starts[i + 1])
                else:
                    end = total_duration

                if end - start > 0.1:  # 0.1秒以上の音声区間のみ
                    vad_segments.append((start, end))
        else:
            # 無音が検出されなかった場合は全体を1つのセグメントとして扱う
            vad_segments = [(0.0, total_duration)]

        return vad_segments

    def _split_segments(
        self, vad_segments: List[Tuple[float, float]], max_duration: float, min_duration: float
    ) -> List[Tuple[float, float]]:
        """セグメントを適切なサイズに分割・結合"""
        # 長いセグメントを分割
        split_segments = []
        for start, end in vad_segments:
            if end - start > max_duration:
                current_start = start
                while current_start < end:
                    segment_end = min(current_start + self.preferred_segment_duration, end)
                    split_segments.append((current_start, segment_end))
                    current_start = segment_end
            else:
                split_segments.append((start, end))

        # 短すぎるセグメントを結合
        merged_segments = []
        i = 0
        while i < len(split_segments):
            start, end = split_segments[i]

            # 次のセグメントと結合可能か確認
            while i + 1 < len(split_segments):
                next_start, next_end = split_segments[i + 1]
                # 間隔が短く、合計時間が最大時間以内なら結合
                if next_start - end < 0.5 and next_end - start <= max_duration:
                    end = next_end
                    i += 1
                else:
                    break

            # 最小長以上なら追加
            if end - start >= min_duration:
                merged_segments.append((start, end))
            i += 1

        return merged_segments

    def _fallback_fixed_segments(
        self, audio_path: str, max_duration: float, min_duration: float
    ) -> List[Tuple[float, float]]:
        """フォールバック：固定長分割"""
        try:
            duration = self.get_audio_duration(audio_path)
        except Exception as e:
            logger.error(f"音声長取得に失敗: {e}")
            duration = 1800.0  # 30分を仮定

        segments = []
        current = 0.0
        while current < duration:
            segment_end = min(current + self.preferred_segment_duration, duration)
            segments.append((current, segment_end))
            current = segment_end

        return segments
