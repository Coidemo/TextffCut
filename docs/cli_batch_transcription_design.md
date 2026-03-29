# CLIバッチ文字起こし機能 設計ドキュメント

作成日: 2026-03-29
ステータス: **ドラフト（レビュー待ち）**

---

## 1. 要件定義

### 1.1 背景・目的

現状のTextffCutはStreamlit WebアプリとしてUIが提供されているが、以下のユースケースに対応できていない：

- 複数の動画を夜間バッチ処理したい
- CI/CDパイプラインや外部スクリプトから呼び出したい
- フォルダ単位で一括処理したい
- GUIを使わずにサーバーで実行したい

CLIバッチ処理機能を追加することで、これらのユースケースに対応する。

### 1.2 機能要件

#### 1.2.1 基本機能

| ID | 要件 |
|----|------|
| F-01 | 複数の動画ファイルパスを引数で渡して一括文字起こしできる |
| F-02 | フォルダを指定して配下の対象動画を一括処理できる |
| F-03 | グロブパターン（`*.mp4` など）で対象ファイルを指定できる |
| F-04 | モデルサイズを指定できる（small / medium / large-v3 等） |
| F-05 | 処理結果（TranscriptionResult）をJSONファイルとして出力できる |
| F-06 | キャッシュが存在する場合はスキップできる（`--use-cache`） |
| F-07 | 並列数を指定できる（`--workers N`） |
| F-08 | ドライラン（`--dry-run`）で実際の処理なく対象ファイルと処理順を確認できる |

#### 1.2.2 進捗表示

| ID | 要件 |
|----|------|
| P-01 | 全体の進捗（N/M 完了）をリアルタイム表示する |
| P-02 | 各ファイルの処理状態（待機中 / 処理中 / 完了 / エラー）を表示する |
| P-03 | 処理時間（経過・推定残り時間）を表示する |
| P-04 | `--quiet` フラグで進捗表示を抑制し、エラーのみ出力できる |
| P-05 | `--json-output` フラグで進捗をJSON Lines形式で出力できる（外部ツール連携用） |

#### 1.2.3 エラーハンドリング

| ID | 要件 |
|----|------|
| E-01 | 1ファイルの処理失敗が他のファイルに影響しない（継続処理） |
| E-02 | エラーになったファイルのリストを処理完了後に表示する |
| E-03 | `--fail-fast` フラグで最初のエラーで中断できる |
| E-04 | リトライ回数を指定できる（`--retry N`、デフォルト 0） |
| E-05 | 処理サマリー（成功N件、失敗N件）を最後に表示する |

#### 1.2.4 出力制御

| ID | 要件 |
|----|------|
| O-01 | 出力先は**動画ファイルと同じフォルダ内の `{動画名}_TextffCut/transcriptions/{model}.json`** に固定する（Streamlit UIのキャッシュと共通フォーマット） |
| O-02 | `--output-dir` オプションは提供しない（UIとの互換性を保つため） |
| O-03 | キャッシュが既に存在する場合はスキップ（`--no-cache` で強制再処理） |
| O-04 | 言語を手動指定できる（`--language ja`、省略時は自動検出） |

**キャッシュパスの仕様（UIと共通フォーマット）**:
```
# UIの場合（videos/ フォルダ固定）
videos/
└── lecture_01.mp4
└── lecture_01_TextffCut/
    └── transcriptions/
        └── medium.json

# CLIの場合（どこにある動画でも、その動画と同じディレクトリに出力）
/any/path/to/
└── lecture_01.mp4
└── lecture_01_TextffCut/       ← 動画の隣に作成
    └── transcriptions/
        └── medium.json
```

- UI は `videos/` フォルダのみを対象とするが、**CLI はパスの制限なし**
- 出力先は常に「渡された動画ファイルと同じディレクトリ」（`video_path.parent`）
- 出力フォルダ構造は UI と同一なので、`videos/` 内の動画をCLIで処理した場合、後でStreamlit UIを開いた際にキャッシュが自動認識される
- 既存の `Transcriber.get_cache_path()` がこの動作を実装済みのため、追加実装不要

