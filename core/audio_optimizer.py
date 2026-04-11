"""
インテリジェントな音声最適化システム
"""

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np

from utils.logging import get_logger

logger = get_logger(__name__)


class IntelligentAudioOptimizer:
    """状況に応じた適応的音声最適化"""

    def __init__(self):
        # サンプルレートを設定（16kHz固定）
        self.target_sample_rate = self._get_target_sample_rate()
        self.optimization_stats = []

    def _get_target_sample_rate(self) -> int:
        """音声処理のサンプルレートを返す（16kHz固定）"""
        return 16000

    def prepare_audio(self, video_path: Path) -> Tuple[np.ndarray, Dict[str, Any]]:
        """
        音声を準備し、最適化の詳細情報を返す（常に最適化を実行）

        Args:
            video_path: 動画ファイルパス

        Returns:
            (音声データ, 最適化情報)
        """

        # パスを確実にPathオブジェクトに
        video_path = Path(video_path)

        # 1. 音声ストリーム情報を分析
        audio_info = self._analyze_audio_streams(video_path)

        # 2. 常に最適化を実行
        try:
            audio, stats = self._optimize_audio(video_path, audio_info, "standard")  # 常に標準戦略を使用
            self.optimization_stats.append(stats)
            return audio, stats
        except Exception as e:
            logger.warning(f"最適化失敗、フォールバック: {e}")
            # フォールバック
            import librosa

            audio, _ = librosa.load(str(video_path), sr=16000, mono=True)
            return audio, {"optimized": False, "reason": str(e)}

    def _analyze_audio_streams(self, video_path: Path) -> Dict[str, Any]:
        """FFprobeで音声ストリーム情報を取得"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate",
            "-of",
            "json",
            str(video_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            data = json.loads(result.stdout)

            if data.get("streams") and len(data["streams"]) > 0:
                stream = data["streams"][0]
                return {
                    "codec": stream.get("codec_name", "unknown"),
                    "sample_rate": int(stream.get("sample_rate", 48000)),
                    "channels": int(stream.get("channels", 2)),
                    "bit_rate": int(stream.get("bit_rate", 0)) if stream.get("bit_rate") else None,
                    "duration": self._get_duration(video_path),
                }
            else:
                raise ValueError("音声ストリームが見つかりません")

        except subprocess.CalledProcessError as e:
            logger.warning(f"ffprobeエラー: {e}")
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析エラー: {e}")
        except Exception as e:
            logger.warning(f"音声分析失敗: {e}")

        # デフォルト値
        return {"codec": "unknown", "sample_rate": 48000, "channels": 2, "bit_rate": None, "duration": 0}

    def _get_duration(self, video_path: Path) -> float:
        """動画の長さを取得（秒）"""
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"duration取得失敗: {e}")
            return 0

    # この関数は削除（常に最適化を実行するため不要）

    def _optimize_audio(
        self, video_path: Path, audio_info: Dict[str, Any], strategy: str
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """音声を最適化"""

        # ユニークな一時ファイル
        temp_path = Path(tempfile.gettempdir()) / f"textffcut_{uuid.uuid4()}.wav"

        start_time = time.time()
        original_size = video_path.stat().st_size

        try:
            # 変換コマンド構築
            cmd = self._build_conversion_command(video_path, temp_path, audio_info, strategy)

            # 実行（タイムアウト付き）
            timeout = max(300, audio_info["duration"] * 0.1)  # 最大5分または動画長の10%
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=timeout)

            # 最適化後の音声を読み込み
            import librosa

            audio, _ = librosa.load(str(temp_path), sr=16000, mono=True)

            # 統計情報
            optimized_size = temp_path.stat().st_size
            conversion_time = time.time() - start_time
            actual_reduction = (1 - optimized_size / original_size) * 100

            stats = {
                "optimized": True,
                "strategy": strategy,
                "original_size_mb": original_size / (1024**2),
                "optimized_size_mb": optimized_size / (1024**2),
                "reduction_percent": actual_reduction,
                "conversion_time_sec": conversion_time,
                "audio_info": audio_info,
            }

            logger.info(
                f"""
            音声最適化完了:
            - 削減率: {actual_reduction:.1f}%
            - 変換時間: {conversion_time:.1f}秒
            - 戦略: {strategy}
            """
            )

            return audio, stats

        except subprocess.TimeoutExpired:
            logger.error(f"音声変換タイムアウト（{timeout}秒）")
            raise
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpegエラー: {e.stderr}")
            raise
        finally:
            # 一時ファイル削除
            temp_path.unlink(missing_ok=True)

    def _build_conversion_command(
        self, input_path: Path, output_path: Path, audio_info: Dict[str, Any], strategy: str
    ) -> list:
        """変換コマンドを構築"""

        base_cmd = [
            "ffmpeg",
            "-i",
            str(input_path),
            "-vn",  # 映像除外
            "-ar",
            str(self.target_sample_rate),
            "-ac",
            "1",  # モノラル
        ]

        if strategy == "aggressive":
            # より積極的な圧縮
            base_cmd.extend(
                [
                    "-acodec",
                    "pcm_u8",  # 8bit（品質劣化リスク）
                    "-af",
                    "volume=1.5,highpass=f=200,lowpass=f=8000",  # 周波数帯域制限
                ]
            )
        else:
            # 標準的な最適化
            base_cmd.extend(
                [
                    "-acodec",
                    "pcm_s16le",  # 16bit
                ]
            )

        # 特殊なコーデックへの対応
        if audio_info["codec"] in ["dts", "ac3", "eac3"]:
            base_cmd.extend(["-strict", "-2"])

        base_cmd.extend(["-y", str(output_path)])

        return base_cmd

    def _estimate_conversion_time(self, duration_sec: float, file_size_mb: float) -> float:
        """変換時間を推定（秒）"""
        # 経験則: 1分の音声につき約2秒の変換時間
        # ファイルサイズが大きいほど時間がかかる
        base_time = duration_sec * 0.033  # 30倍速
        size_factor = min(file_size_mb / 100, 2.0)  # 100MB以上は係数2

        return base_time * size_factor

    def prepare_audio_for_api(self, video_path: Path, target_bitrate: str = "32k") -> Path:
        """API送信用に音声を圧縮"""

        video_path = Path(video_path)
        output_path = video_path.with_suffix(f".api_{target_bitrate}.mp3")

        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-vn",
            "-ar",
            "16000",  # API側でも変換されるので事前に削減
            "-ac",
            "1",
            "-ab",
            target_bitrate,
            "-f",
            "mp3",
            "-y",  # 上書き
            str(output_path),
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)

            # ファイルサイズチェック
            if output_path.stat().st_size > 25 * 1024 * 1024:
                if target_bitrate != "24k":
                    # より低いビットレートで再試行
                    output_path.unlink()
                    return self.prepare_audio_for_api(video_path, "24k")
                else:
                    raise ValueError("ファイルが大きすぎます。より短い動画に分割してください。")

            return output_path

        except subprocess.CalledProcessError as e:
            logger.error(f"API用音声圧縮エラー: {e.stderr}")
            raise

    def get_optimization_summary(self) -> Dict[str, Any]:
        """最適化の統計サマリー"""
        if not self.optimization_stats:
            return {"total_optimizations": 0}

        total_original = sum(s["original_size_mb"] for s in self.optimization_stats)
        total_optimized = sum(s["optimized_size_mb"] for s in self.optimization_stats)
        total_time = sum(s["conversion_time_sec"] for s in self.optimization_stats)

        return {
            "total_optimizations": len(self.optimization_stats),
            "total_reduction_mb": total_original - total_optimized,
            "average_reduction_percent": (1 - total_optimized / total_original) * 100 if total_original > 0 else 0,
            "total_conversion_time_sec": total_time,
            "details": self.optimization_stats,
        }
