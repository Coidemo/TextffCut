"""
TextffCut 統一文字起こし処理実装

2段階処理アーキテクチャのメインオーケストレーター。
文字起こしとアライメントを別々に管理し、堅牢な処理を実現します。
"""

import os
import json
import time
import hashlib
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable
from concurrent.futures import ProcessPoolExecutor, as_completed

from config import Config
from utils.logging import get_logger
from utils.exceptions import TranscriptionError, VideoProcessingError
from .exceptions import AlignmentError
from utils.system_resources import get_memory_info

from .models import (
    TranscriptionResultV2,
    TranscriptionSegmentV2,
    ProcessingRequest,
    ProcessingStatus,
    ProcessingMetadata,
    WordInfo
)
from .interfaces import (
    IUnifiedTranscriber,
    ITranscriptionProcessor,
    IAlignmentProcessor,
    ICacheManager,
    IProgressReporter
)

logger = get_logger(__name__)


class UnifiedTranscriber(IUnifiedTranscriber):
    """
    統一文字起こし処理クラス
    
    特徴:
    - 文字起こしとアライメントの分離処理
    - APIモードとローカルモードの統一インターフェース
    - 堅牢なエラーハンドリングとリトライ機構
    - 効率的なキャッシュ管理
    """
    
    def __init__(
        self,
        config: Config,
        transcription_processor: Optional[ITranscriptionProcessor] = None,
        alignment_processor: Optional[IAlignmentProcessor] = None,
        cache_manager: Optional[ICacheManager] = None,
        progress_reporter: Optional[IProgressReporter] = None
    ):
        """
        初期化
        
        Args:
            config: アプリケーション設定
            transcription_processor: 文字起こしプロセッサー（省略時は自動選択）
            alignment_processor: アライメントプロセッサー（省略時は自動選択）
            cache_manager: キャッシュマネージャー（省略時はデフォルト）
            progress_reporter: 進捗レポーター（省略時はログ出力）
        """
        self.config = config
        
        # プロセッサーの初期化（後で実装を追加）
        self.transcription_processor = transcription_processor
        self.alignment_processor = alignment_processor
        self.cache_manager = cache_manager
        self.progress_reporter = progress_reporter or DefaultProgressReporter()
        
        # 一時ディレクトリ
        self.temp_dir = None
        
    def process(self, request: ProcessingRequest) -> TranscriptionResultV2:
        """
        文字起こしとアライメントの統合処理を実行
        
        Args:
            request: 処理リクエスト
            
        Returns:
            処理結果
        """
        logger.info(f"処理開始: {request.video_path}")
        
        # メタデータの初期化
        from core.video import VideoInfo
        video_info = VideoInfo.from_file(request.video_path)
        
        metadata = ProcessingMetadata(
            video_path=request.video_path,
            video_duration=video_info.duration,
            processing_mode=request.processing_mode,
            model_size=request.model_size,
            language=request.language
        )
        
        # キャッシュチェック
        if request.use_cache and self.cache_manager:
            cache_key = self._get_cache_key(request, "complete")
            cached_result = self.cache_manager.load_cache(cache_key)
            if cached_result:
                logger.info("完全なキャッシュから読み込み")
                self._report_progress(1.0, "キャッシュから読み込み完了", request.progress_callback)
                return cached_result
        
        # 一時ディレクトリの作成
        self.temp_dir = tempfile.mkdtemp(prefix="textffcut_unified_")
        
        try:
            # ステージ1: 文字起こし
            segments = self._process_transcription(request, metadata)
            
            # ステージ2: アライメント
            aligned_segments = self._process_alignment(request, segments, metadata)
            
            # 結果の作成
            result = TranscriptionResultV2(
                segments=aligned_segments,
                metadata=metadata
            )
            
            # 完了時の処理
            metadata.completed_at = datetime.now()
            metadata.total_processing_time = (
                metadata.completed_at - metadata.started_at
            ).total_seconds()
            
            result.transcription_status = ProcessingStatus.COMPLETED
            result.alignment_status = ProcessingStatus.COMPLETED
            result.update_statistics()
            
            # 結果の検証（厳密なチェック）
            try:
                result.require_valid_words()  # wordsフィールドの必須チェック
            except Exception as e:
                # 検証エラーの詳細をログに記録
                logger.error(f"検証エラー: {str(e)}")
                metadata.add_error("validation", str(e))
                raise
            
            if not self.validate_result(result):
                raise VideoProcessingError("処理結果の検証に失敗しました")
            
            # キャッシュ保存
            if request.save_cache and self.cache_manager:
                self._save_to_cache(result, request)
            
            logger.info(
                f"処理完了: セグメント数={result.total_segments}, "
                f"アライメント成功={result.aligned_segments}, "
                f"処理時間={metadata.total_processing_time:.1f}秒"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"処理エラー: {str(e)}")
            metadata.add_error("process", str(e))
            raise
            
        finally:
            # クリーンアップ
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                try:
                    shutil.rmtree(self.temp_dir)
                except Exception as e:
                    logger.warning(f"一時ディレクトリの削除に失敗: {e}")
    
    def _process_transcription(
        self,
        request: ProcessingRequest,
        metadata: ProcessingMetadata
    ) -> List[TranscriptionSegmentV2]:
        """文字起こし処理"""
        logger.info("文字起こし処理を開始")
        metadata.transcription_started_at = datetime.now()
        
        try:
            # キャッシュチェック（文字起こしのみ）
            if request.use_cache and self.cache_manager:
                cache_key = self._get_cache_key(request, "transcription")
                cached_data = self._load_transcription_cache(cache_key)
                if cached_data:
                    logger.info("文字起こしキャッシュから読み込み")
                    self._report_progress(0.5, "文字起こしキャッシュから読み込み", request.progress_callback)
                    return cached_data
            
            # 処理モードに応じた実装を選択
            if request.processing_mode == "api":
                segments = self._transcribe_with_api(request)
            else:
                segments = self._transcribe_locally(request)
            
            metadata.transcription_completed_at = datetime.now()
            
            # 文字起こしキャッシュの保存
            if request.save_cache and self.cache_manager:
                cache_key = self._get_cache_key(request, "transcription")
                self._save_transcription_cache(cache_key, segments, metadata)
            
            return segments
            
        except Exception as e:
            metadata.add_error("transcription", str(e))
            raise TranscriptionError(f"文字起こし処理に失敗: {str(e)}")
    
    def _process_alignment(
        self,
        request: ProcessingRequest,
        segments: List[TranscriptionSegmentV2],
        metadata: ProcessingMetadata
    ) -> List[TranscriptionSegmentV2]:
        """アライメント処理"""
        logger.info("アライメント処理を開始")
        metadata.alignment_started_at = datetime.now()
        
        try:
            # APIモードでもアライメントが必要
            if request.processing_mode == "api":
                # APIモードではサブプロセスでアライメント実行
                if self.config.transcription.api_align_in_subprocess:
                    aligned_segments = self._align_in_subprocess(segments, request)
                else:
                    aligned_segments = self._align_segments(segments, request)
            else:
                # ローカルモードでは通常のアライメント
                aligned_segments = self._align_segments(segments, request)
            
            # アライメント結果の厳密な検証
            valid_count = sum(1 for s in aligned_segments if s.has_valid_alignment())
            failed_segments = [s for s in aligned_segments if not s.has_valid_alignment()]
            segments_without_words = [s for s in aligned_segments if not s.words or len(s.words) == 0]
            
            # wordsフィールドが完全に欠落している場合は即座にエラー
            if segments_without_words:
                from .exceptions import WordsFieldMissingError
                sample_texts = [
                    s.text[:50] + "..." if s.text and len(s.text) > 50 else s.text
                    for s in segments_without_words[:3]
                ]
                raise WordsFieldMissingError(
                    segment_count=len(segments_without_words),
                    sample_segments=sample_texts
                )
            
            # アライメント成功率の検証
            if valid_count == 0:
                from .exceptions import AlignmentValidationError
                raise AlignmentValidationError(
                    "アライメントが全て失敗しました",
                    failed_count=len(aligned_segments),
                    total_count=len(aligned_segments)
                )
            
            # 部分的な失敗の処理
            if valid_count < len(aligned_segments):
                success_rate = valid_count / len(aligned_segments)
                
                # エラータイプの分析
                error_types = {}
                for seg in failed_segments:
                    error_type = seg.alignment_error or "不明なエラー"
                    error_types[error_type] = error_types.get(error_type, 0) + 1
                
                # 成功率が50%未満の場合はエラー
                if success_rate < 0.5:
                    from .exceptions import AlignmentValidationError
                    raise AlignmentValidationError(
                        f"アライメント成功率が低すぎます: {success_rate:.1%}",
                        failed_count=len(failed_segments),
                        total_count=len(aligned_segments),
                        error_types=error_types
                    )
                else:
                    # 警告として記録
                    metadata.add_warning(
                        "alignment",
                        f"{len(failed_segments)}個のセグメントでアライメントに失敗（成功率: {success_rate:.1%}）",
                        {
                            "failed_segments": [s.id for s in failed_segments],
                            "error_types": error_types
                        }
                    )
            
            metadata.alignment_completed_at = datetime.now()
            
            return aligned_segments
            
        except Exception as e:
            metadata.add_error("alignment", str(e))
            raise AlignmentError(f"アライメント処理に失敗: {str(e)}")
    
    def _transcribe_with_api(self, request: ProcessingRequest) -> List[TranscriptionSegmentV2]:
        """API経由での文字起こし"""
        logger.info("APIモードで文字起こしを実行")
        
        # APIトランスクライバーの実装（簡略版）
        from .transcription_api import APITranscriber
        api_transcriber = APITranscriber(self.config)
        
        # プログレスコールバックのラッパー
        def api_progress_callback(progress: float, message: str):
            self._report_progress(progress * 0.5, f"API文字起こし: {message}", request.progress_callback)
        
        # API実行
        result = api_transcriber.transcribe(
            request.video_path,
            request.model_size,
            api_progress_callback,
            use_cache=False,  # 独自のキャッシュ管理を使用
            save_cache=False
        )
        
        # TranscriptionSegmentV2形式に変換
        segments = []
        for i, seg in enumerate(result.segments):
            segment = TranscriptionSegmentV2(
                id=f"seg_{i}",
                text=seg.text,
                start=seg.start,
                end=seg.end,
                transcription_completed=True,
                alignment_completed=False,  # APIでもアライメントは別途必要
                language=request.language
            )
            segments.append(segment)
        
        return segments
    
    def _transcribe_locally(self, request: ProcessingRequest) -> List[TranscriptionSegmentV2]:
        """ローカルでの文字起こし（サブプロセス実行）"""
        logger.info("ローカルモードで文字起こしを実行")
        
        # サブプロセスでの実行設定を作成
        config_data = {
            "video_path": request.video_path,
            "model_size": request.model_size,
            "language": request.language,
            "task_type": "transcribe_only",  # 文字起こしのみ
            "config": self.config.__dict__
        }
        
        # 設定ファイルの保存
        config_path = os.path.join(self.temp_dir, "transcribe_config.json")
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        # ワーカープロセスの実行
        cmd = [
            "python", "worker_transcribe.py",
            config_path
        ]
        
        logger.info(f"サブプロセスを起動: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 進捗監視
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            if line.startswith("PROGRESS:"):
                try:
                    _, data = line.strip().split(":", 1)
                    progress, message = data.split("|", 1)
                    self._report_progress(
                        float(progress) * 0.5,
                        f"ローカル文字起こし: {message}",
                        request.progress_callback
                    )
                except:
                    pass
        
        # 終了待機
        return_code = process.wait()
        
        if return_code != 0:
            stderr = process.stderr.read()
            raise TranscriptionError(f"文字起こしワーカーエラー: {stderr}")
        
        # 結果の読み込み
        result_path = os.path.join(self.temp_dir, "result.json")
        if not os.path.exists(result_path):
            # 旧形式のパスも試す
            result_path = os.path.join(self.temp_dir, "transcribe_result.json")
            if not os.path.exists(result_path):
                raise TranscriptionError("文字起こし結果が見つかりません")
        
        with open(result_path, 'r') as f:
            result_data = json.load(f)
        
        # TranscriptionSegmentV2形式に変換
        segments = []
        for seg_data in result_data["segments"]:
            segment = TranscriptionSegmentV2(
                id=seg_data.get("id", f"seg_{len(segments)}"),
                text=seg_data["text"],
                start=seg_data["start"],
                end=seg_data["end"],
                transcription_completed=True,
                alignment_completed=False,
                language=request.language
            )
            segments.append(segment)
        
        return segments
    
    def _align_segments(
        self,
        segments: List[TranscriptionSegmentV2],
        request: ProcessingRequest
    ) -> List[TranscriptionSegmentV2]:
        """セグメントのアライメント処理"""
        logger.info(f"{len(segments)}個のセグメントをアライメント")
        
        # アライメントプロセッサーの実装（簡略版）
        from .alignment_processor import AlignmentProcessor
        alignment_processor = AlignmentProcessor(self.config)
        
        # プログレスコールバックのラッパー
        def align_progress_callback(progress: float, message: str):
            self._report_progress(
                0.5 + progress * 0.5,
                f"アライメント: {message}",
                request.progress_callback
            )
        
        # アライメント実行
        aligned_segments = alignment_processor.align(
            segments,
            request.video_path,
            request.language,
            align_progress_callback
        )
        
        return aligned_segments
    
    def _align_in_subprocess(
        self,
        segments: List[TranscriptionSegmentV2],
        request: ProcessingRequest
    ) -> List[TranscriptionSegmentV2]:
        """サブプロセスでアライメント実行"""
        logger.info("サブプロセスでアライメントを実行")
        
        # アライメント用設定
        config_data = {
            "segments": [s.to_dict() for s in segments],
            "audio_path": request.video_path,
            "language": request.language,
            "task_type": "align",
            "config": self.config.__dict__
        }
        
        # 設定ファイルの保存
        config_path = os.path.join(self.temp_dir, "align_config.json")
        with open(config_path, 'w') as f:
            json.dump(config_data, f)
        
        # ワーカープロセスの実行
        cmd = [
            "python", "worker_align.py",
            config_path
        ]
        
        logger.info(f"アライメントサブプロセスを起動: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 進捗監視
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            if line.startswith("PROGRESS:"):
                try:
                    _, data = line.strip().split(":", 1)
                    progress, message = data.split("|", 1)
                    self._report_progress(
                        0.5 + float(progress) * 0.5,
                        f"アライメント: {message}",
                        request.progress_callback
                    )
                except:
                    pass
        
        # 終了待機
        return_code = process.wait()
        
        if return_code != 0:
            stderr = process.stderr.read()
            raise AlignmentError(f"アライメントワーカーエラー: {stderr}")
        
        # 結果の読み込み
        result_path = os.path.join(self.temp_dir, "align_result.json")
        if not os.path.exists(result_path):
            raise AlignmentError("アライメント結果が見つかりません")
        
        with open(result_path, 'r') as f:
            result_data = json.load(f)
        
        # TranscriptionSegmentV2形式に復元
        aligned_segments = []
        for seg_data in result_data["segments"]:
            segment = TranscriptionSegmentV2.from_dict(seg_data)
            aligned_segments.append(segment)
        
        return aligned_segments
    
    def process_with_retry(
        self,
        request: ProcessingRequest,
        max_retries: int = 3
    ) -> TranscriptionResultV2:
        """リトライ機能付きで処理を実行"""
        last_error = None
        
        for attempt in range(max_retries):
            try:
                logger.info(f"処理実行: 試行 {attempt + 1}/{max_retries}")
                return self.process(request)
                
            except Exception as e:
                last_error = e
                logger.warning(f"処理エラー（試行 {attempt + 1}）: {str(e)}")
                
                if attempt < max_retries - 1:
                    # 次の試行前に待機
                    wait_time = 2 ** attempt  # 指数バックオフ
                    logger.info(f"{wait_time}秒待機後にリトライ")
                    time.sleep(wait_time)
        
        # すべての試行が失敗
        raise VideoProcessingError(
            f"処理が{max_retries}回失敗しました。最後のエラー: {str(last_error)}"
        )
    
    def validate_result(self, result: TranscriptionResultV2) -> bool:
        """処理結果を検証"""
        # 基本的な検証
        if not result.segments:
            logger.error("セグメントが空です")
            return False
        
        # 少なくとも1つの有効なアライメントが必要
        if not result.has_valid_words():
            logger.error("有効なアライメント情報がありません")
            return False
        
        # 処理ステータスの確認
        if result.transcription_status != ProcessingStatus.COMPLETED:
            logger.error("文字起こしが完了していません")
            return False
        
        if result.alignment_status != ProcessingStatus.COMPLETED:
            logger.error("アライメントが完了していません")
            return False
        
        # 統計情報の整合性
        if result.aligned_segments == 0:
            logger.error("アライメント済みセグメントが0です")
            return False
        
        logger.info(
            f"検証成功: 総セグメント={result.total_segments}, "
            f"アライメント済み={result.aligned_segments}"
        )
        
        return True
    
    def get_available_caches(self, video_path: str) -> List[Dict[str, Any]]:
        """利用可能なキャッシュのリストを取得"""
        if not self.cache_manager:
            return []
        
        caches = self.cache_manager.list_caches(video_path)
        
        # UI表示用に整形
        cache_list = []
        for cache in caches:
            cache_info = {
                "file_path": cache.file_path,
                "model_size": cache.model_size,
                "is_api": cache.processing_mode == "api",
                "created_at": cache.created_at,
                "file_size": cache.file_size_bytes,
                "is_complete": cache.is_complete
            }
            cache_list.append(cache_info)
        
        # 作成日時でソート（新しい順）
        cache_list.sort(key=lambda x: x["created_at"], reverse=True)
        
        return cache_list
    
    def _get_cache_key(self, request: ProcessingRequest, stage: str) -> str:
        """キャッシュキーを生成"""
        # ビデオファイルのハッシュを生成
        video_hash = hashlib.md5(request.video_path.encode()).hexdigest()[:8]
        
        # キーの構成要素
        components = [
            video_hash,
            request.processing_mode,
            request.model_size,
            request.language,
            stage
        ]
        
        return "_".join(components)
    
    def _report_progress(
        self,
        progress: float,
        message: str,
        callback: Optional[Callable[[float, str], None]]
    ):
        """進捗を報告"""
        if self.progress_reporter:
            self.progress_reporter.report_progress(
                "process",
                progress,
                1.0,
                message
            )
        
        if callback:
            callback(progress, message)
    
    def _load_transcription_cache(self, cache_key: str) -> Optional[List[TranscriptionSegmentV2]]:
        """文字起こしキャッシュの読み込み（簡略版）"""
        # 実際の実装では cache_manager を使用
        return None
    
    def _save_transcription_cache(
        self,
        cache_key: str,
        segments: List[TranscriptionSegmentV2],
        metadata: ProcessingMetadata
    ):
        """文字起こしキャッシュの保存（簡略版）"""
        # 実際の実装では cache_manager を使用
        pass
    
    def _save_to_cache(self, result: TranscriptionResultV2, request: ProcessingRequest):
        """完全な結果をキャッシュに保存（簡略版）"""
        # 実際の実装では cache_manager を使用
        pass


class DefaultProgressReporter(IProgressReporter):
    """デフォルトの進捗レポーター（ログ出力）"""
    
    def report_progress(self, stage: str, current: float, total: float, message: str):
        """進捗を報告"""
        percentage = (current / total) * 100 if total > 0 else 0
        logger.info(f"[{stage}] {percentage:.1f}% - {message}")
    
    def report_error(self, stage: str, error: Exception, recoverable: bool = False):
        """エラーを報告"""
        level = "warning" if recoverable else "error"
        getattr(logger, level)(f"[{stage}] エラー: {str(error)}")
    
    def report_warning(self, stage: str, warning: str, details: Optional[Dict[str, Any]] = None):
        """警告を報告"""
        logger.warning(f"[{stage}] 警告: {warning}")
        if details:
            logger.debug(f"詳細: {details}")