#!/usr/bin/env python
"""
ワーカープロセス用の文字起こし処理スクリプト（リファクタリング版）

# 旧実装から新実装への移行
このファイルは後方互換性のために維持されていますが、
新しいorchestrator.TranscriptionWorkerクラスを使用することを推奨します。

責任を明確に分離したクラスベースの実装。
"""

import json
import os
import sys
import time
import logging
import gc
from pathlib import Path
from typing import Dict, Optional, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass

# プロジェクトのルートディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 新しいTranscriptionWorkerクラスをインポート
try:
    from orchestrator import TranscriptionWorker as NewTranscriptionWorker
    NEW_WORKER_AVAILABLE = True
except ImportError:
    NEW_WORKER_AVAILABLE = False

# 定数をインポート
from core.constants import (
    MemoryThresholds, BatchSizeLimits, ChunkSizeLimits,
    TranscriptionSegments, ErrorMessages
)

from utils.logging import get_logger
from config import Config
from core.auto_optimizer import AutoOptimizer
from core.memory_monitor import MemoryMonitor
from core.alignment_processor import AlignmentProcessor
from core.models import TranscriptionResultV2

logger = get_logger(__name__)


@dataclass
class WorkerConfig:
    """ワーカー設定のデータクラス"""
    video_path: str
    model_size: str
    use_cache: bool
    save_cache: bool
    task_type: str
    config_dict: Dict[str, Any]
    

def send_progress(progress: float, message: str = ""):
    """プログレス情報を親プロセスに送信"""
    print(f"PROGRESS:{progress}|{message}", flush=True)


class ConfigLoader:
    """設定ファイルの読み込みと検証"""
    
    def __init__(self, config_path: str):
        self.config_path = config_path
        
    def load(self) -> WorkerConfig:
        """設定を読み込み、検証して返す"""
        self._validate_path()
        config_data = self._read_json()
        return self._build_config(config_data)
    
    def _validate_path(self) -> None:
        """パスの存在確認"""
        if not os.path.exists(self.config_path):
            logger.error(f"設定ファイルが見つかりません: {self.config_path}")
            raise FileNotFoundError(f"設定ファイルが見つかりません: {self.config_path}")
    
    def _read_json(self) -> Dict:
        """JSONファイルを読み込み"""
        with open(self.config_path, 'r') as f:
            return json.load(f)
    
    def _build_config(self, data: Dict) -> WorkerConfig:
        """設定データからWorkerConfigを構築"""
        return WorkerConfig(
            video_path=data['video_path'],
            model_size=data['model_size'],
            use_cache=data.get('use_cache', False),
            save_cache=data.get('save_cache', False),
            task_type=data.get('task_type', 'full'),
            config_dict=data['config']
        )


class MemoryManager:
    """メモリ監視と最適化の管理"""
    
    def __init__(self, model_size: str):
        self.optimizer = AutoOptimizer(model_size)
        self.monitor = MemoryMonitor()
        self.optimizer.reset_diagnostic_mode()
        
    def log_initial_memory(self) -> None:
        """初期メモリ使用量を記録"""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"初期メモリ使用量: {mem_mb:.1f}MB")
        except Exception:
            logger.debug("メモリ情報取得をスキップ")
    
    def log_final_memory(self) -> None:
        """最終メモリ使用量を記録"""
        try:
            import psutil
            process = psutil.Process()
            mem_info = process.memory_info()
            mem_mb = mem_info.rss / 1024 / 1024
            logger.info(f"最終メモリ使用量: {mem_mb:.1f}MB")
        except Exception:
            logger.debug("メモリ情報取得をスキップ")
    
    def get_optimal_params(self) -> Dict:
        """現在のメモリ状況から最適なパラメータを取得"""
        current_memory = self.monitor.get_memory_usage()
        return self.optimizer.get_optimal_params(current_memory)
    
    def save_successful_profile(self, params: Dict, result: Any) -> None:
        """成功した実行のプロファイルを保存"""
        if hasattr(result, 'processing_time') and result.processing_time:
            try:
                # 平均メモリ使用率を計算
                avg_memory = self.monitor.get_average_usage(seconds=int(result.processing_time))
                
                # 実行メトリクスを作成
                metrics = {
                    'completed': True,
                    'avg_memory': avg_memory,
                    'processing_time': result.processing_time,
                    'segments_count': len(result.segments) if result.segments else 0,
                    'successful_runs': 1
                }
                
                # 最適化プロファイルを保存
                self.optimizer.save_successful_run(params, metrics)
                logger.info(f"実行プロファイルを保存しました（平均メモリ: {avg_memory:.1f}%）")
                
            except Exception as e:
                logger.warning(f"プロファイル保存エラー: {e}")


