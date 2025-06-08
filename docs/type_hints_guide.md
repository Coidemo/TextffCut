# 型ヒントガイドライン

## 概要

TextffCutプロジェクトにおける型ヒントの使用ガイドラインです。

## 基本原則

1. **段階的な導入**
   - 新規コードは型ヒント必須
   - 既存コードは段階的に追加
   - 重要度の高いモジュールから優先

2. **明確性を重視**
   - 曖昧な`Any`より具体的な型を使用
   - 複雑な型は型エイリアスで定義
   - 自己文書化的な型定義

3. **実用性とのバランス**
   - 過度に複雑な型は避ける
   - IDEサポートを考慮
   - 実行時の型チェックは最小限

## 型定義の場所

### core/types.py
- プロジェクト全体で使用される共通型
- 型エイリアス、TypedDict、Protocol
- 型ガード関数

### 各モジュール内
- モジュール固有の型定義
- プライベートな型

## 推奨パターン

### 1. 関数の型注釈

```python
# Good
def process_video(
    path: VideoPath,
    options: Optional[TranscriptionOptions] = None
) -> Result[VideoMetadata]:
    ...

# Bad
def process_video(path, options=None):
    ...
```

### 2. Optional の使用

```python
# Good - 明示的なOptional
def get_duration(path: str) -> Optional[float]:
    ...

# Bad - 暗黙的なNone
def get_duration(path: str) -> float | None:  # Python 3.10+なら可
    ...
```

### 3. 辞書の型定義

```python
# Good - TypedDict使用
class VideoInfo(TypedDict):
    width: int
    height: int
    fps: float

# Bad - Dict[str, Any]
video_info: Dict[str, Any] = {...}
```

### 4. コールバック関数

```python
# Good - Protocol使用
class ProgressCallback(Protocol):
    def __call__(self, progress: float, message: str) -> None: ...

# Bad - Callable型
callback: Callable[[float, str], None]
```

### 5. Union型の使用

```python
# Good - 明確な選択肢
VideoFormat = Literal['mp4', 'mov', 'avi']

# Bad - 広すぎるUnion
Format = Union[str, int, bool]
```

## 型チェックの実行

### mypy

```bash
# 基本的な型チェック
mypy .

# 特定のモジュールのみ
mypy core/

# 厳密モード
mypy --strict core/types.py
```

### 設定

`pyproject.toml`で段階的に厳密性を上げる：

1. **Phase 1**: 基本的な型チェック
   - `check_untyped_defs = true`
   - `disallow_untyped_defs = false`

2. **Phase 2**: 新規コードに型を要求
   - `disallow_untyped_defs = true` (新規モジュール)

3. **Phase 3**: 既存コードも型必須
   - すべてのモジュールで`strict = true`

## ベストプラクティス

### 1. ジェネリック型の活用

```python
# 汎用的な結果型
class Result[T]:
    success: bool
    data: Optional[T]
    error: Optional[str]

# 使用例
def get_video_info(path: str) -> Result[VideoMetadata]:
    ...
```

### 2. 型エイリアスの活用

```python
# 共通の型をエイリアスで定義
TimeSeconds = float
VideoPath = Union[str, Path]
SegmentList = List[TranscriptionSegmentV2]
```

### 3. 型ガード関数

```python
def is_video_format(ext: str) -> TypeGuard[VideoFormat]:
    return ext.lower() in ['mp4', 'mov', 'avi']
```

### 4. データクラスの活用

```python
@dataclass
class ProcessingResult:
    segments: List[Segment]
    metadata: Dict[str, Any]
    errors: List[str] = field(default_factory=list)
```

## 移行戦略

### Step 1: 基礎準備（完了）
- [x] core/types.py の作成
- [x] pyproject.toml の設定
- [x] 基本的な型定義

### Step 2: コアモジュール（進行中）
- [ ] core/models.py の型追加
- [ ] services/base.py の型追加
- [ ] 主要なサービスクラス

### Step 3: UI層
- [ ] main.py の型追加
- [ ] ui/components.py の型追加

### Step 4: ユーティリティ
- [ ] utils/ 配下の型追加
- [ ] worker_*.py の型追加

### Step 5: 完全移行
- [ ] すべてのモジュールで型必須
- [ ] CI/CDでの型チェック統合

## トラブルシューティング

### サードパーティライブラリ

型スタブがない場合：
```python
# type: ignore コメントを使用
import untyped_library  # type: ignore
```

### 循環インポート

型注釈のみで使用する場合：
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from other_module import SomeType
```

### 複雑な型

読みやすさを優先：
```python
# 複雑すぎる
ComplexType = Dict[str, List[Tuple[Optional[int], Union[str, float]]]]

# 分割して定義
ValueType = Union[str, float]
ItemType = Tuple[Optional[int], ValueType]
SimpleType = Dict[str, List[ItemType]]
```

## リソース

- [Python Type Hints](https://docs.python.org/3/library/typing.html)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [PEP 484](https://www.python.org/dev/peps/pep-0484/)
- [PEP 526](https://www.python.org/dev/peps/pep-0526/)
- [PEP 544](https://www.python.org/dev/peps/pep-0544/) (Protocols)