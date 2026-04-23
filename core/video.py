"""
動画処理モジュール
"""

import json
import subprocess
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import Config
from utils.file_utils import ensure_directory
from utils.logging import get_logger
from utils.time_utils import format_time

logger = get_logger(__name__)


@dataclass
class VideoInfo:
    """動画情報"""

    path: str
    duration: float
    fps: float
    width: int
    height: int
    codec: str

    @classmethod
    def from_file(cls, video_path: str | Path) -> "VideoInfo":
        """動画ファイルから情報を取得"""
        try:
            # FFprobeで動画情報を取得
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,codec_name",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"FFprobe error: {result.stderr}")

            info = json.loads(result.stdout)

            # ストリーム情報
            stream = info["streams"][0] if "streams" in info and info["streams"] else {}
            width = stream.get("width", 1920)
            height = stream.get("height", 1080)
            codec = stream.get("codec_name", "unknown")

            # フレームレート
            fps_str = stream.get("r_frame_rate", "30/1")
            num, den = map(int, fps_str.split("/"))
            fps = num / den if den != 0 else 30.0

            # 長さ
            duration = float(info.get("format", {}).get("duration", 0))

            return cls(path=str(video_path), duration=duration, fps=fps, width=width, height=height, codec=codec)

        except subprocess.CalledProcessError as e:
            from utils.exceptions import FFmpegError

            raise FFmpegError("ffprobe", e.stderr) from e
        except FileNotFoundError:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(str(video_path)) from None
        except json.JSONDecodeError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"動画メタデータの解析エラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"動画情報取得エラー: {str(e)}") from e


