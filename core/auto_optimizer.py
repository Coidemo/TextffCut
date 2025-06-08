"""
自動最適化エンジン

メモリ使用状況に応じて動的にパラメータを調整し、
最適なパフォーマンスを実現する。
"""

import os
from datetime import datetime
from typing import Dict, Optional, Tuple
import logging

from utils.logging import get_logger

logger = get_logger(__name__)


class AutoOptimizer:
    """自動最適化エンジン"""
    
    # 診断フェーズの設定
    DIAGNOSTIC_CHUNK_SECONDS = 30  # 最初の診断用チャンクサイズ
    DIAGNOSTIC_CHUNKS_COUNT = 3    # 診断用チャンク数
    
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
            'initial_chunk_seconds': 300,  # 5分（より保守的に）
            'initial_align_chunk_seconds': 480,  # 8分
            'initial_max_workers': 1,
            'initial_batch_size': 2,  # 2に削減（メモリ節約）
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
        
        # 診断フェーズ管理
        self.diagnostic_mode = True
        self.diagnostic_chunks_processed = 0
        self.diagnostic_data = {
            'memory_samples': [],
            'processing_times': [],
            'memory_growth_rate': 0.0,
            'base_memory_usage': 0.0
        }
        
        logger.info(f"AutoOptimizer initialized for {model_size} model, target memory: {self.target_memory_percent}%")
    
    def _load_or_create_profile(self) -> Dict:
        """初期パラメータを取得"""
        # 常にデフォルトパラメータを返す
        # ユーザー環境は実行のたびに変わる可能性があるため、
        # 毎回診断フェーズから開始する
        return self._get_initial_params()
    
    def _get_initial_params(self) -> Dict:
        """モデルサイズに応じた初期パラメータ"""
        profile = self.MODEL_PROFILES[self.model_size]
        
        # メモリ状況を確認
        try:
            import psutil
            available_gb = psutil.virtual_memory().available / (1024 ** 3)
            
            # large-v3の場合、利用可能メモリが少ない場合はさらに制限
            if self.model_size == 'large-v3' and available_gb < 8:
                logger.warning(f"Low memory detected for large-v3: {available_gb:.1f}GB available")
                return {
                    'chunk_seconds': min(180, profile['initial_chunk_seconds']),  # 最大3分
                    'align_chunk_seconds': min(300, profile['initial_align_chunk_seconds']),  # 最大5分
                    'max_workers': 1,
                    'batch_size': 1,  # 最小値
                }
        except Exception as e:
            logger.warning(f"Failed to check memory: {e}")
        
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
        
        # 診断フェーズの処理
        if self.diagnostic_mode:
            return self._handle_diagnostic_phase(current_memory_percent)
        
        # 通常の最適化処理
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
    
    def _handle_diagnostic_phase(self, current_memory_percent: float) -> Dict:
        """診断フェーズの処理"""
        import time
        
        # メモリサンプルを記録
        self.diagnostic_data['memory_samples'].append({
            'chunk_number': self.diagnostic_chunks_processed,
            'memory_percent': current_memory_percent,
            'timestamp': time.time()
        })
        
        # 最初のチャンクでベースメモリを記録
        if self.diagnostic_chunks_processed == 0:
            self.diagnostic_data['base_memory_usage'] = current_memory_percent
            logger.info(f"診断フェーズ開始 - ベースメモリ: {current_memory_percent:.1f}%")
        
        self.diagnostic_chunks_processed += 1
        
        # 診断フェーズ中は保守的なパラメータを使用
        diagnostic_params = {
            'chunk_seconds': self.DIAGNOSTIC_CHUNK_SECONDS,
            'align_chunk_seconds': self.DIAGNOSTIC_CHUNK_SECONDS * 2,
            'max_workers': 1,
            'batch_size': min(4, self.current_params['batch_size'])  # 最大4
        }
        
        # 診断フェーズ完了の判定
        if self.diagnostic_chunks_processed >= self.DIAGNOSTIC_CHUNKS_COUNT:
            self.diagnostic_mode = False
            
            # メモリ増加率を計算
            if len(self.diagnostic_data['memory_samples']) >= 2:
                first_sample = self.diagnostic_data['memory_samples'][0]
                last_sample = self.diagnostic_data['memory_samples'][-1]
                
                memory_increase = last_sample['memory_percent'] - first_sample['memory_percent']
                time_elapsed = last_sample['timestamp'] - first_sample['timestamp']
                
                # 1チャンクあたりのメモリ増加率
                self.diagnostic_data['memory_growth_rate'] = memory_increase / self.diagnostic_chunks_processed
                
                logger.info(f"診断フェーズ完了:")
                logger.info(f"  - ベースメモリ: {self.diagnostic_data['base_memory_usage']:.1f}%")
                logger.info(f"  - メモリ増加率: {self.diagnostic_data['memory_growth_rate']:.2f}%/チャンク")
                logger.info(f"  - 現在のメモリ: {current_memory_percent:.1f}%")
                
                # 診断結果に基づいて最適なパラメータを予測
                predicted_params = self._predict_optimal_params()
                self.current_params = predicted_params
                
                logger.info(f"予測された最適パラメータ:")
                logger.info(f"  - チャンクサイズ: {predicted_params['chunk_seconds']}秒")
                logger.info(f"  - バッチサイズ: {predicted_params['batch_size']}")
                
                return predicted_params
        
        logger.info(f"診断フェーズ {self.diagnostic_chunks_processed}/{self.DIAGNOSTIC_CHUNKS_COUNT} - メモリ: {current_memory_percent:.1f}%")
        return diagnostic_params
    
    def _predict_optimal_params(self) -> Dict:
        """診断結果から最適なパラメータを予測"""
        base_memory = self.diagnostic_data['base_memory_usage']
        growth_rate = self.diagnostic_data['memory_growth_rate']
        
        # 利用可能なメモリ容量を計算（目標使用率まで）
        available_memory_headroom = self.target_memory_percent - base_memory
        
        # メモリ増加率が0または負の場合は、デフォルトパラメータを使用
        if growth_rate <= 0:
            logger.warning("メモリ増加率が異常です。デフォルトパラメータを使用します。")
            return self._get_initial_params()
        
        # 最大チャンク数を予測（メモリ制限内で処理できるチャンク数）
        max_chunks_within_memory = int(available_memory_headroom / growth_rate)
        
        # チャンクサイズを計算（30秒チャンクでの増加率から推定）
        # 例: 3チャンクで5%増加した場合、15チャンク（450秒）まで安全
        predicted_chunk_seconds = min(
            max_chunks_within_memory * self.DIAGNOSTIC_CHUNK_SECONDS,
            self.current_params['chunk_seconds']  # 初期値を上限とする
        )
        
        # 最小値の保証
        predicted_chunk_seconds = max(
            self.CHUNK_LIMITS['absolute_minimum'],
            predicted_chunk_seconds
        )
        
        # バッチサイズの調整（メモリ余裕に応じて）
        if available_memory_headroom > 40:  # 40%以上の余裕
            batch_size = self.current_params['batch_size']
        elif available_memory_headroom > 20:  # 20-40%の余裕
            batch_size = max(1, self.current_params['batch_size'] // 2)
        else:  # 20%未満の余裕
            batch_size = 1
        
        return {
            'chunk_seconds': int(predicted_chunk_seconds),
            'align_chunk_seconds': int(predicted_chunk_seconds * 1.5),
            'max_workers': 1 if growth_rate > 2 else self.current_params['max_workers'],
            'batch_size': batch_size
        }
    
    def save_successful_run(self, params: Dict, metrics: Dict) -> None:
        """
        成功した実行のパラメータをログに記録
        
        Args:
            params: 使用したパラメータ
            metrics: 実行メトリクス（完了時間、平均メモリ使用率等）
        """
        # プロファイルの保存は行わず、ログに記録のみ
        if not self._is_valid_metrics(metrics):
            logger.warning("Invalid metrics, not logging")
            return
        
        logger.info(f"Successful run completed for {self.model_size}:")
        logger.info(f"  - Average memory: {metrics.get('avg_memory', 0):.1f}%")
        logger.info(f"  - Processing time: {metrics.get('processing_time', 0):.1f}s")
        logger.info(f"  - Optimal params: chunk={params['chunk_seconds']}s, batch={params['batch_size']}")
    
    def _is_valid_metrics(self, metrics: Dict) -> bool:
        """メトリクスの妥当性チェック"""
        if not metrics.get('completed', False):
            return False
            
        avg_memory = metrics.get('avg_memory', 0)
        if not (5 <= avg_memory <= 95):  # 異常なメモリ使用率（5%未満または95%超）
            return False
            
        return True
    
    def reset_diagnostic_mode(self) -> None:
        """診断モードをリセット（新しい処理開始時）"""
        self.diagnostic_mode = True
        self.diagnostic_chunks_processed = 0
        self.diagnostic_data = {
            'memory_samples': [],
            'processing_times': [],
            'memory_growth_rate': 0.0,
            'base_memory_usage': 0.0
        }
        logger.info("診断モードをリセットしました")
    
    def get_status(self) -> Dict:
        """現在の最適化状態を取得"""
        status = {
            'model_size': self.model_size,
            'target_memory': self.target_memory_percent,
            'current_params': self.current_params.copy(),
            'last_adjustment': self.adjustment_history[-1] if self.adjustment_history else None,
            'diagnostic_mode': self.diagnostic_mode
        }
        
        if self.diagnostic_mode:
            status['diagnostic_progress'] = f"{self.diagnostic_chunks_processed}/{self.DIAGNOSTIC_CHUNKS_COUNT}"
        
        return status