"""
FCPXMLエクスポートゲートウェイの実装

既存のFCPXMLExporterクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

from typing import List, Optional, Dict, Any
from pathlib import Path

from domain.value_objects import FilePath, TimeRange
from use_cases.interfaces import IFCPXMLExportGateway, ExportSegment, TimeMapper
from core.export import FCPXMLExporter as LegacyFCPXMLExporter
from core.export import ExportSegment as LegacyExportSegment
from core.video import VideoInfo
from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)


class FCPXMLTimeMapper(TimeMapper):
    """FCPXML用の時間マッピング実装"""
    
    def __init__(self, silence_ranges: List[TimeRange]):
        super().__init__(silence_ranges)
        self._build_mapping()
    
    def _build_mapping(self):
        """サイレンス範囲から時間マッピングを構築"""
        self.time_offset_map = []
        offset = 0.0
        
        if not self.silence_ranges:
            return
        
        # サイレンス範囲をソート
        sorted_ranges = sorted(self.silence_ranges, key=lambda r: r.start)
        
        for silence in sorted_ranges:
            # サイレンス開始までの時間はそのまま
            self.time_offset_map.append({
                'original_start': 0 if not self.time_offset_map else self.time_offset_map[-1]['original_end'],
                'original_end': silence.start,
                'offset': offset
            })
            # サイレンス分のオフセットを追加
            offset += silence.end - silence.start
        
        # 最後のサイレンス以降
        if self.time_offset_map:
            self.time_offset_map.append({
                'original_start': sorted_ranges[-1].end,
                'original_end': float('inf'),
                'offset': offset
            })
    
    def map_time_range(self, time_range: TimeRange) -> Optional[TimeRange]:
        """時間範囲をマッピング"""
        if not self.time_offset_map:
            return time_range
        
        # 開始時間と終了時間をマッピング
        mapped_start = self._map_time_point(time_range.start)
        mapped_end = self._map_time_point(time_range.end)
        
        if mapped_start is None or mapped_end is None:
            return None
        
        try:
            return TimeRange(mapped_start, mapped_end)
        except ValueError:
            return None
    
    def _map_time_point(self, time: float) -> Optional[float]:
        """単一の時間ポイントをマッピング"""
        for mapping in self.time_offset_map:
            if mapping['original_start'] <= time < mapping['original_end']:
                return time - mapping['offset']
        
        # 最後のマッピング以降の時間
        if self.time_offset_map and time >= self.time_offset_map[-1]['original_start']:
            return time - self.time_offset_map[-1]['offset']
        
        return None


class FCPXMLExportGatewayAdapter(IFCPXMLExportGateway):
    """
    FCPXMLエクスポートゲートウェイのアダプター実装
    
    既存のFCPXMLExporterクラスをラップし、ドメイン層のインターフェースに適合させます。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初期化
        
        Args:
            config: 設定オブジェクト（Noneの場合はデフォルト設定）
        """
        self._config = config or Config()
        self._legacy_exporter = LegacyFCPXMLExporter(self._config)
    
    def export(
        self,
        segments: List[ExportSegment],
        output_path: FilePath,
        project_name: str = "TextffCut Project",
        fps: float = 30.0,
        width: int = 1920,
        height: int = 1080,
        **options: Any
    ) -> None:
        """
        FCPXMLファイルをエクスポート
        
        Args:
            segments: エクスポートするセグメント
            output_path: 出力ファイルパス
            project_name: プロジェクト名
            fps: フレームレート
            width: 動画の幅
            height: 動画の高さ
        """
        try:
            # ドメインセグメントをレガシー形式に変換
            legacy_segments = []
            timeline_start = 0.0
            
            for segment in segments:
                legacy_segment = LegacyExportSegment(
                    source_path=str(segment.video_path),
                    start_time=segment.time_range.start,
                    end_time=segment.time_range.end,
                    timeline_start=timeline_start
                )
                legacy_segments.append(legacy_segment)
                timeline_start += segment.time_range.duration
            
            # レガシーメソッドを呼び出し
            success = self._legacy_exporter.export(
                segments=legacy_segments,
                output_path=str(output_path),
                timeline_fps=int(fps),
                project_name=project_name
            )
            
            if not success:
                raise RuntimeError("FCPXML export failed")
            
            logger.info(f"Exported FCPXML to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to export FCPXML: {e}")
            from use_cases.exceptions import ExportError
            raise ExportError(
                f"Failed to export FCPXML to {output_path}: {str(e)}",
                cause=e
            )
    
    def get_video_info(self, video_path: FilePath) -> Dict[str, Any]:
        """動画情報を取得"""
        try:
            info = VideoInfo.from_file(str(video_path))
            return {
                "path": info.path,
                "duration": info.duration,
                "fps": info.fps,
                "width": info.width,
                "height": info.height,
                "codec": info.codec
            }
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            return {
                "path": str(video_path),
                "error": str(e)
            }
    
    def generate_fcpxml(
        self,
        timeline_name: str,
        asset: Any,
        clips: List[Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        FCPXMLコンテンツを生成
        
        Note: この実装では簡易的にクリップ情報からFCPXMLを生成します。
        実際の実装では、レガシーのFCPXMLExporter._build_fcpxmlメソッドを
        活用する可能性があります。
        """
        # 簡易実装: 基本的なFCPXML構造を生成
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<fcpxml version="1.10">',
            '  <resources>',
        ]
        
        # アセット情報を追加
        if asset:
            xml_lines.append(f'    <asset id="{asset.id}" src="{asset.src}" format="{asset.format}"/>')
        
        xml_lines.extend([
            '  </resources>',
            '  <library>',
            '    <event name="Event">',
            f'      <project name="{timeline_name}">',
            '        <sequence>',
            '          <spine>',
        ])
        
        # クリップを追加
        for clip in clips:
            xml_lines.append(
                f'            <clip offset="{clip.offset}" ref="{clip.ref}" '
                f'duration="{clip.duration}" start="{clip.start}"/>'
            )
        
        xml_lines.extend([
            '          </spine>',
            '        </sequence>',
            '      </project>',
            '    </event>',
            '  </library>',
            '</fcpxml>'
        ])
        
        return '\n'.join(xml_lines)
    
    def create_time_mapper(self, silence_ranges: List[TimeRange]) -> TimeMapper:
        """時間マッピングユーティリティを作成"""
        return FCPXMLTimeMapper(silence_ranges)