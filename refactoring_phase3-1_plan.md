# Phase 3-1: エラーハンドリングの統一計画

## 現状分析

### エラーハンドリングの問題点

1. **複数のExceptionクラスが分散**
   - `utils/exceptions.py`
   - `core/exceptions.py`
   - 各モジュール内で独自のエラー定義

2. **エラーメッセージの不統一**
   - 日本語/英語の混在
   - フォーマットの不統一
   - ユーザー向け/開発者向けメッセージの混在

3. **エラー処理パターンの不統一**
   - try-except の粒度がバラバラ
   - エラーログの出力方法が不統一
   - エラーの再スローポリシーが不明確

## 実装計画

### 1. 統一エラー階層の設計

```python
# core/error_handling.py

class TextffCutError(Exception):
    """基底エラークラス"""
    error_code: str = "UNKNOWN_ERROR"
    user_message: str = "エラーが発生しました"
    
    def __init__(self, message: str, details: Optional[Dict] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)

class ValidationError(TextffCutError):
    """入力検証エラー"""
    error_code = "VALIDATION_ERROR"
    user_message = "入力値が正しくありません"

class ProcessingError(TextffCutError):
    """処理エラー"""
    error_code = "PROCESSING_ERROR"
    user_message = "処理中にエラーが発生しました"

class ConfigurationError(TextffCutError):
    """設定エラー"""
    error_code = "CONFIG_ERROR"
    user_message = "設定にエラーがあります"

class ResourceError(TextffCutError):
    """リソース関連エラー"""
    error_code = "RESOURCE_ERROR"
    user_message = "リソースへのアクセスでエラーが発生しました"
```

### 2. エラーハンドラーの統一

```python
# core/error_handler.py

class ErrorHandler:
    """統一エラーハンドラー"""
    
    @staticmethod
    def handle_error(
        error: Exception,
        context: str,
        logger: Optional[Logger] = None,
        raise_after: bool = True
    ) -> Optional[ErrorResult]:
        """エラーを統一的に処理"""
        pass
    
    @staticmethod
    def format_user_message(error: Exception) -> str:
        """ユーザー向けメッセージを生成"""
        pass
    
    @staticmethod
    def format_log_message(error: Exception, context: str) -> str:
        """ログ用メッセージを生成"""
        pass
```

### 3. 移行ステップ

#### Step 1: エラークラスの統合
- `utils/exceptions.py` と `core/exceptions.py` を統合
- 新しい `core/error_handling.py` を作成
- 既存のエラークラスを新しい階層に移行

#### Step 2: エラーハンドラーの実装
- `ErrorHandler` クラスの実装
- ログ出力の統一
- エラーレスポンスの標準化

#### Step 3: 各モジュールの更新
- 各モジュールのエラーハンドリングを新しいパターンに更新
- try-except ブロックの見直し
- エラーメッセージの統一

#### Step 4: サービス層への適用
- BaseServiceのエラーハンドリングを強化
- ServiceResultとの統合
- エラー伝播の明確化

## 期待される効果

1. **保守性の向上**
   - エラー処理の一元管理
   - 新しいエラータイプの追加が容易

2. **デバッグ効率の向上**
   - 統一されたログフォーマット
   - エラーコンテキストの明確化

3. **ユーザビリティの向上**
   - 一貫性のあるエラーメッセージ
   - 適切な日本語メッセージ

4. **テスタビリティの向上**
   - エラーケースのテストが容易
   - モックしやすい構造

## 実装順序

1. エラークラス階層の作成
2. ErrorHandlerの実装
3. coreモジュールへの適用
4. servicesモジュールへの適用
5. UIレイヤーへの適用
6. テストの作成