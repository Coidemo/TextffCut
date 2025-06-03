"""
長時間動画処理のためのタイムアウトハンドラー
APIレート制限とリトライ処理を含む
"""
import time
import logging
from typing import Any, Callable, Optional, TypeVar, Dict
from concurrent.futures import Future, TimeoutError
import openai

logger = logging.getLogger(__name__)

T = TypeVar('T')


class TimeoutHandler:
    """タイムアウトとリトライを管理するクラス"""
    
    def __init__(self, 
                 max_retries: int = 3,
                 initial_timeout: float = 60.0,
                 timeout_multiplier: float = 1.5,
                 rate_limit_sleep: float = 5.0):
        """
        Args:
            max_retries: 最大リトライ回数
            initial_timeout: 初期タイムアウト時間（秒）
            timeout_multiplier: リトライごとのタイムアウト倍率
            rate_limit_sleep: レート制限時の待機時間（秒）
        """
        self.max_retries = max_retries
        self.initial_timeout = initial_timeout
        self.timeout_multiplier = timeout_multiplier
        self.rate_limit_sleep = rate_limit_sleep
        self.api_call_count = 0
        self.last_api_call_time = 0
        
    def with_timeout_and_retry(self, 
                              func: Callable[..., T], 
                              *args, 
                              task_name: str = "Task",
                              **kwargs) -> Optional[T]:
        """
        タイムアウトとリトライ処理付きで関数を実行
        
        Args:
            func: 実行する関数
            task_name: タスク名（ログ用）
            *args, **kwargs: 関数の引数
            
        Returns:
            関数の戻り値 or None（失敗時）
        """
        timeout = self.initial_timeout
        
        for attempt in range(self.max_retries):
            try:
                # レート制限対策：API呼び出し間隔を調整
                self._rate_limit_wait()
                
                logger.debug(f"{task_name}: 試行 {attempt + 1}/{self.max_retries} (タイムアウト: {timeout}秒)")
                
                # 関数実行
                result = func(*args, **kwargs)
                
                # 成功したらAPI呼び出しカウントを更新
                self.api_call_count += 1
                self.last_api_call_time = time.time()
                
                return result
                
            except openai.RateLimitError as e:
                logger.warning(f"{task_name}: レート制限エラー - {e}")
                if attempt < self.max_retries - 1:
                    sleep_time = self.rate_limit_sleep * (attempt + 1)
                    logger.info(f"{sleep_time}秒待機してリトライします...")
                    time.sleep(sleep_time)
                    timeout *= self.timeout_multiplier
                else:
                    logger.error(f"{task_name}: レート制限エラーでリトライ回数超過")
                    return None
                    
            except openai.APITimeoutError as e:
                logger.warning(f"{task_name}: APIタイムアウト - {e}")
                if attempt < self.max_retries - 1:
                    timeout *= self.timeout_multiplier
                    logger.info(f"タイムアウトを{timeout}秒に増やしてリトライします...")
                else:
                    logger.error(f"{task_name}: タイムアウトでリトライ回数超過")
                    return None
                    
            except openai.APIConnectionError as e:
                logger.warning(f"{task_name}: API接続エラー - {e}")
                if attempt < self.max_retries - 1:
                    sleep_time = 3 * (attempt + 1)
                    logger.info(f"{sleep_time}秒待機してリトライします...")
                    time.sleep(sleep_time)
                else:
                    logger.error(f"{task_name}: 接続エラーでリトライ回数超過")
                    return None
                    
            except Exception as e:
                logger.error(f"{task_name}: 予期しないエラー - {type(e).__name__}: {e}")
                if attempt < self.max_retries - 1:
                    logger.info(f"リトライします... ({attempt + 2}/{self.max_retries})")
                else:
                    logger.error(f"{task_name}: エラーでリトライ回数超過")
                    return None
        
        return None
    
    def _rate_limit_wait(self):
        """レート制限対策の待機処理"""
        # 1分間に60回までの制限を想定（1秒に1回）
        time_since_last_call = time.time() - self.last_api_call_time
        if time_since_last_call < 1.0:
            sleep_time = 1.0 - time_since_last_call
            time.sleep(sleep_time)
    
    def batch_process_with_progress(self,
                                   items: list,
                                   process_func: Callable[[Any], Any],
                                   batch_size: int = 10,
                                   progress_callback: Optional[Callable[[float, str], None]] = None,
                                   task_name: str = "バッチ処理") -> list:
        """
        バッチ処理with進捗表示とタイムアウト管理
        
        Args:
            items: 処理するアイテムのリスト
            process_func: 各アイテムを処理する関数
            batch_size: バッチサイズ
            progress_callback: 進捗コールバック
            task_name: タスク名
            
        Returns:
            処理結果のリスト
        """
        results = []
        total_items = len(items)
        processed_items = 0
        failed_items = 0
        
        for i in range(0, total_items, batch_size):
            batch = items[i:i + batch_size]
            batch_results = []
            
            for item in batch:
                result = self.with_timeout_and_retry(
                    process_func,
                    item,
                    task_name=f"{task_name} - アイテム {processed_items + 1}/{total_items}"
                )
                
                if result is not None:
                    batch_results.append(result)
                else:
                    failed_items += 1
                    logger.warning(f"アイテム {processed_items + 1} の処理に失敗")
                
                processed_items += 1
                
                # 進捗更新
                if progress_callback:
                    progress = processed_items / total_items
                    status = f"{task_name}: {processed_items}/{total_items} 完了"
                    if failed_items > 0:
                        status += f" ({failed_items} 失敗)"
                    progress_callback(progress, status)
            
            results.extend(batch_results)
            
            # バッチ間で少し待機（レート制限対策）
            if i + batch_size < total_items:
                time.sleep(0.5)
        
        logger.info(f"{task_name} 完了: 成功 {len(results)}/{total_items}, 失敗 {failed_items}")
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """統計情報を取得"""
        return {
            "api_call_count": self.api_call_count,
            "last_api_call_time": self.last_api_call_time,
            "calls_per_minute": self._calculate_calls_per_minute()
        }
    
    def _calculate_calls_per_minute(self) -> float:
        """1分あたりのAPI呼び出し回数を計算"""
        if self.api_call_count == 0:
            return 0.0
        
        elapsed_time = time.time() - self.last_api_call_time
        if elapsed_time < 60:
            # 過去1分間の推定値
            return self.api_call_count / (elapsed_time / 60)
        else:
            # 1分以上経過している場合は0
            return 0.0