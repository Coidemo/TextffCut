"""
カスタムプロバイダー

dependency-injectorの標準プロバイダーを拡張したカスタムプロバイダーを定義します。
"""

from typing import TypeVar, Type, Optional, Callable, Any
from dependency_injector import providers
from utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class StreamlitSessionProvider(providers.Provider):
    """
    Streamlitのセッション状態と連携するプロバイダー
    
    セッション状態から値を取得し、存在しない場合はデフォルト値を返します。
    """
    
    def __init__(
        self,
        session_key: str,
        default_factory: Optional[Callable[[], Any]] = None,
        *args,
        **kwargs
    ):
        """
        初期化
        
        Args:
            session_key: セッション状態のキー
            default_factory: デフォルト値を生成する関数
        """
        self.session_key = session_key
        self.default_factory = default_factory
        super().__init__(*args, **kwargs)
    
    def _provide(self, args, kwargs):
        """値を提供"""
        try:
            import streamlit as st
            
            # セッション状態から取得
            if self.session_key in st.session_state:
                return st.session_state[self.session_key]
            
            # デフォルト値を生成
            if self.default_factory:
                default_value = self.default_factory()
                st.session_state[self.session_key] = default_value
                return default_value
            
            return None
            
        except ImportError:
            # Streamlitが利用できない環境（テスト等）
            logger.debug("Streamlit not available, using default factory")
            return self.default_factory() if self.default_factory else None


class ConditionalProvider(providers.Provider):
    """
    条件に基づいて異なるプロバイダーを選択するプロバイダー
    
    例: API使用時とローカル使用時で異なる実装を選択
    """
    
    def __init__(
        self,
        condition: providers.Provider,
        when_true: providers.Provider,
        when_false: providers.Provider,
        *args,
        **kwargs
    ):
        """
        初期化
        
        Args:
            condition: 条件を評価するプロバイダー
            when_true: 条件が真の場合のプロバイダー
            when_false: 条件が偽の場合のプロバイダー
        """
        self.condition = condition
        self.when_true = when_true
        self.when_false = when_false
        super().__init__(*args, **kwargs)
    
    def _provide(self, args, kwargs):
        """条件に基づいて値を提供"""
        condition_value = self.condition()
        
        if condition_value:
            return self.when_true(*args, **kwargs)
        else:
            return self.when_false(*args, **kwargs)


class LazyProvider(providers.Provider):
    """
    遅延初期化プロバイダー
    
    最初にアクセスされるまでインスタンスの作成を遅延します。
    """
    
    def __init__(
        self,
        factory: Callable[[], T],
        *args,
        **kwargs
    ):
        """
        初期化
        
        Args:
            factory: インスタンスを生成する関数
        """
        self.factory = factory
        self._instance: Optional[T] = None
        self._initialized = False
        super().__init__(*args, **kwargs)
    
    def _provide(self, args, kwargs):
        """遅延初期化して値を提供"""
        if not self._initialized:
            logger.debug(f"Lazy initializing {self.factory}")
            self._instance = self.factory()
            self._initialized = True
        
        return self._instance
    
    def reset(self):
        """インスタンスをリセット"""
        self._instance = None
        self._initialized = False


class CachedProvider(providers.Provider):
    """
    キャッシュ機能付きプロバイダー
    
    一定時間または条件に基づいてキャッシュを管理します。
    """
    
    def __init__(
        self,
        provider: providers.Provider,
        cache_key_func: Optional[Callable[..., str]] = None,
        ttl: Optional[float] = None,
        *args,
        **kwargs
    ):
        """
        初期化
        
        Args:
            provider: ラップするプロバイダー
            cache_key_func: キャッシュキーを生成する関数
            ttl: キャッシュの有効期限（秒）
        """
        self.provider = provider
        self.cache_key_func = cache_key_func or self._default_cache_key
        self.ttl = ttl
        self._cache: dict = {}
        self._timestamps: dict = {}
        super().__init__(*args, **kwargs)
    
    def _default_cache_key(self, *args, **kwargs) -> str:
        """デフォルトのキャッシュキー生成"""
        return f"{args}_{kwargs}"
    
    def _is_expired(self, key: str) -> bool:
        """キャッシュが期限切れかチェック"""
        if self.ttl is None:
            return False
        
        if key not in self._timestamps:
            return True
        
        import time
        return time.time() - self._timestamps[key] > self.ttl
    
    def _provide(self, args, kwargs):
        """キャッシュを使用して値を提供"""
        cache_key = self.cache_key_func(*args, **kwargs)
        
        # キャッシュチェック
        if cache_key in self._cache and not self._is_expired(cache_key):
            logger.debug(f"Cache hit for key: {cache_key}")
            return self._cache[cache_key]
        
        # キャッシュミス
        logger.debug(f"Cache miss for key: {cache_key}")
        value = self.provider(*args, **kwargs)
        
        # キャッシュに保存
        self._cache[cache_key] = value
        if self.ttl is not None:
            import time
            self._timestamps[cache_key] = time.time()
        
        return value
    
    def clear_cache(self):
        """キャッシュをクリア"""
        self._cache.clear()
        self._timestamps.clear()