### 1.3 非機能要件

| ID | 要件 |
|----|------|
| NF-01 | 既存のDIコンテナ・ユースケースを再利用し、ロジックの重複を避ける |
| NF-02 | Streamlit UIを起動せずに動作する（Streamlitへの依存なし） |
| NF-03 | **Mac（Apple Silicon）専用**。MLXを強制使用し、WhisperXへのフォールバックは行わない |
| NF-04 | Docker環境・非Apple Silicon環境では起動時にエラーを出して終了する |
| NF-05 | `textffcut` コマンド（またはインストール前は `python -m textffcut`）で起動できる |

### 1.4 スコープ外

- テキスト編集・差分検出（Streamlit UI操作を伴う機能）
- 動画ファイルの切り出し・エクスポート（FCPXML / SRT 等）
- YouTube URLからのダウンロード（将来拡張）
- GUIでのバッチ実行管理

---

## 2. アーキテクチャ設計

### 2.1 既存アーキテクチャとの統合方針

既存のクリーンアーキテクチャを最大限に活用する。

```
┌─────────────────────────────────────────┐
│           Presentation Layer             │
│  ┌─────────────────┐  ┌──────────────┐  │
│  │  Streamlit UI   │  │  CLI Batch   │  │ ← 新規追加
│  │  (main.py)      │  │  (textffcut_cli/)      │  │
│  └────────┬────────┘  └──────┬───────┘  │
└───────────┼──────────────────┼──────────┘
            │                  │
┌───────────┼──────────────────┼──────────┐
│           Application Layer             │
│  ┌────────┴──────────────────┴───────┐  │
│  │         DIコンテナ (di/)           │  │
│  │  TranscribeVideoUseCase           │  │
│  │  BatchTranscribeUseCase  ← 新規   │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
            ↓ (既存のまま)
┌─────────────────────────────────────────┐
│          Infrastructure Layer           │
│  TranscriptionGatewayAdapter            │
│  Transcriber (MLX / WhisperX)           │
└─────────────────────────────────────────┘
```

### 2.2 新規追加ファイル一覧

```
TextffCut/
├── textffcut_cli/                              # 新規ディレクトリ
│   ├── __init__.py
│   ├── __main__.py                   # python -m cli エントリーポイント
│   ├── batch_command.py              # CLIコマンド実装（argparse）
│   └── progress_display.py          # 進捗表示ユーティリティ
│
├── use_cases/
│   └── transcription/
│       └── batch_transcribe.py       # 新規ユースケース
│
└── di/
    └── bootstrap.py                  # create_cli_container() を追加
```

### 2.3 BatchTranscribeUseCase の設計

```python
# use_cases/transcription/batch_transcribe.py

@dataclass
class BatchTranscribeRequest:
    video_paths: list[FilePath]          # 処理対象ファイルリスト
    model_size: str = "medium"
    language: str | None = None
    use_cache: bool = True               # バッチではキャッシュ活用がデフォルト
    max_workers: int = 1                 # 同時処理数（デフォルト1、MLXのメモリ効率のため）
    retry_count: int = 0
    fail_fast: bool = False
    output_dir: Path | None = None
    output_suffix: str = "_transcription.json"
    overwrite: bool = False
    progress_callback: Callable[[BatchProgress], None] | None = None

@dataclass
class BatchProgress:
    total: int
    completed: int
    failed: int
    current_file: str | None
    current_status: str          # "processing" | "completed" | "failed" | "skipped"
    elapsed_seconds: float
    estimated_remaining_seconds: float | None

@dataclass
class BatchTranscribeResult:
    results: list[BatchItemResult]
    total: int
    succeeded: int
    failed: int
    skipped: int
    total_processing_time: float

@dataclass
class BatchItemResult:
    video_path: Path
    status: str                  # "succeeded" | "failed" | "skipped"
    output_path: Path | None
    error: str | None
    processing_time: float
```

