"""
パフォーマンス追跡ユーティリティ
処理時間の測定、統計情報の計算、フィードバック表示を行う
"""
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

@dataclass
class PerformanceMetrics:
    """パフォーマンス指標"""
    start_time: float
    end_time: Optional[float] = None
    duration_seconds: float = 0.0
    video_duration_seconds: float = 0.0
    realtime_factor: float = 0.0  # 処理速度（1.0 = リアルタイム）
    segments_processed: int = 0
    mode: str = "unknown"  # normal, optimized, ultra_optimized
    model_size: str = "base"
    use_api: bool = False
    api_chunks: int = 0
    alignment_chunks: int = 0
    
    def calculate_metrics(self):
        """メトリクスを計算"""
        if self.end_time and self.start_time:
            self.duration_seconds = self.end_time - self.start_time
            
            if self.video_duration_seconds > 0 and self.duration_seconds > 0:
                # リアルタイム係数：動画時間 / 処理時間
                # 例：90分動画を10分で処理 = 9.0倍速
                self.realtime_factor = self.video_duration_seconds / self.duration_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_seconds": self.duration_seconds,
            "video_duration_seconds": self.video_duration_seconds,
            "realtime_factor": self.realtime_factor,
            "segments_processed": self.segments_processed,
            "mode": self.mode,
            "model_size": self.model_size,
            "use_api": self.use_api,
            "api_chunks": self.api_chunks,
            "alignment_chunks": self.alignment_chunks,
            "timestamp": datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PerformanceMetrics':
        """辞書から復元"""
        return cls(**{k: v for k, v in data.items() if k != 'timestamp'})


class PerformanceTracker:
    """パフォーマンス追跡クラス"""
    
    def __init__(self, video_path: str):
        self.video_path = video_path
        self.metrics = None
        self.history_file = self._get_history_file()
        
    def _get_history_file(self) -> Path:
        """履歴ファイルのパスを取得"""
        from utils.file_utils import get_safe_filename
        
        video_name = Path(self.video_path).stem
        video_parent = Path(self.video_path).parent
        safe_name = get_safe_filename(video_name)
        
        # TextffCutフォルダ内のperformance/サブフォルダ
        textffcut_dir = video_parent / f"{safe_name}_TextffCut"
        perf_dir = textffcut_dir / "performance"
        perf_dir.mkdir(parents=True, exist_ok=True)
        
        return perf_dir / "history.json"
    
    def start_tracking(self, mode: str, model_size: str, use_api: bool, 
                      video_duration: float) -> PerformanceMetrics:
        """パフォーマンス追跡を開始"""
        self.metrics = PerformanceMetrics(
            start_time=time.time(),
            mode=mode,
            model_size=model_size,
            use_api=use_api,
            video_duration_seconds=video_duration
        )
        return self.metrics
    
    def end_tracking(self, segments_processed: int = 0, 
                    api_chunks: int = 0, alignment_chunks: int = 0):
        """パフォーマンス追跡を終了"""
        if self.metrics:
            self.metrics.end_time = time.time()
            self.metrics.segments_processed = segments_processed
            self.metrics.api_chunks = api_chunks
            self.metrics.alignment_chunks = alignment_chunks
            self.metrics.calculate_metrics()
            
            # 履歴に保存
            self._save_to_history(self.metrics)
    
    def _save_to_history(self, metrics: PerformanceMetrics):
        """履歴に保存"""
        history = self.load_history()
        history.append(metrics.to_dict())
        
        # 最新20件のみ保持
        history = history[-20:]
        
        with open(self.history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    
    def load_history(self) -> List[Dict[str, Any]]:
        """履歴を読み込み"""
        if not self.history_file.exists():
            return []
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    
    def get_mode_statistics(self) -> Dict[str, Dict[str, float]]:
        """モード別の統計情報を取得"""
        history = self.load_history()
        
        if not history:
            return {}
        
        # モード別に集計
        mode_stats = {}
        
        for record in history:
            mode = record.get('mode', 'unknown')
            if mode not in mode_stats:
                mode_stats[mode] = {
                    'count': 0,
                    'total_duration': 0.0,
                    'total_video_duration': 0.0,
                    'avg_realtime_factor': 0.0,
                    'max_realtime_factor': 0.0,
                    'min_realtime_factor': float('inf')
                }
            
            stats = mode_stats[mode]
            stats['count'] += 1
            stats['total_duration'] += record.get('duration_seconds', 0)
            stats['total_video_duration'] += record.get('video_duration_seconds', 0)
            
            rf = record.get('realtime_factor', 0)
            if rf > 0:
                if rf > stats['max_realtime_factor']:
                    stats['max_realtime_factor'] = rf
                if rf < stats['min_realtime_factor']:
                    stats['min_realtime_factor'] = rf
        
        # 平均を計算
        for mode, stats in mode_stats.items():
            if stats['count'] > 0 and stats['total_duration'] > 0:
                stats['avg_realtime_factor'] = stats['total_video_duration'] / stats['total_duration']
            
            # 無限大を0に変換
            if stats['min_realtime_factor'] == float('inf'):
                stats['min_realtime_factor'] = 0.0
        
        return mode_stats
    
    def get_best_mode(self) -> Optional[str]:
        """最も高速なモードを取得"""
        mode_stats = self.get_mode_statistics()
        
        if not mode_stats:
            return None
        
        best_mode = None
        best_factor = 0.0
        
        for mode, stats in mode_stats.items():
            if stats['avg_realtime_factor'] > best_factor:
                best_factor = stats['avg_realtime_factor']
                best_mode = mode
        
        return best_mode