class BaseTaskHandler(ABC):
    """タスクハンドラーの基底クラス"""
    
    def __init__(self, worker_config: WorkerConfig, optimizer: AutoOptimizer, 
                 memory_monitor: MemoryMonitor):
        self.worker_config = worker_config
        self.config = self._create_config()
        self.optimizer = optimizer
        self.memory_monitor = memory_monitor
        self.progress_callback = self._create_progress_callback()
        
    def _create_config(self) -> Config:
        """Configオブジェクトを作成"""
        config = Config()
        
        # TranscriptionConfigを更新（必要な項目のみ）
        transcription_config = self.worker_config.config_dict['transcription']
        config.transcription.use_api = transcription_config['use_api']
        config.transcription.api_provider = transcription_config.get('api_provider', 'openai')
        config.transcription.api_key = transcription_config.get('api_key')
        config.transcription.model_size = transcription_config['model_size']
        config.transcription.language = transcription_config['language']
        config.transcription.compute_type = transcription_config['compute_type']
        config.transcription.sample_rate = transcription_config['sample_rate']
        config.transcription.isolation_mode = transcription_config.get('isolation_mode', 'none')
        
        return config
        
    @abstractmethod
    def process(self) -> TranscriptionResultV2:
        """タスクを処理（サブクラスで実装）"""
        pass
    
    def _create_progress_callback(self):
        """進捗報告用コールバックを作成"""
        def callback(progress: float, message: str):
            logger.info(f"進捗: {progress:.1%} - {message}")
            send_progress(progress, message)
        return callback
    
    def _create_transcriber(self):
        """Transcriberインスタンスを作成"""
        if self.config.transcription.use_api:
            # APIモードの場合
            from core.transcription import Transcriber
            logger.info("APIモードで処理")
            return Transcriber(self.config)
        else:
            # ローカルモードの場合
            from core.transcription_smart_boundary import SmartBoundaryTranscriber
            logger.info("ローカルモード: 自動最適化による分離処理")
            
            # 初期パラメータをログ
            current_memory = self.memory_monitor.get_memory_usage()
            optimal_params = self.optimizer.get_optimal_params(current_memory)
            logger.info(f"自動最適化パラメータ（初期）: チャンク={optimal_params['chunk_seconds']}秒, ワーカー={optimal_params['max_workers']}")
            
            return SmartBoundaryTranscriber(
                self.config, 
                optimizer=self.optimizer, 
                memory_monitor=self.memory_monitor
            )
    
    def _validate_result(self, result: Any) -> None:
        """結果の検証（wordsフィールドのチェック）"""
        # APIモードの場合は検証をスキップ
        if self.config.transcription.use_api:
            logger.info("APIモード: wordsフィールドの検証をスキップします")
            return
        
        # ローカルモードでtranscribe_onlyの場合もスキップ
        if self.worker_config.task_type == 'transcribe_only':
            logger.info("transcribe_onlyモード: wordsフィールドの検証をスキップします")
            return
        
        # 検証を実行
        if result.segments:
            logger.info("ローカルモード: wordsフィールドの検証を開始します")
            is_valid, errors = result.validate_has_words()
            if not is_valid:
                logger.error("文字起こし結果の検証に失敗しました:")
                for error in errors:
                    logger.error(f"  - {error}")
                
                # V2形式での詳細なエラー生成
                try:
                    v2_result = result.to_v2_format()
                    v2_result.require_valid_words()
                except Exception as e:
                    logger.error(f"V2形式でのエラー: {str(e)}")
                    # エラーメッセージを親プロセスに送信
                    print(f"ERROR:{str(e)}", flush=True)
                    raise


