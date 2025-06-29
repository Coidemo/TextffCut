"""
アライメント診断モジュール

アライメント処理に特化した診断機能を提供し、
最適なバッチサイズとメモリ使用量を推定する。
"""

import gc
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

import psutil

from config import Config
from core.constants import BatchSizeLimits, MemoryEstimates, MemoryThresholds
from core.memory_monitor import MemoryMonitor
from utils.logging import get_logger

if TYPE_CHECKING:
    from core.transcription_result import TranscriptionResultV2, TranscriptionSegmentV2

logger = get_logger(__name__)


class DiagnosticLevel(Enum):
    """診断レベル"""

    OK = "ok"  # 正常
    WARNING = "warning"  # 警告
    ERROR = "error"  # エラー
    CRITICAL = "critical"  # 致命的


@dataclass
class SegmentDiagnostic:
    """セグメント単位の診断結果"""

    segment_id: str
    level: DiagnosticLevel
    message: str
    details: dict[str, Any] | None = None

    def is_ok(self) -> bool:
        """正常かどうか"""
        return self.level == DiagnosticLevel.OK

    def is_warning_or_worse(self) -> bool:
        """警告以上かどうか"""
        return self.level in [DiagnosticLevel.WARNING, DiagnosticLevel.ERROR, DiagnosticLevel.CRITICAL]


@dataclass
class DiagnosticResult:
    """診断結果を格納するデータクラス"""

    optimal_batch_size: int
    model_memory_usage_mb: float
    base_memory_percent: float
    estimated_memory_per_batch: float
    available_memory_gb: float
    segment_count: int
    recommendations: list[str]
    warnings: list[str]

    def get_summary(self) -> str:
        """診断結果のサマリーを取得"""
        summary_lines = [
            "診断結果サマリー:",
            f"  最適バッチサイズ: {self.optimal_batch_size}",
            f"  モデルメモリ使用量: {self.model_memory_usage_mb:.1f}MB",
            f"  ベースメモリ使用率: {self.base_memory_percent:.1f}%",
            f"  バッチあたりメモリ: {self.estimated_memory_per_batch:.1f}MB",
            f"  利用可能メモリ: {self.available_memory_gb:.1f}GB",
            f"  セグメント数: {self.segment_count}",
        ]

        if self.recommendations:
            summary_lines.append("推奨事項:")
            for rec in self.recommendations:
                summary_lines.append(f"  - {rec}")

        if self.warnings:
            summary_lines.append("警告:")
            for warn in self.warnings:
                summary_lines.append(f"  - {warn}")

        return "\n".join(summary_lines)


