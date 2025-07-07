"""
OpenAI APIとの通信ゲートウェイ
"""

import json
import logging
from typing import Any

from openai import OpenAI

from domain.entities.buzz_clip import (
    BuzzClipCandidate,
    BuzzClipGenerationRequest,
    BuzzClipGenerationResult,
)
from domain.gateways.ai_gateway import AIGatewayInterface

logger = logging.getLogger(__name__)


class OpenAIGateway(AIGatewayInterface):
    """OpenAI APIゲートウェイの実装"""

    def __init__(self, api_key: str):
        """
        初期化

        Args:
            api_key: OpenAI APIキー
        """
        self.client = OpenAI(api_key=api_key)
        self.model = "gpt-4o"  # GPT-4oを使用（高速・低コスト）
        logger.info("OpenAI Gateway initialized with GPT-4o")

    def generate_buzz_clips(self, request: BuzzClipGenerationRequest) -> BuzzClipGenerationResult:
        """
        バズる切り抜き候補を生成

        Args:
            request: 生成リクエスト

        Returns:
            生成結果
        """
        import time

        start_time = time.time()

        try:
            # プロンプトを作成
            prompt = self._create_prompt(request)

            # OpenAI APIを呼び出し
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            # レスポンスを解析
            content = response.choices[0].message.content
            logger.debug(f"OpenAI response: {content[:500]}...")

            # JSON形式で返ってくるレスポンスをパース
            result_data = json.loads(content)

            # BuzzClipCandidateのリストを作成
            candidates = []
            for clip_data in result_data.get("clips", []):
                candidate = BuzzClipCandidate.create(
                    title=clip_data["title"],
                    text=clip_data["text"],
                    start_time=clip_data["start_time"],
                    end_time=clip_data["end_time"],
                    score=clip_data["score"],
                    category=clip_data["category"],
                    reasoning=clip_data["reasoning"],
                    keywords=clip_data.get("keywords", []),
                )
                candidates.append(candidate)

            # 使用量情報を取得
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

            processing_time = time.time() - start_time

            return BuzzClipGenerationResult(
                candidates=candidates, total_processing_time=processing_time, model_used=self.model, usage=usage
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def _create_prompt(self, request: BuzzClipGenerationRequest) -> str:
        """プロンプトを作成"""
        segments_text = self._format_segments(request.transcription_segments)

        prompt = f"""以下の動画の文字起こし結果から、{request.min_duration}〜{request.max_duration}秒の「保存したくなる」切り抜きショート動画の候補を{request.num_candidates}個選んでください。

【文字起こし結果】
{segments_text}

【編集ルール】※違反は不採用
1. 引用厳守：文字起こし結果の文字のみ使用（一切の追加禁止）
2. フィラー削除：「あの」「その」「えっと」「まあ」などを削る
3. 大胆カット：本筋に関係ない例示・補足説明・挨拶は削除
4. 重複削除：同じ内容の繰り返しは1回に圧縮
5. 数字・単位：原文のまま（95パー→ 95パー）
6. 語尾：重複語尾は1回に圧縮しつつ原文を保持

【選定基準】  
- 各候補は{request.min_duration}〜{request.max_duration}秒の長さ（約300-500文字目安）
- 「これは保存したい！」「誰かに教えたい！」と思える内容
- 断定的で分かりやすい主張
- 読後に「行動」か「気づき」が残る形で締める

【構成パターン】（どれか1つを選択）
A. Q→A型：問題提起→解決策→行動提案
B. 主張型：主張→理由→提案／未来予測
C. Tips型：結論→具体例の列挙（「〜すると」「〜とか」で並列）

- タイトルは「〇〇する方法」「〇〇の理由」など実用的に
- スコア（0-20）で評価"""

        # 既存候補がある場合は重複を避けるよう指示
        if request.existing_candidates:
            prompt += "\n\n【既存の候補との重複回避】\n以下の時間範囲の候補は既に生成されているため、これらと重複しない新しい候補を選んでください：\n"
            for candidate in request.existing_candidates:
                prompt += f"- {candidate.start_time:.1f}s〜{candidate.end_time:.1f}s: {candidate.title}\n"

        prompt += """

【出力形式】
JSON形式で以下の構造で出力してください：
{
  "clips": [
    {
      "title": "タイトル案",
      "text": "切り抜き部分のテキスト",
      "start_time": 開始時間（秒）,
      "end_time": 終了時間（秒）,
      "score": バズスコア（0-20）,
      "category": "カテゴリ（仕事術/人間関係/ライフハック/日常の疑問/新しい視点/その他）",
      "reasoning": "選定理由",
      "keywords": ["キーワード1", "キーワード2"]
    }
  ]
}"""

        if request.categories:
            prompt += f"\n\n優先カテゴリ: {', '.join(request.categories)}"
        
        prompt += """

【セルフ検品フェーズ】（全案に必ず実行）
① 時間…{request.min_duration}〜{request.max_duration}秒内か
② 引用違反…原文にない語彙・語順変更がないか
③ フィラー残存…「えー」「あの」等を取り除いたか
④ 余談残り…挨拶や無関係な例示が残っていないか
⑤ 構成…A〜Cいずれかに適合しているか
→ 1つでもNG項目があれば該当案を再生成せよ。""".replace("{request.min_duration}", str(request.min_duration)).replace("{request.max_duration}", str(request.max_duration))

        return prompt

    def _format_segments(self, segments: list[dict[str, Any]]) -> str:
        """セグメントをフォーマット"""
        formatted_lines = []
        for seg in segments:
            time_str = f"[{seg['start']:.1f}s - {seg['end']:.1f}s]"
            formatted_lines.append(f"{time_str} {seg['text']}")
        return "\n".join(formatted_lines)

    def _get_system_prompt(self) -> str:
        """システムプロンプトを取得"""
        return """あなたは「保存したくなる」「誰かに教えたくなる」ショート動画を特定する専門家です。
長い会話から、視聴者が「これは役立つ！」「あるある！」と思う部分を見つけることが得意です。

以下の基準で切り抜き候補を選んでください：

1. 実用性（すぐに実践できる具体的なアドバイスや解決策）
2. 共感性（「あるある」「それな！」と思える日常の悩みや疑問）  
3. 明快さ（断定的で分かりやすい主張、「なるほど！」という気づき）
4. 現代性（AI、リモートワークなど現代的な話題やツール）
5. 完結性（問題提起→原因分析→解決策の流れが30-40秒で完結）

特に以下のような内容を優先してください：
- 仕事や人間関係の悩みへの具体的な解決策
- 日常の「あるある」や素朴な疑問への答え
- すぐに試せるライフハックや仕事術
- 「そういう考え方があったのか！」という新しい視点

各候補に0-20のスコアを付けて、スコアの高い順に返してください。"""

    def analyze_text_for_highlights(self, text: str, num_highlights: int = 5) -> list[dict[str, Any]]:
        """
        テキストからハイライトを抽出（オプショナル機能）

        Args:
            text: 分析対象のテキスト
            num_highlights: 抽出するハイライト数

        Returns:
            ハイライトのリスト
        """
        # 将来的な拡張用
        raise NotImplementedError("This method is not implemented yet")

    def check_connection(self) -> bool:
        """
        接続確認

        Returns:
            接続可能かどうか
        """
        try:
            # 簡単なリクエストで接続確認
            response = self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI connection check failed: {e}")
            return False