### 2.4 DIコンテナへの統合

CLIバッチ処理ではStreamlitのセッション状態が不要なため、軽量なコンテナを用意する。

```python
# di/bootstrap.py への追加

def create_cli_container(model_size: str = "medium") -> ApplicationContainer:
    """CLI用の軽量DIコンテナを作成する。

    Streamlit依存のPresentation層コンポーネントを除いた
    Application/Infrastructure層のみを初期化する。
    """
    config = Config()
    container = ApplicationContainer()
    container.config.from_dict({"legacy_config": config})
    container.wire(modules=["use_cases.transcription.batch_transcribe"])
    return container
```

### 2.5 CLIコマンド設計

```
textffcut_cli/
├── __main__.py       # エントリーポイント
├── batch_command.py  # argparse定義 + コマンド実行
└── progress_display.py  # tqdm / Rich による進捗表示
```

**エントリーポイント方式**:
```bash
# 方法1: モジュール実行
python -m cli batch video1.mp4 video2.mp4

# 方法2: スクリプト（将来的に setup.cfg で登録）
# textffcut-batch video1.mp4 video2.mp4
```

---

## 3. CLIインターフェース設計

### 3.1 コマンド構造

```
python -m cli batch [OPTIONS] [FILES/DIRS...]
```

### 3.2 引数・オプション

```
positional arguments:
  files                 処理する動画ファイルまたはフォルダのパス
                        （複数指定可、グロブパターン対応）

optional arguments:
  -h, --help            ヘルプを表示して終了

  -- 文字起こし設定 --
  -m, --model MODEL     使用するモデルサイズ
                        選択肢: small, medium, large-v3, large-v3-turbo
                        デフォルト: medium
  -l, --language LANG   言語コード（例: ja, en）。省略時は自動検出

  -- バッチ制御 --
  -w, --workers N       同時処理数（デフォルト: 1）
                        ※ MLX強制使用のためメモリ消費が大きい。増やす場合は注意
  --use-cache           キャッシュがあればスキップ（デフォルト: 有効）
  --no-cache            キャッシュを無視して常に再処理
  --retry N             失敗時のリトライ回数（デフォルト: 0）
  --fail-fast           最初のエラーで処理を中断

  -- 出力制御 --
  -o, --output-dir DIR  出力ディレクトリ（省略時は入力ファイルと同じ場所）
  --overwrite           既存の出力ファイルを上書き
  --suffix SUFFIX       出力ファイルのサフィックス
                        デフォルト: _transcription.json

  -- 表示制御 --
  -q, --quiet           エラー以外の出力を抑制
  --dry-run             ファイルを処理せず、対象ファイル一覧のみ表示
  --json-progress       進捗をJSON Lines形式で標準出力（--quietと組み合わせて使用）
```

### 3.3 使用例

```bash
# 基本: 2ファイルを処理
python -m cli batch video1.mp4 video2.mp4

# フォルダ内の全mp4を処理（サブフォルダは含まない）
python -m cli batch ./videos/*.mp4

# フォルダを再帰的に処理
python -m cli batch ./videos/

# large-v3モデルで、出力を./outputフォルダに保存
python -m cli batch -m large-v3 -o ./output ./videos/*.mp4

# ドライランで対象確認
python -m cli batch --dry-run ./videos/

# キャッシュを使わず全て再処理、失敗でも継続
python -m cli batch --no-cache ./videos/*.mp4

# 外部スクリプト連携（進捗をJSONで出力）
python -m cli batch --quiet --json-progress ./videos/*.mp4 | jq .
```

### 3.4 出力フォーマット

#### 通常の進捗表示（ターミナル）

```
TextffCut Batch Transcription
==============================
対象ファイル: 5件 | モデル: medium | workers: 1

[1/5] 処理中: lecture_01.mp4
      ████████████████░░░░░░░░  65%  経過: 0:01:23  残り推定: 0:00:45

[2/5] 完了  ✓  lecture_02.mp4  (2:34)
[3/5] スキップ  -  lecture_03.mp4  (キャッシュあり)

==============================
完了: 4  失敗: 1  スキップ: 1

失敗したファイル:
  - lecture_05.mp4
    エラー: Failed to load audio file (codec not supported)

処理時間: 0:08:42
```

