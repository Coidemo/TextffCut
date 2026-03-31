"""
最適化された文字起こしゲートウェイの実装

音声最適化とエラー回復機能を統合した文字起こしゲートウェイ
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

import psutil

try:
    import torch
except ImportError:
    torch = None  # MLXモードではtorch不要

from adapters.gateways.transcription.transcription_gateway import TranscriptionGatewayAdapter
from application.interfaces.audio_optimizer_gateway import IAudioOptimizerGateway
from config import Config
from domain.entities.performance_profile import PerformanceProfile, PerformanceMetrics
from domain.repositories.performance_profile_repository import IPerformanceProfileRepository
from domain.value_objects import FilePath
from domain.entities import TranscriptionResult
from use_cases.interfaces import ITranscriptionGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class OptimizedTranscriptionGatewayAdapter(TranscriptionGatewayAdapter):
    """
    最適化された文字起こしゲートウェイ
    
    音声最適化、エラー回復、パフォーマンスプロファイルを統合
    """
    
    def __init__(
        self,
        config: Config,
        audio_optimizer: IAudioOptimizerGateway,
        profile_repository: IPerformanceProfileRepository
    ):
        super().__init__(config)
        self.audio_optimizer = audio_optimizer
        self.profile_repository = profile_repository
        self.profile = self._load_or_create_profile()
        self.max_retries = 3
        
    
    def _load_or_create_profile(self) -> PerformanceProfile:
        """プロファイルを読み込みまたは作成"""
        profile = self.profile_repository.load()
        if profile is None:
            profile = self.profile_repository.get_default()
            self.profile_repository.save(profile)
        return profile
    
    def transcribe(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        language: str | None = None,
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """
        動画ファイルを文字起こし（適応的最適化付き）
        """
        # MLXモードの場合、VAD/legacyをバイパスしてTranscriberに委譲
        from utils.environment import MLX_AVAILABLE
        if MLX_AVAILABLE and getattr(self.config.transcription, 'use_mlx_whisper', False):
            logger.info("MLXモードで文字起こし（OptimizedGatewayからTranscriberに委譲）")
            return self._transcribe_mlx(
                video_path=video_path,
                model_size=model_size,
                use_cache=use_cache,
                progress_callback=progress_callback,
            )

        # MLXモードが必須（Apple Silicon専用）
        raise NotImplementedError(
            "MLXモードのみサポートしています（Apple Silicon必須）。"
            "config.transcription.use_mlx_whisper = True を設定してください。"
        )

    def _transcribe_mlx(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """MLXモードの文字起こし（既存の_legacy_transcriberに委譲）"""
        # 親クラスで初期化済みの_legacy_transcriberを再利用（#4, #6修正）
        transcriber = self._legacy_transcriber

        # #2修正: progress_callbackの型を安全にラップ
        # Gatewayのシグネチャは Callable[[float], None] だが、
        # CoreTranscriberは Callable[[float, str], None] を期待する
        def safe_callback(progress: float, status: str = "") -> None:
            if progress_callback:
                try:
                    progress_callback(progress, status)
                except TypeError:
                    # 1引数のcallbackが渡された場合のフォールバック
                    progress_callback(progress)

        core_result = transcriber.transcribe(
            video_path=str(video_path),
            model_size=model_size,
            progress_callback=safe_callback,
            use_cache=use_cache,
        )

        # core.transcription.TranscriptionResult → domain.entities.TranscriptionResult に変換
        import uuid
        from domain.entities.transcription import TranscriptionResult as DomainResult
        from domain.entities.transcription import TranscriptionSegment as DomainSegment

        # #1修正: duration は動画の長さ（最後のセグメントの終了時間）を使う
        duration = 0.0
        domain_segments = []
        for seg in core_result.segments:
            domain_segments.append(DomainSegment(
                id=str(uuid.uuid4()),
                start=seg.start,
                end=seg.end,
                text=seg.text,
                words=seg.words,
                chars=seg.chars,
            ))
            if seg.end > duration:
                duration = seg.end

        return DomainResult(
            id=str(uuid.uuid4()),
            video_id=str(video_path),
            language=core_result.language,
            segments=domain_segments,
            duration=duration,
            original_audio_path=str(video_path),
            model_size=core_result.model_size,
            processing_time=core_result.processing_time,
        )

    def _transcribe_legacy(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        language: str | None = None,
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """
        従来の文字起こし処理（既存の実装）
        """
        start_time = datetime.now()
        
        for attempt in range(self.max_retries):
            try:
                # 現在の設定を取得
                current_config = self._get_current_config()
                
                logger.info(f"""
                文字起こし試行 {attempt + 1}/{self.max_retries}
                設定: batch_size={current_config['batch_size']}, 
                      compute_type={current_config['compute_type']}
                """)
                
                if progress_callback:
                    progress_callback("処理を開始しています... (0%)")
                
                # 音声最適化（常に実行）
                audio_path = video_path
                if not self.config.transcription.use_api:
                    # ローカルモードの場合のみ音声最適化を実施
                    audio_data, optimization_info = self.audio_optimizer.prepare_audio(
                        video_path
                    )
                    
                    if optimization_info.get('optimized', False):
                        message = f"音声最適化: {optimization_info.get('reduction_percent', 0):.0f}%削減"
                    else:
                        message = f"音声最適化スキップ: {optimization_info.get('reason', '')}"
                    
                    logger.info(message)
                    if progress_callback:
                        progress_callback("音声最適化完了 (10%)")
                
                # 既存のtranscribeメソッドを実行
                # バッチサイズとcompute_typeを一時的に設定
                original_batch_size = getattr(self._legacy_transcriber, 'DEFAULT_BATCH_SIZE', 8)
                original_compute_type = self.config.transcription.compute_type
                
                try:
                    # 設定を適用
                    self._legacy_transcriber.DEFAULT_BATCH_SIZE = current_config['batch_size']
                    self.config.transcription.compute_type = current_config['compute_type']
                    
                    # 基底クラスのtranscribeを実行
                    # TranscriptionGatewayAdapterは内部でsave_cache=Trueを使用するので、ここでは指定不要
                    result = super().transcribe(
                        video_path=video_path,
                        model_size=model_size,
                        language=language,
                        use_cache=use_cache,
                        progress_callback=lambda progress, msg="": progress_callback(f"{msg} ({int(progress*100)}%)") if progress_callback else None
                    )
                    
                finally:
                    # 設定を元に戻す
                    self._legacy_transcriber.DEFAULT_BATCH_SIZE = original_batch_size
                    self.config.transcription.compute_type = original_compute_type
                
                # 成功を記録
                processing_time = (datetime.now() - start_time).total_seconds()
                metrics = PerformanceMetrics(
                    timestamp=datetime.now(),
                    success=True,
                    processing_time=processing_time,
                    optimization_info=optimization_info if 'optimization_info' in locals() else None
                )
                self.profile.add_metrics(metrics)
                self.profile_repository.save(self.profile)
                
                logger.info(f"文字起こし成功: {processing_time:.1f}秒")
                
                return result
                
            except MemoryError as e:
                # システムメモリエラー
                self._handle_memory_error(e, "System", attempt)

            except Exception as e:
                # GPUメモリエラーのチェック
                if torch is not None and isinstance(e, torch.cuda.OutOfMemoryError):
                    self._handle_memory_error(e, "GPU", attempt)
                else:
                    # その他のエラー
                    self._handle_general_error(e, attempt)
        
        # すべての試行が失敗
        raise RuntimeError(
            f"文字起こしがすべての試行で失敗しました。"
            f"最後のエラー: {self.profile.metrics_history[-1].error_message if self.profile.metrics_history else 'Unknown'}"
        )
    
    def _transcribe_with_vad(
        self,
        video_path: FilePath,
        model_size: str = "large-v3",
        language: str | None = None,
        use_cache: bool = True,
        progress_callback: Callable[[float], None] | None = None,
    ) -> TranscriptionResult:
        """
        VADベースの文字起こし処理
        SmartBoundaryTranscriberのロジックをインフラ層に統合
        """
        # キャッシュチェック
        if use_cache:
            cached_result = self.load_from_cache(video_path, model_size)
            if cached_result:
                logger.info("VADベース処理: キャッシュから読み込みました")
                if progress_callback:
                    progress_callback("キャッシュから読み込み完了 (100%)")
                return cached_result
        
        from infrastructure.external.ffmpeg_vad_processor import FFmpegVADProcessor
        from core.auto_optimizer import AutoOptimizer
        from core.memory_monitor import MemoryMonitor
        from core.transcription import TranscriptionResult as CoreResult
        from core.transcription import TranscriptionSegment as CoreSegment
        import tempfile
        import shutil
        import os
        import subprocess
        
        start_time = datetime.now()
        
        # VADプロセッサーの初期化
        vad_processor = FFmpegVADProcessor()
        
        # オプティマイザーとメモリモニターの初期化
        optimizer = AutoOptimizer(model_size)
        memory_monitor = MemoryMonitor()
        
        # 一時ディレクトリ作成
        temp_dir = tempfile.mkdtemp(prefix="textffcut_vad_")
        
        try:
            if progress_callback:
                progress_callback("音声を抽出中... (5%)")
            
            # 全体の音声を抽出
            temp_audio = os.path.join(temp_dir, "audio.wav")
            extract_cmd = [
                "ffmpeg", "-y", "-i", str(video_path),
                "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
                temp_audio
            ]
            subprocess.run(extract_cmd, capture_output=True, check=True)
            
            if progress_callback:
                progress_callback("音声区間を検出中... (10%)")
            
            # VADベースでセグメントを検出
            segments = vad_processor.detect_segments(
                temp_audio,
                max_segment_duration=30.0,  # Whisperの制約
                min_segment_duration=5.0,
                silence_threshold=-35.0,
                min_silence_duration=0.3
            )
            
            logger.info(f"VADセグメント数: {len(segments)}")
            
            # 各セグメントを処理
            all_segments = []
            for i, (start, end) in enumerate(segments):
                if progress_callback:
                    base_progress = 0.2 + (0.7 * i / len(segments))
                    progress_callback(f"セグメント {i+1}/{len(segments)} を処理中... ({base_progress*100:.0f}%)")
                
                # セグメントを処理
                segment_results = self._process_vad_segment(
                    video_path=str(video_path),
                    start=start,
                    end=end,
                    model_size=model_size,
                    segment_index=i,
                    optimizer=optimizer,
                    memory_monitor=memory_monitor,
                    temp_dir=temp_dir,
                    language=language
                )
                all_segments.extend(segment_results)
            
            # CoreResultをドメインのTranscriptionResultに変換
            domain_result = self._convert_to_domain_result(
                all_segments,
                language or self.config.transcription.language,
                str(video_path),
                model_size,
                (datetime.now() - start_time).total_seconds()
            )
            
            if progress_callback:
                progress_callback("処理完了 (100%)")
            
            # キャッシュに保存（新規文字起こしの場合）
            # use_cacheがTrueでもキャッシュから読み込めなかった場合は新規実行なので保存する
            self.save_to_cache(video_path, model_size, domain_result)
            logger.info("VADベースの文字起こし結果をキャッシュに保存しました")
            
            # 成功を記録
            processing_time = (datetime.now() - start_time).total_seconds()
            metrics = PerformanceMetrics(
                timestamp=datetime.now(),
                success=True,
                processing_time=processing_time,
                optimization_info={'vad_segments': len(segments)}
            )
            self.profile.add_metrics(metrics)
            self.profile_repository.save(self.profile)
            
            logger.info(f"VADベース文字起こし成功: {processing_time:.1f}秒")
            
            return domain_result
            
        except Exception as e:
            logger.error(f"VADベース文字起こしエラー: {e}")
            # エラー時は従来の処理にフォールバック
            return self._transcribe_legacy(
                video_path=video_path,
                model_size=model_size,
                language=language,
                use_cache=use_cache,
                progress_callback=progress_callback
            )
            
        finally:
            # クリーンアップ
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def _convert_to_domain_result(
        self,
        segments: list,
        language: str,
        video_path: str,
        model_size: str,
        processing_time: float
    ) -> TranscriptionResult:
        """CoreセグメントをドメインのTranscriptionResultに変換"""
        from domain.entities.transcription import TranscriptionResult as DomainResult
        from domain.entities.transcription import TranscriptionSegment as DomainSegment, Word, Char
        from domain.value_objects import FilePath, Duration, TimeRange
        
        domain_segments = []
        for seg in segments:
            # wordsの変換
            words = []
            if seg.words:
                for w in seg.words:
                    if isinstance(w, dict):
                        word = Word(
                            word=w.get('word', ''),
                            start=w.get('start', 0.0),
                            end=w.get('end', 0.0),
                            confidence=w.get('probability', 1.0)
                        )
                        words.append(word)
            
            # charsの変換
            chars = []
            if seg.chars:
                for c in seg.chars:
                    if isinstance(c, dict):
                        char = Char(
                            char=c.get('char', ''),
                            start=c.get('start', 0.0),
                            end=c.get('end', 0.0),
                            confidence=c.get('probability', 1.0)
                        )
                        chars.append(char)
            
            # セグメントの作成
            domain_segment = DomainSegment(
                id=str(seg.start),  # IDを生成
                text=seg.text,
                start=seg.start,
                end=seg.end,
                words=words,
                chars=chars
            )
            domain_segments.append(domain_segment)
        
        # TranscriptionResultの作成
        import uuid
        return DomainResult(
            id=str(uuid.uuid4()),
            video_id=str(uuid.uuid4()),
            segments=domain_segments,
            language=language,
            duration=max(seg.end for seg in domain_segments) if domain_segments else 0.0,
            original_audio_path=video_path,
            model_size=model_size,
            processing_time=processing_time
        )
    
    def _get_current_config(self) -> dict:
        """現在の処理設定を取得"""
        available_memory = psutil.virtual_memory().available / (1024**3)
        
        # AutoOptimizerで動的に決定されるため、デフォルト値を使用
        # VAD処理ではAutoOptimizerが各セグメントごとに最適値を決定
        # レガシー処理用のフォールバック値
        default_batch_size = 8 if available_memory >= 8 else 4
        
        config = {
            'batch_size': default_batch_size,
            'compute_type': self.profile.get_effective_compute_type(),
        }
        
        # メモリ制約時の自動調整
        if available_memory < 4 and config['batch_size'] > 2:
            config['batch_size'] = 2
            logger.warning(f"メモリ不足のためバッチサイズを調整: {config['batch_size']}")
        
        return config
    
    def _handle_memory_error(self, error: Exception, memory_type: str, attempt: int):
        """メモリエラーのハンドリング"""
        error_message = f"{memory_type}メモリ不足: {str(error)}"
        logger.warning(error_message)
        
        # エラーを記録
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            success=False,
            processing_time=0,
            error_message=error_message
        )
        self.profile.add_metrics(metrics)
        
        # 設定を調整
        # バッチサイズは完全に自動化されているため、compute_typeのみ調整
        self.profile.compute_type = 'int8'
        
        # optimization_preferenceは削除（常に最適化を実行）
        
        self.profile_repository.save(self.profile)
        
        # GPUメモリをクリア
        if memory_type == "GPU" and torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        # 最後の試行でなければ待機
        if attempt < self.max_retries - 1:
            time.sleep(2)
        else:
            raise
    
    def _handle_general_error(self, error: Exception, attempt: int):
        """一般的なエラーのハンドリング"""
        error_message = f"エラー: {type(error).__name__} - {str(error)}"
        logger.error(error_message)
        
        # エラーを記録
        metrics = PerformanceMetrics(
            timestamp=datetime.now(),
            success=False,
            processing_time=0,
            error_message=error_message
        )
        self.profile.add_metrics(metrics)
        self.profile_repository.save(self.profile)
        
        # 最後の試行でなければ再試行
        if attempt < self.max_retries - 1:
            time.sleep(1)
        else:
            raise
    
    def get_performance_profile(self) -> PerformanceProfile:
        """現在のパフォーマンスプロファイルを取得"""
        return self.profile
    
    def update_performance_profile(self, profile: PerformanceProfile):
        """パフォーマンスプロファイルを更新"""
        self.profile = profile
        self.profile_repository.save(profile)

    def __del__(self):
        """デストラクタ"""
        pass