@dataclass
class VideoSegment:
    """動画セグメント"""

    start: float
    end: float
    output_path: str | Path | None = None

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class SilenceInfo:
    """無音情報"""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def _rescue_missing_words(
    keep_ranges: list[tuple[float, float]],
    words: list[Any],
    time_ranges: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """無音削除後の keep_ranges に含まれない word を救済する。

    word が完全に keep 区間外（= silence 領域に落ちた）場合、その word の時間範囲
    そのものを keep_ranges に追加する（padding なし）。word を含む元 time_range
    に完全に収まっているため、境界が元 time_ranges の外に出ることは無い。
    """

    def _word_attr(w: Any, name: str) -> float | None:
        if hasattr(w, name):
            return getattr(w, name)
        if isinstance(w, dict):
            return w.get(name)
        return None

    def _overlaps_any(start: float, end: float, ranges: list[tuple[float, float]]) -> bool:
        """word と range 群のいずれかに重なりがあるか（境界接触は含まない）。"""
        return any(start < r_end and end > r_start for r_start, r_end in ranges)

    rescued = list(keep_ranges)
    rescue_count = 0
    for w in words:
        w_start = _word_attr(w, "start")
        w_end = _word_attr(w, "end")
        if w_start is None or w_end is None or w_end <= w_start:
            continue
        # word が完全に含まれる元 time_range を特定（境界跨ぎの word はスキップ）
        if not any(r_s <= w_start and w_end <= r_e for r_s, r_e in time_ranges):
            continue
        # keep 区間のいずれかと少しでも重なっていれば「音として残っている」と見做し救済対象外
        if _overlaps_any(w_start, w_end, rescued):
            continue
        # 救済: word 範囲そのまま（padding 無し）。word は元 time_range 内なので
        # 境界を超えることは無い。
        rescued.append((w_start, w_end))
        rescue_count += 1

    if rescue_count == 0:
        return keep_ranges

    # マージ: 重なる/接する range を統合
    rescued.sort(key=lambda x: x[0])
    merged: list[tuple[float, float]] = []
    for s, e in rescued:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    logger.info(f"無音削除: {rescue_count}個のword を救済（消失防止）")
    return merged


class VideoProcessor:
    """動画処理クラス"""

    def __init__(self, config: Config) -> None:
        self.config = config

    def extract_segment(
        self,
        input_path: str | Path,
        start: float,
        end: float,
        output_path: str | Path,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> bool:
        """
        動画から指定セグメントを抽出

        Args:
            input_path: 入力動画パス
            start: 開始時間（秒）
            end: 終了時間（秒）
            output_path: 出力パス
            progress_callback: 進捗コールバック

        Returns:
            成功したかどうか
        """
        try:
            # 出力ディレクトリを確保
            ensure_directory(Path(output_path).parent)

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-ss",
                str(start),
                "-to",
                str(end),
                "-c:v",
                self.config.video.video_codec,
                "-preset",
                self.config.video.ffmpeg_preset,
                "-c:a",
                self.config.video.audio_codec,
                "-b:a",
                self.config.video.audio_bitrate,
                "-avoid_negative_ts",
                "1",
                str(output_path),
            ]

            if progress_callback:
                # プログレス付きで実行
                process = subprocess.Popen(
                    cmd + ["-progress", "pipe:1"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )

                self._monitor_ffmpeg_progress(process, end - start, progress_callback)

                return process.returncode == 0
            else:
                # 通常実行
                result = subprocess.run(cmd, capture_output=True)
                return result.returncode == 0

        except subprocess.CalledProcessError as e:
            from utils.exceptions import FFmpegError

            cmd_str = " ".join(str(c) for c in cmd)
            raise FFmpegError(cmd_str, e.stderr) from e
        except FileNotFoundError:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(str(input_path)) from None
        except OSError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"ファイルシステムエラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"セグメント抽出エラー: {str(e)}") from e

    def detect_silence_from_wav(
        self,
        wav_path: str | Path,
        noise_threshold: float = -35,
        min_silence_duration: float = 0.3,
        start: float | None = None,
        end: float | None = None,
    ) -> list[SilenceInfo]:
        """
        WAVファイルから直接無音部分を検出

        Args:
            wav_path: WAV音声ファイルパス
            noise_threshold: 無音判定の閾値（dB）
            min_silence_duration: 最小無音時間（秒）
            start: 検出開始時間
            end: 検出終了時間

        Returns:
            無音部分のリスト
        """
        # 無音検出コマンドを構築
        detect_cmd = ["ffmpeg", "-y", "-i", str(wav_path)]

        # 時間範囲の指定
        if start is not None:
            detect_cmd.extend(["-ss", str(start)])
        if end is not None:
            detect_cmd.extend(["-to", str(end)])

        detect_cmd.extend(
            ["-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}", "-f", "null", "-"]
        )

        result = subprocess.run(detect_cmd, capture_output=True, text=True)

        # 結果を解析
        silences = []
        current_start = None
        offset = start if start is not None else 0

        for line in result.stderr.split("\n"):
            if "silence_start" in line:
                try:
                    time_val = float(line.split("silence_start: ")[1].split()[0])
                    current_start = time_val + offset
                except (ValueError, IndexError, AttributeError):
                    # FFmpegの出力パースエラーは無視（フォーマットが変わる可能性があるため）
                    pass

            elif "silence_end" in line and current_start is not None:
                try:
                    time_val = float(line.split("silence_end: ")[1].split()[0])
                    silences.append(SilenceInfo(start=current_start, end=time_val + offset))
                    current_start = None
                except (ValueError, IndexError, AttributeError):
                    # FFmpegの出力パースエラーは無視（フォーマットが変わる可能性があるため）
                    pass

        return silences

    def detect_silence(
        self,
        input_path: str | Path,
        noise_threshold: float = -35,
        min_silence_duration: float = 0.3,
        start: float | None = None,
        end: float | None = None,
    ) -> list[SilenceInfo]:
        """
        動画から直接無音部分を検出（WAVファイル作成不要）

        Args:
            input_path: 入力動画パス（MP4やWAVファイル）
            noise_threshold: 無音判定の閾値（dB）
            min_silence_duration: 最小無音時間（秒）
            start: 検出開始時間
            end: 検出終了時間

        Returns:
            無音部分のリスト
        """
        # 動画から直接無音検出（一時ファイル不要）
        detect_cmd = ["ffmpeg", "-y", "-i", str(input_path)]

        # 時間範囲の指定
        if start is not None:
            detect_cmd.extend(["-ss", str(start)])
        if end is not None:
            detect_cmd.extend(["-to", str(end)])

        detect_cmd.extend(
            ["-af", f"silencedetect=noise={noise_threshold}dB:d={min_silence_duration}", "-f", "null", "-"]
        )

        result = subprocess.run(detect_cmd, capture_output=True, text=True)

        # 結果を解析
        silences = []
        current_start = None
        offset = start if start is not None else 0

        for line in result.stderr.split("\n"):
            if "silence_start" in line:
                try:
                    time_val = float(line.split("silence_start: ")[1].split()[0])
                    current_start = time_val + offset
                except (ValueError, IndexError, AttributeError):
                    # FFmpegの出力パースエラーは無視（フォーマットが変わる可能性があるため）
                    pass

            elif "silence_end" in line and current_start is not None:
                try:
                    time_val = float(line.split("silence_end: ")[1].split()[0])
                    silences.append(SilenceInfo(start=current_start, end=time_val + offset))
                    current_start = None
                except (ValueError, IndexError, AttributeError):
                    # FFmpegの出力パースエラーは無視（フォーマットが変わる可能性があるため）
                    pass

        return silences

    def extract_audio_for_ranges(
        self,
        input_path: str | Path,
        time_ranges: list[tuple[float, float]],
        output_dir: str,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> list[tuple[str, tuple[float, float]]]:
        """
        指定された時間範囲の音声をWAVファイルとして抽出

        Args:
            input_path: 入力動画パス
            time_ranges: 時間範囲のリスト [(start, end), ...]
            output_dir: 出力ディレクトリ
            progress_callback: 進捗コールバック

        Returns:
            [(wav_file_path, (start, end)), ...] WAVファイルパスと対応する時間範囲
        """
        output_dir_path = ensure_directory(Path(output_dir))
        wav_files = []

        total = len(time_ranges)
        for i, (start, end) in enumerate(time_ranges):
            if progress_callback:
                progress = i / total
                progress_callback(progress, f"音声抽出中... セグメント {i + 1}/{total}")

            # WAVファイル名（時間情報を含む）
            wav_filename = f"segment_{i + 1}_{start:.1f}_{end:.1f}.wav"
            wav_path = output_dir_path / wav_filename

            # 音声を抽出
            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-to",
                str(end),
                "-i",
                str(input_path),
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-f",
                "wav",
                str(wav_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                wav_files.append((str(wav_path), (start, end)))
                logger.info(f"音声抽出成功: {wav_filename}")
            else:
                logger.error(f"音声抽出失敗: {result.stderr}")

        if progress_callback:
            progress_callback(1.0, "音声抽出完了")

        return wav_files

    def remove_silence(
        self,
        input_path: str | Path,
        output_dir: str,
        segments: list[VideoSegment],
        noise_threshold: float = -35,
        min_silence_duration: float = 0.3,
        min_segment_duration: float = 0.3,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> tuple[list[str], dict[str, VideoSegment]]:
        """
        セグメントから無音を削除

        Args:
            input_path: 入力動画パス
            output_dir: 出力ディレクトリ
            segments: 処理するセグメントのリスト
            noise_threshold: 無音判定の閾値
            min_silence_duration: 最小無音時間
            min_segment_duration: 最小セグメント時間
            progress_callback: 進捗コールバック

        Returns:
            (出力ファイルパスのリスト, ファイルパスとセグメント情報の辞書)
        """
        output_dir_path = ensure_directory(Path(output_dir))
        output_files = []
        segment_info = {}

        total_segments = len(segments)

        for i, segment in enumerate(segments):
            if progress_callback:
                base_progress = i / total_segments
                status = f"セグメント {i + 1}/{total_segments} を処理中..."
                progress_callback(base_progress, status)

            # 無音を検出
            silences = self.detect_silence(
                input_path, noise_threshold, min_silence_duration, segment.start, segment.end
            )

            # 無音を除いた部分を計算
            keep_segments = self._calculate_keep_segments(
                segment.start, segment.end, silences, min_segment_duration, 0.0, 0.0  # 古い関数ではパディングなし
            )

            # 各部分を抽出
            part_files = []
            logger.info(f"セグメント {i + 1}: {len(keep_segments)}個の部分を抽出")
            for j, keep_seg in enumerate(keep_segments):
                part_file = output_dir_path / f"segment_{i + 1}_part_{j + 1}.mp4"

                logger.info(
                    f"セグメント {i + 1}-部分 {j + 1}: {keep_seg.start:.1f}s - {keep_seg.end:.1f}s -> {part_file}"
                )
                if self.extract_segment(input_path, keep_seg.start, keep_seg.end, str(part_file)):
                    part_files.append(str(part_file))
                    segment_info[str(part_file)] = keep_seg
                    # ファイルサイズを確認
                    file_size = Path(part_file).stat().st_size if Path(part_file).exists() else 0
                    logger.info(f"セグメント {i + 1}-部分 {j + 1}: 抽出成功、サイズ: {file_size} bytes")
                else:
                    logger.error(f"セグメント {i + 1}-部分 {j + 1}: 抽出失敗")

            # 部分を結合
            if len(part_files) > 1:
                output_file = output_dir_path / f"segment_{i + 1}.mp4"
                logger.info(f"セグメント {i + 1}: {len(part_files)}個の部分ファイルを結合")
                if self.combine_videos(part_files, str(output_file)):
                    output_files.append(str(output_file))
                    logger.info(f"セグメント {i + 1}: 結合成功、部分ファイルを削除")
                    # 部分ファイルを削除
                    for part in part_files:
                        try:
                            Path(part).unlink()
                        except Exception as e:
                            logger.warning(f"部分ファイル削除エラー {part}: {e}")
                else:
                    logger.error(f"セグメント {i + 1}: 結合失敗")

            elif len(part_files) == 1:
                # 1つだけの場合はリネーム
                output_file = output_dir_path / f"segment_{i + 1}.mp4"
                logger.info(f"セグメント {i + 1}: 単一ファイルをリネーム {part_files[0]} -> {output_file}")
                try:
                    Path(part_files[0]).rename(output_file)
                    output_files.append(str(output_file))
                    logger.info(f"セグメント {i + 1}: リネーム成功")
                except Exception as e:
                    logger.error(f"セグメント {i + 1}: リネームエラー: {e}")
            else:
                logger.warning(f"セグメント {i + 1}: 有効な部分ファイルがありません")

            # 進捗を更新（セグメント処理完了）
            if progress_callback:
                progress = (i + 1) / total_segments
                status = f"セグメント {i + 1}/{total_segments} の処理完了"
                progress_callback(progress, status)

        # 最終確認: 全ての出力ファイルの存在を確認
        logger.info(f"無音削除処理完了: {len(output_files)}個のセグメント生成")
        final_output_files = []
        for i, file_path in enumerate(output_files):
            exists = Path(file_path).exists()
            size = Path(file_path).stat().st_size if exists else 0
            logger.info(f"  セグメント {i + 1}: {Path(file_path).name} - 存在: {exists}, サイズ: {size} bytes")
            if exists and size > 0:
                final_output_files.append(file_path)
            else:
                logger.error(f"  セグメント {i + 1}: ファイルが無効または存在しません")

        logger.info(f"有効なセグメント: {len(final_output_files)}/{len(output_files)}")
        return final_output_files, segment_info

    def remove_silence_new(
        self,
        input_path: str | Path,
        time_ranges: list[tuple[float, float]],
        output_dir: str,
        noise_threshold: float = -35,
        min_silence_duration: float = 0.3,
        min_segment_duration: float = 0.3,
        padding_start: float = 0.1,
        padding_end: float = 0.1,
        progress_callback: Callable[[float, str], None] | None = None,
        transcription_words: list[Any] | None = None,
    ) -> list[tuple[float, float]]:
        """
        新フロー：時間範囲から無音を検出し、残す部分の時間範囲を返す

        Args:
            input_path: 入力動画パス
            time_ranges: 処理する時間範囲のリスト
            output_dir: 一時ファイル用ディレクトリ
            noise_threshold: 無音判定の閾値
            min_silence_duration: 最小無音時間
            min_segment_duration: 最小セグメント時間
            padding_start: セグメント開始前に追加するパディング時間
            padding_end: セグメント終了後に追加するパディング時間
            progress_callback: 進捗コールバック

        Returns:
            残す部分の時間範囲のリスト [(start, end), ...]
        """
        output_dir_path = ensure_directory(Path(output_dir))
        keep_ranges = []

        # Step 1: 時間範囲のWAVファイルを抽出
        if progress_callback:
            progress_callback(0.0, "音声ファイルを抽出中...")

        wav_files = self.extract_audio_for_ranges(
            input_path,
            time_ranges,
            str(output_dir_path / "temp_wav"),
            lambda p, s: progress_callback(p * 0.3, s) if progress_callback else None,
        )

        # Step 2: 各WAVファイルから無音を検出
        total_wav = len(wav_files)
        for i, (wav_path, (original_start, original_end)) in enumerate(wav_files):
            if progress_callback:
                base_progress = 0.3 + (i / total_wav) * 0.6
                progress_callback(base_progress, f"無音検出中... セグメント {i + 1}/{total_wav}")

            # WAVファイルから無音を検出（オフセットなし）
            silences = self.detect_silence_from_wav(wav_path, noise_threshold, min_silence_duration)

            # 無音を除いた部分を計算（WAVファイル内の相対時間）
            wav_duration = original_end - original_start
            keep_segments = self._calculate_keep_segments(
                0, wav_duration, silences, min_segment_duration, padding_start, padding_end  # WAVファイルの開始は0
            )

            # 元動画の時間にオフセットを適用
            for seg in keep_segments:
                keep_ranges.append((original_start + seg.start, original_start + seg.end))

            logger.info(f"セグメント {i + 1}: {len(silences)}個の無音検出、{len(keep_segments)}個の部分を保持")

        # Step 3: 一時WAVファイルをクリーンアップ
        if progress_callback:
            progress_callback(0.9, "一時ファイルをクリーンアップ中...")

        for wav_path, _ in wav_files:
            try:
                Path(wav_path).unlink()
            except Exception as e:
                logger.warning(f"WAVファイル削除エラー: {e}")

        # 一時ディレクトリも削除
        # 一時ディレクトリの削除エラーは無視（空でない場合など）
        with suppress(OSError):
            (output_dir_path / "temp_wav").rmdir()

        # output_dir_path自体も削除を試みる
        with suppress(OSError):
            output_dir_path.rmdir()

        if progress_callback:
            progress_callback(1.0, "無音検出完了")

        # 時間順にソート
        keep_ranges.sort(key=lambda x: x[0])

        # 消えた word を救済（word が完全に silence 領域に落ちた場合のみ復活）
        if transcription_words:
            keep_ranges = _rescue_missing_words(
                keep_ranges,
                transcription_words,
                time_ranges,
            )

        return keep_ranges

    def _calculate_keep_segments(
        self,
        start: float,
        end: float,
        silences: list[SilenceInfo],
        min_duration: float,
        padding_start: float = 0.0,
        padding_end: float = 0.0,
    ) -> list[VideoSegment]:
        """無音部分を除いたセグメントを計算（パディング付き）"""
        keep_segments = []
        current_pos = start

        for silence in silences:
            # 無音の前の部分
            if silence.start - current_pos >= min_duration:
                # パディングを適用してセグメントを拡張
                segment_start = max(start, current_pos - padding_start)
                segment_end = min(end, silence.start + padding_end)

                keep_segments.append(VideoSegment(start=segment_start, end=segment_end))
            current_pos = silence.end

        # 最後の部分
        if end - current_pos >= min_duration:
            # パディングを適用してセグメントを拡張
            segment_start = max(start, current_pos - padding_start)
            segment_end = min(end, end)  # 最後は元の終了時間まで

            keep_segments.append(VideoSegment(start=segment_start, end=segment_end))

        return keep_segments

    def extract_audio_from_segments(
        self,
        input_path: str | Path,
        segments: list[VideoSegment],
        output_audio_path: str | Path,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> bool:
        """
        指定セグメントから音声のみを抽出して結合

        Args:
            input_path: 入力動画パス
            segments: 抽出するセグメントのリスト
            output_audio_path: 出力音声ファイルパス
            progress_callback: 進捗コールバック

        Returns:
            成功したかどうか
        """
        try:
            # 一時ファイルリスト
            temp_audio_files = []
            temp_dir = Path(output_audio_path).parent

            # 各セグメントから音声を抽出
            for i, segment in enumerate(segments):
                temp_audio = temp_dir / f"temp_audio_{i:04d}.wav"

                duration = segment.end - segment.start
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-ss",
                    str(segment.start),
                    "-t",
                    str(duration),  # -to の代わりに -t (duration) を使用
                    "-vn",  # ビデオなし
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",  # Whisper用のサンプリングレート
                    "-ac",
                    "1",  # モノラル
                    str(temp_audio),
                ]

                logger.info(f"音声抽出コマンド実行: セグメント {i + 1} ({segment.start:.1f}s - {segment.end:.1f}s)")
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    temp_audio_files.append(str(temp_audio))
                    # ファイルサイズを確認
                    file_size = Path(temp_audio).stat().st_size
                    logger.info(f"音声抽出成功: セグメント {i + 1}, ファイルサイズ: {file_size} bytes")
                else:
                    logger.error(f"音声抽出エラー セグメント {i + 1}: {result.stderr}")
                    # エラーでも処理を続行せずに失敗を返す
                    return False

                if progress_callback:
                    progress = (i + 1) / len(segments) * 0.5
                    progress_callback(progress, f"音声抽出中... ({i + 1}/{len(segments)})")

            # 音声ファイルを結合
            if len(temp_audio_files) > 1:
                # 各音声ファイルの情報をログに記録
                for i, audio_file in enumerate(temp_audio_files):
                    try:
                        probe_cmd = [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "default=noprint_wrappers=1:nokey=1",
                            str(audio_file),
                        ]
                        probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
                        if probe_result.returncode == 0:
                            duration = float(probe_result.stdout.strip())
                            logger.info(f"音声ファイル {i + 1}: {Path(audio_file).name}, 長さ: {duration:.1f}秒")
                    except (ValueError, subprocess.CalledProcessError):
                        pass

                # リストファイルを作成
                list_file = temp_dir / "audio_list.txt"
                with open(list_file, "w") as f:
                    for audio_file in temp_audio_files:
                        f.write(f"file '{Path(audio_file).resolve()}'\n")

                # 結合
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(list_file),
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    "-f",
                    "wav",  # 出力フォーマットを明示的に指定
                    str(output_audio_path),
                ]

                logger.info(f"音声結合開始: {len(temp_audio_files)}ファイル")
                result = subprocess.run(cmd, capture_output=True, text=True)
                success = result.returncode == 0

                if not success:
                    logger.error(f"音声結合エラー: {result.stderr}")
                else:
                    logger.info(f"音声結合成功: {output_audio_path}")

                # リストファイルを削除
                # リストファイルの削除エラーは無視（既に削除されている場合など）
                with suppress(ValueError, IndexError, AttributeError):
                    list_file.unlink()

            elif len(temp_audio_files) == 1:
                # 単一ファイルの場合はリネーム
                Path(temp_audio_files[0]).rename(output_audio_path)
                success = True
            else:
                success = False

            # 一時ファイルを削除（デバッグモードでない場合のみ）
            if not progress_callback or "デバッグ" not in str(progress_callback):
                for temp_file in temp_audio_files:
                    try:
                        if Path(temp_file).exists():
                            Path(temp_file).unlink()
                    except OSError as e:
                        logger.warning(f"一時ファイル削除に失敗: {temp_file} - {str(e)}")
                    except Exception as e:
                        logger.warning(f"予期しない一時ファイル削除エラー: {temp_file} - {str(e)}")
            else:
                logger.info(f"デバッグモード: 一時音声ファイルを保持しました ({len(temp_audio_files)}ファイル)")

            if progress_callback and success:
                progress_callback(1.0, "音声抽出完了")

            return success

        except Exception as e:
            logger.error(f"音声抽出エラー: {e}")
            return False

    def combine_videos(
        self, input_files: list[str], output_file: str, progress_callback: Callable[[float, str], None] | None = None
    ) -> bool:
        """
        複数の動画を結合

        Args:
            input_files: 入力ファイルのリスト
            output_file: 出力ファイル
            progress_callback: 進捗コールバック

        Returns:
            成功したかどうか
        """
        try:
            # デバッグ: 入力ファイルの存在確認
            logger.info(f"動画結合開始: {len(input_files)}ファイル -> {output_file}")
            for i, file in enumerate(input_files):
                file_path = Path(file)
                exists = file_path.exists()
                size = file_path.stat().st_size if exists else 0
                logger.info(f"  入力ファイル {i + 1}: {file_path.name} - 存在: {exists}, サイズ: {size} bytes")
                if not exists:
                    logger.error(f"入力ファイルが見つかりません: {file}")
                    return False

            # 一時的なリストファイルを作成
            list_file = Path(output_file).parent / f"concat_list_{int(time.time())}.txt"

            with open(list_file, "w") as f:
                for file in input_files:
                    f.write(f"file '{Path(file).resolve()}'\n")

            # デバッグ: リストファイルの内容を確認
            logger.info(f"結合リストファイル作成: {list_file}")
            with open(list_file) as f:
                list_content = f.read()
                logger.info(f"リストファイル内容:\n{list_content}")

            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(output_file)]

            logger.info(f"FFmpegコマンド実行: {' '.join(cmd)}")

            if progress_callback:
                # 合計時間を計算
                total_duration = sum(VideoInfo.from_file(f).duration for f in input_files)

                process = subprocess.Popen(
                    cmd + ["-progress", "pipe:1"],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    universal_newlines=True,
                )

                self._monitor_ffmpeg_progress(process, total_duration, progress_callback)

                success = process.returncode == 0
                if not success:
                    stderr_output = process.stderr.read() if process.stderr else ""
                    logger.error(f"FFmpeg stderr: {stderr_output}")
            else:
                result = subprocess.run(cmd, capture_output=True, text=True)
                success = result.returncode == 0
                if not success:
                    logger.error(f"FFmpeg結合エラー - stdout: {result.stdout}")
                    logger.error(f"FFmpeg結合エラー - stderr: {result.stderr}")

            # リストファイルを削除
            list_file.unlink()

            if success:
                logger.info(f"動画結合成功: {output_file}")
            else:
                logger.error(f"動画結合失敗: {output_file}")

            return success

        except subprocess.CalledProcessError as e:
            from utils.exceptions import FFmpegError

            cmd_str = " ".join(str(c) for c in cmd)
            raise FFmpegError(cmd_str, e.stderr) from e
        except FileNotFoundError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(str(e)) from e
        except OSError as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"ファイルシステムエラー: {str(e)}") from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"動画結合エラー: {str(e)}") from e

    def extract_audio_segment(
        self, input_path: str | Path, start_time: float, end_time: float, output_path: str | Path
    ) -> None:
        """
        指定された時間範囲の音声を抽出

        Args:
            input_path: 入力動画ファイルパス
            start_time: 開始時間（秒）
            end_time: 終了時間（秒）
            output_path: 出力音声ファイルパス
        """
        try:
            # 時間パラメータを数値に変換
            start_time = float(start_time)
            end_time = float(end_time)

            # 継続時間を計算
            duration = end_time - start_time

            cmd = [
                "ffmpeg",
                "-y",
                "-ss",
                str(start_time),
                "-i",
                str(input_path),
                "-t",  # -toではなく-tで継続時間を指定
                str(duration),
                "-vn",  # ビデオなし
                "-acodec",
                "pcm_s16le",
                "-ar",
                "44100",
                "-ac",
                "1",
                "-f",
                "wav",
                str(output_path),
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                from utils.exceptions import FFmpegError

                logger.error(f"FFmpeg command failed: {' '.join(cmd)}")
                logger.error(f"FFmpeg stderr: {result.stderr}")
                raise FFmpegError(" ".join(cmd), result.stderr)

            logger.info(f"音声セグメント抽出成功: {start_time}s-{end_time}s")

        except subprocess.CalledProcessError as e:
            from utils.exceptions import FFmpegError

            raise FFmpegError(" ".join(cmd), e.stderr) from e
        except FileNotFoundError as e:
            from utils.exceptions import FileNotFoundError as TextffCutFileNotFoundError

            raise TextffCutFileNotFoundError(str(e)) from e
        except Exception as e:
            from utils.exceptions import VideoProcessingError

            raise VideoProcessingError(f"音声抽出エラー: {str(e)}") from e

    def create_speed_changed_video(
        self,
        source_path: str | Path,
        output_path: str | Path,
        speed: float = 1.2,
    ) -> str:
        """ソース動画をspeed倍速化した動画を生成する。

        映像は再エンコードせずタイムスタンプのみ変更（品質劣化なし）。
        音声はatempo filterでピッチ保持した速度変更。
        既に変換済みファイルが存在すればスキップ（キャッシュ）。

        Args:
            source_path: 入力動画パス
            output_path: 出力動画パス
            speed: 再生速度（0.5〜2.0）

        Returns:
            出力動画パス
        """
        if not (0.5 <= speed <= 2.0):
            raise ValueError(f"speedは0.5〜2.0の範囲で指定してください: {speed}")

        output_path = Path(output_path)

        # キャッシュ: 出力ファイルが既に存在すればスキップ
        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"速度変更済みファイルが既に存在: {output_path}")
            return str(output_path)

        ensure_directory(output_path.parent)

        itsscale = 1.0 / speed

        cmd = [
            "ffmpeg",
            "-y",
            "-itsscale:v",
            str(itsscale),
            "-i",
            str(source_path),
            "-c:v",
            "copy",
            "-af",
            f"atempo={speed}",
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            str(output_path),
        ]

        logger.info(f"速度変更開始: {speed}x ({source_path} → {output_path})")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            from utils.exceptions import FFmpegError

            raise FFmpegError(" ".join(cmd), result.stderr)

        logger.info(f"速度変更完了: {output_path}")
        return str(output_path)

    def _monitor_ffmpeg_progress(
        self, process: subprocess.Popen, total_duration: float, progress_callback: Callable[[float, str], None]
    ) -> None:
        """FFmpegの進捗を監視"""
        start_time = time.time()

        while process.poll() is None:
            output = process.stderr.readline() if process.stderr else b""
            if not output:
                continue

            try:
                output = output.decode("utf-8", errors="ignore")
                if "time=" in output:
                    # 時間情報を抽出
                    time_str = output.split("time=")[1].split()[0]
                    hours, minutes, seconds = time_str.split(":")
                    current_time = float(hours) * 3600 + float(minutes) * 60 + float(seconds)

                    # 進捗率を計算
                    progress = min(current_time / total_duration, 1.0)

                    # 残り時間を計算
                    elapsed = time.time() - start_time
                    if progress > 0:
                        estimated_total = elapsed / progress
                        remaining = estimated_total - elapsed
                        status = f"処理中... (残り約{format_time(remaining)})"
                    else:
                        status = "処理中..."

                    progress_callback(progress, status)

            except Exception:
                pass
