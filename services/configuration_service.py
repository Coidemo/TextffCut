"""
設定管理サービス

アプリケーション設定、検証、パス生成などの設定関連ビジネスロジックを提供。
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.constants import ErrorMessages, MemoryEstimates
from utils.file_utils import ensure_directory

from .base import BaseService, ServiceResult, ValidationError


class ConfigurationService(BaseService):
    """アプリケーション設定の管理

    責任:
    - API料金の計算
    - モデル設定の検証
    - 出力パスの生成
    - プロジェクト設定の管理
    """

    # API料金定数（2025年5月時点）
    API_COST_PER_MINUTE = 0.006  # $0.006/分
    CURRENCY_RATE = 150  # 1USD = 150円（概算）

    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド（BaseServiceの要求を満たす）"""
        action = kwargs.get("action", "calculate_api_cost")

        if action == "calculate_api_cost":
            return self.calculate_api_cost(**kwargs)
        elif action == "validate_model_settings":
            return self.validate_model_settings(**kwargs)
        elif action == "get_output_path":
            return self.get_output_path(**kwargs)
        else:
            return self.create_error_result(f"不明なアクション: {action}", "ValidationError")

    def calculate_api_cost(self, duration_minutes: float, currency: str = "JPY") -> ServiceResult:
        """API使用料金の計算

        Args:
            duration_minutes: 動画の長さ（分）
            currency: 通貨（JPY or USD）

        Returns:
            ServiceResult: 料金情報
        """
        try:
            if duration_minutes < 0:
                raise ValidationError("動画の長さは0以上である必要があります")

            # USD計算
            cost_usd = duration_minutes * self.API_COST_PER_MINUTE

            # 通貨変換
            if currency.upper() == "JPY":
                cost = cost_usd * self.CURRENCY_RATE
                symbol = "円"
            else:
                cost = cost_usd
                symbol = "$"

            # 料金情報
            cost_info = {
                "duration_minutes": duration_minutes,
                "cost": cost,
                "cost_usd": cost_usd,
                "cost_jpy": cost_usd * self.CURRENCY_RATE,
                "currency": currency.upper(),
                "symbol": symbol,
                "rate_per_minute": self.API_COST_PER_MINUTE,
                "exchange_rate": self.CURRENCY_RATE,
            }

            self.logger.info(f"API料金計算: {duration_minutes:.1f}分 → " f"{cost:.2f}{symbol} (${cost_usd:.3f})")

            return self.create_success_result(data=cost_info, metadata={"calculation_date": datetime.now().isoformat()})

        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"料金計算エラー: {e}", exc_info=True)
            return self.create_error_result(f"料金計算中にエラーが発生しました: {str(e)}", "CalculationError")

    def validate_model_settings(
        self, model_size: str, use_api: bool, available_memory_gb: float | None = None
    ) -> ServiceResult:
        """モデル設定の検証

        Args:
            model_size: モデルサイズ
            use_api: API使用フラグ
            available_memory_gb: 利用可能メモリ（GB）

        Returns:
            ServiceResult: 検証結果と推奨事項
        """
        try:
            validation_result: dict[str, Any] = {
                "valid": True,
                "warnings": [],
                "recommendations": [],
                "memory_status": None,
            }

            if use_api:
                # APIモードの検証
                if model_size != "whisper-1":
                    validation_result["warnings"].append("APIモードではwhisper-1モデルのみ使用可能です")
                    validation_result["valid"] = False
            else:
                # ローカルモードの検証
                valid_models = ["base", "small", "medium", "large-v3"]
                if model_size not in valid_models:
                    validation_result["warnings"].append(f"無効なモデルサイズ: {model_size}")
                    validation_result["valid"] = False

                # メモリチェック（large-v3の場合）
                if model_size == "large-v3" and available_memory_gb is not None:
                    if available_memory_gb < MemoryEstimates.MINIMUM_MEMORY_GB:
                        validation_result["warnings"].append(
                            ErrorMessages.MEMORY_LIMIT_INFO.format(available_memory_gb)
                        )
                        validation_result["recommendations"].append("mediumモデルの使用を推奨します")
                        validation_result["memory_status"] = "critical"
                    elif available_memory_gb < MemoryEstimates.LOW_MEMORY_GB:
                        validation_result["warnings"].append(
                            ErrorMessages.LOW_MEMORY_WARNING.format(available_memory_gb)
                        )
                        validation_result["memory_status"] = "warning"
                    else:
                        validation_result["memory_status"] = "ok"

            # 推奨事項の追加
            if use_api:
                validation_result["recommendations"].append("APIモードは高速で安定していますが、料金が発生します")
            else:
                if model_size == "base":
                    validation_result["recommendations"].append("baseモデルは高速ですが、精度が低い可能性があります")
                elif model_size == "large-v3":
                    validation_result["recommendations"].append("large-v3は最高精度ですが、処理時間が長くなります")

            return self.create_success_result(
                data=validation_result,
                metadata={"model_size": model_size, "use_api": use_api, "available_memory_gb": available_memory_gb},
            )

        except Exception as e:
            self.logger.error(f"モデル設定検証エラー: {e}", exc_info=True)
            return self.create_error_result(f"モデル設定の検証中にエラーが発生しました: {str(e)}", "ValidationError")

    def get_output_path(
        self,
        video_path: str,
        process_type: str,
        output_format: str,
        custom_output_dir: str | None = None,
        include_timestamp: bool = False,
    ) -> ServiceResult:
        """出力パスの生成

        Args:
            video_path: 元動画のパス
            process_type: 処理タイプ（clip, silence, both）
            output_format: 出力形式（fcpxml, xmeml, mp4など）
            custom_output_dir: カスタム出力ディレクトリ
            include_timestamp: タイムスタンプを含めるか

        Returns:
            ServiceResult: 生成された出力パス
        """
        try:
            video_file = Path(video_path)
            if not video_file.exists():
                raise ValidationError(f"動画ファイルが見つかりません: {video_path}")

            # 出力ディレクトリの決定
            if custom_output_dir:
                output_dir = Path(custom_output_dir)
            else:
                # Docker環境の判定
                is_docker = os.path.exists("/.dockerenv")
                if is_docker:
                    output_dir = Path("/app/videos")
                else:
                    output_dir = video_file.parent / "output"

            # ディレクトリを作成
            ensure_directory(output_dir)

            # ベースファイル名の生成
            base_name = video_file.stem

            # プロセスタイプのサフィックス
            process_suffix = self._get_process_suffix(process_type)

            # タイムスタンプ（オプション）
            timestamp = ""
            if include_timestamp:
                timestamp = f"_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # 拡張子の決定
            extension = self._get_extension(output_format)

            # ファイル名の組み立て
            output_name = f"{base_name}{process_suffix}{timestamp}{extension}"
            output_path = output_dir / output_name

            # 重複チェックと連番付与
            counter = 1
            while output_path.exists():
                output_name = f"{base_name}{process_suffix}{timestamp}_{counter}{extension}"
                output_path = output_dir / output_name
                counter += 1

            path_info = {
                "output_path": str(output_path),
                "output_dir": str(output_dir),
                "file_name": output_name,
                "base_name": base_name,
                "process_type": process_type,
                "format": output_format,
                "is_docker": is_docker,
            }

            self.logger.info(f"出力パス生成: {output_name} " f"(タイプ: {process_type}, 形式: {output_format})")

            return self.create_success_result(data=path_info, metadata={"path_generated": True})

        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"出力パス生成エラー: {e}", exc_info=True)
            return self.create_error_result(f"出力パスの生成中にエラーが発生しました: {str(e)}", "PathGenerationError")

    def get_project_settings(
        self, video_path: str, custom_project_name: str | None = None, custom_event_name: str | None = None
    ) -> ServiceResult:
        """プロジェクト設定の生成

        Args:
            video_path: 動画ファイルパス
            custom_project_name: カスタムプロジェクト名
            custom_event_name: カスタムイベント名

        Returns:
            ServiceResult: プロジェクト設定
        """
        try:
            video_file = Path(video_path)

            # デフォルト値の生成
            default_project_name = f"{video_file.stem}_編集"
            default_event_name = datetime.now().strftime("%Y-%m-%d")

            # プロジェクト設定
            project_settings = {
                "project_name": custom_project_name or default_project_name,
                "event_name": custom_event_name or default_event_name,
                "source_file": video_file.name,
                "created_date": datetime.now().isoformat(),
            }

            return self.create_success_result(
                data=project_settings,
                metadata={
                    "defaults_used": {
                        "project_name": custom_project_name is None,
                        "event_name": custom_event_name is None,
                    }
                },
            )

        except Exception as e:
            self.logger.error(f"プロジェクト設定生成エラー: {e}", exc_info=True)
            return self.create_error_result(
                f"プロジェクト設定の生成中にエラーが発生しました: {str(e)}", "SettingsError"
            )

    def _get_process_suffix(self, process_type: str) -> str:
        """処理タイプに応じたサフィックスを取得

        Args:
            process_type: 処理タイプ

        Returns:
            サフィックス文字列
        """
        suffix_map = {
            "clip": "_clipped",
            "silence": "_nosilence",
            "both": "_clipped_nosilence",
            "full": "_processed",
            "original": "",
        }
        return suffix_map.get(process_type, "_processed")

    def _get_extension(self, output_format: str) -> str:
        """出力形式に応じた拡張子を取得

        Args:
            output_format: 出力形式

        Returns:
            拡張子（ドット付き）
        """
        extension_map = {
            "fcpxml": ".fcpxml",
            "xmeml": ".xml",
            "edl": ".edl",
            "mp4": ".mp4",
            "mov": ".mov",
            "json": ".json",
            "srt": ".srt",
            "vtt": ".vtt",
        }
        return extension_map.get(output_format.lower(), ".xml")

    def validate_api_key(self, api_key: str) -> ServiceResult:
        """APIキーの基本的な検証

        Args:
            api_key: 検証するAPIキー

        Returns:
            ServiceResult: 検証結果
        """
        try:
            if not api_key:
                raise ValidationError("APIキーが設定されていません")

            # 基本的な形式チェック
            if not api_key.startswith(("sk-", "sess-")):
                raise ValidationError("APIキーの形式が正しくありません。" "'sk-'または'sess-'で始まる必要があります")

            if len(api_key) < 20:
                raise ValidationError("APIキーが短すぎます")

            # マスク処理したキーを返す
            masked_key = f"{api_key[:8]}...{api_key[-4:]}"

            return self.create_success_result(
                data={"valid": True, "masked_key": masked_key}, metadata={"key_length": len(api_key)}
            )

        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"APIキー検証エラー: {e}", exc_info=True)
            return self.create_error_result(f"APIキーの検証中にエラーが発生しました: {str(e)}", "ValidationError")
