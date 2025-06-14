# エラーハンドリング統合ガイド

## 概要

新しい統一エラーハンドリングシステムへの移行ガイドです。

## 移行手順

### 1. インポートの更新

**旧:**
```python
from utils.exceptions import VideoProcessingError, TranscriptionError
# または
from core.exceptions import ProcessingError, AlignmentError
```

**新:**
```python
from core.error_handling import (
    VideoProcessingError,
    TranscriptionError,
    ProcessingError,
    AlignmentError,
    ErrorHandler
)
```

### 2. エラーの発生

**旧:**
```python
raise VideoProcessingError("動画処理に失敗しました")
```

**新:**
```python
raise VideoProcessingError(
    "動画処理に失敗しました",
    details={
        "video_path": video_path,
        "error_type": "codec_not_supported"
    },
    user_message="この動画形式はサポートされていません"
)
```

### 3. エラーハンドリング

**旧:**
```python
try:
    process_video(path)
except Exception as e:
    logger.error(f"エラー: {e}")
    raise
```

**新:**
```python
try:
    process_video(path)
except TextffCutError as e:
    # 統一エラーハンドラーを使用
    self.error_handler.handle_error(
        e,
        context="video_processing",
        raise_after=True
    )
```

### 4. サービス層での使用

**旧:**
```python
class VideoService(BaseService):
    def process(self, path: str) -> ServiceResult:
        try:
            # 処理
            return self.create_success_result(data)
        except Exception as e:
            return self.create_error_result(str(e))
```

**新:**
```python
class VideoService(BaseService):
    def process(self, path: str) -> ServiceResult:
        try:
            # 処理
            return self.create_success_result(data)
        except Exception as e:
            # 統一エラーハンドリング
            return self.handle_service_error('process', e)
```

## エラークラスマッピング

| 旧クラス (utils.exceptions) | 新クラス (core.error_handling) |
|---------------------------|------------------------------|
| BuzzClipError | TextffCutError |
| TranscriptionError | TranscriptionError |
| VideoProcessingError | VideoProcessingError |
| FileNotFoundError | FileValidationError |
| FFmpegError | FFmpegError |
| WhisperError | WhisperError |
| MemoryError | InsufficientMemoryError |
| ConfigurationError | ConfigurationError |

| 旧クラス (core.exceptions) | 新クラス (core.error_handling) |
|--------------------------|------------------------------|
| ProcessingError | ProcessingError |
| TranscriptionValidationError | ValidationError |
| WordsFieldMissingError | WordsFieldMissingError |
| AlignmentError | AlignmentError |

## 主な改善点

1. **統一されたエラー階層**
   - すべてのエラーが`TextffCutError`を継承
   - カテゴリとセキュリティレベルの明確化

2. **ユーザー向けメッセージ**
   - 開発者向けとユーザー向けメッセージの分離
   - 適切な日本語メッセージ

3. **詳細情報の構造化**
   - `details`フィールドで追加情報を管理
   - エラーコードによる分類

4. **回復可能性の明示**
   - `recoverable`フラグで回復可能なエラーを識別
   - UIでの適切な処理が可能

5. **ログ出力の統一**
   - ErrorHandlerによる一貫したログ形式
   - コンテキスト情報の自動付与

## 移行例

### core/video.py の例

```python
# 旧実装
def process_video(self, path: str):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Video file not found: {path}")
    
    try:
        # FFmpeg処理
    except subprocess.CalledProcessError as e:
        raise FFmpegError(f"FFmpeg failed: {e.stderr}")

# 新実装
def process_video(self, path: str):
    if not os.path.exists(path):
        raise FileValidationError(
            f"動画ファイルが見つかりません: {path}",
            details={"path": path},
            user_message="指定された動画ファイルが見つかりません"
        )
    
    try:
        # FFmpeg処理
    except subprocess.CalledProcessError as e:
        raise FFmpegError(
            f"FFmpeg実行エラー: {e.stderr}",
            details={
                "command": e.cmd,
                "returncode": e.returncode,
                "stderr": e.stderr
            },
            cause=e,
            user_message="動画の処理中にエラーが発生しました"
        )
```

### main.py の例

```python
# 旧実装
try:
    result = transcribe_video(video_path)
except Exception as e:
    st.error(f"エラー: {str(e)}")
    return

# 新実装
try:
    result = transcribe_video(video_path)
except TextffCutError as e:
    # ユーザー向けメッセージを表示
    st.error(e.user_message)
    
    # 回復可能なエラーの場合は追加情報を表示
    if e.recoverable:
        st.info("設定を確認して再試行してください")
    
    # 詳細情報をexpanderで表示
    with st.expander("エラーの詳細"):
        st.code(e.get_log_message())
except Exception as e:
    # 予期しないエラー
    st.error("システムエラーが発生しました")
    logger.error("Unexpected error", exc_info=True)
```

## ベストプラクティス

1. **具体的なエラークラスを使用**
   - 汎用的な`ProcessingError`より`VideoProcessingError`を優先

2. **詳細情報を含める**
   - `details`に診断に役立つ情報を追加

3. **ユーザーメッセージを設定**
   - 技術的でない、分かりやすい日本語メッセージ

4. **原因となった例外を保持**
   - `cause`パラメータで元の例外を保持

5. **コンテキスト情報を提供**
   - ErrorHandlerの`context`でエラー発生箇所を明確化