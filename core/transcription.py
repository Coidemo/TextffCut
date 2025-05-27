"""
文字起こし処理モジュール
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable

import whisperx
import torch

from config import Config


@dataclass
class TranscriptionSegment:
    """文字起こしセグメント"""
    start: float
    end: float
    text: str
    words: Optional[List[Dict[str, Any]]] = None
    chars: Optional[List[Dict[str, Any]]] = None


@dataclass
class TranscriptionResult:
    """文字起こし結果"""
    language: str
    segments: List[TranscriptionSegment]
    original_audio_path: str
    model_size: str
    processing_time: float
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            'language': self.language,
            'segments': [
                {
                    'start': seg.start,
                    'end': seg.end,
                    'text': seg.text,
                    'words': seg.words,
                    'chars': seg.chars
                }
                for seg in self.segments
            ],
            'original_audio_path': self.original_audio_path,
            'model_size': self.model_size,
            'processing_time': self.processing_time
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranscriptionResult':
        """辞書形式から生成"""
        segments = [
            TranscriptionSegment(
                start=seg['start'],
                end=seg['end'],
                text=seg['text'],
                words=seg.get('words'),
                chars=seg.get('chars')
            )
            for seg in data['segments']
        ]
        return cls(
            language=data['language'],
            segments=segments,
            original_audio_path=data.get('original_audio_path', ''),
            model_size=data.get('model_size', ''),
            processing_time=data.get('processing_time', 0.0)
        )
    
    def get_full_text(self) -> str:
        """全セグメントのテキストを結合"""
        full_text = ""
        for seg in self.segments:
            if seg.words:
                text = "".join(word['word'] for word in seg.words)
            else:
                text = seg.text
            full_text += text
        return full_text.strip()


class Transcriber:
    """文字起こし処理クラス"""
    
    def __init__(self, config: Config):
        self.config = config
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
    def get_cache_path(self, video_path: str, model_size: str) -> Path:
        """キャッシュファイルのパスを取得"""
        video_name = Path(video_path).stem
        cache_dir = self.config.paths.transcriptions_path
        return cache_dir / f"{video_name}_{model_size}.json"
    
    def load_from_cache(self, cache_path: Path) -> Optional[TranscriptionResult]:
        """キャッシュから文字起こし結果を読み込み"""
        if not cache_path.exists():
            return None
            
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return TranscriptionResult.from_dict(data)
        except Exception:
            return None
    
    def save_to_cache(self, result: TranscriptionResult, cache_path: Path):
        """文字起こし結果をキャッシュに保存"""
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
    
    def transcribe_chunk(self, chunk: Dict[str, Any], asr_model: Any) -> List[Dict[str, Any]]:
        """チャンク単位の文字起こし"""
        res = asr_model.transcribe(
            chunk["array"],
            batch_size=self.config.transcription.batch_size,
            language=self.config.transcription.language
        )
        
        # デバッグ情報
        if res["segments"]:
            print(f"チャンク処理完了: 開始 {chunk['start']:.1f}秒, セグメント数: {len(res['segments'])}")
        
        # チャンクのオフセットを適用
        for seg in res["segments"]:
            seg["start"] += chunk["start"]
            seg["end"] += chunk["start"]
            
        return res["segments"]
    
    def transcribe(
        self, 
        video_path: str, 
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True
    ) -> TranscriptionResult:
        """
        動画の文字起こしを実行
        
        Args:
            video_path: 動画ファイルのパス
            model_size: Whisperモデルサイズ
            progress_callback: 進捗コールバック関数 (progress: 0.0-1.0, status: str)
            use_cache: キャッシュを使用するか
            
        Returns:
            TranscriptionResult: 文字起こし結果
        """
        start_time = time.time()
        model_size = model_size or self.config.transcription.model_size
        
        # キャッシュ確認
        cache_path = self.get_cache_path(video_path, model_size)
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result
        
        # 音声の読み込み
        if progress_callback:
            progress_callback(0.0, "音声を読み込み中...")
        
        # デバッグ情報
        print(f"音声ファイルを読み込み中: {video_path}")
        if not Path(video_path).exists():
            print(f"警告: 音声ファイルが存在しません: {video_path}")
        
        audio = whisperx.load_audio(video_path)
        
        # モデルの読み込み
        if progress_callback:
            progress_callback(0.1, "モデルを読み込み中...")
        asr_model = whisperx.load_model(
            model_size,
            self.device,
            compute_type=self.config.transcription.compute_type,
            language=self.config.transcription.language
        )
        
        # チャンク分割
        chunk_sec = self.config.transcription.chunk_seconds
        sr = self.config.transcription.sample_rate
        num_workers = self.config.transcription.num_workers
        
        step = chunk_sec * sr
        chunks = [
            {
                "array": audio[i:i+step],
                "start": i / sr,
                "duration": min(step, len(audio)-i) / sr
            }
            for i in range(0, len(audio), step)
        ]
        
        # デバッグ情報
        total_audio_duration = len(audio) / sr
        print(f"音声の総時間: {total_audio_duration:.1f}秒, チャンク数: {len(chunks)}, チャンクサイズ: {chunk_sec}秒")
        
        # 並列処理で文字起こし
        segments_all = []
        total_chunks = len(chunks)
        completed_chunks = 0
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.transcribe_chunk, chunk, asr_model) for chunk in chunks]
            
            for future in as_completed(futures):
                segments = future.result()
                segments_all.extend(segments)
                completed_chunks += 1
                
                if progress_callback:
                    progress = 0.1 + (0.6 * completed_chunks / total_chunks)
                    status = f"文字起こし中... ({completed_chunks}/{total_chunks} チャンク)"
                    progress_callback(progress, status)
        
        # セグメントをソート
        segments_all.sort(key=lambda x: x["start"])
        
        # デバッグ情報
        print(f"文字起こし完了: 全セグメント数: {len(segments_all)}")
        if segments_all:
            print(f"最初のセグメント: {segments_all[0]['start']:.1f}秒 - {segments_all[0]['end']:.1f}秒")
            print(f"最後のセグメント: {segments_all[-1]['start']:.1f}秒 - {segments_all[-1]['end']:.1f}秒")
        
        # アライメント処理
        try:
            if progress_callback:
                progress_callback(0.7, "アライメント処理中...")
                
            align_model, meta = whisperx.load_align_model(
                self.config.transcription.language, 
                device=self.device
            )
            
            aligned_result = whisperx.align(
                segments_all,
                align_model,
                meta,
                audio,
                self.device,
                return_char_alignments=True
            )
            
            segments_all = aligned_result["segments"]
            
        except Exception as e:
            # アライメントが失敗しても続行
            print(f"アライメント処理に失敗しました: {e}")
        
        # 結果を構築
        segments = [
            TranscriptionSegment(
                start=seg["start"],
                end=seg["end"],
                text=seg["text"],
                words=seg.get("words"),
                chars=seg.get("chars")
            )
            for seg in segments_all
        ]
        
        processing_time = time.time() - start_time
        
        result = TranscriptionResult(
            language=self.config.transcription.language,
            segments=segments,
            original_audio_path=video_path,
            model_size=model_size,
            processing_time=processing_time
        )
        
        # キャッシュに保存
        self.save_to_cache(result, cache_path)
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        return result