"""
ワークフローサービス

複数のサービスを組み合わせた統合的なワークフローを提供。
"""

from typing import Optional, Dict, Any, List, Callable, Union
from pathlib import Path
from dataclasses import dataclass
import time

from .base import BaseService, ServiceResult, ValidationError, ProcessingError
from .transcription_service import TranscriptionService
from .text_editing_service import TextEditingService
from .video_processing_service import VideoProcessingService
from .export_service import ExportService
from config import Config
from core.models import TranscriptionResultV2
from core import TranscriptionSegment as Segment
from utils.file_utils import ensure_directory, get_safe_filename


@dataclass
class WorkflowSettings:
    """ワークフロー設定"""
    # 文字起こし設定
    model_size: str = "medium"
    use_api: bool = False
    api_key: Optional[str] = None
    language: str = "ja"
    use_cache: bool = True
    save_cache: bool = True
    
    # 無音削除設定
    remove_silence: bool = False
    silence_threshold: float = -35.0
    min_silence_duration: float = 0.3
    pad_start: float = 0.0
    pad_end: float = 0.0
    min_segment_duration: float = 0.3
    
    # エクスポート設定
    export_format: str = "fcpxml"
    output_dir: Optional[str] = None
    project_name: Optional[str] = None
    event_name: Optional[str] = None
    
    # 動画処理設定
    process_video: bool = False
    video_output_path: Optional[str] = None
    
    # その他の設定
    separated_mode: bool = False
    task_type: str = "full"


