"""
ChatGPT API統合サービス
文字起こし結果から単語削除のみで文章を構築する機能を提供
"""
import os
import json
import re
from typing import List, Dict, Optional, Tuple
from openai import OpenAI
import streamlit as st


class ChatGPTService:
    """ChatGPT API統合サービス"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        初期化
        
        Args:
            api_key: OpenAI APIキー（Noneの場合は環境変数から取得）
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key)
    
    def is_configured(self) -> bool:
        """API設定が完了しているか確認"""
        return self.client is not None
    
    def extract_segments_from_text(self, original_text: str) -> List[str]:
        """
        元のテキストから単語/フレーズのセグメントを抽出
        日本語の場合は文節や単語単位で分割
        
        Args:
            original_text: 元の文字起こしテキスト
            
        Returns:
            セグメントのリスト
        """
        # 改行で分割してから、各行を処理
        lines = original_text.strip().split('\n')
        segments = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 句読点で区切る
            parts = re.split(r'([。、！？])', line)
            
            for part in parts:
                if not part:
                    continue
                    
                # 句読点は単独のセグメントとして保持
                if part in '。、！？':
                    segments.append(part)
                else:
                    # 日本語の場合、助詞や接続詞で区切る
                    # より細かい単位での分割
                    sub_parts = re.split(r'(は|が|を|に|で|と|の|も|や|から|まで|より|など|って|という|こと|もの)', part)
                    
                    for i, sub_part in enumerate(sub_parts):
                        if sub_part:
                            # 助詞は前の単語とセットにする
                            if i > 0 and sub_part in 'はがをにでとのもやからまでよりなど':
                                if segments and not segments[-1] in '。、！？':
                                    segments[-1] += sub_part
                                else:
                                    segments.append(sub_part)
                            else:
                                segments.append(sub_part.strip())
        
        # 空のセグメントを除去
        segments = [s for s in segments if s.strip()]
        
        return segments
    
    def reconstruct_text_from_indices(self, segments: List[str], indices: List[int]) -> str:
        """
        セグメントのインデックスリストから文章を再構築
        
        Args:
            segments: 元のセグメントリスト
            indices: 使用するセグメントのインデックスリスト（順序保持）
            
        Returns:
            再構築された文章
        """
        result = []
        prev_idx = -1
        
        for idx in sorted(indices):
            if 0 <= idx < len(segments):
                # 連続性を保つため、必要に応じてスペースを追加
                if prev_idx >= 0 and idx > prev_idx + 1:
                    # 非連続の場合、句読点の前でなければスペースを追加
                    if segments[idx] not in '。、！？':
                        result.append(' ')
                
                result.append(segments[idx])
                prev_idx = idx
        
        # 結果を結合し、不要なスペースを整理
        text = ''.join(result)
        text = re.sub(r'\s+([。、！？])', r'\1', text)  # 句読点前のスペースを削除
        text = re.sub(r'\s+', ' ', text)  # 連続するスペースを1つに
        
        return text.strip()
    
    def generate_buzz_clips(self, original_text: str, num_suggestions: int = 3) -> List[Dict[str, any]]:
        """
        ChatGPT APIを使用してバズる切り抜き案を生成
        元の文字起こしから単語を削除することでのみ文章を作成
        
        Args:
            original_text: 元の文字起こしテキスト
            num_suggestions: 生成する提案数
            
        Returns:
            提案のリスト（各提案には text と indices が含まれる）
        """
        if not self.is_configured():
            raise ValueError("OpenAI APIキーが設定されていません")
        
        # セグメントに分割
        segments = self.extract_segments_from_text(original_text)
        
        # プロンプトを構築
        prompt = f"""以下の文字起こしテキストから、バズりそうな切り抜き部分を{num_suggestions}個提案してください。

重要な制約:
1. 元のテキストにある単語のみを使用してください（新しい単語の追加は禁止）
2. 単語の順序は元のテキストと同じ順序を保ってください
3. 単語を削除することでのみ、新しい文章を作成してください
4. 各提案は30秒〜1分程度で話せる長さにしてください

元のテキストをセグメントに分割しました。各セグメントには0から始まるインデックスがあります:
{json.dumps({i: seg for i, seg in enumerate(segments)}, ensure_ascii=False, indent=2)}

出力形式:
各提案について、使用するセグメントのインデックスをJSON形式で返してください。
必ず以下の形式で、suggestionsキーを持つJSONオブジェクトとして返してください:
{{
  "suggestions": [
    {{"title": "提案タイトル", "indices": [使用するセグメントのインデックスのリスト], "reason": "バズる理由の簡単な説明"}},
    {{"title": "提案タイトル2", "indices": [使用するセグメントのインデックスのリスト], "reason": "バズる理由の簡単な説明"}}
  ]
}}

元のテキスト:
{original_text}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "あなたは動画編集のエキスパートで、バズる切り抜きを作るのが得意です。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=2000
            )
            
            # レスポンスをパース
            result = json.loads(response.choices[0].message.content)
            
            # 結果を処理
            suggestions = []
            suggestions_list = result.get('suggestions', [])
            
            for item in suggestions_list:
                if isinstance(item, dict) and 'indices' in item:
                    text = self.reconstruct_text_from_indices(segments, item['indices'])
                    suggestions.append({
                        'title': item.get('title', '無題'),
                        'text': text,
                        'indices': item['indices'],
                        'reason': item.get('reason', ''),
                        'segments': segments  # デバッグ用
                    })
            
            return suggestions
            
        except Exception as e:
            st.error(f"ChatGPT API エラー: {str(e)}")
            return []
    
    def generate_title_suggestions(self, clip_text: str, num_suggestions: int = 5) -> List[str]:
        """
        切り抜きテキストに対するタイトル案を生成
        
        Args:
            clip_text: 切り抜きテキスト
            num_suggestions: 生成するタイトル数
            
        Returns:
            タイトル案のリスト
        """
        if not self.is_configured():
            raise ValueError("OpenAI APIキーが設定されていません")
        
        prompt = f"""以下の動画切り抜きテキストに対して、YouTubeやTikTokでバズりそうなタイトルを{num_suggestions}個提案してください。

タイトルの条件:
1. 15-30文字程度
2. 視聴者の興味を引く
3. クリックしたくなる
4. 内容を適切に表現している

切り抜きテキスト:
{clip_text}

JSON形式で返してください:
{{"titles": ["タイトル1", "タイトル2", ...]}}"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "あなたはSNSマーケティングのエキスパートです。"},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
                max_tokens=500
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get('titles', [])
            
        except Exception as e:
            st.error(f"ChatGPT API エラー: {str(e)}")
            return []