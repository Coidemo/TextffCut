# Phase 3-2: 型ヒントの強化計画

## 現状分析

### 型ヒントの使用状況

1. **部分的に型ヒントあり**
   - 新しいモジュール（services/、一部のcore/）
   - dataclassを使用している箇所

2. **型ヒントなし/不完全**
   - main.py（Streamlit関連）
   - 古いモジュール（utils/の一部）
   - worker_*.py

3. **型の曖昧さ**
   - Dict[str, Any]の多用
   - Optional[]の不適切な使用
   - Union型の未使用

## 実装計画

### 1. 型定義の整理

```python
# core/types.py - 共通型定義

from typing import TypedDict, Literal, Union, Protocol
from pathlib import Path

# 基本型エイリアス
VideoPath = Union[str, Path]
AudioPath = Union[str, Path]
TimeSeconds = float
FrameNumber = int

# リテラル型
VideoFormat = Literal['mp4', 'mov', 'avi', 'mkv']
AudioFormat = Literal['wav', 'mp3', 'aac']
ExportFormat = Literal['fcpxml', 'xmeml', 'edl']
ModelSize = Literal['base', 'small', 'medium', 'large', 'large-v3', 'whisper-1']

# TypedDict（辞書の型安全性）
class VideoMetadata(TypedDict):
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    
class TranscriptionOptions(TypedDict, total=False):
    language: str
    model_size: ModelSize
    compute_type: str
    batch_size: int
    
# Protocol（構造的サブタイピング）
class ProgressCallback(Protocol):
    def __call__(self, progress: float, message: str) -> None: ...
```

### 2. 主要モジュールの型強化

#### core/models.py
- すべてのメソッドに戻り値の型を追加
- Optionalの適切な使用
- ジェネリック型の活用

#### services/
- TypedServiceResultの活用
- メソッドシグネチャの明確化
- コールバック型の定義

#### main.py
- Streamlit関数の戻り値型
- セッション状態の型定義
- イベントハンドラーの型

### 3. 型チェックツールの設定

#### mypy設定（pyproject.toml）
```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
disallow_any_generics = true
no_implicit_optional = true
warn_redundant_casts = true
warn_unused_ignores = true
warn_unreachable = true
strict_equality = true

[[tool.mypy.overrides]]
module = "streamlit.*"
ignore_missing_imports = true
```

### 4. 段階的な移行

#### Step 1: 基本的な型追加
- 関数の引数と戻り値
- クラスの属性
- 明らかな型の追加

#### Step 2: 複雑な型の定義
- TypedDictの活用
- Protocolの定義
- ジェネリック型の使用

#### Step 3: 型チェックの実行
- mypyでのチェック
- エラーの修正
- 型スタブの作成（必要に応じて）

## 実装例

### Before
```python
def process_video(path, segments, options=None):
    if not options:
        options = {}
    # 処理
    return result
```

### After
```python
from typing import Optional, List, Dict, Any
from pathlib import Path
from core.types import VideoPath, TranscriptionOptions
from core.models import TranscriptionSegmentV2, ProcessingResult

def process_video(
    path: VideoPath,
    segments: List[TranscriptionSegmentV2],
    options: Optional[TranscriptionOptions] = None
) -> ProcessingResult:
    if options is None:
        options = {}
    # 処理
    return result
```

## 期待される効果

1. **開発効率の向上**
   - IDEの補完機能向上
   - 早期のバグ発見
   - リファクタリングの安全性

2. **コードの可読性向上**
   - 関数の契約が明確
   - ドキュメントとしての役割

3. **保守性の向上**
   - 型の不整合を防止
   - インターフェースの明確化

4. **品質の向上**
   - 実行時エラーの削減
   - テストカバレッジの補完