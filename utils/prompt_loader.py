"""
プロンプトテンプレートローダー
"""

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PromptLoader:
    """プロンプトテンプレートを読み込んで処理するクラス"""
    
    def __init__(self, prompts_dir: Path | None = None):
        """
        初期化
        
        Args:
            prompts_dir: プロンプトファイルのディレクトリ
        """
        if prompts_dir is None:
            # プロジェクトルートからの相対パス
            self.prompts_dir = Path(__file__).parent.parent / "prompts"
        else:
            self.prompts_dir = Path(prompts_dir)
    
    def load_buzz_clip_prompt(self, transcription_segments: list[dict[str, Any]]) -> str:
        """
        バズクリップ生成用のプロンプトを読み込んで文字起こし結果を埋め込む
        
        Args:
            transcription_segments: 文字起こしセグメントのリスト
            
        Returns:
            完成したプロンプト
        """
        prompt_file = self.prompts_dir / "buzz_clip.md"
        
        if not prompt_file.exists():
            logger.error(f"Prompt file not found: {prompt_file}")
            raise FileNotFoundError(f"プロンプトファイルが見つかりません: {prompt_file}")
        
        # プロンプトテンプレートを読み込む
        with open(prompt_file, "r", encoding="utf-8") as f:
            template = f.read()
        
        # セグメントをフォーマット
        formatted_segments = self._format_segments(transcription_segments)
        
        # プレースホルダーを置き換え
        prompt = template.replace("{TRANSCRIPTION}", formatted_segments)
        
        return prompt
    
    def _format_segments(self, segments: list[dict[str, Any]]) -> str:
        """セグメントをフォーマット"""
        formatted_lines = []
        for seg in segments:
            time_str = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
            formatted_lines.append(f"{time_str} {seg['text']}")
        return "\n".join(formatted_lines)