#### JSON Lines 形式（`--json-progress`）

```json
{"type":"start","total":5,"model":"medium","timestamp":"2026-03-29T10:00:00"}
{"type":"progress","file":"lecture_01.mp4","status":"processing","index":1,"total":5}
{"type":"progress","file":"lecture_01.mp4","status":"completed","index":1,"total":5,"output":"lecture_01_transcription.json","elapsed":154.3}
{"type":"progress","file":"lecture_02.mp4","status":"skipped","index":2,"total":5,"reason":"cache_hit"}
{"type":"summary","succeeded":4,"failed":1,"skipped":1,"total_elapsed":522.1}
```

---

## 4. 実装フェーズ計画

### フェーズ1: コアロジック（ユースケース）

**対象ファイル**:
- `use_cases/transcription/batch_transcribe.py` （新規）
- `di/bootstrap.py` （`create_cli_container()` 追加）

**内容**:
- `BatchTranscribeUseCase` の実装
- 順次処理（`max_workers=1`）と並列処理（`max_workers>1`）
- キャッシュ有無の判定・スキップロジック
- エラーハンドリング（継続 / fail-fast）
- リトライロジック
- 出力JSON保存

**完了条件**:
```python
# テストで確認
use_case = BatchTranscribeUseCase(transcription_gateway)
result = use_case.execute(BatchTranscribeRequest(
    video_paths=[FilePath("test.mp4")],
    model_size="small",
))
assert result.succeeded == 1
```

### フェーズ2: CLIエントリーポイント

**対象ファイル**:
- `textffcut_cli/__init__.py` （新規）
- `textffcut_cli/__main__.py` （新規）
- `textffcut_cli/batch_command.py` （新規）

**内容**:
- `argparse` によるオプション定義
- DIコンテナ初期化 → ユースケース実行
- ドライランモード
- 終了コード（成功: 0、失敗あり: 1、全件失敗: 2）

### フェーズ3: 進捗表示

**対象ファイル**:
- `textffcut_cli/progress_display.py` （新規）

**内容**:
- tqdm または Rich による進捗バー表示
- `BatchProgress` コールバックの実装
- `--quiet` / `--json-progress` モード対応

**依存ライブラリ**: `rich`（既にStreamlitと共存可能）または `tqdm`

### フェーズ4: テスト

**対象ファイル**:
- `tests/use_cases/transcription/test_batch_transcribe.py` （新規）
- `tests/textffcut_cli/test_batch_command.py` （新規）

**内容**:
- `BatchTranscribeUseCase` の単体テスト（モックゲートウェイ使用）
- CLIオプション解析のテスト
- エラーハンドリング・リトライのテスト

---

## 5. 未決事項・リスク

| 項目 | 内容 | 優先度 |
|------|------|--------|
| 並列処理のメモリ制御 | MLXモードでのマルチプロセス時のメモリ上限（デフォルト1のため通常は問題なし） | 低 |
| 再帰的フォルダ探索 | サブフォルダを含めるオプションの扱い | 低 |
| YouTube URLのバッチ対応 | URLリストファイルからのダウンロード+文字起こし | スコープ外 |
| 進捗ライブラリ選定 | `rich` vs `tqdm`（既存の依存関係に合わせる） | 低 |

---

## 6. 関連ファイル（既存）

- `use_cases/transcription/transcribe_video.py` — 単一動画ユースケース（再利用）
- `use_cases/transcription/parallel_transcribe.py` — 並列処理（参考）
- `di/bootstrap.py` — DIコンテナ初期化（拡張対象）
- `adapters/gateways/transcription/transcription_gateway.py` — ゲートウェイ（そのまま利用）
- `utils/environment.py` — MLX自動検出（そのまま利用）