class AlignmentDiagnostics:
    """アライメント処理専用の診断クラス"""

    # モデルサイズ別のメモリ使用量推定値（MB）
    MODEL_MEMORY_ESTIMATES = {
        "base": 150,
        "small": 200,
        "medium": 300,
        "large": 400,
        "large-v3": 500,
        "whisper-1": 100,  # API使用時
    }

    # モデルサイズ別のセグメント処理能力（1GBあたり）
    SEGMENTS_PER_GB = {
        "base": 150,
        "small": 120,
        "medium": 100,
        "large": 75,
        "large-v3": 50,
        "whisper-1": 200,  # API使用時
    }

    def __init__(self, model_size: str, config: Config) -> None:
        """
        初期化

        Args:
            model_size: Whisperモデルサイズ
            config: アプリケーション設定
        """
        self.model_size = model_size
        self.config = config
        self.memory_monitor = MemoryMonitor()

        # デフォルト値の設定
        if model_size not in self.MODEL_MEMORY_ESTIMATES:
            logger.warning(f"Unknown model size: {model_size}, using 'base' estimates")
            self.model_size = "base"

    def run_diagnostics(self, segment_count: int, language: str, test_alignment: bool = True) -> DiagnosticResult:
        """
        診断フェーズを実行

        Args:
            segment_count: 処理するセグメント数
            language: 言語コード
            test_alignment: 実際にアライメントモデルをロードしてテストするか

        Returns:
            DiagnosticResult: 診断結果
        """
        logger.info(f"アライメント診断開始: {segment_count}セグメント, {self.model_size}モデル")

        # 初期メモリ状態を記録
        base_memory_percent = self.memory_monitor.get_memory_usage()
        available_memory_gb = psutil.virtual_memory().available / (1024**3)

        logger.info(f"診断開始時 - メモリ使用率: {base_memory_percent:.1f}%, 利用可能: {available_memory_gb:.1f}GB")

        # モデルメモリ使用量を測定または推定
        if test_alignment and base_memory_percent < MemoryThresholds.COMFORTABLE:
            model_memory_mb = self._measure_model_memory_usage(language)
        else:
            model_memory_mb = self._estimate_model_memory_usage()
            logger.info(f"メモリ制約によりモデルロードをスキップ、推定値を使用: {model_memory_mb}MB")

        # 最適なバッチサイズを計算
        optimal_batch_size = self._calculate_optimal_batch_size(
            available_memory_gb, segment_count, model_memory_mb, base_memory_percent
        )

        # バッチあたりのメモリ使用量を推定
        estimated_memory_per_batch = self._estimate_memory_per_batch(optimal_batch_size, model_memory_mb)

        # 推奨事項と警告を生成
        recommendations, warnings = self._generate_recommendations(
            available_memory_gb, segment_count, optimal_batch_size, base_memory_percent
        )

        result = DiagnosticResult(
            optimal_batch_size=optimal_batch_size,
            model_memory_usage_mb=model_memory_mb,
            base_memory_percent=base_memory_percent,
            estimated_memory_per_batch=estimated_memory_per_batch,
            available_memory_gb=available_memory_gb,
            segment_count=segment_count,
            recommendations=recommendations,
            warnings=warnings,
        )

        logger.info(result.get_summary())

        return result

    def estimate_optimal_batch_size(self, available_memory_gb: float, segment_count: int) -> int:
        """
        利用可能メモリとセグメント数から最適なバッチサイズを推定

        Args:
            available_memory_gb: 利用可能メモリ（GB）
            segment_count: セグメント数

        Returns:
            最適なバッチサイズ
        """
        # 現在のメモリ使用率
        current_memory_percent = self.memory_monitor.get_memory_usage()

        # モデルメモリ使用量の推定
        model_memory_mb = self._estimate_model_memory_usage()

        return self._calculate_optimal_batch_size(
            available_memory_gb, segment_count, model_memory_mb, current_memory_percent
        )

    def _measure_model_memory_usage(self, language: str) -> float:
        """
        アライメントモデルの実際のメモリ使用量を測定

        Args:
            language: 言語コード

        Returns:
            メモリ使用量（MB）
        """
        try:
            from core.alignment_processor import AlignmentProcessor

            logger.info("アライメントモデルのメモリ使用量を測定中...")

            # 測定前のメモリ使用量
            gc.collect()
            time.sleep(0.5)
            before_memory = self.memory_monitor.get_memory_usage()

            # テスト用のプロセッサーを作成（最小バッチサイズ）
            test_processor = AlignmentProcessor(self.config, batch_size=1)

            # モデルをロード
            test_processor._load_align_model(language)

            # 測定後のメモリ使用量
            time.sleep(0.5)
            after_memory = self.memory_monitor.get_memory_usage()

            # メモリ増加量を計算
            memory_increase_percent = after_memory - before_memory
            total_memory_mb = psutil.virtual_memory().total / (1024**2)
            model_memory_mb = (memory_increase_percent / 100) * total_memory_mb

            # クリーンアップ
            del test_processor
            gc.collect()

            logger.info(f"測定完了: モデルメモリ使用量 = {model_memory_mb:.1f}MB ({memory_increase_percent:.1f}%増加)")

            return max(model_memory_mb, self.MODEL_MEMORY_ESTIMATES.get(self.model_size, 300))

        except Exception as e:
            logger.warning(f"モデルメモリ測定中にエラー: {e}")
            return self._estimate_model_memory_usage()

    def _estimate_model_memory_usage(self) -> float:
        """モデルメモリ使用量の推定値を返す"""
        return self.MODEL_MEMORY_ESTIMATES.get(self.model_size, 300)

    def _calculate_optimal_batch_size(
        self, _available_memory_gb: float, segment_count: int, model_memory_mb: float, base_memory_percent: float
    ) -> int:
        """
        最適なバッチサイズを計算

        Args:
            available_memory_gb: 利用可能メモリ（GB）
            segment_count: セグメント数
            model_memory_mb: モデルのメモリ使用量（MB）
            base_memory_percent: ベースメモリ使用率（%）

        Returns:
            最適なバッチサイズ
        """
        # 利用可能なメモリ容量を計算（目標使用率まで）
        target_memory_percent = MemoryThresholds.TARGET
        available_memory_percent = target_memory_percent - base_memory_percent

        if available_memory_percent <= 0:
            logger.warning(f"メモリ不足: 現在{base_memory_percent:.1f}%使用中")
            return BatchSizeLimits.MINIMUM

        # 利用可能メモリ（MB）
        total_memory_mb = psutil.virtual_memory().total / (1024**2)
        available_memory_mb = (available_memory_percent / 100) * total_memory_mb

        # モデル以外に使用可能なメモリ
        processing_memory_mb = available_memory_mb - model_memory_mb

        if processing_memory_mb <= 0:
            logger.warning(f"処理用メモリ不足: モデルだけで{model_memory_mb:.1f}MB必要")
            return BatchSizeLimits.MINIMUM

        # セグメント処理能力から計算
        segments_per_gb = self.SEGMENTS_PER_GB.get(self.model_size, 100)
        max_segments_in_memory = int((processing_memory_mb / 1024) * segments_per_gb)

        # バッチサイズの計算（10回のバッチ処理を想定）
        optimal_batch_size = min(max_segments_in_memory // 10, segment_count // 5)  # 最低5バッチに分割

        # 制限の適用
        optimal_batch_size = max(BatchSizeLimits.MINIMUM, min(BatchSizeLimits.MAXIMUM, optimal_batch_size))

        # モデルサイズに応じた上限
        if self.model_size == "large-v3":
            optimal_batch_size = min(optimal_batch_size, BatchSizeLimits.DIAGNOSTIC_MAX)
        elif self.model_size in ["large", "medium"]:
            optimal_batch_size = min(optimal_batch_size, BatchSizeLimits.DEFAULT)

        logger.info(
            f"バッチサイズ計算: メモリ{available_memory_mb:.0f}MB, "
            f"モデル{model_memory_mb:.0f}MB → バッチサイズ{optimal_batch_size}"
        )

        return optimal_batch_size

    def _estimate_memory_per_batch(self, batch_size: int, _model_memory_mb: float) -> float:
        """
        バッチあたりのメモリ使用量を推定

        Args:
            batch_size: バッチサイズ
            model_memory_mb: モデルのメモリ使用量（MB）

        Returns:
            バッチあたりのメモリ使用量（MB）
        """
        # 基本的な推定: セグメントあたり5-10MB
        base_per_segment = 7.0

        # モデルサイズに応じた調整
        if self.model_size == "large-v3":
            base_per_segment = 10.0
        elif self.model_size == "large":
            base_per_segment = 8.0
        elif self.model_size in ["base", "small"]:
            base_per_segment = 5.0

        return batch_size * base_per_segment

    def _generate_recommendations(
        self, available_memory_gb: float, segment_count: int, optimal_batch_size: int, base_memory_percent: float
    ) -> tuple[list[str], list[str]]:
        """
        推奨事項と警告を生成

        Args:
            available_memory_gb: 利用可能メモリ（GB）
            segment_count: セグメント数
            optimal_batch_size: 計算されたバッチサイズ
            base_memory_percent: ベースメモリ使用率

        Returns:
            (推奨事項のリスト, 警告のリスト)
        """
        recommendations = []
        warnings = []

        # メモリ不足の警告
        if available_memory_gb < MemoryEstimates.LOW_MEMORY_GB:
            warnings.append(f"メモリ不足: {available_memory_gb:.1f}GB。" f"処理が遅くなる可能性があります。")
            recommendations.append("他のアプリケーションを終了してメモリを解放してください")

        # large-v3モデルの警告
        if self.model_size == "large-v3" and available_memory_gb < MemoryEstimates.MINIMUM_MEMORY_GB:
            warnings.append(f"large-v3モデルには{MemoryEstimates.MINIMUM_MEMORY_GB}GB以上のメモリを推奨")
            recommendations.append("mediumモデルの使用を検討してください")

        # バッチサイズが小さい場合の警告
        if optimal_batch_size <= BatchSizeLimits.EMERGENCY:
            warnings.append(f"バッチサイズが非常に小さい({optimal_batch_size})ため、処理に時間がかかります")

        # 大量セグメントの警告
        if segment_count > 1000:
            estimated_time = (segment_count / optimal_batch_size) * 2  # 概算処理時間（分）
            if estimated_time > 30:
                warnings.append(f"処理時間が長くなる可能性があります（推定{estimated_time:.0f}分）")
                recommendations.append("必要に応じて処理を分割することを検討してください")

        # ベースメモリが高い場合
        if base_memory_percent > MemoryThresholds.HIGH:
            warnings.append(f"開始時のメモリ使用率が高い: {base_memory_percent:.1f}%")
            recommendations.append("処理前にメモリを解放することを推奨")

        return recommendations, warnings

    def analyze_segment(
        self, segment: "TranscriptionSegmentV2", _context: dict[str, Any] | None = None
    ) -> SegmentDiagnostic:
        """
        個別セグメントを診断

        Args:
            segment: 診断対象セグメント
            context: 追加のコンテキスト情報

        Returns:
            セグメント診断結果
        """
        # 基本的な検証
        if not segment.text or not segment.text.strip():
            return SegmentDiagnostic(
                segment_id=segment.id,
                level=DiagnosticLevel.ERROR,
                message="テキストが空です",
                details={"text_length": 0},
            )

        # タイムスタンプの検証
        if segment.start < 0 or segment.end <= segment.start:
            return SegmentDiagnostic(
                segment_id=segment.id,
                level=DiagnosticLevel.ERROR,
                message=f"無効なタイムスタンプ: {segment.start}-{segment.end}",
                details={"start": segment.start, "end": segment.end},
            )

        # アライメント情報の検証
        if segment.alignment_completed:
            if not segment.words:
                return SegmentDiagnostic(
                    segment_id=segment.id,
                    level=DiagnosticLevel.WARNING,
                    message="アライメント完了だがword情報がありません",
                    details={"has_words": False},
                )

            # word情報の品質チェック
            valid_words = sum(1 for w in segment.words if hasattr(w, "start") and hasattr(w, "end"))
            if valid_words < len(segment.words) * 0.8:
                return SegmentDiagnostic(
                    segment_id=segment.id,
                    level=DiagnosticLevel.WARNING,
                    message=f"word情報の品質が低い: {valid_words}/{len(segment.words)}",
                    details={"valid_words": valid_words, "total_words": len(segment.words)},
                )

        # セグメントの長さチェック
        duration = segment.end - segment.start
        if duration > 300:  # 5分以上
            return SegmentDiagnostic(
                segment_id=segment.id,
                level=DiagnosticLevel.WARNING,
                message=f"セグメントが長すぎます: {duration:.1f}秒",
                details={"duration": duration},
            )

        # 正常
        return SegmentDiagnostic(
            segment_id=segment.id,
            level=DiagnosticLevel.OK,
            message="正常",
            details={"duration": duration, "text_length": len(segment.text)},
        )

    def analyze_result(self, result: "TranscriptionResultV2") -> dict[str, Any]:
        """
        文字起こし結果全体を診断

        Args:
            result: 文字起こし結果

        Returns:
            診断結果の辞書
        """
        segment_diagnostics = []
        level_counts = dict.fromkeys(DiagnosticLevel, 0)

        # 各セグメントを診断
        for segment in result.segments:
            diag = self.analyze_segment(segment)
            segment_diagnostics.append(diag)
            level_counts[diag.level] += 1

        # 全体的な診断
        total_segments = len(result.segments)

        # 全体レベルの判定
        if level_counts[DiagnosticLevel.CRITICAL] > 0:
            overall_level = DiagnosticLevel.CRITICAL
        elif level_counts[DiagnosticLevel.ERROR] > total_segments * 0.1:
            overall_level = DiagnosticLevel.ERROR
        elif level_counts[DiagnosticLevel.WARNING] > total_segments * 0.3:
            overall_level = DiagnosticLevel.WARNING
        else:
            overall_level = DiagnosticLevel.OK

        return {
            "overall_level": overall_level.value,
            "level_counts": {level.value: count for level, count in level_counts.items()},
            "segment_diagnostics": [
                {"segment_id": d.segment_id, "level": d.level.value, "message": d.message, "details": d.details}
                for d in segment_diagnostics
                if d.level != DiagnosticLevel.OK  # OKは省略
            ],
            "summary": {
                "total_segments": total_segments,
                "ok_segments": level_counts[DiagnosticLevel.OK],
                "warning_segments": level_counts[DiagnosticLevel.WARNING],
                "error_segments": level_counts[DiagnosticLevel.ERROR],
                "critical_segments": level_counts[DiagnosticLevel.CRITICAL],
            },
        }

    def generate_report(self, result: "TranscriptionResultV2", _include_ok: bool = False) -> str:
        """
        診断レポートを生成

        Args:
            result: 文字起こし結果
            include_ok: 正常なセグメントも含めるか

        Returns:
            レポート文字列
        """
        analysis = self.analyze_result(result)

        lines = ["=== アライメント診断レポート ==="]
        lines.append(f"全体評価: {analysis['overall_level']}")
        lines.append("")

        # サマリー
        lines.append("サマリー:")
        summary = analysis["summary"]
        lines.append(f"  総セグメント数: {summary['total_segments']}")
        lines.append(f"  正常: {summary['ok_segments']}")
        if summary["warning_segments"] > 0:
            lines.append(f"  警告: {summary['warning_segments']}")
        if summary["error_segments"] > 0:
            lines.append(f"  エラー: {summary['error_segments']}")
        if summary["critical_segments"] > 0:
            lines.append(f"  致命的: {summary['critical_segments']}")
        lines.append("")

        # 問題のあるセグメント
        if analysis["segment_diagnostics"]:
            lines.append("問題のあるセグメント:")
            for diag in analysis["segment_diagnostics"]:
                lines.append(f"  [{diag['level']}] {diag['segment_id']}: {diag['message']}")
                if diag.get("details"):
                    for key, value in diag["details"].items():
                        lines.append(f"    - {key}: {value}")

        return "\n".join(lines)
