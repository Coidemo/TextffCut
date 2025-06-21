"""
エクスポートサービス

FCPXML、EDL、その他の形式へのエクスポートビジネスロジックを提供。
"""

from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

from .base import BaseService, ServiceResult, ValidationError, ProcessingError
from config import Config
from core.export import FCPXMLExporter, XMEMLExporter, ExportSegment
from core import TranscriptionSegment as Segment, VideoSegment
from core.video import VideoInfo
from utils.file_utils import ensure_directory, get_safe_filename


class ExportService(BaseService):
    """エクスポート処理のビジネスロジック
    
    責任:
    - 各種フォーマットへのエクスポート
    - エクスポート設定の管理
    - メタデータの付与
    - エクスポートファイルの検証
    """
    
    def _initialize(self):
        """サービス固有の初期化"""
        self.fcpxml_exporter = FCPXMLExporter(self.config)
        self.xmeml_exporter = XMEMLExporter(self.config)
    
    def execute(self, **kwargs) -> ServiceResult:
        """汎用実行メソッド（export_fcpxmlにデリゲート）"""
        export_format = kwargs.get('format', 'fcpxml').lower()
        
        # formatパラメータを削除してから各メソッドに渡す
        kwargs_without_format = {k: v for k, v in kwargs.items() if k != 'format'}
        
        if export_format == 'fcpxml':
            return self.export_fcpxml(**kwargs_without_format)
        elif export_format == 'xmeml':
            return self.export_xmeml(**kwargs_without_format)
        else:
            return self.create_error_result(
                f"サポートされていないエクスポート形式: {export_format}",
                "ValidationError"
            )
    
    def export_fcpxml(
        self,
        video_path: str,
        segments: List[Union[Segment, VideoSegment, ExportSegment]],
        output_path: str,
        project_name: Optional[str] = None,
        event_name: Optional[str] = None,
        remove_silence: bool = False,
        video_output_path: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult:
        """FCPXMLエクスポート
        
        Args:
            video_path: 元動画のパス
            segments: エクスポートするセグメント
            output_path: 出力FCPXMLファイルパス
            project_name: プロジェクト名
            event_name: イベント名
            remove_silence: 無音削除フラグ
            video_output_path: 処理済み動画の出力パス
            metadata: 追加メタデータ
            
        Returns:
            ServiceResult: エクスポート結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not segments:
                raise ValidationError("エクスポートするセグメントがありません")
            
            # 出力ディレクトリを確保
            output_file = Path(output_path)
            ensure_directory(output_file.parent)
            
            # 動画情報を取得
            video_info = VideoInfo.from_file(str(video_file))
            
            # プロジェクト名とイベント名のデフォルト設定
            if not project_name:
                project_name = f"{video_file.stem}_編集"
            if not event_name:
                event_name = datetime.now().strftime("%Y-%m-%d")
            
            self.logger.info(
                f"FCPXMLエクスポート開始: {len(segments)} セグメント -> {output_file.name}"
            )
            
            # ExportSegmentに変換（video_pathを渡す）
            export_segments = self._convert_to_export_segments(segments, str(video_file))
            
            # FCPXMLエクスポート実行
            self.fcpxml_exporter.export(
                segments=export_segments,
                output_path=str(output_file),
                project_name=project_name
            )
            
            # エクスポートファイルの検証
            if not output_file.exists():
                raise ProcessingError("FCPXMLファイルの作成に失敗しました")
            
            # エクスポート結果の統計
            stats = self._calculate_export_stats(export_segments, video_info)
            
            result_metadata = {
                'format': 'FCPXML',
                'segments_count': len(export_segments),
                'total_duration': stats['total_duration'],
                'used_duration': stats['used_duration'],
                'usage_ratio': stats['usage_ratio'],
                'project_name': project_name,
                'event_name': event_name,
                'file_size': output_file.stat().st_size
            }
            
            # 追加メタデータがあれば統合
            if metadata:
                result_metadata.update(metadata)
            
            self.logger.info(
                f"FCPXMLエクスポート完了: {output_file.name} "
                f"({result_metadata['file_size'] / 1024:.1f}KB)"
            )
            
            return self.create_success_result(
                data={'output_path': str(output_file)},
                metadata=result_metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"FCPXMLエクスポートエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"FCPXMLエクスポート中にエラーが発生しました: {str(e)}")
            )
    
    def export_xmeml(
        self,
        video_path: str,
        segments: List[Union[Segment, VideoSegment, ExportSegment]],
        output_path: str,
        sequence_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> ServiceResult:
        """XMEMLエクスポート（Adobe Premiere Pro用）
        
        Args:
            video_path: 元動画のパス
            segments: エクスポートするセグメント
            output_path: 出力XMEMLファイルパス
            sequence_name: シーケンス名
            metadata: 追加メタデータ
            
        Returns:
            ServiceResult: エクスポート結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not segments:
                raise ValidationError("エクスポートするセグメントがありません")
            
            # 出力ディレクトリを確保
            output_file = Path(output_path)
            ensure_directory(output_file.parent)
            
            # 動画情報を取得
            video_info = VideoInfo.from_file(str(video_file))
            
            # シーケンス名のデフォルト設定
            if not sequence_name:
                sequence_name = f"{video_file.stem}_シーケンス"
            
            self.logger.info(
                f"XMEMLエクスポート開始: {len(segments)} セグメント -> {output_file.name}"
            )
            
            # ExportSegmentに変換（video_pathを渡す）
            export_segments = self._convert_to_export_segments(segments, str(video_file))
            
            # XMEMLエクスポート実行
            self.xmeml_exporter.export(
                segments=export_segments,
                output_path=str(output_file),
                project_name=sequence_name
            )
            
            # エクスポートファイルの検証
            if not output_file.exists():
                raise ProcessingError("XMEMLファイルの作成に失敗しました")
            
            # エクスポート結果の統計
            stats = self._calculate_export_stats(export_segments, video_info)
            
            result_metadata = {
                'format': 'XMEML',
                'segments_count': len(export_segments),
                'total_duration': stats['total_duration'],
                'used_duration': stats['used_duration'],
                'usage_ratio': stats['usage_ratio'],
                'sequence_name': sequence_name,
                'file_size': output_file.stat().st_size
            }
            
            # 追加メタデータがあれば統合
            if metadata:
                result_metadata.update(metadata)
            
            self.logger.info(
                f"XMEMLエクスポート完了: {output_file.name} "
                f"({result_metadata['file_size'] / 1024:.1f}KB)"
            )
            
            return self.create_success_result(
                data={'output_path': str(output_file)},
                metadata=result_metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"XMEMLエクスポートエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"XMEMLエクスポート中にエラーが発生しました: {str(e)}")
            )
    
    def export_edl(
        self,
        video_path: str,
        segments: List[Union[Segment, VideoSegment, ExportSegment]],
        output_path: str,
        title: Optional[str] = None,
        frame_rate: Optional[float] = None
    ) -> ServiceResult:
        """EDLエクスポート（Edit Decision List）
        
        Args:
            video_path: 元動画のパス
            segments: エクスポートするセグメント
            output_path: 出力EDLファイルパス
            title: タイトル
            frame_rate: フレームレート
            
        Returns:
            ServiceResult: エクスポート結果
        """
        try:
            # 入力検証
            video_file = self.validate_file_exists(video_path)
            if not segments:
                raise ValidationError("エクスポートするセグメントがありません")
            
            # 出力ディレクトリを確保
            output_file = Path(output_path)
            ensure_directory(output_file.parent)
            
            # 動画情報を取得
            video_info = VideoInfo.from_file(str(video_file))
            
            # フレームレートの設定
            if not frame_rate:
                frame_rate = video_info.fps
            
            # タイトルのデフォルト設定
            if not title:
                title = video_file.stem
            
            self.logger.info(
                f"EDLエクスポート開始: {len(segments)} セグメント -> {output_file.name}"
            )
            
            # EDLフォーマットで出力
            self._export_edl_format(
                segments=segments,
                output_file=output_file,
                title=title,
                frame_rate=frame_rate
            )
            
            # エクスポートファイルの検証
            if not output_file.exists():
                raise ProcessingError("EDLファイルの作成に失敗しました")
            
            result_metadata = {
                'format': 'EDL',
                'segments_count': len(segments),
                'title': title,
                'frame_rate': frame_rate,
                'file_size': output_file.stat().st_size
            }
            
            self.logger.info(
                f"EDLエクスポート完了: {output_file.name} "
                f"({result_metadata['file_size'] / 1024:.1f}KB)"
            )
            
            return self.create_success_result(
                data={'output_path': str(output_file)},
                metadata=result_metadata
            )
            
        except ValidationError as e:
            return self.wrap_error(e)
        except Exception as e:
            self.logger.error(f"EDLエクスポートエラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"EDLエクスポート中にエラーが発生しました: {str(e)}")
            )
    
    def validate_export_file(self, file_path: str, format: str) -> ServiceResult:
        """エクスポートファイルの検証
        
        Args:
            file_path: 検証するファイルパス
            format: ファイル形式
            
        Returns:
            ServiceResult: 検証結果
        """
        try:
            file = self.validate_file_exists(file_path)
            
            validation_result = {
                'valid': False,
                'errors': [],
                'warnings': []
            }
            
            if format.lower() == 'fcpxml':
                validation_result = self._validate_fcpxml(file)
            elif format.lower() == 'xmeml':
                validation_result = self._validate_xmeml(file)
            elif format.lower() == 'edl':
                validation_result = self._validate_edl(file)
            else:
                validation_result['errors'].append(
                    f"サポートされていない形式: {format}"
                )
            
            if validation_result['valid']:
                return self.create_success_result(
                    data=validation_result,
                    metadata={'file_path': str(file)}
                )
            else:
                return self.create_error_result(
                    f"検証エラー: {', '.join(validation_result['errors'])}",
                    "ValidationError",
                    metadata=validation_result
                )
            
        except Exception as e:
            self.logger.error(f"ファイル検証エラー: {e}", exc_info=True)
            return self.wrap_error(
                ProcessingError(f"ファイル検証中にエラーが発生しました: {str(e)}")
            )
    
    def _convert_to_export_segments(
        self,
        segments: List[Union[Segment, VideoSegment, ExportSegment]],
        video_path: str
    ) -> List[ExportSegment]:
        """セグメントをExportSegment形式に変換
        
        Args:
            segments: 変換元のセグメント
            
        Returns:
            ExportSegmentのリスト
        """
        export_segments = []
        timeline_position = 0.0
        
        for i, segment in enumerate(segments):
            if isinstance(segment, ExportSegment):
                export_segments.append(segment)
            elif isinstance(segment, (Segment, VideoSegment)):
                # 正しいパラメータ名で作成
                export_segment = ExportSegment(
                    source_path=video_path,
                    start_time=segment.start,
                    end_time=segment.end,
                    timeline_start=timeline_position
                )
                export_segments.append(export_segment)
                timeline_position += export_segment.duration
            else:
                # 辞書形式の場合
                start_time = segment.get('start', 0)
                end_time = segment.get('end', 0)
                export_segment = ExportSegment(
                    source_path=video_path,
                    start_time=start_time,
                    end_time=end_time,
                    timeline_start=timeline_position
                )
                export_segments.append(export_segment)
                timeline_position += export_segment.duration
        
        return export_segments
    
    def _calculate_export_stats(
        self,
        segments: List[ExportSegment],
        video_info: VideoInfo
    ) -> Dict[str, float]:
        """エクスポート統計を計算
        
        Args:
            segments: エクスポートセグメント
            video_info: 動画情報
            
        Returns:
            統計情報
        """
        # 使用される総時間
        used_duration = sum(seg.end_time - seg.start_time for seg in segments)
        
        # 動画の総時間
        total_duration = video_info.duration
        
        # 使用率
        usage_ratio = used_duration / total_duration if total_duration > 0 else 0
        
        return {
            'total_duration': total_duration,
            'used_duration': used_duration,
            'usage_ratio': usage_ratio
        }
    
    def _export_edl_format(
        self,
        segments: List[Any],
        output_file: Path,
        title: str,
        frame_rate: float
    ):
        """EDL形式でエクスポート
        
        Args:
            segments: セグメント
            output_file: 出力ファイル
            title: タイトル
            frame_rate: フレームレート
        """
        with open(output_file, 'w', encoding='utf-8') as f:
            # EDLヘッダー
            f.write(f"TITLE: {title}\n")
            f.write(f"FCM: NON-DROP FRAME\n\n")
            
            # 各セグメントをEDL形式で出力
            for i, segment in enumerate(segments, 1):
                # タイムコードに変換
                start_tc = self._seconds_to_timecode(segment.start, frame_rate)
                end_tc = self._seconds_to_timecode(segment.end, frame_rate)
                
                # EDLエントリ
                f.write(f"{i:03d}  001      V     C        ")
                f.write(f"{start_tc} {end_tc} ")
                f.write(f"{start_tc} {end_tc}\n")
                
                # コメント（テキスト）
                if hasattr(segment, 'text') and segment.text:
                    f.write(f"* FROM CLIP NAME: {segment.text[:50]}\n")
                
                f.write("\n")
    
    def _seconds_to_timecode(self, seconds: float, frame_rate: float) -> str:
        """秒数をタイムコードに変換
        
        Args:
            seconds: 秒数
            frame_rate: フレームレート
            
        Returns:
            タイムコード文字列（HH:MM:SS:FF）
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        frames = int((seconds % 1) * frame_rate)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d}:{frames:02d}"
    
    def _validate_fcpxml(self, file: Path) -> Dict[str, Any]:
        """FCPXMLファイルの検証
        
        Args:
            file: 検証するファイル
            
        Returns:
            検証結果
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        try:
            # XMLとして解析
            tree = ET.parse(file)
            root = tree.getroot()
            
            # 必須要素のチェック
            if root.tag != 'fcpxml':
                result['errors'].append("ルート要素がfcpxmlではありません")
                result['valid'] = False
            
            # バージョンチェック
            version = root.get('version')
            if not version:
                result['warnings'].append("バージョン情報がありません")
            
            # プロジェクト要素のチェック
            projects = root.findall('.//project')
            if not projects:
                result['errors'].append("プロジェクト要素がありません")
                result['valid'] = False
            
        except ET.ParseError as e:
            result['errors'].append(f"XML解析エラー: {e}")
            result['valid'] = False
        
        return result
    
    def _validate_xmeml(self, file: Path) -> Dict[str, Any]:
        """XMEMLファイルの検証
        
        Args:
            file: 検証するファイル
            
        Returns:
            検証結果
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        try:
            # XMLとして解析
            tree = ET.parse(file)
            root = tree.getroot()
            
            # 必須要素のチェック
            if root.tag != 'xmeml':
                result['errors'].append("ルート要素がxmemlではありません")
                result['valid'] = False
            
            # シーケンス要素のチェック
            sequences = root.findall('.//sequence')
            if not sequences:
                result['errors'].append("シーケンス要素がありません")
                result['valid'] = False
            
        except ET.ParseError as e:
            result['errors'].append(f"XML解析エラー: {e}")
            result['valid'] = False
        
        return result
    
    def _validate_edl(self, file: Path) -> Dict[str, Any]:
        """EDLファイルの検証
        
        Args:
            file: 検証するファイル
            
        Returns:
            検証結果
        """
        result = {'valid': True, 'errors': [], 'warnings': []}
        
        try:
            with open(file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 基本的な形式チェック
            if not lines:
                result['errors'].append("ファイルが空です")
                result['valid'] = False
                return result
            
            # タイトル行のチェック
            if not any(line.startswith('TITLE:') for line in lines[:5]):
                result['warnings'].append("タイトル行が見つかりません")
            
            # EDLエントリのチェック
            entry_count = 0
            for line in lines:
                # EDLエントリの基本パターン
                if line.strip() and line[0:3].strip().isdigit():
                    entry_count += 1
            
            if entry_count == 0:
                result['errors'].append("EDLエントリが見つかりません")
                result['valid'] = False
            
        except Exception as e:
            result['errors'].append(f"ファイル読み込みエラー: {e}")
            result['valid'] = False
        
        return result