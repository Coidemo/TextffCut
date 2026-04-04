"""
OpenAI APIを使用した切り抜き候補生成ゲートウェイ

3段階パイプライン:
1. detect_topics: 話題の時間範囲を検出（テキスト編集なし）
2. （機械的処理 — Gatewayの外で実行）
3. select_best_variant: ベストパターンを選定
"""

import json
import logging
import time
from pathlib import Path

from openai import OpenAI

from domain.entities.clip_suggestion import (
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface

logger = logging.getLogger(__name__)

AVAILABLE_MODELS = ["gpt-4.1-mini", "gpt-4.1"]

MODEL_PRICING = {
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
}

DEFAULT_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "clip_suggestions_v2.md"


class OpenAIClipSuggestionGateway(ClipSuggestionGatewayInterface):

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini"):
        self.client = OpenAI(api_key=api_key)
        if model not in AVAILABLE_MODELS:
            logger.warning(f"Unknown model '{model}', falling back to gpt-4.1-mini")
            model = "gpt-4.1-mini"
        self.model = model

    def detect_topics(self, request: TopicDetectionRequest) -> TopicDetectionResult:
        start = time.time()

        prompt = self._build_topic_prompt(request)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "あなたは動画から面白い話題を見つける専門家です。必ずJSON形式で回答してください。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result_data = json.loads(content)

        topics = []
        num_segments = len(request.transcription_segments)
        for topic_data in result_data.get("topics", []):
            seg_start = topic_data.get("segment_start_index", 0)
            seg_end = topic_data.get("segment_end_index", 0)

            if seg_start < 0 or seg_end >= num_segments or seg_start > seg_end:
                logger.warning(f"Invalid segment range [{seg_start}-{seg_end}], skipping")
                continue

            topics.append(TopicRange.create(
                title=topic_data.get("title", ""),
                segment_start_index=seg_start,
                segment_end_index=seg_end,
                score=topic_data.get("score", 0),
                category=topic_data.get("category", ""),
                reasoning=topic_data.get("reasoning", ""),
                keywords=topic_data.get("keywords", []),
            ))

        token_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        pricing = MODEL_PRICING.get(self.model, MODEL_PRICING["gpt-4.1-mini"])
        cost = (
            (token_usage["prompt_tokens"] / 1_000_000) * pricing["input"]
            + (token_usage["completion_tokens"] / 1_000_000) * pricing["output"]
        )

        return TopicDetectionResult(
            topics=topics,
            model_used=self.model,
            processing_time=time.time() - start,
            token_usage=token_usage,
            estimated_cost_usd=cost,
        )

    def select_best_variant(self, topic_title: str, variants: list[dict]) -> int | None:
        if not variants:
            return None
        if len(variants) == 1:
            return 0

        # バリアント情報をフォーマット
        options = []
        for i, v in enumerate(variants):
            options.append(
                f"パターン{i+1}（{v['label']}、{v['duration']:.0f}秒）:\n{v['text'][:300]}"
            )

        prompt = f"""以下は「{topic_title}」という話題の切り抜きパターン候補です。
ショート動画として最も「保存したくなる」「誰かに教えたくなる」パターンを1つ選んでください。

選定基準:
- 冒頭が引きになっている（問題提起、断定、驚き）
- 結末が行動提案や気づきで締まっている
- 話の流れが自然で完結している
- 無駄な脱線や繰り返しが少ない

{chr(10).join(options)}

必ずJSON形式で回答してください: {{"selected": パターン番号(1始まり), "reason": "選定理由"}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "ショート動画の編集専門家です。JSON形式で回答してください。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=200,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            selected = result.get("selected", 1)
            logger.info(f"AI selected pattern {selected}: {result.get('reason', '')}")
            return max(0, min(selected - 1, len(variants) - 1))
        except Exception as e:
            logger.warning(f"AI variant selection failed: {e}, using first variant")
            return 0

    def review_naturalness(
        self,
        title: str,
        segments_text: list[str],
        cut_issues: list[dict],
    ) -> list[dict]:
        issues_desc = ""
        for issue in cut_issues:
            issues_desc += f"- クリップ{issue['index']+1}の末尾: ピッチ{issue['direction']}\n"

        # 最大10クリップまで（トークン節約）
        segs = segments_text[:10]
        segments_desc = "\n".join(f"クリップ{i+1}: {t}" for i, t in enumerate(segs))

        prompt = f"""「{title}」の切り抜きクリップをレビュー。

クリップ一覧:
{segments_desc}

音声分析の問題:
{issues_desc if issues_desc else "なし"}

各クリップを判定（problemあるもののみ出力）:
- extend: 次と結合すべき（文が途中で切れている、「〜なので」「〜けど」で終わって続きが必要）
- remove: 単独では意味がない
- keep: 問題なし（省略可）

JSON: {{"reviews": [{{"index": 0, "action": "extend", "reason": "理由"}}]}}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "動画編集レビュー担当。必ず短いJSONで回答。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            reviews = result.get("reviews", [])
            for r in reviews:
                logger.info(f"  Review: clip {r.get('index')}: {r.get('action')} - {r.get('reason', '')}")
            return reviews
        except Exception as e:
            logger.warning(f"Naturalness review failed: {e}")
            return []

    def check_connection(self) -> bool:
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI connection check failed: {e}")
            return False

    def get_available_models(self) -> list[str]:
        return list(AVAILABLE_MODELS)

    def _build_topic_prompt(self, request: TopicDetectionRequest) -> str:
        prompt_path = Path(request.prompt_path) if request.prompt_path else DEFAULT_PROMPT_PATH
        if prompt_path.exists():
            template = prompt_path.read_text(encoding="utf-8")
        else:
            template = self._inline_topic_template()

        segments_text = self._format_segments(request.transcription_segments)
        min_chars = request.min_duration * 5
        max_chars = request.max_duration * 7

        template = template.replace("{NUM_CANDIDATES}", str(request.num_candidates))
        template = template.replace("{MIN_DURATION}", str(request.min_duration))
        template = template.replace("{MAX_DURATION}", str(request.max_duration))
        template = template.replace("{MIN_CHARS}", str(min_chars))
        template = template.replace("{MAX_CHARS}", str(max_chars))
        template = template.replace("{TOTAL_SEGMENTS_MINUS_1}", str(len(request.transcription_segments) - 1))
        template = template.replace("{SEGMENTS}", segments_text)

        return template

    def _format_segments(self, segments: list[dict]) -> str:
        if not segments:
            return ""

        CHUNK_DURATION = 30.0
        lines = []
        chunk_start_idx = 0
        chunk_start_time = segments[0].get("start", 0.0)
        chunk_texts = []

        for i, seg in enumerate(segments):
            chunk_texts.append(seg.get("text", ""))
            seg_end = seg.get("end", 0.0)

            is_last = (i == len(segments) - 1)
            if seg_end - chunk_start_time >= CHUNK_DURATION or is_last:
                combined_text = "".join(chunk_texts)
                lines.append(
                    f"[{chunk_start_idx}-{i}] "
                    f"({chunk_start_time:.1f}s-{seg_end:.1f}s) "
                    f"{combined_text}"
                )
                if not is_last:
                    chunk_start_idx = i + 1
                    chunk_start_time = segments[i + 1].get("start", seg_end)
                    chunk_texts = []

        return "\n".join(lines)

    def _inline_topic_template(self) -> str:
        return """以下のセグメント一覧から、{MIN_DURATION}〜{MAX_DURATION}秒のショート動画に適した話題の範囲を{NUM_CANDIDATES}個見つけてください。
テキスト編集は不要です。範囲だけ指定してください。

JSON形式: {"topics": [{"title": "...", "segment_start_index": 0, "segment_end_index": 10, "score": 15, "category": "...", "reasoning": "...", "keywords": [...]}]}

セグメント一覧（インデックス 0〜{TOTAL_SEGMENTS_MINUS_1}）:
{SEGMENTS}"""
