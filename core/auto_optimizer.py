"""
自動最適化エンジン

メモリ使用状況に応じて動的にパラメータを調整し、
最適なパフォーマンスを実現する。
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
import logging

from utils.logging import get_logger

logger = get_logger(__name__)


class AutoOptimizer:
    """自動最適化エンジン"""
    
    # モデルサイズ別の基本設定
    MODEL_PROFILES = {
        'base': {
            'base_memory_gb': 1.5,
            'initial_chunk_seconds': 1200,  # 20分
            'initial_align_chunk_seconds': 1800,  # 30分
            'initial_max_workers': 3,
            'initial_batch_size': 16,
        },
        'small': {
            'base_memory_gb': 2.0,
            'initial_chunk_seconds': 900,  # 15分
            'initial_align_chunk_seconds': 1200,  # 20分
            'initial_max_workers': 2,
            'initial_batch_size': 12,
        },
        'medium': {
            'base_memory_gb': 3.0,
            'initial_chunk_seconds': 600,  # 10分
            'initial_align_chunk_seconds': 900,  # 15分
            'initial_max_workers': 2,
            'initial_batch_size': 8,
        },
        'large': {
            'base_memory_gb': 4.0,
            'initial_chunk_seconds': 480,  # 8分
            'initial_align_chunk_seconds': 600,  # 10分
            'initial_max_workers': 1,
            'initial_batch_size': 4,
        },
        'large-v3': {
            'base_memory_gb': 4.5,
            'initial_chunk_seconds': 480,  # 8分
            'initial_align_chunk_seconds': 600,  # 10分
            'initial_max_workers': 1,
            'initial_batch_size': 4,
        }
    }
    
    # チャンクサイズの制限
    CHUNK_LIMITS = {
        'absolute_minimum': 180,  # 3分
        'emergency_minimum': 300,  # 5分
        'maximum': 1800,  # 30分
    }
    
    def __init__(self, model_size: str, target_memory_percent: float = 75.0):
        """
        初期化
        
        Args:
            model_size: Whisperモデルサイズ
            target_memory_percent: 目標メモリ使用率
        """
        # モデルサイズの検証
        if model_size not in self.MODEL_PROFILES:
            logger.warning(f"Unknown model size: {model_size}, using 'base' as fallback")
            model_size = 'base'
            
        self.model_size = model_size
        self.target_memory_percent = max(50.0, min(90.0, target_memory_percent))
        
        # 現在のパラメータ（プロファイルから初期化）
        self.current_params = self._load_or_create_profile()
        
        # 調整履歴
        self.adjustment_history = []
        self.last_memory_percent = 0.0
        
        logger.info(f"AutoOptimizer initialized for {model_size} model, target memory: {self.target_memory_percent}%")
    
    def _load_or_create_profile(self) -> Dict:
        """プロファイルの読み込みまたは作成"""
        profile_dir = Path.home() / '.textffcut'
        profile_path = profile_dir / f'optimizer_profile_{self.model_size}.json'
        
        try:
            # ディレクトリ作成
            profile_dir.mkdir(exist_ok=True)
            
            # 既存プロファイルの読み込み
            if profile_path.exists():
                with open(profile_path, 'r') as f:
                    profile = json.load(f)
                    logger.info(f"Loaded existing profile for {self.model_size}")
                    return profile.get('optimal_params', self._get_initial_params())
            
        except Exception as e:
            logger.warning(f"Failed to load profile: {e}")
        
        # デフォルトパラメータを返す
        return self._get_initial_params()
    
    def _get_initial_params(self) -> Dict:
        """モデルサイズに応じた初期パラメータ"""
        profile = self.MODEL_PROFILES[self.model_size]
        return {
            'chunk_seconds': profile['initial_chunk_seconds'],
            'align_chunk_seconds': profile['initial_align_chunk_seconds'],
            'max_workers': profile['initial_max_workers'],
            'batch_size': profile['initial_batch_size'],
        }
    
    def get_optimal_params(self, current_memory_percent: float) -> Dict:
        """
        現在のメモリ使用率から最適なパラメータを計算
        
        Args:
            current_memory_percent: 現在のメモリ使用率（0-100）
            
        Returns:
            最適化されたパラメータ辞書
        """
        # 入力検証
        try:
            current_memory_percent = float(current_memory_percent)
            current_memory_percent = max(0.0, min(100.0, current_memory_percent))
        except (TypeError, ValueError):
            logger.error(f"Invalid memory percent: {current_memory_percent}, using 50.0")
            current_memory_percent = 50.0
        
        # メモリ変化速度の計算
        memory_velocity = current_memory_percent - self.last_memory_percent
        self.last_memory_percent = current_memory_percent
        
        # 調整方向の決定
        adjustment_type = self._determine_adjustment_type(
            current_memory_percent, memory_velocity
        )
        
        # パラメータ調整
        new_params = self._adjust_parameters(adjustment_type)
        
        # 履歴に記録
        self.adjustment_history.append({
            'timestamp': datetime.now().isoformat(),
            'memory_percent': current_memory_percent,
            'adjustment_type': adjustment_type,
            'params': new_params.copy()
        })
        
        # 履歴は最新20件のみ保持
        if len(self.adjustment_history) > 20:
            self.adjustment_history.pop(0)
        
        self.current_params = new_params
        return new_params
    
    def _determine_adjustment_type(self, memory_percent: float, velocity: float) -> str:
        """調整タイプの決定"""
        
        # 緊急レベル
        if memory_percent > 90:
            return 'emergency_decrease'
        elif memory_percent > 85:
            return 'aggressive_decrease'
        
        # 警戒レベル
        elif memory_percent > 80:
            if velocity > 5:  # 急上昇中
                return 'moderate_decrease'
            else:
                return 'slight_decrease'
        
        # 目標範囲付近
        elif 70 <= memory_percent <= 80:
            if abs(memory_percent - self.target_memory_percent) < 5:
                return 'maintain'
            elif memory_percent > self.target_memory_percent:
                return 'slight_decrease'
            else:
                return 'slight_increase'
        
        # 余裕あり
        elif memory_percent < 60:
            return 'moderate_increase'
        else:
            return 'slight_increase'
    
    def _adjust_parameters(self, adjustment_type: str) -> Dict:
        """パラメータの調整"""
        params = self.current_params.copy()
        
        adjustments = {
            'emergency_decrease': {
                'chunk_factor': 0.5,  # 半分に
                'worker_change': -2,
                'batch_factor': 0.25
            },
            'aggressive_decrease': {
                'chunk_factor': 0.7,
                'worker_change': -1,
                'batch_factor': 0.5
            },
            'moderate_decrease': {
                'chunk_seconds_change': -180,  # -3分
                'worker_change': -1,
                'batch_change': -4
            },
            'slight_decrease': {
                'chunk_seconds_change': -60,  # -1分
                'worker_change': 0,
                'batch_change': -2
            },
            'maintain': {
                # 変更なし
            },
            'slight_increase': {
                'chunk_seconds_change': 60,  # +1分
                'worker_change': 0,
                'batch_change': 2
            },
            'moderate_increase': {
                'chunk_seconds_change': 120,  # +2分
                'worker_change': 1,
                'batch_change': 4
            }
        }
        
        adj = adjustments.get(adjustment_type, {})
        
        # チャンクサイズ調整
        if 'chunk_factor' in adj:
            params['chunk_seconds'] = int(params['chunk_seconds'] * adj['chunk_factor'])
            params['align_chunk_seconds'] = int(params['align_chunk_seconds'] * adj['chunk_factor'])
        elif 'chunk_seconds_change' in adj:
            params['chunk_seconds'] += adj['chunk_seconds_change']
            params['align_chunk_seconds'] += int(adj['chunk_seconds_change'] * 1.5)
        
        # 制限の適用
        params['chunk_seconds'] = max(
            self.CHUNK_LIMITS['absolute_minimum'],
            min(self.CHUNK_LIMITS['maximum'], params['chunk_seconds'])
        )
        params['align_chunk_seconds'] = max(
            self.CHUNK_LIMITS['absolute_minimum'],
            min(self.CHUNK_LIMITS['maximum'] * 2, params['align_chunk_seconds'])
        )
        
        # ワーカー数調整
        if 'worker_change' in adj:
            params['max_workers'] = max(1, min(4, 
                params['max_workers'] + adj['worker_change']))
        
        # バッチサイズ調整
        if 'batch_factor' in adj:
            params['batch_size'] = max(1, int(params['batch_size'] * adj['batch_factor']))
        elif 'batch_change' in adj:
            params['batch_size'] = max(1, min(32, 
                params['batch_size'] + adj['batch_change']))
        
        logger.debug(f"Adjusted parameters: {adjustment_type} -> {params}")
        return params
    
    def save_successful_run(self, params: Dict, metrics: Dict) -> None:
        """
        成功した実行のパラメータを保存
        
        Args:
            params: 使用したパラメータ
            metrics: 実行メトリクス（完了時間、平均メモリ使用率等）
        """
        try:
            # 異常値の除外
            if not self._is_valid_metrics(metrics):
                logger.warning("Invalid metrics, not saving")
                return
            
            profile_dir = Path.home() / '.textffcut'
            profile_path = profile_dir / f'optimizer_profile_{self.model_size}.json'
            
            profile = {
                'model_size': self.model_size,
                'last_updated': datetime.now().isoformat(),
                'successful_runs': metrics.get('successful_runs', 1),
                'average_memory_usage': metrics.get('avg_memory', 0),
                'optimal_params': params,
                'metrics': metrics
            }
            
            # ディレクトリ作成
            profile_dir.mkdir(exist_ok=True)
            
            # 保存
            with open(profile_path, 'w') as f:
                json.dump(profile, f, indent=2)
                
            logger.info(f"Saved successful profile for {self.model_size}")
            
        except Exception as e:
            logger.error(f"Failed to save profile: {e}")
            # エラーでも処理は継続
    
    def _is_valid_metrics(self, metrics: Dict) -> bool:
        """メトリクスの妥当性チェック"""
        if not metrics.get('completed', False):
            return False
            
        avg_memory = metrics.get('avg_memory', 0)
        if not (5 <= avg_memory <= 95):  # 異常なメモリ使用率（5%未満または95%超）
            return False
            
        return True
    
    def get_status(self) -> Dict:
        """現在の最適化状態を取得"""
        return {
            'model_size': self.model_size,
            'target_memory': self.target_memory_percent,
            'current_params': self.current_params.copy(),
            'last_adjustment': self.adjustment_history[-1] if self.adjustment_history else None
        }