class TranscribeOnlyHandler(BaseTaskHandler):
    """文字起こしのみのハンドラー"""
    
    def process(self) -> TranscriptionResultV2:
        logger.info("文字起こしのみモード（アライメントなし）")
        
        transcriber = self._create_transcriber()
        
        result = transcriber.transcribe(
            video_path=self.worker_config.video_path,
            model_size=self.worker_config.model_size,
            progress_callback=self.progress_callback,
            use_cache=False,
            save_cache=False,
            skip_alignment=True
        )
        
        logger.info("文字起こしのみ完了（アライメント処理は別途実行）")
        
        # 検証（transcribe_onlyなのでスキップされる）
        self._validate_result(result)
        
        return result


class FullProcessHandler(BaseTaskHandler):
    """フル処理（文字起こし＋アライメント）のハンドラー"""
    
    def process(self) -> TranscriptionResultV2:
        logger.info("フル処理モード（文字起こし＋アライメント）")
        
        transcriber = self._create_transcriber()
        
        result = transcriber.transcribe(
            video_path=self.worker_config.video_path,
            model_size=self.worker_config.model_size,
            progress_callback=self.progress_callback,
            use_cache=self.worker_config.use_cache,
            save_cache=self.worker_config.save_cache,
            skip_alignment=False
        )
        
        # 検証
        self._validate_result(result)
        
        return result