class WorkflowService(BaseService):
    """複数のサービスを組み合わせたワークフロー
    
    責任:
    - 複数サービスの協調
    - ワークフロー全体の進捗管理
    - トランザクション的な処理
    - エラーのロールバック
    """
    
    def _initialize(self):
        """サービス固有の初期化"""
        # 各サービスのインスタンスを作成
        self.transcription_service = TranscriptionService(self.config)
        self.text_editing_service = TextEditingService(self.config)
        self.video_processing_service = VideoProcessingService(self.config)
        self.export_service = ExportService(self.config)
        
        # 一時ファイル管理
        self.temp_files: List[Path] = []
    
    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド"""
        workflow_type = kwargs.get('workflow_type', 'complete')
        
        if workflow_type == 'complete':
            return self.complete_workflow(**kwargs)
        elif workflow_type == 'transcription_only':
            return self.transcription_only_workflow(**kwargs)
        elif workflow_type == 'export_only':
            return self.export_only_workflow(**kwargs)
        else:
            return self.create_error_result(
                f"サポートされていないワークフロー: {workflow_type}",
                "ValidationError"
            )
    
    def complete_workflow(
        self,
        video_path: str,
        edited_text: Optional[str] = None,
        settings: Optional[WorkflowSettings] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """完全なワークフロー（文字起こし→編集→無音削除→エクスポート）
        
        Args:
            video_path: 動画ファイルパス
            edited_text: 編集されたテキスト（Noneの場合は全セグメント使用）
            settings: ワークフロー設定
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: ワークフロー実行結果
        """
        start_time = time.time()
        
        try:
            # デフォルト設定
            if not settings:
                settings = WorkflowSettings()
            
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            
            # 進捗管理
            progress = WorkflowProgress(progress_callback)
            
            self.logger.info(f"完全ワークフロー開始: {video_file.name}")
            
            # Step 1: 文字起こし (0-40%)
            progress.update(0.0, "文字起こしを実行中...")
            
            transcription_result = self.transcription_service.execute(
                video_path=str(video_file),
                model_size=settings.model_size,
                use_api=settings.use_api,
                api_key=settings.api_key,
                language=settings.language,
                use_cache=settings.use_cache,
                save_cache=settings.save_cache,
                separated_mode=settings.separated_mode,
                task_type=settings.task_type,
                progress_callback=lambda p, m: progress.update(p * 0.4, f"文字起こし: {m}")
            )
            
            if not transcription_result.success:
                return transcription_result
            
            transcription_data: TranscriptionResult = transcription_result.data
            segments = transcription_data.segments
            
            # Step 2: テキスト編集/差分検出 (40-50%)
            if edited_text:
                progress.update(0.4, "差分を検出中...")
                
                diff_result = self.text_editing_service.find_differences(
                    original_segments=segments,
                    edited_text=edited_text
                )
                
                if not diff_result.success:
                    return diff_result
                
                segments = diff_result.data
                progress.update(0.5, f"差分検出完了: {len(segments)} セグメント")
            else:
                progress.update(0.5, "全セグメントを使用")
            
            # Step 3: 無音削除 (50-70%)
            if settings.remove_silence:
                progress.update(0.5, "無音部分を削除中...")
                
                silence_result = self.video_processing_service.remove_silence(
                    video_path=str(video_file),
                    segments=segments,
                    threshold=settings.silence_threshold,
                    min_silence_duration=settings.min_silence_duration,
                    pad_start=settings.pad_start,
                    pad_end=settings.pad_end,
                    min_segment_duration=settings.min_segment_duration,
                    progress_callback=lambda p, m: progress.update(0.5 + p * 0.2, f"無音削除: {m}")
                )
                
                if not silence_result.success:
                    return silence_result
                
                segments = silence_result.data
                progress.update(0.7, f"無音削除完了: {len(segments)} セグメント")
            else:
                progress.update(0.7, "無音削除をスキップ")
            
            # Step 4: 動画処理（オプション）(70-85%)
            video_output_path = None
            if settings.process_video and segments:
                progress.update(0.7, "動画を処理中...")
                
                # 動画の切り出しと結合
                video_result = self._process_video_segments(
                    video_file=video_file,
                    segments=segments,
                    settings=settings,
                    progress_callback=lambda p, m: progress.update(0.7 + p * 0.15, f"動画処理: {m}")
                )
                
                if not video_result.success:
                    return video_result
                
                video_output_path = video_result.data
                progress.update(0.85, "動画処理完了")
            
            # Step 5: エクスポート (85-100%)
            progress.update(0.85, f"{settings.export_format.upper()}をエクスポート中...")
            
            # 出力パスの決定
            output_path = self._determine_output_path(
                video_file, 
                settings.export_format,
                settings.output_dir
            )
            
            # エクスポート実行
            export_result = self.export_service.execute(
                format=settings.export_format,
                video_path=str(video_output_path or video_file),
                segments=segments,
                output_path=str(output_path),
                project_name=settings.project_name,
                event_name=settings.event_name,
                remove_silence=settings.remove_silence,
                video_output_path=video_output_path
            )
            
            if not export_result.success:
                return export_result
            
            progress.update(1.0, "完了！")
            
            # 実行時間を計算
            execution_time = time.time() - start_time
            
            # 最終的なメタデータを統合
            workflow_metadata = {
                'workflow_type': 'complete',
                'execution_time': execution_time,
                'steps_completed': {
                    'transcription': transcription_result.metadata,
                    'text_editing': diff_result.metadata if edited_text else None,
                    'silence_removal': silence_result.metadata if settings.remove_silence else None,
                    'video_processing': video_result.metadata if settings.process_video else None,
                    'export': export_result.metadata
                },
                'final_segments_count': len(segments),
                'output_files': {
                    'export': export_result.data['output_path'],
                    'video': video_output_path
                }
            }
            
            self.logger.info(
                f"完全ワークフロー完了: {execution_time:.1f}秒, "
                f"{len(segments)} セグメント"
            )
            
            return self.create_success_result(
                data=export_result.data,
                metadata=workflow_metadata
            )
            
        except Exception as e:
            self.logger.error(f"ワークフローエラー: {e}", exc_info=True)
            self._cleanup_temp_files()
            return self.wrap_error(
                ProcessingError(f"ワークフロー実行中にエラーが発生しました: {str(e)}")
            )
    
    def transcription_only_workflow(
        self,
        video_path: str,
        settings: Optional[WorkflowSettings] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """文字起こしのみのワークフロー
        
        Args:
            video_path: 動画ファイルパス
            settings: ワークフロー設定
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: 文字起こし結果
        """
        try:
            if not settings:
                settings = WorkflowSettings()
            
            self.logger.info("文字起こしのみワークフロー開始")
            
            # 文字起こし実行
            result = self.transcription_service.execute(
                video_path=video_path,
                model_size=settings.model_size,
                use_api=settings.use_api,
                api_key=settings.api_key,
                language=settings.language,
                use_cache=settings.use_cache,
                save_cache=settings.save_cache,
                separated_mode=settings.separated_mode,
                task_type="transcribe_only",
                progress_callback=progress_callback
            )
            
            if result.success:
                self.logger.info("文字起こしのみワークフロー完了")
            
            return result
            
        except Exception as e:
            self.logger.error(f"文字起こしワークフローエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"文字起こし実行中にエラーが発生しました: {str(e)}")
            )
    
    def export_only_workflow(
        self,
        video_path: str,
        segments: List[Segment],
        settings: Optional[WorkflowSettings] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """エクスポートのみのワークフロー
        
        Args:
            video_path: 動画ファイルパス
            segments: エクスポートするセグメント
            settings: ワークフロー設定
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: エクスポート結果
        """
        try:
            if not settings:
                settings = WorkflowSettings()
            
            video_file = self.validate_file_exists(video_path)
            
            if not segments:
                raise ValidationError("エクスポートするセグメントがありません")
            
            self.logger.info(f"エクスポートのみワークフロー開始: {len(segments)} セグメント")
            
            # 出力パスの決定
            output_path = self._determine_output_path(
                video_file,
                settings.export_format,
                settings.output_dir
            )
            
            # エクスポート実行
            result = self.export_service.execute(
                format=settings.export_format,
                video_path=str(video_file),
                segments=segments,
                output_path=str(output_path),
                project_name=settings.project_name,
                event_name=settings.event_name
            )
            
            if result.success:
                self.logger.info("エクスポートのみワークフロー完了")
            
            return result
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"エクスポートワークフローエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"エクスポート実行中にエラーが発生しました: {str(e)}")
            )
    
    def _process_video_segments(
        self,
        video_file: Path,
        segments: List[Segment],
        settings: WorkflowSettings,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> ServiceResult:
        """動画セグメントの処理（切り出しと結合）
        
        Args:
            video_file: 動画ファイル
            segments: 処理するセグメント
            settings: ワークフロー設定
            progress_callback: 進捗通知コールバック
            
        Returns:
            ServiceResult: 処理済み動画のパス
        """
        try:
            # 一時ディレクトリを作成
            temp_dir = self.temp_dir / f"workflow_{int(time.time())}"
            ensure_directory(temp_dir)
            self.temp_files.append(temp_dir)
            
            # セグメントごとに切り出し
            extract_result = self.video_processing_service.extract_segments(
                video_path=str(video_file),
                segments=segments,
                output_dir=str(temp_dir),
                progress_callback=lambda p, m: progress_callback(p * 0.7, m) if progress_callback else None
            )
            
            if not extract_result.success:
                return extract_result
            
            extracted_files = extract_result.data
            
            # 出力パスの決定
            if settings.video_output_path:
                output_path = settings.video_output_path
            else:
                output_name = f"{video_file.stem}_processed.mp4"
                output_path = str(video_file.parent / output_name)
            
            # 動画を結合
            merge_result = self.video_processing_service.merge_videos(
                video_files=extracted_files,
                output_path=output_path,
                progress_callback=lambda p, m: progress_callback(0.7 + p * 0.3, m) if progress_callback else None
            )
            
            if not merge_result.success:
                return merge_result
            
            return self.create_success_result(
                data=output_path,
                metadata={
                    'segments_processed': len(segments),
                    'output_path': output_path
                }
            )
            
        except Exception as e:
            self.logger.error(f"動画処理エラー: {e}", exc_info=True)
            raise
    
    def _determine_output_path(
        self,
        video_file: Path,
        export_format: str,
        output_dir: Optional[str] = None
    ) -> Path:
        """出力パスを決定
        
        Args:
            video_file: 元動画ファイル
            export_format: エクスポート形式
            output_dir: 出力ディレクトリ（オプション）
            
        Returns:
            出力パス
        """
        # 拡張子マッピング
        extension_map = {
            'fcpxml': '.fcpxml',
            'xmeml': '.xml',
            'edl': '.edl',
            'srt': '.srt'
        }
        
        extension = extension_map.get(export_format.lower(), '.xml')
        
        # 出力ディレクトリ
        if output_dir:
            output_path = Path(output_dir)
        else:
            output_path = video_file.parent / "output"
        
        ensure_directory(output_path)
        
        # ファイル名
        output_name = f"{video_file.stem}_export{extension}"
        
        # 重複を避ける
        final_path = output_path / output_name
        counter = 1
        while final_path.exists():
            output_name = f"{video_file.stem}_export_{counter}{extension}"
            final_path = output_path / output_name
            counter += 1
        
        return final_path
    
    def _cleanup_temp_files(self):
        """一時ファイルのクリーンアップ"""
        for temp_file in self.temp_files:
            try:
                if temp_file.is_dir():
                    import shutil
                    shutil.rmtree(temp_file)
                elif temp_file.exists():
                    temp_file.unlink()
            except Exception as e:
                self.logger.warning(f"一時ファイル削除エラー: {temp_file}, {e}")
        
        self.temp_files.clear()


class WorkflowProgress:
    """ワークフロー進捗管理"""
    
    def __init__(self, callback: Optional[Callable[[float, str], None]] = None):
        self.callback = callback
        self.current_progress = 0.0
        self.current_message = ""
    
    def update(self, progress: float, message: str):
        """進捗を更新
        
        Args:
            progress: 進捗率（0.0-1.0）
            message: 進捗メッセージ
        """
        self.current_progress = max(0.0, min(1.0, progress))
        self.current_message = message
        
        if self.callback:
            self.callback(self.current_progress, self.current_message)