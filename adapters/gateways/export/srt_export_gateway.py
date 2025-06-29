"""
SRT字幕エクスポートゲートウェイの実装

既存のSRTExporterクラスをラップし、クリーンアーキテクチャのインターフェースを提供します。
"""

from typing import List, Optional, Tuple
from pathlib import Path

from domain.entities import TranscriptionResult
from domain.value_objects import FilePath, TimeRange
from use_cases.interfaces import ISRTExportGateway
from core.srt_exporter import SRTExporter as LegacySRTExporter
from core.transcription import TranscriptionResult as LegacyTranscriptionResult
from core.transcription import TranscriptionSegment as LegacyTranscriptionSegment
from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)


class SRTExportGatewayAdapter(ISRTExportGateway):
    """
    SRT字幕エクスポートゲートウェイのアダプター実装
    
    既存のSRTExporterクラスをラップし、ドメイン層のインターフェースに適合させます。
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        初期化
        
        Args:
            config: 設定オブジェクト（Noneの場合はデフォルト設定）
        """
        self._config = config or Config()
        self._legacy_exporter = LegacySRTExporter(self._config)
    
    def export_from_transcription(
        self,
        transcription_result: TranscriptionResult,
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2,
        min_duration: float = 0.5,
        max_duration: float = 7.0
    ) -> None:
        """
        文字起こし結果からSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
            min_duration: 最小表示時間（秒）
            max_duration: 最大表示時間（秒）
        """
        try:
            # ドメインエンティティをレガシー形式に変換
            legacy_transcription = self._convert_to_legacy_transcription(transcription_result)
            
            # レガシーメソッドを呼び出し
            success = self._legacy_exporter.export(
                transcription=legacy_transcription,
                output_path=str(output_path),
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines,
                min_duration=min_duration,
                max_duration=max_duration
            )
            
            if not success:
                raise RuntimeError("SRT export failed")
            
            logger.info(f"Exported SRT to {output_path}")
            
        except Exception as e:
            logger.error(f"Failed to export SRT: {e}")
            from use_cases.exceptions import ExportError
            raise ExportError(
                f"Failed to export SRT to {output_path}: {str(e)}",
                cause=e
            )
    
    def export_from_diff(
        self,
        transcription_result: TranscriptionResult,
        time_ranges: List[TimeRange],
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2,
        min_duration: float = 0.5,
        max_duration: float = 7.0
    ) -> None:
        """
        差分結果からSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            time_ranges: 出力する時間範囲
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
            min_duration: 最小表示時間（秒）
            max_duration: 最大表示時間（秒）
        """
        try:
            # 時間範囲に含まれるセグメントをフィルタリング
            filtered_segments = []
            
            for segment in transcription_result.segments:
                # セグメントが時間範囲内にあるかチェック
                segment_range = TimeRange(segment.start, segment.end)
                for time_range in time_ranges:
                    if self._ranges_overlap(segment_range, time_range):
                        filtered_segments.append(segment)
                        break
            
            # フィルタリングされた結果で新しいTranscriptionResultを作成
            filtered_result = TranscriptionResult(
                id=transcription_result.id,
                language=transcription_result.language,
                segments=filtered_segments,
                original_audio_path=transcription_result.original_audio_path,
                model_size=transcription_result.model_size,
                processing_time=transcription_result.processing_time,
                metadata=transcription_result.metadata
            )
            
            # 通常のエクスポートを実行
            self.export_from_transcription(
                transcription_result=filtered_result,
                output_path=output_path,
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines,
                min_duration=min_duration,
                max_duration=max_duration
            )
            
        except Exception as e:
            logger.error(f"Failed to export SRT from diff: {e}")
            from use_cases.exceptions import ExportError
            raise ExportError(
                f"Failed to export SRT from diff to {output_path}: {str(e)}",
                cause=e
            )
    
    def export_with_time_mapping(
        self,
        transcription_result: TranscriptionResult,
        time_mapping: List[Tuple[TimeRange, TimeRange]],
        output_path: FilePath,
        max_chars_per_line: int = 21,
        max_lines: int = 2
    ) -> None:
        """
        時間マッピングを適用してSRT字幕をエクスポート
        
        Args:
            transcription_result: 文字起こし結果
            time_mapping: 元の時間→新しい時間のマッピング
            output_path: 出力ファイルパス
            max_chars_per_line: 1行の最大文字数
            max_lines: 最大行数
        """
        try:
            # 時間マッピングを適用してセグメントを調整
            adjusted_segments = []
            
            for segment in transcription_result.segments:
                segment_range = TimeRange(segment.start, segment.end)
                
                # マッピングを適用
                for original_range, mapped_range in time_mapping:
                    if self._ranges_overlap(segment_range, original_range):
                        # オーバーラップしている部分を計算
                        overlap_start = max(segment.start, original_range.start)
                        overlap_end = min(segment.end, original_range.end)
                        
                        # マッピングされた時間を計算
                        offset_in_original = overlap_start - original_range.start
                        duration_ratio = mapped_range.duration / original_range.duration
                        mapped_start = mapped_range.start + offset_in_original * duration_ratio
                        mapped_duration = (overlap_end - overlap_start) * duration_ratio
                        mapped_end = mapped_start + mapped_duration
                        
                        # 新しいセグメントを作成
                        adjusted_segment = type(segment)(
                            id=segment.id,
                            text=segment.text,
                            start=mapped_start,
                            end=mapped_end,
                            words=segment.words,
                            chars=segment.chars
                        )
                        adjusted_segments.append(adjusted_segment)
                        break
            
            # 調整されたセグメントで新しいTranscriptionResultを作成
            adjusted_result = TranscriptionResult(
                id=transcription_result.id,
                language=transcription_result.language,
                segments=adjusted_segments,
                original_audio_path=transcription_result.original_audio_path,
                model_size=transcription_result.model_size,
                processing_time=transcription_result.processing_time,
                metadata=transcription_result.metadata
            )
            
            # 通常のエクスポートを実行
            self.export_from_transcription(
                transcription_result=adjusted_result,
                output_path=output_path,
                max_chars_per_line=max_chars_per_line,
                max_lines=max_lines
            )
            
        except Exception as e:
            logger.error(f"Failed to export SRT with time mapping: {e}")
            from use_cases.exceptions import ExportError
            raise ExportError(
                f"Failed to export SRT with time mapping to {output_path}: {str(e)}",
                cause=e
            )
    
    def _convert_to_legacy_transcription(
        self,
        transcription: TranscriptionResult
    ) -> LegacyTranscriptionResult:
        """ドメインの文字起こし結果をレガシー形式に変換"""
        # セグメントの変換
        legacy_segments = []
        for segment in transcription.segments:
            # Wordsの変換
            words = None
            if segment.words:
                words = [
                    {
                        "word": w.word,
                        "start": w.start,
                        "end": w.end,
                        "confidence": w.confidence
                    }
                    for w in segment.words
                ]
            
            # Charsの変換
            chars = None
            if segment.chars:
                chars = [
                    {
                        "char": c.char,
                        "start": c.start,
                        "end": c.end,
                        "confidence": c.confidence
                    }
                    for c in segment.chars
                ]
            
            legacy_segment = LegacyTranscriptionSegment(
                start=segment.start,
                end=segment.end,
                text=segment.text,
                words=words,
                chars=chars
            )
            legacy_segments.append(legacy_segment)
        
        return LegacyTranscriptionResult(
            language=transcription.language,
            segments=legacy_segments,
            original_audio_path=transcription.original_audio_path,
            model_size=transcription.model_size,
            processing_time=transcription.processing_time
        )
    
    def _ranges_overlap(self, range1: TimeRange, range2: TimeRange) -> bool:
        """2つの時間範囲が重なっているかチェック"""
        return range1.start < range2.end and range2.start < range1.end