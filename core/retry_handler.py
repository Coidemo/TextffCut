"""
TextffCut リトライハンドラー

処理の失敗時に適切なリトライ戦略を実行するハンドラー。
エラーの種類に応じて異なるリトライ戦略を適用します。
"""

import time
import random
from typing import Callable, Optional, TypeVar, Dict, Any, List
from functools import wraps
import logging

from .exceptions import (
    ProcessingError,
    TranscriptionValidationError,
    WordsFieldMissingError,
    AlignmentValidationError,
    SubprocessError,
    CacheError,
    RetryExhaustedError
)

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryStrategy:
    """リトライ戦略の基底クラス"""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        Args:
            max_retries: 最大リトライ回数
            base_delay: 基本待機時間（秒）
            max_delay: 最大待機時間（秒）
            exponential_base: 指数バックオフの基数
            jitter: ジッターを追加するか
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """
        リトライすべきかどうかを判定
        
        Args:
            error: 発生したエラー
            attempt: 現在の試行回数（0から開始）
            
        Returns:
            リトライすべきならTrue
        """
        if attempt >= self.max_retries:
            return False
        
        # エラーの種類によってリトライ判定
        if isinstance(error, WordsFieldMissingError):
            # wordsフィールド欠落は基本的にリトライしない（再実行が必要）
            return False
        
        if isinstance(error, TranscriptionValidationError):
            # 検証エラーは内容による
            if "words情報が欠落" in str(error):
                return False  # 根本的な問題なのでリトライしない
            return True
        
        if isinstance(error, AlignmentValidationError):
            # アライメントエラーは回復可能
            return error.recoverable
        
        if isinstance(error, SubprocessError):
            # サブプロセスエラーは基本的にリトライ
            return True
        
        if isinstance(error, CacheError):
            # キャッシュエラーは回復可能
            return True
        
        if isinstance(error, ProcessingError):
            # その他の処理エラーは回復可能フラグで判定
            return error.recoverable
        
        # 未知のエラーはリトライしない
        return False
    
    def get_delay(self, attempt: int) -> float:
        """
        次のリトライまでの待機時間を取得
        
        Args:
            attempt: 現在の試行回数
            
        Returns:
            待機時間（秒）
        """
        # 指数バックオフ
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay
        )
        
        # ジッターの追加
        if self.jitter:
            delay *= (0.5 + random.random())
        
        return delay


class AdaptiveRetryStrategy(RetryStrategy):
    """エラーの種類に応じて戦略を変更するリトライ戦略"""
    
    def __init__(self):
        super().__init__()
        
        # エラータイプ別の設定
        self.error_configs = {
            SubprocessError: {
                "max_retries": 3,
                "base_delay": 2.0,
                "exponential_base": 2.0
            },
            AlignmentValidationError: {
                "max_retries": 2,
                "base_delay": 5.0,
                "exponential_base": 1.5
            },
            CacheError: {
                "max_retries": 5,
                "base_delay": 0.5,
                "exponential_base": 1.5
            }
        }
    
    def should_retry(self, error: Exception, attempt: int) -> bool:
        """エラータイプに応じたリトライ判定"""
        # エラータイプ別の設定を取得
        for error_type, config in self.error_configs.items():
            if isinstance(error, error_type):
                return attempt < config["max_retries"]
        
        # デフォルトの判定
        return super().should_retry(error, attempt)
    
    def get_delay(self, error: Exception, attempt: int) -> float:
        """エラータイプに応じた待機時間"""
        # エラータイプ別の設定を取得
        for error_type, config in self.error_configs.items():
            if isinstance(error, error_type):
                base_delay = config["base_delay"]
                exponential_base = config["exponential_base"]
                
                delay = min(
                    base_delay * (exponential_base ** attempt),
                    self.max_delay
                )
                
                if self.jitter:
                    delay *= (0.5 + random.random())
                
                return delay
        
        # デフォルトの待機時間
        return super().get_delay(attempt)


