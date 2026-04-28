"""
OpenAI APIを使用した切り抜き候補生成ゲートウェイ

主要API:
1. detect_topics: 話題の時間範囲を検出（Phase 1）
2. refine_topic_boundary: 話題境界の補正（Phase 1.5）
3. find_core_and_conclusion: 骨子と結びを検出（Phase 2c）
4. select_best_clip: 最良候補を選定（Phase 3）
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

# 品質に直結する sub-step メソッド一覧。
# `--quality-model` を `--ai-model` と別に指定すると、ここに列挙された method
# だけ高品質モデルで実行する (cost と quality のバランス調整用)。
# 一覧外の method (= タイトル画像生成、SE 配置等) は ai_model のまま。
QUALITY_OVERRIDE_METHODS = (
    "detect_topics",
    "evaluate_clip_quality",
    "trim_clips",
    "select_best_clip",
    "judge_segment_relevance",
    "refine_topic_boundary",
    "find_core_and_conclusion",
)


def build_gateway(
    api_key: str,
    ai_model: str = "gpt-4.1-mini",
    quality_model: str | None = None,
) -> "OpenAIClipSuggestionGateway":
    """SuggestAndExportRequest 互換の引数から gateway を構築する。

    `quality_model` が `ai_model` と異なる (かつ None でない) 場合、
    `QUALITY_OVERRIDE_METHODS` で列挙された method だけ `quality_model`
    で実行されるよう `model_overrides` を組み立てる。

    GUI と CLI の両方からこの helper を呼ぶことで、gateway 構築ロジックの
    drift を防止する (issue #153 対策)。
    """
    overrides: dict[str, str] = {}
    if quality_model and quality_model != ai_model:
        overrides = {method: quality_model for method in QUALITY_OVERRIDE_METHODS}
    return OpenAIClipSuggestionGateway(
        api_key=api_key, model=ai_model, model_overrides=overrides
    )


DEFAULT_PROMPT_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "clip_suggestions_v2.md"


class OpenAIClipSuggestionGateway(ClipSuggestionGatewayInterface):

    def __init__(self, api_key: str, model: str = "gpt-4.1-mini", model_overrides: dict[str, str] | None = None):
        self._client = OpenAI(api_key=api_key)
        if model not in AVAILABLE_MODELS:
            logger.warning(f"Unknown model '{model}', falling back to gpt-4.1-mini")
            model = "gpt-4.1-mini"
        self.model = model
        self._model_overrides = model_overrides or {}

    @property
    def client(self) -> OpenAI:
        """OpenAIクライアントを返す。"""
        return self._client

    @property
    def api_key(self) -> str | None:
        """APIキーを返す。"""
        return self._client.api_key

    def _resolve_model(self, method_name: str) -> str:
        """メソッド名に応じたモデルを返す。overridesがなければデフォルト。"""
        override = self._model_overrides.get(method_name)
        if override and override in AVAILABLE_MODELS:
            return override
        return self.model

    def detect_topics(self, request: TopicDetectionRequest, format_mode: str = "chunk_30s") -> TopicDetectionResult:
        start = time.time()

        prompt = self._build_topic_prompt(request, format_mode=format_mode)

        response = self._client.chat.completions.create(
            model=self._resolve_model("detect_topics"),
            messages=[
                {
                    "role": "system",
                    "content": "あなたは動画から面白い話題を見つける専門家です。必ずJSON形式で回答してください。",
                },
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

            topics.append(
                TopicRange.create(
                    title=topic_data.get("title", ""),
                    segment_start_index=seg_start,
                    segment_end_index=seg_end,
                    score=topic_data.get("score", 0),
                    category=topic_data.get("category", ""),
                    reasoning=topic_data.get("reasoning", ""),
                    keywords=topic_data.get("keywords", []),
                )
            )

        token_usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        resolved = self._resolve_model("detect_topics")
        pricing = MODEL_PRICING.get(resolved, MODEL_PRICING["gpt-4.1-mini"])
        cost = (token_usage["prompt_tokens"] / 1_000_000) * pricing["input"] + (
            token_usage["completion_tokens"] / 1_000_000
        ) * pricing["output"]

        return TopicDetectionResult(
            topics=topics,
            model_used=resolved,
            processing_time=time.time() - start,
            token_usage=token_usage,
            estimated_cost_usd=cost,
        )

    def judge_segment_relevance(self, title: str, segments: list[dict]) -> list[int]:
        if not segments:
            return []

        segs_desc = "\n".join(
            f"[{s['index']}] ({s['start']:.0f}s) {s['text']}" for s in segments[:30]  # 最大30セグメント
        )

        prompt = f"""「{title}」というショート動画の素材として、以下のセグメントがあります。
切り抜き動画に**不要な**セグメントを選んでください。

不要の基準:
- 独り言（「何話そうと思ったんだっけ」「自分で書いておきたい」等）
- 挨拶・定型句（「ここから本編です」「はいどうも」等）
- 前の話題の残り（このトピックと無関係な内容）
- 読み上げの繰り返し（同じ質問を2回読む等）

必要な場合は空リストを返してください。

セグメント:
{segs_desc}

JSON: {{"remove": [不要なセグメントのindex番号]}}"""

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("judge_segment_relevance"),
                messages=[
                    {"role": "system", "content": "動画編集のセグメント選別担当。JSON形式で回答。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            remove_indices = result.get("remove", [])
            if remove_indices:
                logger.info(f"AI segment judge: {len(remove_indices)} segments to remove")
            return remove_indices
        except Exception as e:
            logger.warning(f"Segment relevance judge failed: {e}")
            return []

    def evaluate_clip_quality(
        self,
        title: str,
        transcribed_text: str,
        audio_issues: list[str] | None = None,
    ) -> dict:
        prompt = f"""以下はショート動画「{title}」の出来上がり音声を文字起こししたテキストです。
以下の5軸で評価してください（各1-5点）:

1. Hook強度: 冒頭で視聴者の注意を引けるか
   5=断定/驚き/問いかけで始まる 1=前置き/挨拶/文脈なしで始まる

2. 完結性: 問題提起→展開→結論/提案が揃っているか
   5=明確な結論あり 1=問題提起だけで結論なし

3. コンパクトさ: 冗長な部分がないか
   5=無駄ゼロ 1=繰り返し/脱線/不要な補足が多い

4. 末尾の締まり: 自然に終わっているか
   5=結論/提案で締まっている 1=「〜とか」「〜けど」で途切れている

5. タイトル整合性: タイトルの内容が実際に語られているか
   5=完全一致 1=タイトルと無関係

合計15点以上で合格。

音響分析:
{chr(10).join(f'  - {issue}' for issue in (audio_issues or [])) or '  問題なし'}

テキスト:
{transcribed_text}

JSON: {{"scores": {{"hook": 4, "completeness": 3, "compactness": 5, "ending": 4, "title_relevance": 5}}, "ok": true/false, "issues": ["問題1"], "fix_suggestions": ["修正案1"]}}
問題がなければ {{"scores": {{...}}, "ok": true, "issues": [], "fix_suggestions": []}}"""

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("evaluate_clip_quality"),
                messages=[
                    {"role": "system", "content": "ショート動画の品質管理担当。厳しく判定。JSON形式で回答。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.warning(f"AI quality check failed: {e}")
            return {"ok": False, "issues": ["quality check failed"], "fix_suggestions": []}

    def select_best_clip(
        self,
        title: str,
        candidates_text: str,
    ) -> int:
        prompt = f"""「{title}」のショート動画候補があります。
YouTubeショートで最も再生数が回りそうな候補を1つ選んでください。

選定基準（重要度順）:
1. 冒頭の引き: 最初の一文で「続きが気になる」と思わせるか
2. コンパクトさ: 同じ内容なら短い方が良い。冗長な前置きや繰り返しがないか
3. 結論の明確さ: 「要するにこういうこと」と言い切っているか
4. 共感・意外性: 視聴者が「わかる」「そうなんだ」と反応しそうか
5. 完結性: 途中で切れていないか

{candidates_text}

JSON: {{"selected": 候補番号(1始まり), "reason": "選定理由（どの基準で優れていたか具体的に）"}}"""

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("select_best_clip"),
                messages=[
                    {
                        "role": "system",
                        "content": "YouTubeショート動画の編集ディレクター。再生数を最大化する候補を選定する。JSON形式で回答。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            return result.get("selected", 1)
        except Exception as e:
            logger.warning(f"AI clip selection failed: {e}")
            return 1

    def trim_clips(
        self,
        title: str,
        clips_text: str,
        max_duration: float,
    ) -> list[int]:
        prompt = f"""以下はショート動画のクリップ一覧です。
{max_duration:.0f}秒以内にする必要があります。

**主張と結論は必ず残してください。** 削除すべきは:
- 繰り返し・冗長な説明
- 本筋と関係ない例え話・脱線
- なくても主張が伝わる補足
- **質問の読み上げ部分**（質問が長い場合は最短の1クリップだけ残して残りを削除。タイトルで内容は伝わるので質問は最小限に）

冒頭（話の導入）と末尾（結論）は原則残してください。中間から削除するのが理想です。

{clips_text}

JSON: {{"remove": [削除するクリップのindex番号], "reason": "理由"}}"""

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("trim_clips"),
                messages=[
                    {
                        "role": "system",
                        "content": "動画編集の中間カット担当。主張と結論を残して不要部分を大胆に削除。JSON形式で回答。",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            remove_indices = result.get("remove", [])
            if remove_indices:
                logger.info(f"trim_clips: {len(remove_indices)} clips to remove, reason: {result.get('reason', '')}")
            return remove_indices
        except Exception as e:
            logger.warning(f"trim_clips failed: {e}")
            return []

    def refine_topic_boundary(
        self,
        title: str,
        all_segments: list[dict],
        extension_candidates: list[dict],
    ) -> dict:
        all_desc = "\n".join(
            f"[{i}] seg_idx={s['index']} ({s['start']:.1f}-{s['end']:.1f}s) {s['text']}"
            for i, s in enumerate(all_segments)
        )
        ext_desc = (
            "\n".join(
                f"[{chr(65 + i)}] seg_idx={s['index']} ({s['start']:.1f}-{s['end']:.1f}s) {s['text']}"
                for i, s in enumerate(extension_candidates)
            )
            if extension_candidates
            else "なし"
        )

        prompt = f"""タイトル: {title}

話題の全セグメント:
{all_desc}

後続セグメント（拡張候補）:
{ext_desc}

判定してください:
1. 末尾に別の話題のセグメントが混入していませんか？
   - 話題と無関係な内容が末尾にあれば、どこで切るべきか
2. 後続セグメントに結論が含まれていませんか？
   - 含まれていれば、どこまで拡張すべきか
3. 最終的な範囲（trim/extend後）で話題の論点は完結しますか？
   - 主張→根拠→結論の流れが成立しているか
   - 末尾が接続形（〜ので/〜けど/〜て）で終わっていないか
   - **is_completeはtrim/extend適用後の最終範囲について判定してください**

JSON: {{"action": "keep" | "trim" | "extend", "end_segment_index": 最終セグメントのseg_idx, "is_complete": 最終範囲で話題が完結しているか(true/false), "reason": "判定理由"}}"""

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("refine_topic_boundary"),
                messages=[
                    {"role": "system", "content": "話題の境界を判定する専門家。JSON形式で回答。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            # デフォルト値の補完
            if "action" not in result:
                result["action"] = "keep"
            if "end_segment_index" not in result:
                result["end_segment_index"] = all_segments[-1]["index"] if all_segments else 0
            if "is_complete" not in result:
                result["is_complete"] = True
            if "reason" not in result:
                result["reason"] = ""
            return result
        except Exception as e:
            logger.warning(f"refine_topic_boundary failed: {e}")
            return {
                "action": "keep",
                "end_segment_index": all_segments[-1]["index"] if all_segments else 0,
                "is_complete": True,
                "reason": f"API error: {e}",
            }

    def find_core_and_conclusion(
        self,
        title: str,
        segments: list[dict],
    ) -> dict:
        system_prompt = """あなたはポッドキャストの切り抜き動画の編集者です。

話題のセグメント一覧を渡します。以下の2つを特定してください。

## 骨子（核心の主張）
この話題で話者が最も伝えたいメインの主張・意見が述べられているセグメント範囲。
- 具体例や体験談ではなく、抽象的な主張そのもの
- 複数箇所ある場合は最も重要な1-2箇所

## 結び（まとめ・言い切り）
話題の締めくくり。主張を要約したり「という話でした」のように話をまとめているセグメント範囲。
- 必ず文が完結している（言い切りで終わる）箇所
- 話題の後半にあることが多い

出力形式（JSONオブジェクト）:
{
  "core": [{"start": 開始idx, "end": 終了idx, "summary": "主張の要約"}],
  "conclusion": [{"start": 開始idx, "end": 終了idx, "summary": "結びの要約"}]
}

idxはセグメント配列の0始まりインデックスです。"""

        seg_list = [{"idx": s["idx"], "text": s["text"]} for s in segments]
        user_content = f"話題: {title}\n\nセグメント:\n{json.dumps(seg_list, ensure_ascii=False)}"

        try:
            response = self._client.chat.completions.create(
                model=self._resolve_model("find_core_and_conclusion"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            cores = result.get("core", [])
            conclusions = result.get("conclusion", [])
            logger.info(f"find_core_and_conclusion: {title} — " f"骨子={len(cores)}箇所, 結び={len(conclusions)}箇所")
            return result
        except Exception as e:
            logger.warning(f"find_core_and_conclusion failed: {e}")
            return {"core": [], "conclusion": []}

    def get_available_models(self) -> list[str]:
        return list(AVAILABLE_MODELS)

    def _build_topic_prompt(self, request: TopicDetectionRequest, format_mode: str = "chunk_30s") -> str:
        prompt_path = Path(request.prompt_path) if request.prompt_path else DEFAULT_PROMPT_PATH
        if prompt_path.exists():
            template = prompt_path.read_text(encoding="utf-8")
        else:
            template = self._inline_topic_template()

        segments_text = self._format_segments(request.transcription_segments, format_mode=format_mode)
        min_chars = request.min_duration * 5
        max_chars = request.max_duration * 7

        template = template.replace("{NUM_CANDIDATES}", str(request.num_candidates))
        template = template.replace("{MIN_DURATION}", str(request.min_duration))
        template = template.replace("{MAX_DURATION}", str(request.max_duration))
        template = template.replace("{MIN_CHARS}", str(min_chars))
        template = template.replace("{MAX_CHARS}", str(max_chars))
        # SEGMENT_FORMAT_DESCRIPTION 内に {TOTAL_SEGMENTS_MINUS_1} が含まれるため先に展開
        template = template.replace("{SEGMENT_FORMAT_DESCRIPTION}", self._segment_format_description(format_mode))
        template = template.replace("{TOTAL_SEGMENTS_MINUS_1}", str(len(request.transcription_segments) - 1))
        template = template.replace("{SEGMENTS}", segments_text)

        return template

    @staticmethod
    def _segment_format_description(format_mode: str) -> str:
        """フォーマットモードに応じたセグメント説明テキスト"""
        if format_mode == "chunk_30s":
            return (
                "各行は `[開始インデックス-終了インデックス] (開始秒-終了秒) テキスト` の形式で、"
                "約30秒ごとにまとめて表示しています。\n\n"
                "**重要:**\n"
                "- セグメントのインデックスは 0 から {TOTAL_SEGMENTS_MINUS_1} までです。\n"
                "- segment_start_index と segment_end_index には"
                "**この表示のチャンク境界にとらわれず、任意のセグメントインデックスを指定**してください。\n"
                "- 例えば [0-11] と [12-25] をまたいで、segment_start_index: 8, "
                "segment_end_index: 20 のような指定が可能です。\n"
                "- 話題が自然に始まり自然に終わる範囲を選んでください。"
            )

        base = (
            "各行は `[セグメントインデックス] (開始秒-終了秒) テキスト` の形式で、"
            "1セグメント1行で表示しています。\n\n"
            "**重要:**\n"
            "- セグメントのインデックスは 0 から {TOTAL_SEGMENTS_MINUS_1} までです。\n"
            "- segment_start_index と segment_end_index にはセグメントインデックスを指定してください。\n"
            "- 話題が自然に始まり自然に終わる範囲を選んでください。"
        )

        if format_mode in ("individual_noise", "individual_full"):
            base += (
                "\n\n**ノイズタグについて:**\n"
                "- `[NOISE:*]` タグ付きセグメントは話題の開始・終了位置として使わないでください。\n"
                "- ノイズセグメントは話題の中間に含まれていてもOKですが、"
                "話題の境界判定には使わないでください。"
            )

        if format_mode in ("individual_gap", "individual_full"):
            base += (
                "\n\n**沈黙ギャップについて:**\n"
                "- `--- Xs silence ---` は話題の切り替わりの手がかりとして活用してください。\n"
                "- 長い沈黙（5秒以上）は特に話題転換の可能性が高いです。"
            )

        return base

    def _format_segments(self, segments: list[dict], format_mode: str = "chunk_30s") -> str:
        if not segments:
            return ""

        if format_mode == "chunk_30s":
            return self._format_chunk_30s(segments)
        elif format_mode == "individual":
            return self._format_individual(segments)
        elif format_mode == "individual_gap":
            return self._format_individual(segments, show_gap=True)
        elif format_mode == "individual_noise":
            return self._format_individual(segments, show_noise=True)
        elif format_mode == "individual_full":
            return self._format_individual(segments, show_gap=True, show_noise=True, show_low_conf=True)
        else:
            logger.warning(f"Unknown format_mode '{format_mode}', falling back to chunk_30s")
            return self._format_chunk_30s(segments)

    def _format_chunk_30s(self, segments: list[dict]) -> str:
        """現行フォーマット: 30秒チャンクに連結"""
        CHUNK_DURATION = 30.0
        lines = []
        chunk_start_idx = 0
        chunk_start_time = segments[0].get("start", 0.0)
        chunk_texts = []

        for i, seg in enumerate(segments):
            chunk_texts.append(seg.get("text", ""))
            seg_end = seg.get("end", 0.0)

            is_last = i == len(segments) - 1
            if seg_end - chunk_start_time >= CHUNK_DURATION or is_last:
                combined_text = "".join(chunk_texts)
                lines.append(
                    f"[{chunk_start_idx}-{i}] " f"({chunk_start_time:.1f}s-{seg_end:.1f}s) " f"{combined_text}"
                )
                if not is_last:
                    chunk_start_idx = i + 1
                    chunk_start_time = segments[i + 1].get("start", seg_end)
                    chunk_texts = []

        return "\n".join(lines)

    def _format_individual(
        self,
        segments: list[dict],
        *,
        show_gap: bool = False,
        show_noise: bool = False,
        show_low_conf: bool = False,
    ) -> str:
        """セグメント個別表示フォーマット"""
        GAP_THRESHOLD = 0.5
        LOW_CONF_THRESHOLD = 0.5
        lines = []

        for i, seg in enumerate(segments):
            text = seg.get("text", "").strip()
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)

            # ギャップ表示（前のセグメントとの間に沈黙がある場合）
            if show_gap and i > 0:
                prev_end = segments[i - 1].get("end", 0.0)
                gap = start - prev_end
                if gap > GAP_THRESHOLD:
                    lines.append(f"  --- {gap:.1f}s silence ---")

            # タグ構築
            tags = []
            if show_noise:
                noise_tag = self._detect_noise_tag(seg)
                if noise_tag:
                    tags.append(noise_tag)
            if show_low_conf:
                avg_conf = self._avg_word_confidence(seg)
                if avg_conf is not None and avg_conf < LOW_CONF_THRESHOLD:
                    tags.append(f"[conf:{avg_conf:.2f}]")

            tag_str = " ".join(tags)
            if tag_str:
                tag_str += " "

            lines.append(f"[{i}] ({start:.1f}-{end:.1f}) {tag_str}{text}")

        return "\n".join(lines)

    def _detect_noise_tag(self, seg: dict) -> str | None:
        """セグメントのノイズタグを検出"""
        from use_cases.ai.filler_constants import detect_noise_tag

        # テキストベースの判定は共通関数に委譲
        tag = detect_noise_tag(seg.get("text", ""))
        if tag:
            return tag

        # [NOISE:low-conf] — word平均confidence < 0.3（words依存なのでgateway側に残す）
        avg_conf = self._avg_word_confidence(seg)
        if avg_conf is not None and avg_conf < 0.3:
            return "[NOISE:low-conf]"

        return None

    def _avg_word_confidence(self, seg: dict) -> float | None:
        """セグメントのword平均confidenceを計算"""
        words = seg.get("words", [])
        if not words:
            return None
        confidences = [w.get("probability", w.get("confidence", 1.0)) for w in words]
        if not confidences:
            return None
        return sum(confidences) / len(confidences)

    def _inline_topic_template(self) -> str:
        return """以下のセグメント一覧から、{MIN_DURATION}〜{MAX_DURATION}秒のショート動画に適した話題の範囲を{NUM_CANDIDATES}個見つけてください。
テキスト編集は不要です。範囲だけ指定してください。

JSON形式: {"topics": [{"title": "...", "segment_start_index": 0, "segment_end_index": 10, "score": 15, "category": "...", "reasoning": "...", "keywords": [...]}]}

セグメント一覧（インデックス 0〜{TOTAL_SEGMENTS_MINUS_1}）:
{SEGMENTS}"""
