"""
サブプロセス分離による文字起こし処理

別プロセスで文字起こしを実行することで、
プロセス終了時に確実にメモリを解放し、メモリリーク問題を解決する。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from typing import Any

from core.transcription import Transcriber, TranscriptionResult
from utils.logging import logger


class SubprocessTranscriber(Transcriber):
    """
    サブプロセス分離による文字起こし処理クラス

    文字起こし処理を別プロセスで実行し、
    処理完了後にプロセスを終了することで完全なメモリクリーンアップを実現。
    """

    def __init__(self, config):
        super().__init__(config)
        self.enable_subprocess_isolation = config.transcription.isolation_mode == "subprocess"
        logger.info(f"サブプロセス分離モード: {self.enable_subprocess_isolation}")

    def transcribe(
        self,
        video_path: str,
        model_size: str | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
        use_cache: bool = True,
        save_cache: bool = True,
        skip_alignment: bool = False,
    ) -> TranscriptionResult:
        """
        サブプロセス分離された文字起こし処理
        """

        # サブプロセス分離が無効な場合は親クラスの処理を実行
        if not self.enable_subprocess_isolation:
            return super().transcribe(video_path, model_size, progress_callback, use_cache, save_cache, skip_alignment)

        logger.info("サブプロセス分離による文字起こし処理を開始")

        # キャッシュ確認
        if use_cache:
            cache_path = self.get_cache_path(video_path, model_size or self.config.transcription.model_size)
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result

        # 作業ディレクトリを作成
        work_dir = tempfile.mkdtemp(prefix="textffcut_subprocess_")

        try:
            # 設定をJSON形式で保存
            config_data = {
                "video_path": video_path,
                "model_size": model_size or self.config.transcription.model_size,
                "use_cache": False,  # ワーカープロセスではキャッシュ読み込みしない
                "save_cache": False,  # ワーカープロセスではキャッシュ保存しない
                "config": self._serialize_config(),
            }

            config_path = os.path.join(work_dir, "config.json")
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=2)

            # 結果ファイルのパス
            result_path = os.path.join(work_dir, "result.json")

            # ワーカープロセスを実行
            cmd = [sys.executable, "worker_transcribe.py", config_path]  # 現在のPythonインタープリタ

            logger.info(f"ワーカープロセスを起動: {' '.join(cmd)}")

            # プロセスを実行
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, universal_newlines=True
            )

            # プログレス監視
            start_time = time.time()
            last_progress = 0.0

            try:
                # 標準出力を監視してプログレスを更新
                for line in process.stdout:
                    line = line.strip()

                    # プログレス情報を抽出
                    if line.startswith("PROGRESS:"):
                        try:
                            parts = line.split("|", 1)
                            progress = float(parts[0].split(":")[1])
                            message = parts[1] if len(parts) > 1 else ""

                            if progress_callback:
                                progress_callback(progress, message)
                            last_progress = progress
                        except Exception as e:
                            logger.warning(f"プログレス解析エラー: {e}, 行: {line}")

                    # エラーチェック
                    elif line.startswith("ERROR:"):
                        logger.error(f"ワーカープロセスエラー: {line}")

                    # その他のログ
                    elif line:
                        logger.debug(f"ワーカーログ: {line}")

                # プロセスの終了を待つ
                return_code = process.wait()

                if return_code != 0:
                    # エラー出力を取得
                    stderr = process.stderr.read()
                    logger.error(f"ワーカープロセスが異常終了 (exit code: {return_code})")
                    logger.error(f"エラー出力:\n{stderr}")

                    # Exit code -9はSIGKILL（通常OOM）
                    if return_code == -9:
                        error_details = "メモリ不足により処理が強制終了されました。\nより小さなモデル（medium等）の使用を推奨します。"
                        raise MemoryError(error_details)

                    # エラー結果ファイルがある場合は読み込む
                    error_details = f"Exit code: {return_code}\n"
                    if os.path.exists(result_path):
                        try:
                            with open(result_path) as f:
                                error_result = json.load(f)
                            if not error_result.get("success", True):
                                error_msg = error_result.get("error", "不明なエラー")
                                error_traceback = error_result.get("traceback", "")
                                error_details += f"エラー詳細: {error_msg}\n"
                                if error_traceback:
                                    error_details += f"トレースバック:\n{error_traceback}"
                                logger.error(f"ワーカーエラー詳細:\n{error_details}")
                        except Exception as e:
                            logger.error(f"エラー結果の読み込みに失敗: {e}")

                    raise RuntimeError(
                        f"ワーカープロセスが異常終了しました (exit code: {return_code})\n{error_details}"
                    )

                # 結果を読み込み
                if os.path.exists(result_path):
                    with open(result_path) as f:
                        result_data = json.load(f)

                    result = TranscriptionResult.from_dict(result_data)

                    # キャッシュに保存
                    if save_cache:
                        cache_path = self.get_cache_path(video_path, result.model_size)
                        self.save_to_cache(result, cache_path)

                    logger.info(
                        f"サブプロセス分離による文字起こし処理が完了 (処理時間: {time.time() - start_time:.1f}秒)"
                    )
                    return result
                else:
                    raise RuntimeError("ワーカープロセスから結果を取得できませんでした")

            except subprocess.TimeoutExpired:
                logger.error("ワーカープロセスがタイムアウトしました")
                process.kill()
                raise RuntimeError("文字起こし処理がタイムアウトしました")
            except Exception as e:
                # エラー時はプロセスを強制終了
                try:
                    process.kill()
                except:
                    pass
                raise e

        finally:
            # 作業ディレクトリをクリーンアップ
            try:
                shutil.rmtree(work_dir)
            except:
                pass

    def _serialize_config(self) -> dict[str, Any]:
        """設定をシリアライズ"""
        # デフォルト値
        DEFAULT_SAMPLE_RATE = 16000
        DEFAULT_NUM_WORKERS = 3
        DEFAULT_BATCH_SIZE = 16

        return {
            "transcription": {
                "use_api": self.config.transcription.use_api,
                "api_provider": self.config.transcription.api_provider,
                "api_key": self.config.transcription.api_key,
                "model_size": self.config.transcription.model_size,
                "language": self.config.transcription.language,
                "compute_type": self.config.transcription.compute_type,
                "sample_rate": DEFAULT_SAMPLE_RATE,
                "num_workers": DEFAULT_NUM_WORKERS,
                "batch_size": DEFAULT_BATCH_SIZE,
                "adaptive_workers": True,  # デフォルトで有効
                "isolation_mode": "none",  # ワーカープロセス内では分離を無効化
            }
        }