class SeparatedModeHandler(BaseTaskHandler):
    """分離モード（文字起こし→アライメント）のハンドラー"""
    
    def process(self) -> TranscriptionResultV2:
        logger.info("分離モード: 文字起こしフェーズ開始")
        
        # ステップ1: 文字起こし
        transcription_result = self._process_transcription()
        
        # ステップ2: アライメント
        aligned_result = self._process_alignment(transcription_result)
        
        # 検証
        self._validate_result(aligned_result)
        
        return aligned_result
    
    def _process_transcription(self) -> Any:
        """文字起こしフェーズ"""
        def transcribe_progress(progress: float, message: str):
            # 文字起こしは全体の50%
            self.progress_callback(progress * 0.5, f"[文字起こし] {message}")
        
        logger.info("文字起こしフェーズ: 動的最適化が有効です")
        
        transcriber = self._create_transcriber()
        
        result = transcriber.transcribe(
            video_path=self.worker_config.video_path,
            model_size=self.worker_config.model_size,
            progress_callback=transcribe_progress,
            use_cache=False,
            save_cache=False,
            skip_alignment=True
        )
        
        return result
    
    def _process_alignment(self, result: Any) -> Any:
        """アライメントフェーズ"""
        logger.info("分離モード: アライメントフェーズ開始")
        
        def alignment_progress(progress: float, message: str):
            # アライメントは全体の50-100%
            self.progress_callback(0.5 + progress * 0.5, f"[アライメント] {message}")
        
        # アライメント前に再度パラメータを最適化
        current_memory = self.memory_monitor.get_memory_usage()
        optimal_params = self.optimizer.get_optimal_params(current_memory)
        
        # アライメント診断を実行
        optimal_batch_size = self._run_alignment_diagnostic(
            result, 
            optimal_params, 
            alignment_progress
        )
        
        logger.info(f"アライメント用パラメータ: バッチサイズ={optimal_batch_size}")
        
        # 最適化されたバッチサイズで本番用AlignmentProcessorを初期化
        alignment_processor = AlignmentProcessor(self.config, batch_size=optimal_batch_size)
        
        # V2形式に変換してアライメント実行
        if hasattr(result, 'to_v2_format'):
            v2_result = result.to_v2_format()
            segments = v2_result.segments
        else:
            segments = result.segments
        
        # アライメント本体の実行
        def main_alignment_progress(progress: float, message: str):
            # 診断が20%まで使用、本体は20-100%
            actual_progress = 0.2 + progress * 0.8
            alignment_progress(actual_progress, message)
        
        aligned_segments = alignment_processor.align(
            segments,
            self.worker_config.video_path,
            result.language,
            progress_callback=main_alignment_progress
        )
        
        # アライメント結果で更新
        if aligned_segments:
            result.segments = aligned_segments
            logger.info("分離モード: アライメント完了")
        else:
            logger.error("分離モード: アライメント失敗")
        
        return result
    
    def _run_alignment_diagnostic(self, result: Any, optimal_params: Dict, 
                                  alignment_progress) -> int:
        """アライメント診断を実行して最適なバッチサイズを決定"""
        logger.info("アライメント用診断フェーズを開始")
        
        # 診断結果のキャッシュキーを生成
        try:
            file_stat = os.stat(self.worker_config.video_path)
            cache_key = f"{self.worker_config.video_path}_{file_stat.st_size}_{len(result.segments)}"
        except:
            cache_key = None
        
        # キャッシュされた診断結果を確認（現在は無効化）
        diagnostic_result = None
        
        # キャッシュがない場合は診断を実行
        if not diagnostic_result:
            # 診断用のAlignmentProcessorを作成
            diagnostic_processor = AlignmentProcessor(self.config)
            
            # 診断用のサンプルセグメントを準備
            sample_segments = None
            if hasattr(result, 'to_v2_format'):
                v2_result = result.to_v2_format()
                sample_segments = v2_result.segments[:TranscriptionSegments.SAMPLE_SEGMENTS_COUNT] \
                    if len(v2_result.segments) >= TranscriptionSegments.SAMPLE_SEGMENTS_COUNT \
                    else v2_result.segments
            elif result.segments:
                sample_segments = result.segments[:TranscriptionSegments.SAMPLE_SEGMENTS_COUNT] \
                    if len(result.segments) >= TranscriptionSegments.SAMPLE_SEGMENTS_COUNT \
                    else result.segments
            
            # 診断を実行
            diagnostic_result = diagnostic_processor.run_diagnostic(
                audio_path=self.worker_config.video_path,
                language=result.language,
                sample_segments=sample_segments,
                progress_callback=lambda p, m: alignment_progress(p * 0.2, f"[診断] {m}")
            )
            
            # 診断用プロセッサをクリーンアップ
            del diagnostic_processor
            gc.collect()
        
        # 診断結果を使用
        if diagnostic_result['diagnostic_completed']:
            optimal_batch_size = diagnostic_result['optimal_batch_size']
            logger.info(f"診断完了: 最適バッチサイズ={optimal_batch_size}")
            logger.info(f"  - モデルメモリ: {diagnostic_result['model_memory']:.1f}%")
            logger.info(f"  - 音声メモリ（推定）: {diagnostic_result['audio_memory']:.1f}%")
            logger.info(f"  - バッチあたり: {diagnostic_result['batch_memory_per_segment']:.1f}%/セグメント")
        else:
            # 診断が失敗した場合は推定ロジックを使用
            logger.warning("診断が完了しなかったため、推定値を使用")
            optimal_batch_size = self._estimate_batch_size(optimal_params)
        
        return optimal_batch_size
    
    def _estimate_batch_size(self, optimal_params: Dict) -> int:
        """診断が失敗した場合のバッチサイズ推定"""
        # バッチサイズはチャンクサイズと相関させる
        if optimal_params['align_chunk_seconds'] >= ChunkSizeLimits.BATCH_SIZE_THRESHOLD_LARGE:
            optimal_batch_size = BatchSizeLimits.SMALL
        elif optimal_params['align_chunk_seconds'] >= ChunkSizeLimits.BATCH_SIZE_THRESHOLD_MEDIUM:
            optimal_batch_size = 6  # TODO: 定数化検討
        elif optimal_params['align_chunk_seconds'] >= ChunkSizeLimits.BATCH_SIZE_THRESHOLD_SMALL:
            optimal_batch_size = BatchSizeLimits.DEFAULT
        else:
            optimal_batch_size = BatchSizeLimits.MEDIUM
        
        # メモリ使用率が高い場合はさらに削減
        current_memory = self.memory_monitor.get_memory_usage()
        if current_memory > MemoryThresholds.COMFORTABLE:
            optimal_batch_size = max(BatchSizeLimits.EMERGENCY, optimal_batch_size // 2)
        
        return optimal_batch_size


class TranscriptionWorker:
    """ワーカープロセスのメインクラス"""
    
    def __init__(self, config_path: str):
        """初期化
        
        Args:
            config_path: 設定ファイルのパス
        """
        self.config_loader = ConfigLoader(config_path)
        self.worker_config = self.config_loader.load()
        self.memory_manager = MemoryManager(self.worker_config.model_size)
        self.result_path = os.path.join(os.path.dirname(config_path), 'result.json')
        
    def execute(self) -> None:
        """メイン実行メソッド"""
        try:
            logger.info(f"ワーカー処理を開始: {self.worker_config.video_path} (タスク: {self.worker_config.task_type})")
            send_progress(0.0, "処理を開始しています...")
            
            # 初期メモリ使用量を記録
            self.memory_manager.log_initial_memory()
            
            # タスクハンドラーを取得して実行
            handler = self._create_task_handler()
            result = handler.process()
            
            # 結果を保存
            self._save_result(result)
            
            # 成功時の後処理
            self._handle_success(result)
            
            # 最終メモリ使用量を記録
            self.memory_manager.log_final_memory()
            
            logger.info("処理が完了しました")
            send_progress(1.0, "処理が完了しました")
            
            sys.exit(0)
            
        except MemoryError as e:
            self._handle_memory_error(e)
        except Exception as e:
            self._handle_general_error(e)
    
    def _create_task_handler(self) -> BaseTaskHandler:
        """タスクタイプに応じたハンドラーを作成"""
        task_type = self.worker_config.task_type
        
        # APIモードの場合は常にフル処理
        if self.worker_config.config_dict['transcription']['use_api']:
            task_type = 'full'
        # ローカルモードの場合は分離モードを強制
        elif task_type != 'transcribe_only':
            task_type = 'separated_mode'
        
        handlers = {
            'transcribe_only': TranscribeOnlyHandler,
            'separated_mode': SeparatedModeHandler,
            'full': FullProcessHandler
        }
        
        handler_class = handlers.get(task_type, FullProcessHandler)
        return handler_class(
            self.worker_config,
            self.memory_manager.optimizer,
            self.memory_manager.monitor
        )
    
    def _save_result(self, result: Any) -> None:
        """結果を保存"""
        result_data = result.to_dict()
        
        logger.info(f"文字起こし結果 - セグメント数: {len(result.segments) if result.segments else 0}")
        if result.segments:
            logger.info(f"最初のセグメント: {result.segments[0].text[:50] if result.segments[0].text else '(空)'}...")
        
        with open(self.result_path, 'w', encoding='utf-8') as f:
            json.dump(result_data, f, ensure_ascii=False, indent=2)
    
    def _handle_success(self, result: Any) -> None:
        """成功時の後処理"""
        # ローカルモードの場合、成功したプロファイルを保存
        if not self.worker_config.config_dict['transcription']['use_api']:
            optimal_params = self.memory_manager.get_optimal_params()
            self.memory_manager.save_successful_profile(optimal_params, result)
    
    def _handle_memory_error(self, e: MemoryError) -> None:
        """メモリエラーの処理"""
        logger.error(f"メモリ不足エラー: {str(e)}")
        print(f"ERROR:メモリ不足により処理を中断しました: {str(e)}", file=sys.stderr, flush=True)
        
        # エラー結果を保存
        error_result = {
            "success": False,
            "error": f"メモリ不足: {str(e)}",
            "error_type": "MemoryError",
            "suggestion": ErrorMessages.MEMORY_ERROR_SUGGESTION
        }
        
        with open(self.result_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)
    
    def _handle_general_error(self, e: Exception) -> None:
        """一般的なエラーの処理"""
        import traceback
        error_traceback = traceback.format_exc()
        logger.error(f"ワーカー処理でエラー: {str(e)}\n{error_traceback}")
        
        # エラー詳細を標準エラー出力にも出力
        print(f"ERROR:ワーカー処理エラー: {str(e)}", file=sys.stderr, flush=True)
        print(f"TRACEBACK:\n{error_traceback}", file=sys.stderr, flush=True)
        
        # エラー結果を保存
        error_result = {
            "success": False,
            "error": str(e),
            "traceback": error_traceback
        }
        
        with open(self.result_path, 'w', encoding='utf-8') as f:
            json.dump(error_result, f, ensure_ascii=False, indent=2)
        
        sys.exit(1)


def main():
    """既存のmain関数との互換性のためのラッパー"""
    try:
        # コマンドライン引数から設定ファイルパスを取得
        if len(sys.argv) < 2:
            logger.error("設定ファイルパスが指定されていません")
            sys.exit(1)
        
        config_path = sys.argv[1]
        
        # 新しいワーカーを実行
        worker = TranscriptionWorker(config_path)
        worker.execute()
        
    except Exception as e:
        logger.error(f"ワーカー初期化エラー: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()