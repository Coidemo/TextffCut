"""
UI用データ生成ユースケース

差分検出結果をUI表示用のデータ形式に変換する。
"""

from typing import List, Dict, Any, Optional, Tuple
from domain.entities.text_difference import DifferenceType
from domain.value_objects.lcs_match import DifferenceBlock
from utils.logging import get_logger

logger = get_logger(__name__)


class UIDataGenerator:
    """
    UI用データ生成ユースケース
    
    差分ブロックをStreamlitなどのUIで表示しやすい形式に変換する。
    """
    
    def generate_highlights(
        self, 
        original_text: str, 
        blocks: List[DifferenceBlock]
    ) -> List[Dict[str, Any]]:
        """
        ハイライト表示用データ生成
        
        Args:
            original_text: 元のテキスト
            blocks: 差分ブロックのリスト
            
        Returns:
            ハイライト表示用のデータリスト
        """
        highlights = []
        
        # ブロックを位置順にソート
        sorted_blocks = sorted(
            blocks, 
            key=lambda b: (b.original_start_pos or 0, b.original_end_pos or 0)
        )
        
        for block in sorted_blocks:
            highlight = {
                "type": block.type.value,
                "text": block.text,
                "char_count": len(block.text),
            }
            
            # 位置情報
            if block.original_start_pos is not None:
                highlight["start_pos"] = block.original_start_pos
                highlight["end_pos"] = block.original_end_pos
            
            # 時間情報
            if block.start_time is not None and block.end_time is not None:
                highlight["start_time"] = block.start_time
                highlight["end_time"] = block.end_time
                highlight["duration"] = block.duration
                highlight["time_display"] = self._format_time_range(
                    block.start_time, block.end_time
                )
            
            # CSSクラス
            highlight["css_class"] = self._get_css_class(block.type)
            
            # ツールチップ用の情報
            highlight["tooltip"] = self._generate_tooltip(block)
            
            highlights.append(highlight)
        
        logger.info(f"ハイライトデータを生成: {len(highlights)}個")
        return highlights
    
    def generate_deletion_summary(
        self, 
        deletion_blocks: List[DifferenceBlock]
    ) -> Dict[str, Any]:
        """
        削除確認モーダル用データ生成
        
        Args:
            deletion_blocks: 削除ブロックのリスト
            
        Returns:
            削除サマリーデータ
        """
        if not deletion_blocks:
            return {
                "has_deletions": False,
                "total_count": 0,
                "total_duration": 0.0,
                "groups": []
            }
        
        # 削除をカテゴリ分け
        filler_blocks = []
        short_blocks = []  # 0.5秒未満
        normal_blocks = []  # それ以外
        
        for block in deletion_blocks:
            if self._is_filler(block.text):
                filler_blocks.append(block)
            elif block.duration < 0.5:
                short_blocks.append(block)
            else:
                normal_blocks.append(block)
        
        # 合計時間
        total_duration = sum(b.duration for b in deletion_blocks if b.duration > 0)
        
        summary = {
            "has_deletions": True,
            "total_count": len(deletion_blocks),
            "total_duration": total_duration,
            "total_chars": sum(len(b.text) for b in deletion_blocks),
            "groups": []
        }
        
        # フィラーグループ
        if filler_blocks:
            summary["groups"].append({
                "type": "fillers",
                "label": "フィラー（えー、あのー等）",
                "count": len(filler_blocks),
                "duration": sum(b.duration for b in filler_blocks if b.duration > 0),
                "items": [self._block_to_item(b) for b in filler_blocks[:5]],  # 最初の5個
                "has_more": len(filler_blocks) > 5
            })
        
        # 短い削除グループ
        if short_blocks:
            summary["groups"].append({
                "type": "short",
                "label": "短い削除（0.5秒未満）",
                "count": len(short_blocks),
                "duration": sum(b.duration for b in short_blocks if b.duration > 0),
                "items": [self._block_to_item(b) for b in short_blocks[:5]],
                "has_more": len(short_blocks) > 5
            })
        
        # 通常の削除グループ
        if normal_blocks:
            summary["groups"].append({
                "type": "normal",
                "label": "その他の削除",
                "count": len(normal_blocks),
                "duration": sum(b.duration for b in normal_blocks if b.duration > 0),
                "items": [self._block_to_item(b) for b in normal_blocks],
                "has_more": False
            })
        
        logger.info(
            f"削除サマリー生成: {summary['total_count']}個の削除, "
            f"合計{summary['total_duration']:.1f}秒"
        )
        
        return summary
    
    def generate_progress_indicator(
        self,
        original_text: str,
        edited_text: str,
        blocks: List[DifferenceBlock]
    ) -> Dict[str, Any]:
        """
        編集進捗インジケーター用データ生成
        
        Args:
            original_text: 元のテキスト
            edited_text: 編集後のテキスト
            blocks: 差分ブロックのリスト
            
        Returns:
            進捗データ
        """
        unchanged_chars = sum(len(b.text) for b in blocks if b.type == DifferenceType.UNCHANGED)
        deleted_chars = sum(len(b.text) for b in blocks if b.type == DifferenceType.DELETED)
        added_chars = sum(len(b.text) for b in blocks if b.type == DifferenceType.ADDED)
        
        original_length = len(original_text)
        edited_length = len(edited_text)
        
        # 圧縮率
        compression_rate = (1 - edited_length / original_length) * 100 if original_length > 0 else 0
        
        # 時間情報
        time_blocks = [b for b in blocks if b.start_time is not None and b.end_time is not None]
        
        total_original_duration = 0
        total_edited_duration = 0
        
        if time_blocks:
            # 元の時間範囲
            min_time = min(b.start_time for b in time_blocks)
            max_time = max(b.end_time for b in time_blocks)
            total_original_duration = max_time - min_time
            
            # 編集後の時間（UNCHANGEDブロックのみ）
            unchanged_time_blocks = [b for b in time_blocks if b.type == DifferenceType.UNCHANGED]
            if unchanged_time_blocks:
                total_edited_duration = sum(b.duration for b in unchanged_time_blocks)
        
        time_compression_rate = (
            (1 - total_edited_duration / total_original_duration) * 100 
            if total_original_duration > 0 else 0
        )
        
        progress = {
            "original_length": original_length,
            "edited_length": edited_length,
            "compression_rate": compression_rate,
            "unchanged_chars": unchanged_chars,
            "deleted_chars": deleted_chars,
            "added_chars": added_chars,
            "total_original_duration": total_original_duration,
            "total_edited_duration": total_edited_duration,
            "time_compression_rate": time_compression_rate,
            "stats": {
                "unchanged_percentage": (unchanged_chars / original_length * 100) if original_length > 0 else 0,
                "deleted_percentage": (deleted_chars / original_length * 100) if original_length > 0 else 0,
                "added_percentage": (added_chars / edited_length * 100) if edited_length > 0 else 0,
            }
        }
        
        logger.info(
            f"進捗データ生成: {compression_rate:.1f}%圧縮 "
            f"(文字: {original_length}→{edited_length}, "
            f"時間: {total_original_duration:.1f}s→{total_edited_duration:.1f}s)"
        )
        
        return progress
    
    def _format_time_range(self, start: float, end: float) -> str:
        """時間範囲を表示用にフォーマット"""
        return f"{self._format_time(start)} - {self._format_time(end)}"
    
    def _format_time(self, seconds: float) -> str:
        """秒を mm:ss.s 形式にフォーマット"""
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}:{secs:05.2f}"
    
    def _get_css_class(self, diff_type: DifferenceType) -> str:
        """差分タイプに応じたCSSクラスを返す"""
        return {
            DifferenceType.UNCHANGED: "diff-unchanged",
            DifferenceType.DELETED: "diff-deleted",
            DifferenceType.ADDED: "diff-added"
        }.get(diff_type, "")
    
    def _generate_tooltip(self, block: DifferenceBlock) -> str:
        """ツールチップ用のテキストを生成"""
        parts = []
        
        if block.type == DifferenceType.UNCHANGED:
            parts.append("保持")
        elif block.type == DifferenceType.DELETED:
            parts.append("削除")
        elif block.type == DifferenceType.ADDED:
            parts.append("追加")
        
        # 文字数
        parts.append(f"{len(block.text)}文字")
        
        # 時間情報
        if block.start_time is not None and block.end_time is not None:
            parts.append(f"{block.duration:.1f}秒")
            parts.append(self._format_time_range(block.start_time, block.end_time))
        
        return " | ".join(parts)
    
    def _is_filler(self, text: str) -> bool:
        """フィラーかどうかを判定"""
        fillers = [
            "えー", "えーっと", "えっと", "あの", "あのー", "その", "そのー",
            "まあ", "ちょっと", "なんか", "こう", "ええ", "うーん", "んー",
            "あー", "うー", "おー"
        ]
        
        normalized = text.strip().replace("、", "").replace("。", "")
        return normalized in fillers
    
    def _block_to_item(self, block: DifferenceBlock) -> Dict[str, Any]:
        """ブロックをアイテム形式に変換"""
        item = {
            "text": block.text,
            "char_count": len(block.text),
            "is_filler": self._is_filler(block.text)
        }
        
        if block.start_time is not None and block.end_time is not None:
            item["start_time"] = block.start_time
            item["end_time"] = block.end_time
            item["duration"] = block.duration
            item["time_display"] = self._format_time_range(block.start_time, block.end_time)
        
        return item