def with_retry(
    strategy: Optional[RetryStrategy] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    リトライ機能を追加するデコレーター
    
    Args:
        strategy: リトライ戦略（省略時はデフォルト）
        on_retry: リトライ時のコールバック
    """
    if strategy is None:
        strategy = RetryStrategy()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_error = None
            
            for attempt in range(strategy.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                    
                except Exception as e:
                    last_error = e
                    
                    # リトライ判定
                    if not strategy.should_retry(e, attempt):
                        logger.warning(
                            f"{func.__name__}でリトライ不可能なエラー: {str(e)}"
                        )
                        raise
                    
                    if attempt < strategy.max_retries:
                        # 待機時間の計算
                        if isinstance(strategy, AdaptiveRetryStrategy):
                            delay = strategy.get_delay(e, attempt)
                        else:
                            delay = strategy.get_delay(attempt)
                        
                        logger.info(
                            f"{func.__name__}のリトライ {attempt + 1}/{strategy.max_retries} "
                            f"({delay:.1f}秒待機): {str(e)}"
                        )
                        
                        # コールバック実行
                        if on_retry:
                            on_retry(e, attempt)
                        
                        # 待機
                        time.sleep(delay)
            
            # 全てのリトライが失敗
            raise RetryExhaustedError(
                f"{func.__name__}が{strategy.max_retries}回の再試行後も失敗しました",
                attempts=strategy.max_retries + 1,
                last_error=last_error
            )
        
        return wrapper
    return decorator


class RetryHandler:
    """リトライ処理を管理するハンドラー"""
    
    def __init__(self, strategy: Optional[RetryStrategy] = None):
        """
        Args:
            strategy: リトライ戦略
        """
        self.strategy = strategy or AdaptiveRetryStrategy()
        self.retry_history: List[Dict[str, Any]] = []
    
    def execute_with_retry(
        self,
        func: Callable[..., T],
        *args,
        on_retry: Optional[Callable[[Exception, int], None]] = None,
        **kwargs
    ) -> T:
        """
        リトライ機能付きで関数を実行
        
        Args:
            func: 実行する関数
            on_retry: リトライ時のコールバック
            *args, **kwargs: 関数の引数
            
        Returns:
            関数の戻り値
        """
        last_error = None
        start_time = time.time()
        
        for attempt in range(self.strategy.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                
                # 成功時の記録
                self.retry_history.append({
                    "function": func.__name__,
                    "attempt": attempt,
                    "success": True,
                    "duration": time.time() - start_time
                })
                
                return result
                
            except Exception as e:
                last_error = e
                
                # エラーの記録
                self.retry_history.append({
                    "function": func.__name__,
                    "attempt": attempt,
                    "success": False,
                    "error": str(e),
                    "error_type": type(e).__name__
                })
                
                # リトライ判定
                if not self.strategy.should_retry(e, attempt):
                    logger.warning(
                        f"{func.__name__}でリトライ不可能なエラー: {str(e)}"
                    )
                    raise
                
                if attempt < self.strategy.max_retries:
                    # 待機時間の計算
                    if isinstance(self.strategy, AdaptiveRetryStrategy):
                        delay = self.strategy.get_delay(e, attempt)
                    else:
                        delay = self.strategy.get_delay(attempt)
                    
                    logger.info(
                        f"{func.__name__}のリトライ {attempt + 1}/{self.strategy.max_retries} "
                        f"({delay:.1f}秒待機): {str(e)}"
                    )
                    
                    # コールバック実行
                    if on_retry:
                        on_retry(e, attempt)
                    
                    # 待機
                    time.sleep(delay)
        
        # 全てのリトライが失敗
        total_duration = time.time() - start_time
        
        raise RetryExhaustedError(
            f"{func.__name__}が{self.strategy.max_retries}回の再試行後も失敗しました",
            attempts=self.strategy.max_retries + 1,
            last_error=last_error
        )
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """リトライ統計を取得"""
        if not self.retry_history:
            return {}
        
        total_attempts = len(self.retry_history)
        successful_attempts = sum(1 for h in self.retry_history if h["success"])
        failed_attempts = total_attempts - successful_attempts
        
        # 関数別の統計
        function_stats = {}
        for history in self.retry_history:
            func_name = history["function"]
            if func_name not in function_stats:
                function_stats[func_name] = {
                    "attempts": 0,
                    "successes": 0,
                    "failures": 0,
                    "error_types": {}
                }
            
            stats = function_stats[func_name]
            stats["attempts"] += 1
            
            if history["success"]:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
                error_type = history.get("error_type", "Unknown")
                stats["error_types"][error_type] = stats["error_types"].get(error_type, 0) + 1
        
        return {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "failed_attempts": failed_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0,
            "function_stats": function_stats
        }