"""
ChatGPT連携サービス
文字起こし結果や切り抜き箇所をChatGPTに送信するための機能を提供
"""
import urllib.parse
from typing import Optional, List, Dict
from dataclasses import dataclass
from enum import Enum


class PromptTemplate(Enum):
    """プロンプトテンプレートの種類"""
    VIRAL_CLIP = "viral_clip"
    TITLE_SUGGESTION = "title_suggestion"
    SUMMARY = "summary"
    CUSTOM = "custom"


@dataclass
class ChatGPTPromptConfig:
    """ChatGPTプロンプトの設定"""
    template: PromptTemplate
    custom_prompt: Optional[str] = None
    include_context: bool = True
    max_text_length: int = 4000  # ChatGPTのURL制限を考慮


class ChatGPTService:
    """ChatGPT連携サービス"""
    
    # プロンプトテンプレート
    PROMPT_TEMPLATES = {
        PromptTemplate.VIRAL_CLIP: """以下の動画の文字起こし内容から、バズりそうな切り抜き案を5つ提案してください。
各提案には以下を含めてください：
1. 切り抜きタイトル案
2. なぜバズる可能性があるか
3. 推奨される切り抜き箇所（開始と終了の文章）

文字起こし内容：
{text}""",
        
        PromptTemplate.TITLE_SUGGESTION: """以下の切り抜き内容に対して、魅力的でクリックされやすいタイトルを10個提案してください。
タイトルは以下の要素を考慮してください：
- 興味を引く
- 内容が分かりやすい
- 30文字以内

切り抜き内容：
{text}""",
        
        PromptTemplate.SUMMARY: """以下の内容を簡潔に要約してください。重要なポイントを箇条書きでまとめてください。

内容：
{text}""",
    }
    
    def __init__(self):
        self.chatgpt_url = "https://chat.openai.com/chat"
    
    def create_prompt(self, text: str, config: ChatGPTPromptConfig) -> str:
        """プロンプトを作成する
        
        Args:
            text: 対象テキスト
            config: プロンプト設定
            
        Returns:
            作成されたプロンプト
        """
        # テキストの長さを制限
        if len(text) > config.max_text_length:
            text = text[:config.max_text_length] + "...\n（以下省略）"
        
        if config.template == PromptTemplate.CUSTOM:
            # カスタムプロンプトの場合
            if not config.custom_prompt:
                raise ValueError("カスタムプロンプトが指定されていません")
            
            # {text}プレースホルダーを置換
            prompt = config.custom_prompt.replace("{text}", text)
        else:
            # テンプレートを使用
            template = self.PROMPT_TEMPLATES.get(config.template)
            if not template:
                raise ValueError(f"不明なテンプレート: {config.template}")
            
            prompt = template.format(text=text)
        
        return prompt
    
    def generate_chatgpt_url(self, prompt: str) -> str:
        """ChatGPTのURLを生成する
        
        Args:
            prompt: 送信するプロンプト
            
        Returns:
            ChatGPTのURL
        """
        # プロンプトをURLエンコード
        encoded_prompt = urllib.parse.quote(prompt)
        
        # ChatGPTのURLを構築
        # 注: ChatGPTの正確なURL構造は変更される可能性があるため、
        # 実際にはクリップボードにコピーする方が確実
        return f"{self.chatgpt_url}?q={encoded_prompt}"
    
    def prepare_for_clipboard(self, text: str, config: ChatGPTPromptConfig) -> str:
        """クリップボードにコピーするためのテキストを準備する
        
        Args:
            text: 対象テキスト
            config: プロンプト設定
            
        Returns:
            クリップボード用のテキスト
        """
        return self.create_prompt(text, config)
    
    def get_prompt_examples(self) -> List[Dict[str, str]]:
        """プロンプトの例を取得する
        
        Returns:
            プロンプト例のリスト
        """
        return [
            {
                "name": "バズる切り抜き案",
                "description": "動画からバズりそうな部分を提案",
                "template": PromptTemplate.VIRAL_CLIP.value
            },
            {
                "name": "タイトル提案",
                "description": "切り抜きに魅力的なタイトルを提案",
                "template": PromptTemplate.TITLE_SUGGESTION.value
            },
            {
                "name": "内容要約",
                "description": "選択した内容を簡潔に要約",
                "template": PromptTemplate.SUMMARY.value
            }
        ]