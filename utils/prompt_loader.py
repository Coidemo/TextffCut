"""
プロンプトテンプレートローダー
"""

import logging
import shutil
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
            
        # プロンプトファイルの初期化（Docker環境でのみ必要）
        self._initialize_prompts()
    
    def load_buzz_clip_prompt(self, transcription_segments: list[dict[str, Any]]) -> str:
        """
        バズクリップ生成用のプロンプトを読み込んで文字起こし結果を埋め込む
        
        Args:
            transcription_segments: 文字起こしセグメントのリスト
            
        Returns:
            完成したプロンプト
        """
        # 初期化処理を再実行（念のため）
        self._initialize_prompts()
        
        prompt_file = self.prompts_dir / "clip_suggestions.md"
        
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
    
    def load_title_generation_prompt(self, edited_text: str) -> str:
        """
        タイトル生成用のプロンプトを読み込んで編集テキストを埋め込む
        
        Args:
            edited_text: 編集された切り抜きテキスト
            
        Returns:
            完成したプロンプト
        """
        # 初期化処理を再実行（念のため）
        self._initialize_prompts()
        
        prompt_file = self.prompts_dir / "title_generation.md"
        
        if not prompt_file.exists():
            logger.error(f"Prompt file not found: {prompt_file}")
            raise FileNotFoundError(f"プロンプトファイルが見つかりません: {prompt_file}")
        
        # プロンプトテンプレートを読み込む
        with open(prompt_file, "r", encoding="utf-8") as f:
            template = f.read()
        
        # プレースホルダーを置き換え
        prompt = template.replace("{EDITED_TEXT}", edited_text)
        
        return prompt
    
    def _initialize_prompts(self):
        """
        プロンプトファイルを初期化（存在しない場合はデフォルトからコピー）
        """
        # プロンプトディレクトリが存在しない場合は作成
        if not self.prompts_dir.exists():
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created prompts directory: {self.prompts_dir}")
        
        # 必要なプロンプトファイルのリスト
        prompt_files = ["clip_suggestions.md", "title_generation.md"]
        
        # Docker環境でのデフォルトプロンプトディレクトリ
        default_prompts_dir = Path("/app/default_prompts")
        
        for filename in prompt_files:
            target_file = self.prompts_dir / filename
            
            # ファイルが存在しない場合
            if not target_file.exists():
                # デフォルトプロンプトディレクトリから試す
                if default_prompts_dir.exists():
                    source_file = default_prompts_dir / filename
                    if source_file.exists():
                        try:
                            shutil.copy2(source_file, target_file)
                            logger.info(f"Copied default prompt file: {filename}")
                            continue
                        except Exception as e:
                            logger.error(f"Failed to copy default prompt file {filename}: {e}")
                
                # デフォルトが利用できない場合は、基本的な内容を作成
                logger.warning(f"Creating basic prompt file: {filename}")
                logger.warning("Note: This is a basic template. For better results, please provide a complete prompt file.")
                try:
                    if filename == "clip_suggestions.md":
                        # より完全な基本プロンプト
                        basic_content = """# バズクリップ候補生成

以下の文字起こしから、バズりそうな切り抜き候補を10個生成してください。

## 文字起こし内容
{TRANSCRIPTION}

## 生成条件
- 各候補は150-250文字程度
- エンタメ性の高い内容を優先
- 視聴者の興味を引くタイトル案も提案

## 出力フォーマット
各候補について以下の形式で出力してください：
- タイトル案：
- 内容要約：
- 開始時刻：
- 終了時刻：
"""
                        target_file.write_text(basic_content, encoding="utf-8")
                    elif filename == "title_generation.md":
                        # より完全な基本プロンプト
                        basic_content = """# タイトル生成

以下の切り抜きテキストから、魅力的なタイトルを生成してください。

## 切り抜きテキスト
{EDITED_TEXT}

## タイトル生成条件
- 20-40文字程度
- クリックしたくなる魅力的な表現
- 内容を正確に表現
- 5個のタイトル案を提案

## 出力フォーマット
1. [タイトル案1]
2. [タイトル案2]
3. [タイトル案3]
4. [タイトル案4]
5. [タイトル案5]
"""
                        target_file.write_text(basic_content, encoding="utf-8")
                except Exception as e:
                    logger.error(f"Failed to create basic prompt file {filename}: {e}")