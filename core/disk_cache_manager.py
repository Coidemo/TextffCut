"""
ディスクキャッシュ管理モジュール
メモリ効率的な処理のためにAPI結果を一時的にディスクに保存
"""
import json
import pickle
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
import shutil

from utils.logging import get_logger

logger = get_logger(__name__)


class DiskCacheManager:
    """ディスクキャッシュ管理クラス"""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Args:
            cache_dir: キャッシュディレクトリ（Noneの場合は一時ディレクトリ）
        """
        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._is_temp = False
        else:
            self.cache_dir = Path(tempfile.mkdtemp(prefix="textffcut_cache_"))
            self._is_temp = True
        
        logger.info(f"ディスクキャッシュを初期化: {self.cache_dir}")
        
        # サブディレクトリ
        self.api_results_dir = self.cache_dir / "api_results"
        self.audio_chunks_dir = self.cache_dir / "audio_chunks"
        self.aligned_results_dir = self.cache_dir / "aligned_results"
        
        # ディレクトリ作成
        self.api_results_dir.mkdir(exist_ok=True)
        self.audio_chunks_dir.mkdir(exist_ok=True)
        self.aligned_results_dir.mkdir(exist_ok=True)
    
    def save_api_result(self, chunk_idx: int, segments: List[Dict[str, Any]]) -> Path:
        """API結果をディスクに保存"""
        file_path = self.api_results_dir / f"chunk_{chunk_idx:04d}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False)
        return file_path
    
    def load_api_result(self, chunk_idx: int) -> Optional[List[Dict[str, Any]]]:
        """API結果をディスクから読み込み"""
        file_path = self.api_results_dir / f"chunk_{chunk_idx:04d}.json"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"API結果の読み込みエラー: {file_path} - {e}")
            return None
    
    def save_audio_chunk(self, chunk_idx: int, audio_data: Any) -> Path:
        """音声チャンクをディスクに保存"""
        file_path = self.audio_chunks_dir / f"chunk_{chunk_idx:04d}.pkl"
        with open(file_path, 'wb') as f:
            pickle.dump(audio_data, f, protocol=pickle.HIGHEST_PROTOCOL)
        return file_path
    
    def load_audio_chunk(self, chunk_idx: int) -> Optional[Any]:
        """音声チャンクをディスクから読み込み"""
        file_path = self.audio_chunks_dir / f"chunk_{chunk_idx:04d}.pkl"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"音声チャンクの読み込みエラー: {file_path} - {e}")
            return None
    
    def save_aligned_result(self, chunk_idx: int, segments: List[Any]) -> Path:
        """アライメント結果をディスクに保存"""
        file_path = self.aligned_results_dir / f"chunk_{chunk_idx:04d}.pkl"
        with open(file_path, 'wb') as f:
            pickle.dump(segments, f, protocol=pickle.HIGHEST_PROTOCOL)
        return file_path
    
    def load_aligned_result(self, chunk_idx: int) -> Optional[List[Any]]:
        """アライメント結果をディスクから読み込み"""
        file_path = self.aligned_results_dir / f"chunk_{chunk_idx:04d}.pkl"
        if not file_path.exists():
            return None
        
        try:
            with open(file_path, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            logger.error(f"アライメント結果の読み込みエラー: {file_path} - {e}")
            return None
    
    def get_completed_api_chunks(self) -> List[int]:
        """完了したAPIチャンクのインデックスリストを取得"""
        indices = []
        for file_path in sorted(self.api_results_dir.glob("chunk_*.json")):
            try:
                idx = int(file_path.stem.split('_')[1])
                indices.append(idx)
            except:
                pass
        return indices
    
    def get_completed_align_chunks(self) -> List[int]:
        """完了したアライメントチャンクのインデックスリストを取得"""
        indices = []
        for file_path in sorted(self.aligned_results_dir.glob("chunk_*.pkl")):
            try:
                idx = int(file_path.stem.split('_')[1])
                indices.append(idx)
            except:
                pass
        return indices
    
    def get_cache_size_mb(self) -> float:
        """キャッシュの総サイズをMB単位で取得"""
        total_size = 0
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size / (1024 * 1024)
    
    def cleanup(self, keep_results: bool = False):
        """キャッシュをクリーンアップ"""
        if keep_results:
            # 結果以外を削除
            if self.api_results_dir.exists():
                shutil.rmtree(self.api_results_dir)
            if self.audio_chunks_dir.exists():
                shutil.rmtree(self.audio_chunks_dir)
        else:
            # 全て削除
            if self._is_temp and self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                logger.info(f"ディスクキャッシュを削除: {self.cache_dir}")
    
    def __del__(self):
        """デストラクタでクリーンアップ"""
        if self._is_temp:
            self.cleanup()