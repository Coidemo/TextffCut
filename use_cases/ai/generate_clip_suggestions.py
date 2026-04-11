"""
AI切り抜き候補生成ユースケース

1. AI: 話題の時間範囲を検出
2. 力任せ探索: セグメント組み合わせで大量候補生成 → 機械スコアで上位5件
3. AI: 出来上がり音声を文字起こしして最良候補を選定
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from domain.entities.clip_suggestion import (
    ClipSuggestion,
    TopicDetectionRequest,
    TopicDetectionResult,
    TopicRange,
)
from domain.entities.transcription import TranscriptionResult
from domain.gateways.clip_suggestion_gateway import ClipSuggestionGatewayInterface
from use_cases.ai.brute_force_clip_generator import ClipCandidate, generate_candidates

logger = logging.getLogger(__name__)


class GenerateClipSuggestionsUseCase:

    def __init__(self, gateway: ClipSuggestionGatewayInterface):
        self.gateway = gateway

    def execute(
        self,
        transcription: TranscriptionResult,
        video_path: Path,
        num_candidates: int = 5,
        min_duration: int = 30,
        max_duration: int = 60,
        prompt_path: str | None = None,
    ) -> list[ClipSuggestion]:

        segments_dicts = [{"text": seg.text, "start": seg.start, "end": seg.end} for seg in transcription.segments]

        # Phase 1: AI話題検出
        request = TopicDetectionRequest(
            transcription_segments=segments_dicts,
            num_candidates=num_candidates,
            min_duration=min_duration,
            max_duration=max_duration,
            prompt_path=prompt_path,
        )
        detection_result = self.gateway.detect_topics(request)
        self.last_detection_result = detection_result

        logger.info(
            f"Phase 1: {len(detection_result.topics)} topics "
            f"({detection_result.processing_time:.1f}s, "
            f"${detection_result.estimated_cost_usd:.4f})"
        )

        # Phase 2 & 3: 各話題に対して候補生成→AI選定
        suggestions = []
        for topic in detection_result.topics:
            suggestion = self._process_topic(topic, transcription, video_path, min_duration, max_duration)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def _process_topic(
        self,
        topic: TopicRange,
        transcription: TranscriptionResult,
        video_path: Path,
        min_duration: float,
        max_duration: float,
    ) -> ClipSuggestion | None:

        # Phase 2: 力任せ候補生成
        candidates = generate_candidates(topic, transcription, min_duration, max_duration)

        if not candidates:
            logger.warning(f"候補なし: {topic.title}")
            return None

        # 候補が1つだけならそのまま採用
        if len(candidates) == 1:
            best = candidates[0]
        else:
            # Phase 3: 上位候補の出来上がり音声をAIに評価させる
            best = self._ai_select_best(topic.title, candidates, video_path)

        if not best:
            return None

        return ClipSuggestion(
            id=best.segment_indices[0].__str__(),
            title=topic.title,
            text=best.text,
            time_ranges=best.time_ranges,
            total_duration=best.total_duration,
            score=topic.score,
            category=topic.category,
            reasoning=topic.reasoning,
            keywords=topic.keywords,
            variant_label=f"{len(best.segment_indices)}segs, score={best.mechanical_score:.0f}",
        )

    def _ai_select_best(
        self,
        title: str,
        candidates: list[ClipCandidate],
        video_path: Path,
    ) -> ClipCandidate | None:
        """上位候補の出来上がり音声を文字起こしし、AIに最良を選ばせる。"""
        from concurrent.futures import ThreadPoolExecutor

        # 各候補を並列に文字起こし
        def _transcribe(i: int) -> tuple[int, str]:
            text = self._transcribe_candidate(candidates[i], video_path)
            return (i, text) if text else (i, candidates[i].text[:200])

        with ThreadPoolExecutor(max_workers=min(len(candidates), 4)) as executor:
            transcriptions = list(executor.map(_transcribe, range(len(candidates))))

        if not transcriptions:
            return candidates[0]

        # AIに評価させる
        options = []
        for i, text in transcriptions:
            cand = candidates[i]
            options.append(
                f"候補{i+1}（{cand.total_duration:.0f}秒、{len(cand.time_ranges)}クリップ）:\n" f"{text[:300]}"
            )

        try:
            candidates_text = chr(10).join(options)
            selected_num = self.gateway.select_best_clip(
                title=title,
                candidates_text=candidates_text,
            )
            selected = max(0, min(selected_num - 1, len(candidates) - 1))
            logger.info(f"AI選定: 候補{selected+1} " f"({candidates[selected].total_duration:.0f}s)")
            return candidates[selected]

        except Exception as e:
            logger.warning(f"AI選定失敗: {e}")
            return candidates[0]

    def _transcribe_candidate(
        self,
        candidate: ClipCandidate,
        video_path: Path,
    ) -> str | None:
        """候補の出来上がり音声を文字起こしする。"""
        import os
        from dotenv import load_dotenv

        load_dotenv()
        from openai import OpenAI

        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("TEXTFFCUT_API_KEY")
        if not api_key:
            return None

        try:
            client = OpenAI(api_key=api_key)

            with tempfile.TemporaryDirectory() as tmpdir:
                # FFmpeg並列抽出ヘルパーを使用
                from use_cases.ai.srt_subtitle_generator import _extract_audio_parts_parallel

                parts = _extract_audio_parts_parallel(candidate.time_ranges, video_path, tmpdir, ffmpeg_timeout=15)
                if parts is None:
                    return None

                with open(f"{tmpdir}/list.txt", "w") as f:
                    for p in parts:
                        f.write(f"file '{p}'\n")
                proc = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        f"{tmpdir}/list.txt",
                        "-c",
                        "copy",
                        f"{tmpdir}/out.wav",
                    ],
                    capture_output=True,
                    timeout=15,
                )
                if proc.returncode != 0:
                    stderr = (
                        proc.stderr.decode(errors="replace")[:200]
                        if isinstance(proc.stderr, bytes)
                        else str(proc.stderr)[:200]
                    )
                    logger.debug(f"ffmpeg concat failed: {stderr}")
                    return None

                with open(f"{tmpdir}/out.wav", "rb") as f:
                    resp = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=f,
                        language="ja",
                        response_format="text",
                    )
                return resp if isinstance(resp, str) else str(resp)

        except Exception as e:
            logger.debug(f"Transcription failed: {e}")
            return None
