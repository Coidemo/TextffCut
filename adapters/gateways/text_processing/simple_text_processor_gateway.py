"""
シンプルなテキスト処理ゲートウェイ

レガシーコードを使わず、ドメイン層のユースケースを直接使用する実装。
"""

from domain.entities import TextDifference, TranscriptionResult
from domain.use_cases.text_difference_detector import TextDifferenceDetector
from domain.use_cases.time_range_calculator import TimeRangeCalculator
from domain.value_objects import TimeRange
from use_cases.interfaces import ITextProcessorGateway
from utils.logging import get_logger

logger = get_logger(__name__)


class SimpleTextProcessorGateway(ITextProcessorGateway):
    """
    シンプルなテキスト処理ゲートウェイ
    
    レガシーコードに依存せず、クリーンな実装を提供。
    """
    
    def __init__(self):
        """初期化"""
        self._detector = TextDifferenceDetector()
        self._calculator = TimeRangeCalculator()
    
    def find_differences(
        self, original_text: str, edited_text: str, skip_normalization: bool = False
    ) -> TextDifference:
        """
        テキストの差分を検出
        
        Args:
            original_text: 元のテキスト
            edited_text: 編集後のテキスト
            skip_normalization: 正規化をスキップするか（現在は未使用）
            
        Returns:
            差分情報
        """
        logger.info(
            f"差分検出開始: 元{len(original_text)}文字, 編集{len(edited_text)}文字"
        )
        
        return self._detector.detect_differences(original_text, edited_text)
    
    def get_time_ranges_from_differences(
        self, differences: TextDifference, transcription: TranscriptionResult
    ) -> list[TimeRange]:
        """
        差分情報から時間範囲を取得
        
        Args:
            differences: 差分情報
            transcription: 文字起こし結果
            
        Returns:
            時間範囲のリスト
        """
        # TimeRangeCalculatorを使用して時間範囲を計算
        time_tuples = self._calculator.calculate_time_ranges(differences, transcription)
        
        # TimeRangeオブジェクトに変換
        time_ranges = [TimeRange(start=start, end=end) for start, end in time_tuples]
        
        return time_ranges
    
    def get_time_ranges(
        self, differences: TextDifference, transcription: TranscriptionResult
    ) -> list[tuple[float, float]]:
        """
        差分情報から時間範囲のタプルを取得（後方互換性）
        
        Args:
            differences: 差分情報
            transcription: 文字起こし結果
            
        Returns:
            時間範囲のタプルリスト
        """
        time_ranges = self.get_time_ranges_from_differences(differences, transcription)
        return [(tr.start, tr.end) for tr in time_ranges]
    
    def normalize_text(self, text: str) -> str:
        """
        テキストを正規化
        
        Args:
            text: 正規化するテキスト
            
        Returns:
            正規化されたテキスト
        """
        # 全角半角の統一など
        import unicodedata
        return unicodedata.normalize("NFKC", text)
    
    def split_into_sentences(self, text: str) -> list[str]:
        """
        テキストを文に分割
        
        Args:
            text: 分割するテキスト
            
        Returns:
            文のリスト
        """
        # 句点で分割
        sentences = []
        current = ""
        
        for char in text:
            current += char
            if char in "。！？":
                sentences.append(current.strip())
                current = ""
        
        if current.strip():
            sentences.append(current.strip())
        
        return sentences
    
    def find_differences_with_separator(
        self,
        source_text: str,
        target_text: str,
        transcription_result: TranscriptionResult,
        separator: str,
        skip_normalization: bool = False
    ) -> TextDifference:
        """
        セパレータ付きテキストの差分検出
        
        Args:
            source_text: 元のテキスト
            target_text: 対象テキスト
            transcription_result: 文字起こし結果
            separator: セパレータ
            skip_normalization: 正規化をスキップするか
            
        Returns:
            差分情報
        """
        # セパレータで分割して各セクションの差分を検出
        sections = self.split_text_by_separator(target_text, separator)
        
        # 現在は単純に全体の差分を検出
        return self._detector.detect_differences(source_text, target_text, transcription_result)
    
    def split_text_by_separator(self, text: str, separator: str) -> list[str]:
        """
        テキストをセパレータで分割
        
        Args:
            text: 分割するテキスト
            separator: セパレータ
            
        Returns:
            分割されたテキストのリスト
        """
        return [section.strip() for section in text.split(separator) if section.strip()]
    
    def remove_boundary_markers(self, text: str) -> str:
        """
        境界調整マーカーを削除
        
        Args:
            text: マーカーを削除するテキスト
            
        Returns:
            マーカーを削除したテキスト
        """
        # マーカーパターン: [<数値], [数値>]
        import re
        text = re.sub(r'\[<[\d.]+\]', '', text)
        text = re.sub(r'\[[\d.]+>\]', '', text)
        return text
    
    def extract_existing_markers(self, text: str) -> dict[str, dict[str, float]]:
        """
        既存のマーカー情報を抽出
        
        Args:
            text: マーカーを抽出するテキスト
            
        Returns:
            マーカー情報の辞書
        """
        import re
        markers = {}
        
        # パターン: [<開始値]テキスト[終了値>]
        pattern = r'\[<([\d.]+)\]([^[]+)\[([\d.]+)>\]'
        
        for match in re.finditer(pattern, text):
            start_val = float(match.group(1))
            content = match.group(2)
            end_val = float(match.group(3))
            
            markers[content] = {
                'start': start_val,
                'end': end_val
            }
        
        return markers
    
    def adjust_boundaries(
        self,
        video_path: str,
        time_ranges: list[tuple[float, float]],
        adjustments: dict[str, dict[str, float]]
    ) -> list[tuple[float, float]]:
        """
        境界を調整
        
        Args:
            video_path: 動画ファイルパス
            time_ranges: 時間範囲のリスト
            adjustments: 調整値の辞書
            
        Returns:
            調整された時間範囲のリスト
        """
        # 簡易実装：調整値を適用
        adjusted = []
        
        for i, (start, end) in enumerate(time_ranges):
            # 調整値があれば適用
            key = f"range_{i}"
            if key in adjustments:
                adj = adjustments[key]
                start += adj.get('start', 0)
                end += adj.get('end', 0)
            
            adjusted.append((start, end))
        
        return adjusted