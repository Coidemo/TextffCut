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
import numpy as np

try:
    import whisperx
    import torch
    WHISPERX_AVAILABLE = True
except ImportError:
    WHISPERX_AVAILABLE = False

from config import Config
from utils.logging import get_logger

logger = get_logger(__name__)


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
            # words が存在し、かつ空でない場合のみ words を使用
            if seg.words and len(seg.words) > 0:
                text = "".join(word['word'] for word in seg.words)
            else:
                text = seg.text
            full_text += text
        return full_text.strip()


class Transcriber:
    """文字起こし処理クラス（ローカル/API統合版）"""
    
    def __init__(self, config: Config):
        self.config = config
        
        # APIモードかローカルモードかを判定
        if self.config.transcription.use_api:
            # API版を使用
            from .transcription_api import APITranscriber
            self.api_transcriber = APITranscriber(config)
            self.device = None
            logger.info(f"APIモードで初期化: {self.config.transcription.api_provider}")
        else:
            # ローカル版を使用
            if not WHISPERX_AVAILABLE:
                raise ImportError(
                    "WhisperXが利用できません。API版を使用するか、WhisperXをインストールしてください。\n"
                    "pip install whisperx"
                )
            self.api_transcriber = None
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"ローカルモードで初期化: デバイス={self.device}")
        
    def get_cache_path(self, video_path: str, model_size: str) -> Path:
        """キャッシュファイルのパスを取得（TextffCutフォルダ内のtranscriptions/）"""
        from utils.file_utils import get_safe_filename
        
        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)
        
        # TextffCutフォルダ内のtranscriptions/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"
        
        # シンプルなファイル名（動画名不要）
        return cache_dir / f"{model_size}.json"
    
    def get_available_caches(self, video_path: str) -> List[Dict[str, Any]]:
        """利用可能なキャッシュファイルのリストを取得"""
        from utils.file_utils import get_safe_filename
        
        video_name = Path(video_path).stem
        video_parent = Path(video_path).parent
        safe_name = get_safe_filename(video_name)
        
        # 動画と同じディレクトリの {動画名}_TextffCut/transcriptions/ を確認
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        cache_dir = textffcut_dir / "transcriptions"
        
        if not cache_dir.exists():
            return []
        
        available_caches = []
        
        # キャッシュディレクトリ内のすべてのJSONファイルを検索
        for cache_file in cache_dir.glob("*.json"):
            try:
                # ファイル名からモデル情報を抽出
                # 新しい構造では: {モデル名}.json または {モデル名}_api.json
                filename = cache_file.stem
                
                # キャッシュファイルの情報を読み込み
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # APIモードかローカルモードかを判定
                is_api_mode = filename.endswith("_api")
                
                if is_api_mode:
                    # _apiを除去してモデル名を取得
                    model_size = filename.replace("_api", "")
                    mode = "API"
                else:
                    # そのままモデル名として使用
                    model_size = filename
                    mode = "ローカル"
                
                # ファイルの更新時刻を取得
                modified_time = cache_file.stat().st_mtime
                
                available_caches.append({
                    "model_size": model_size,
                    "mode": mode,
                    "is_api": is_api_mode,
                    "file_path": cache_file,
                    "modified_time": modified_time,
                    "processing_time": data.get("processing_time", 0.0),
                    "segments_count": len(data.get("segments", []))
                })
                
            except json.JSONDecodeError as e:
                logger.warning(f"キャッシュファイル形式エラー: {cache_file} - {e}")
                continue
            except OSError as e:
                logger.warning(f"キャッシュファイルアクセスエラー: {cache_file} - {e}")
                continue
            except Exception as e:
                logger.warning(f"キャッシュファイル読み込みエラー: {cache_file} - {e}")
                continue
        
        # 更新時刻でソート（新しい順）
        available_caches.sort(key=lambda x: x["modified_time"], reverse=True)
        
        return available_caches
    
    def load_from_cache(self, cache_path: Path) -> Optional[TranscriptionResult]:
        """キャッシュから文字起こし結果を読み込み"""
        if not cache_path.exists():
            return None
            
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return TranscriptionResult.from_dict(data)
        except json.JSONDecodeError as e:
            logger.error(f"キャッシュファイル形式エラー: {cache_path} - {e}")
            return None
        except OSError as e:
            logger.error(f"キャッシュファイルアクセスエラー: {cache_path} - {e}")
            return None
        except Exception as e:
            logger.error(f"キャッシュ読み込みエラー: {cache_path} - {e}")
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
        use_cache: bool = True,
        save_cache: bool = True
    ) -> TranscriptionResult:
        """
        動画の文字起こしを実行（API/ローカル自動切り替え）
        
        Args:
            video_path: 動画ファイルのパス
            model_size: Whisperモデルサイズ
            progress_callback: 進捗コールバック関数 (progress: 0.0-1.0, status: str)
            use_cache: キャッシュを読み込むか
            save_cache: キャッシュに保存するか
            
        Returns:
            TranscriptionResult: 文字起こし結果
        """
        # APIモードの場合はAPITranscriberに委譲
        if self.config.transcription.use_api:
            return self._transcribe_api(video_path, model_size, progress_callback, use_cache, save_cache)
        else:
            return self._transcribe_local(video_path, model_size, progress_callback, use_cache, save_cache)
    
    def _transcribe_api(
        self, 
        video_path: str, 
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True,
        save_cache: bool = True
    ) -> TranscriptionResult:
        """API版の文字起こし"""
        model_size = model_size or self.config.transcription.model_size
        
        # キャッシュ確認
        cache_path = self.get_cache_path(video_path, f"{model_size}_api")
        if use_cache:
            cached_result = self.load_from_cache(cache_path)
            if cached_result:
                if progress_callback:
                    progress_callback(1.0, "キャッシュから読み込み完了")
                return cached_result
        
        # APIで文字起こし実行
        result = self.api_transcriber.transcribe(video_path, model_size, progress_callback)
        
        # キャッシュに保存
        if save_cache:
            self.save_to_cache(result, cache_path)
        
        return result
    
    def _transcribe_local(
        self, 
        video_path: str, 
        model_size: Optional[str] = None,
        progress_callback: Optional[Callable[[float, str], None]] = None,
        use_cache: bool = True,
        save_cache: bool = True
    ) -> TranscriptionResult:
        """ローカル版の文字起こし（既存の実装）"""
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
        
        # チャンクを作成（APIモードと同じ処理）
        chunks = []
        MIN_CHUNK_DURATION = 1.0  # 1秒未満のチャンクは結合（品質向上のため）
        
        # 短いチャンクを一時保存する変数
        pending_chunk = None
        
        for i in range(0, len(audio), step):
            chunk_audio = audio[i:i+step]
            start_time = i / sr
            duration = len(chunk_audio) / sr
            
            # pending_chunkがある場合は先に結合を試みる
            if pending_chunk is not None:
                # 前の短いチャンクと現在のチャンクを結合
                combined_audio = np.concatenate([pending_chunk["array"], chunk_audio])
                combined_chunk = {
                    "array": combined_audio,
                    "start": pending_chunk["start"],
                    "duration": len(combined_audio) / sr
                }
                chunks.append(combined_chunk)
                logger.info(f"短いチャンクを次のチャンクと結合しました (新しい長さ: {combined_chunk['duration']:.1f}秒)")
                pending_chunk = None
                continue
            
            # 1秒未満のチャンクは処理しない
            if duration < MIN_CHUNK_DURATION:
                logger.warning(f"チャンクが短すぎます ({duration:.3f}秒) - 結合処理を行います")
                # 前のチャンクがある場合は結合
                if chunks:
                    last_chunk = chunks[-1]
                    # 前のチャンクに結合
                    combined_audio = np.concatenate([last_chunk["array"], chunk_audio])
                    chunks[-1] = {
                        "array": combined_audio,
                        "start": last_chunk["start"],
                        "duration": len(combined_audio) / sr
                    }
                    logger.info(f"短いチャンクを前のチャンクに結合しました (新しい長さ: {chunks[-1]['duration']:.1f}秒)")
                else:
                    # 最初のチャンクが短すぎる場合は一時保存して次と結合
                    pending_chunk = {
                        "array": chunk_audio,
                        "start": start_time,
                        "duration": duration
                    }
                    logger.warning(f"最初のチャンクが短いため、次のチャンクと結合します ({duration:.3f}秒)")
                continue
            
            chunks.append({
                "array": chunk_audio,
                "start": start_time,
                "duration": duration
            })
        
        # 最後にpending_chunkが残っている場合（音声全体が短い場合）
        if pending_chunk is not None:
            chunks.append(pending_chunk)
            logger.warning(f"最後の短いチャンクをそのまま追加します ({pending_chunk['duration']:.3f}秒)")
        
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
            
        except RuntimeError as e:
            if "CUDA" in str(e) or "memory" in str(e):
                logger.warning(f"メモリ不足でアライメント失敗、スキップ: {e}")
            else:
                logger.warning(f"ランタイムエラーでアライメント失敗、スキップ: {e}")
        except ImportError as e:
            logger.warning(f"アライメントモジュール不足、スキップ: {e}")
        except Exception as e:
            logger.warning(f"アライメント処理に失敗、スキップ: {e}")
        
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
        if save_cache:
            self.save_to_cache(result, cache_path)
        
        if progress_callback:
            progress_callback(1.0, "文字起こし完了")
        
        return result