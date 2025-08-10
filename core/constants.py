"""
TextffCut 共通定数定義

コード全体で使用される定数を一元管理します。
マジックナンバーを排除し、保守性を向上させます。
"""

from typing import Final


class ProcessingDefaults:
    """処理全般のデフォルト設定"""

    # 言語設定
    LANGUAGE: Final[str] = "ja"  # デフォルト言語（日本語）

    # ファイル設定
    OUTPUT_FORMAT: Final[str] = "mp4"  # デフォルト出力形式
    TEMP_DIR_PREFIX: Final[str] = "textffcut_"  # 一時ディレクトリプレフィックス

    # タイムアウト設定
    PROCESS_TIMEOUT: Final[int] = 3600  # プロセスタイムアウト（秒）
    SUBPROCESS_TIMEOUT: Final[int] = 300  # サブプロセスタイムアウト（秒）

    # リトライ設定
    MAX_RETRIES: Final[int] = 3  # 最大リトライ回数
    RETRY_DELAY: Final[float] = 1.0  # リトライ遅延（秒）


class ModelSettings:
    """モデル関連の設定"""

    # デフォルトモデル
    DEFAULT_SIZE: Final[str] = "medium"  # デフォルトモデルサイズ
    DEFAULT_COMPUTE_TYPE: Final[str] = "int8"  # デフォルト計算精度

    # モデルサイズ一覧
    AVAILABLE_SIZES: Final[tuple] = ("base", "small", "medium", "large", "large-v3")

    # VAD設定
    VAD_THRESHOLD: Final[float] = 0.5  # Voice Activity Detection閾値
    VAD_MIN_SPEECH_DURATION: Final[float] = 0.1  # 最小発話時間（秒）
    VAD_MIN_SILENCE_DURATION: Final[float] = 0.1  # 最小無音時間（秒）


class ApiSettings:
    """API関連の設定"""

    # OpenAI Whisper API
    OPENAI_API_URL: Final[str] = "https://api.openai.com/v1/audio/transcriptions"
    OPENAI_MODEL: Final[str] = "whisper-1"
    OPENAI_MAX_FILE_SIZE: Final[int] = 25 * 1024 * 1024  # 25MB
    OPENAI_CHUNK_DURATION: Final[int] = 600  # 10分
    OPENAI_COST_PER_MINUTE: Final[float] = 0.006  # $0.006/分（2025年5月時点）

    # リトライ設定
    API_MAX_RETRIES: Final[int] = 3
    API_RETRY_DELAY: Final[float] = 2.0
    API_TIMEOUT: Final[int] = 300  # 5分


class PerformanceSettings:
    """パフォーマンス関連の設定"""

    # 並列処理
    DEFAULT_NUM_WORKERS: Final[int] = 2
    MAX_PARALLEL_JOBS: Final[int] = 4

    # プログレスバー
    PROGRESS_UPDATE_INTERVAL: Final[float] = 0.1  # 更新間隔（秒）

    # キャッシュ
    ENABLE_CACHE: Final[bool] = True
    CACHE_SIZE_MB: Final[int] = 500  # キャッシュサイズ（MB）


class MemoryThresholds:
    """メモリ使用率の閾値定義"""

    # 緊急レベル
    CRITICAL: Final[float] = 90.0  # 即座に処理を制限
    EMERGENCY: Final[float] = 85.0  # 積極的にパラメータを削減

    # 警戒レベル
    HIGH: Final[float] = 80.0  # 注意が必要
    WARNING: Final[float] = 80.0  # 警告レベル

    # 目標・通常レベル
    TARGET: Final[float] = 75.0  # 目標使用率
    COMFORTABLE: Final[float] = 70.0  # 快適な使用率
    NORMAL: Final[float] = 60.0  # 通常使用率

    # 調整判定用
    INCREASE_THRESHOLD: Final[float] = 60.0  # これ以下なら増加可能
    MAINTAIN_RANGE: Final[float] = 5.0  # 目標値からの許容範囲
    VELOCITY_THRESHOLD: Final[float] = 5.0  # 急上昇判定の速度


class BatchSizeLimits:
    """バッチサイズの制限値"""

    MINIMUM: Final[int] = 1
    EMERGENCY: Final[int] = 2  # 緊急時の最小バッチサイズ
    SMALL: Final[int] = 4
    DEFAULT: Final[int] = 8
    MEDIUM: Final[int] = 12
    LARGE: Final[int] = 16
    MAXIMUM: Final[int] = 32

    # 診断用
    DIAGNOSTIC_MAX: Final[int] = 4  # 診断フェーズの最大バッチサイズ

    # テスト用バッチサイズ
    TEST_SIZES: Final[tuple] = (1, 2, 4)


