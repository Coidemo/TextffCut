"""
最適化された文字起こしゲートウェイの実装

音声最適化とエラー回復機能を統合した文字起こしゲートウェイ
"""

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Optional

import psutil
import torch

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
        
        # モデルキャッシュの初期化
        self._model_cache = {
            'whisper': None,
            'whisper_params': {},
            'align': None,
            'align_language': None
        }
        # キャッシュ統計
        self._cache_stats = {
            'whisper_hits': 0,
            'whisper_misses': 0,
            'align_hits': 0,
            'align_misses': 0
        }
    
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
        # VADベース処理を使用するかどうかのフラグ
        use_vad_processing = getattr(self.config.transcription, 'use_vad_processing', False)
        
        if use_vad_processing and not self.config.transcription.use_api:
            # VADベースの処理を使用
            return self._transcribe_with_vad(
                video_path=video_path,
                model_size=model_size,
                language=language,
                use_cache=use_cache,
                progress_callback=progress_callback
            )
        else:
            # 従来の処理を使用
            return self._transcribe_legacy(
                video_path=video_path,
                model_size=model_size,
                language=language,
                use_cache=use_cache,
                progress_callback=progress_callback
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
                
            except torch.cuda.OutOfMemoryError as e:
                # GPUメモリエラー
                self._handle_memory_error(e, "GPU", attempt)
                
            except MemoryError as e:
                # システムメモリエラー
                self._handle_memory_error(e, "System", attempt)
                
            except Exception as e:
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
            
            # キャッシュ統計をログに出力
            total_whisper = self._cache_stats['whisper_hits'] + self._cache_stats['whisper_misses']
            total_align = self._cache_stats['align_hits'] + self._cache_stats['align_misses']
            
            if total_whisper > 0:
                whisper_hit_rate = self._cache_stats['whisper_hits'] / total_whisper * 100
                logger.info(f"Whisperモデルキャッシュ: {self._cache_stats['whisper_hits']}ヒット/{total_whisper}回 (ヒット率: {whisper_hit_rate:.1f}%)")
            
            if total_align > 0:
                align_hit_rate = self._cache_stats['align_hits'] / total_align * 100
                logger.info(f"アライメントモデルキャッシュ: {self._cache_stats['align_hits']}ヒット/{total_align}回 (ヒット率: {align_hit_rate:.1f}%)")
            
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

    def _get_cached_whisper_model(self, model_size: str, device: str, compute_type: str, language: str):
        """Whisperモデルのキャッシュ管理"""
        params = {
            'model_size': model_size,
            'device': device,
            'compute_type': compute_type,
            'language': language
        }
        
        # キャッシュが有効か確認
        if (self._model_cache['whisper'] is None or 
            self._model_cache['whisper_params'] != params):
            
            # 古いモデルをクリア
            if self._model_cache['whisper'] is not None:
                del self._model_cache['whisper']
                if device == 'cuda':
                    torch.cuda.empty_cache()
            
            # 新しいモデルを読み込み
            logger.info(f"Whisperモデルを読み込み中: {model_size}, {compute_type}")
            import whisperx
            self._model_cache['whisper'] = whisperx.load_model(
                model_size, device, 
                compute_type=compute_type, 
                language=language
            )
            self._model_cache['whisper_params'] = params.copy()
            self._cache_stats['whisper_misses'] += 1
        else:
            logger.debug(f"Whisperモデルをキャッシュから使用")
            self._cache_stats['whisper_hits'] += 1
        
        return self._model_cache['whisper']
    
    def _get_cached_align_model(self, language: str, device: str):
        """アライメントモデルのキャッシュ管理"""
        if (self._model_cache['align'] is None or 
            self._model_cache['align_language'] != language):
            
            # 古いモデルをクリア
            if self._model_cache['align'] is not None:
                del self._model_cache['align'][0]  # align_model
                del self._model_cache['align'][1]  # metadata
                if device == 'cuda':
                    torch.cuda.empty_cache()
            
            # 新しいモデルを読み込み
            logger.info(f"アライメントモデルを読み込み中: {language}")
            import whisperx
            align_model, metadata = whisperx.load_align_model(
                language_code=language, device=device
            )
            self._model_cache['align'] = (align_model, metadata)
            self._model_cache['align_language'] = language
            self._cache_stats['align_misses'] += 1
        else:
            logger.debug(f"アライメントモデルをキャッシュから使用")
            self._cache_stats['align_hits'] += 1
        
        return self._model_cache['align']
    
    def _clear_model_cache(self):
        """キャッシュをクリア"""
        logger.info("モデルキャッシュをクリア")
        
        if self._model_cache['whisper'] is not None:
            del self._model_cache['whisper']
            self._model_cache['whisper'] = None
            self._model_cache['whisper_params'] = {}
        
        if self._model_cache['align'] is not None:
            # タプル全体を削除（タプルの個別要素は削除できない）
            del self._model_cache['align']
            self._model_cache['align'] = None
            self._model_cache['align_language'] = None
        
        # GPUメモリもクリア
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def _process_vad_segment(
        self,
        video_path: str,
        start: float,
        end: float,
        model_size: str,
        segment_index: int,
        optimizer,
        memory_monitor,
        temp_dir: str,
        language: str | None = None
    ) -> list:
        """VADセグメントを処理"""
        import whisperx
        import subprocess
        import os
        from core.transcription import TranscriptionSegment as CoreSegment
        
        # 動的メモリ最適化
        current_memory = memory_monitor.get_memory_usage()
        optimal_params = optimizer.get_optimal_params(current_memory)
        
        logger.info(
            f"セグメント {segment_index} - メモリ: {current_memory:.1f}%, "
            f"バッチサイズ: {optimal_params['batch_size']}, "
            f"compute_type: {optimal_params['compute_type']}"
        )
        
        # セグメントのWAVファイルを作成
        segment_wav = os.path.join(temp_dir, f"segment_{segment_index}.wav")
        
        # FFmpegで音声を抽出
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-i", video_path,
            "-t", str(end - start), "-vn", "-ar", "16000", "-ac", "1",
            "-f", "wav", segment_wav
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        
        try:
            # WhisperXで処理
            audio = whisperx.load_audio(segment_wav)
            
            # デバイスの設定
            device = "cuda" if torch.cuda.is_available() else "cpu"
            
            # キャッシュされたモデルを取得
            lang = language or self.config.transcription.language
            model = self._get_cached_whisper_model(
                model_size=model_size,
                device=device,
                compute_type=optimal_params['compute_type'],
                language=lang
            )
            
            # 文字起こし
            result = model.transcribe(
                audio, 
                batch_size=optimal_params['batch_size'], 
                language=lang
            )
            
            # アライメント処理
            try:
                # キャッシュされたアライメントモデルを取得
                align_model, metadata = self._get_cached_align_model(
                    language=lang,
                    device=device
                )
                
                aligned_result = whisperx.align(
                    result["segments"], align_model, metadata, audio, device,
                    return_char_alignments=True
                )
                segments_data = aligned_result["segments"]
            except Exception as e:
                logger.warning(f"アライメント処理に失敗: {e}")
                segments_data = result["segments"]
            
            # セグメントを変換（オフセット適用）
            segments = []
            for seg in segments_data:
                segment = CoreSegment(
                    start=seg["start"] + start,
                    end=seg["end"] + start,
                    text=seg["text"],
                    words=seg.get("words"),
                    chars=seg.get("chars")
                )
                segments.append(segment)
            
            # メモリが非常に逼迫している場合のみキャッシュをクリア
            if current_memory > 90:
                logger.warning(f"メモリ使用率が非常に高い: {current_memory:.1f}% - キャッシュをクリア")
                self._clear_model_cache()
                
            return segments
            
        finally:
            # セグメントファイルを削除
            if os.path.exists(segment_wav):
                os.unlink(segment_wav)
    
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
        if memory_type == "GPU" and torch.cuda.is_available():
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
        """デストラクタ：インスタンス破棄時にキャッシュをクリア"""
        try:
            self._clear_model_cache()
        except Exception as e:
            # デストラクタ内でのエラーは無視
            pass