class ChunkSizeLimits:
    """チャンクサイズの制限値（秒）"""

    # 絶対的な制限（Whisperの30秒制約）
    ABSOLUTE_MINIMUM: Final[int] = 5  # 5秒
    EMERGENCY_MINIMUM: Final[int] = 10  # 10秒
    MAXIMUM: Final[int] = 30  # 30秒（Whisperの最大）
    ALIGN_MAXIMUM_MULTIPLIER: Final[float] = 2.0  # アライメント用の最大倍率

    # 調整用の値
    SMALL_ADJUSTMENT: Final[int] = 5  # 5秒
    MEDIUM_ADJUSTMENT: Final[int] = 10  # 10秒
    LARGE_ADJUSTMENT: Final[int] = 15  # 15秒
    ALIGN_MULTIPLIER: Final[float] = 1.5  # アライメントチャンクの基本倍率

    # 診断用
    DIAGNOSTIC_CHUNK: Final[int] = 30  # 診断用チャンクサイズ
    DIAGNOSTIC_COUNT: Final[int] = 3  # 診断チャンク数

    # バッチサイズ決定用の閾値（30秒ベースのため無効化）
    BATCH_SIZE_THRESHOLD_LARGE: Final[int] = 30  # 30秒
    BATCH_SIZE_THRESHOLD_MEDIUM: Final[int] = 20  # 20秒
    BATCH_SIZE_THRESHOLD_SMALL: Final[int] = 10  # 10秒


class WorkerLimits:
    """ワーカー数の制限値"""

    MINIMUM: Final[int] = 1
    MAXIMUM: Final[int] = 4
    DEFAULT: Final[int] = 2


class AudioProcessing:
    """音声処理関連の定数"""

    SAMPLE_RATE: Final[int] = 16000  # サンプリングレート
    CHANNELS: Final[int] = 1  # モノラル
    DIAGNOSTIC_DURATION: Final[int] = 60  # 診断用音声の長さ（秒）
    DEFAULT_DURATION_ESTIMATE: Final[float] = 3600.0  # デフォルトの推定時間（1時間）


class SilenceDetection:
    """無音検出関連の定数"""

    DEFAULT_THRESHOLD: Final[float] = -35.0  # デフォルトの無音判定閾値（dB）
    MIN_SILENCE_DURATION: Final[float] = 0.3  # 最小無音時間（秒）
    MIN_SEGMENT_DURATION: Final[float] = 0.3  # 最小セグメント時間（秒）
    DEFAULT_PAD_START: Final[float] = 0.0  # デフォルトの開始パディング（秒）
    DEFAULT_PAD_END: Final[float] = 0.0  # デフォルトの終了パディング（秒）


class MemoryEstimates:
    """メモリ使用量の推定値"""

    # 利用可能メモリの計算
    SAFETY_MARGIN: Final[float] = 0.5  # 安全マージン（50%）

    # 診断結果のデフォルト値
    DEFAULT_AUDIO_MEMORY: Final[float] = 10.0  # 音声メモリのデフォルト推定値
    DEFAULT_OPTIMAL_BATCH: Final[int] = 4  # 診断失敗時のデフォルトバッチサイズ

    # メモリ不足判定
    LOW_MEMORY_GB: Final[float] = 8.0  # large-v3用の低メモリ判定
    MINIMUM_MEMORY_GB: Final[float] = 12.0  # 推奨最小メモリ


class TranscriptionSegments:
    """文字起こしセグメント関連の定数"""

    SAMPLE_SEGMENTS_COUNT: Final[int] = 10  # 診断用サンプルセグメント数
    DUMMY_SEGMENT_TEXT_REPEAT: Final[int] = 5  # ダミーテキストの繰り返し数
    SEGMENT_DURATION: Final[float] = 10.0  # ダミーセグメントの長さ（秒）


class AdjustmentFactors:
    """パラメータ調整用の係数"""

    # チャンクサイズ調整係数
    EMERGENCY_CHUNK_FACTOR: Final[float] = 0.5  # 緊急時は半分に
    AGGRESSIVE_CHUNK_FACTOR: Final[float] = 0.7

    # バッチサイズ調整係数
    EMERGENCY_BATCH_FACTOR: Final[float] = 0.25
    AGGRESSIVE_BATCH_FACTOR: Final[float] = 0.5

    # ワーカー数調整
    EMERGENCY_WORKER_CHANGE: Final[int] = -2
    AGGRESSIVE_WORKER_CHANGE: Final[int] = -1
    MODERATE_WORKER_CHANGE: Final[int] = -1


class ErrorMessages:
    """エラーメッセージ定数"""

    MEMORY_ERROR_SUGGESTION: Final[str] = "より小さなモデル（medium等）を使用するか、システムメモリを増やしてください。"
    LOW_MEMORY_WARNING: Final[str] = (
        "利用可能メモリ: {:.1f}GB - large-v3は高メモリを必要とします。mediumモデルの使用を推奨します。"
    )
    MEMORY_LIMIT_INFO: Final[str] = "利用可能メモリ: {:.1f}GB - 自動最適化により処理速度が制限される場合があります。"
