# TextffCut クリーンアーキテクチャ移行計画

## 目次
1. [概要](#概要)
2. [現状の課題](#現状の課題)
3. [クリーンアーキテクチャの採用理由](#クリーンアーキテクチャの採用理由)
4. [アーキテクチャ設計](#アーキテクチャ設計)
5. [実装計画](#実装計画)
6. [移行戦略](#移行戦略)
7. [リスクと対策](#リスクと対策)
8. [成功指標](#成功指標)

## 概要

このドキュメントは、TextffCutアプリケーションを現在のモノリシック構造からクリーンアーキテクチャへ移行するための詳細な計画を記述します。

### 目的
- コードの保守性向上
- テスタビリティの改善
- 拡張性の確保
- 開発効率の向上

### 期間
約15週間（段階的実装）

#### 期間設定の根拠
- 各フェーズに十分なバッファを確保
- Streamlit特有の課題への対応時間を考慮
- 既存機能の動作確認とテスト期間を重視
- チーム学習とドキュメント作成時間を含む

#### 期間に関する注意事項
- この期間は専任チームを前提とした見積もりです
- 特にPhase 5（既存コードの移行）とPhase 7（Streamlit最適化）は不確実性が高く、追加期間が必要になる可能性があります
- 各フェーズ終了時に進捗を評価し、必要に応じて期間を調整する計画的な柔軟性を持たせます
- 遅延リスクに備え、MVPの定義と優先順位を明確にしておくことを推奨します

### 対象バージョン
TextffCut v1.0.0以降

## 現状の課題

### Streamlit特有の課題

#### セッション状態管理の複雑さ
- **現状**: `st.session_state`が至る所に散在
- **問題点**:
  - 状態の追跡が困難
  - テストが事実上不可能
  - リファクタリング時の影響範囲が不明確

#### UIとビジネスロジックの密結合
- **現状**: Streamlitウィジェットとロジックが混在
- **問題点**:
  - ユニットテストが書けない
  - UI変更がロジックに影響
  - 再利用性の欠如

#### リアクティブ更新の制御困難
- **現状**: `st.rerun()`が随所に存在
- **問題点**:
  - 予期しない再実行
  - パフォーマンス劣化
  - デバッグの困難さ

### 1. アーキテクチャレベルの問題

#### main.pyの肥大化
- **現状**: 2,119行の巨大な単一ファイル
- **問題点**:
  - 責任の混在（UI、ビジネスロジック、エラーハンドリング、ファイル操作）
  - コードの重複（SRT出力処理が3箇所で重複）
  - 深いネスト構造（最大8レベル）
  - 状態管理の複雑さ

#### 層の境界が不明確
- services層が十分に活用されていない
- main.pyが直接core層を呼び出している
- 依存関係が複雑で循環的

### 2. 保守性の問題

#### テストの困難さ
- StreamlitのUIとビジネスロジックが密結合
- モックが困難
- 副作用が多い（ファイル操作、外部プロセス実行）

#### 拡張性の欠如
- 新機能追加時にmain.pyの修正が必須
- 影響範囲の予測が困難
- 変更による副作用のリスクが高い

### 3. コード品質の問題
- 命名の不統一
- エラーハンドリングパターンの重複
- 設定値のハードコーディング

## クリーンアーキテクチャの採用理由

### 他のアーキテクチャとの比較

| アーキテクチャ | 利点 | 欠点 | TextffCutへの適合性 |
|--------------|-----|------|-------------------|
| MVC | シンプル、一般的 | ビジネスロジックの肥大化 | ⭐⭐☆☆☆ |
| MVP | テストしやすい | Streamlitと相性悪い | ⭐⭐☆☆☆ |
| MVVM | データバインディング | 複雑、Python非標準 | ⭐☆☆☆☆ |
| Hexagonal | 完全な分離 | 初期設定が複雑 | ⭐⭐⭐☆☆ |
| **Clean Architecture** | **段階的移行可能、高い拡張性** | **初期の複雑さ** | **⭐⭐⭐⭐⭐** |

### クリーンアーキテクチャを選択した理由

1. **段階的な移行が可能**
   - 既存コードを壊さずに徐々に改善できる
   - 各フェーズで動作確認しながら進められる

2. **TextffCutの特性にマッチ**
   - 複雑なビジネスロジック（文字起こし、動画処理）
   - 複数の外部依存（WhisperX、FFmpeg、API）
   - 将来の拡張計画（YouTube対応、AI機能）

3. **明確な利点**
   - ビジネスロジックの独立性
   - 高いテスタビリティ
   - 依存関係の明確化

## アーキテクチャ設計

### 層構造

```
┌─────────────────────────────────────────────────┐
│                 Presentation Layer               │
│          (Streamlit UI / REST API)              │
├─────────────────────────────────────────────────┤
│                 Application Layer                │
│              (Use Cases / DTOs)                 │
├─────────────────────────────────────────────────┤
│                  Domain Layer                    │
│          (Entities / Value Objects)             │
├─────────────────────────────────────────────────┤
│               Infrastructure Layer               │
│    (External Services / File System / DB)       │
└─────────────────────────────────────────────────┘
```

### 依存関係の方向

```
UI → Controllers → Use Cases → Domain
                       ↓
                    Gateways
                       ↓
                Infrastructure
```

### ディレクトリ構造

```
TextffCut/
├── app.py                          # エントリーポイント（100行以内）
├── domain/                         # ドメイン層（ビジネスエンティティ）
│   ├── entities/
│   │   ├── transcription.py       # 文字起こし結果エンティティ
│   │   ├── video_segment.py       # 動画セグメントエンティティ
│   │   └── time_range.py          # 時間範囲値オブジェクト
│   └── value_objects/
│       ├── file_path.py           # ファイルパス値オブジェクト
│       └── duration.py            # 時間長値オブジェクト
│
├── use_cases/                      # ユースケース層（ビジネスロジック）
│   ├── transcription/
│   │   ├── transcribe_video.py    # 動画文字起こしユースケース
│   │   └── load_cache.py          # キャッシュ読み込みユースケース
│   ├── editing/
│   │   ├── find_differences.py    # 差分検出ユースケース
│   │   └── adjust_boundaries.py   # 境界調整ユースケース
│   └── export/
│       ├── export_video.py        # 動画エクスポートユースケース
│       └── export_subtitles.py    # 字幕エクスポートユースケース
│
├── adapters/                       # アダプター層（インターフェース実装）
│   ├── controllers/               # 入力アダプター
│   │   ├── transcription_controller.py
│   │   ├── editing_controller.py
│   │   └── export_controller.py
│   ├── presenters/                # 出力アダプター
│   │   ├── transcription_presenter.py
│   │   └── export_presenter.py
│   └── gateways/                  # 外部サービスゲートウェイ
│       ├── whisper_gateway.py
│       ├── ffmpeg_gateway.py
│       └── file_gateway.py
│
└── infrastructure/                 # インフラ層（具体的実装）
    ├── ui/                        # Streamlit UI
    │   ├── pages/
    │   │   ├── transcription_page.py
    │   │   ├── editing_page.py
    │   │   └── export_page.py
    │   └── components/            # 再利用可能なUIコンポーネント
    ├── persistence/               # ファイルシステム実装
    │   └── file_repository.py
    ├── external/                  # 外部サービス実装
    │   ├── whisper_service.py
    │   └── ffmpeg_service.py
    └── di/                        # 依存性注入
        ├── __init__.py
        ├── container.py           # DIコンテナ定義
        └── providers.py           # プロバイダー定義
```

### 依存性注入（DI）の方針

#### DIの実装方法
プロジェクトの複雑さと保守性のバランスを考慮し、以下の2つのアプローチを段階的に採用：

##### Phase 1-3: 手動での依存性組み立て
```python
# app.py
class AppFactory:
    """アプリケーションの依存関係を手動で組み立てる"""
    
    @staticmethod
    def create_transcription_controller() -> TranscriptionController:
        # インフラストラクチャ層の実装を作成
        whisper_service = WhisperService()
        file_repository = FileRepository()
        
        # ゲートウェイの作成
        transcription_gateway = TranscriptionGateway(
            whisper_service=whisper_service,
            file_repository=file_repository
        )
        
        # ユースケースの作成
        use_case = TranscribeVideoUseCase(
            gateway=transcription_gateway
        )
        
        # プレゼンターの作成
        presenter = TranscriptionPresenter()
        
        # コントローラーの作成
        return TranscriptionController(
            use_case=use_case,
            presenter=presenter
        )
```

##### Phase 4以降: DIコンテナライブラリの導入
```python
# infrastructure/di/container.py
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    """アプリケーション全体のDIコンテナ"""
    
    config = providers.Configuration()
    
    # インフラストラクチャ層
    whisper_service = providers.Singleton(WhisperService)
    file_repository = providers.Singleton(FileRepository)
    
    # ゲートウェイ
    transcription_gateway = providers.Factory(
        TranscriptionGateway,
        whisper_service=whisper_service,
        file_repository=file_repository
    )
    
    # ユースケース
    transcribe_video_use_case = providers.Factory(
        TranscribeVideoUseCase,
        gateway=transcription_gateway
    )
    
    # プレゼンター
    transcription_presenter = providers.Factory(
        TranscriptionPresenter
    )
    
    # コントローラー
    transcription_controller = providers.Factory(
        TranscriptionController,
        use_case=transcribe_video_use_case,
        presenter=transcription_presenter
    )
```

#### DI導入の利点
1. **テスタビリティ**: モックの注入が容易
2. **柔軟性**: 実装の切り替えが簡単
3. **保守性**: 依存関係が一箇所に集約
4. **型安全性**: 依存関係の型チェックが可能

## 実装計画

### Phase 1: 基盤整備とmain.py分割（3週間）

#### 目標
- main.pyを機能別のセクションに分割（UIは1ページのまま維持）
- 基本的なクリーンアーキテクチャ構造の確立
- セッション状態管理の抽象化

#### 完了したタスク ✅
1. **プロジェクト構造の作成**
   - domain, use_cases, adapters, infrastructureディレクトリ作成済み
   - 各層の責任を明確化するREADME配置済み

2. **app.pyとRouterの実装**
   - レガシーモードと新アーキテクチャモードの切り替え可能
   - 既存のmain.pyとの完全な互換性維持

3. **セッション管理の抽象化**
   - `SessionManager`クラスで状態管理を一元化
   - 既存のセッション状態との互換性保持
   - テスト可能な設計

4. **セクションの部分的な分割**
   - ✅ 動画入力セクション（`video_input_section.py`）
   - ✅ エクスポートセクション（`export_section.py`）
   - ⏳ 文字起こしセクション（プレースホルダーのみ）
   - ⏳ 編集セクション（プレースホルダーのみ）

#### 重要な決定事項
- **UIレイアウトは変更しない**: "ページ"ではなく"セクション"として実装
- **段階的移行**: 文字起こし・編集セクションは相互依存が強いため、Phase 2後に実装
- **レガシー実装の保持**: 移行期間中の安全性のため、既存ロジックを別ファイルに保存

#### 次のステップ
Phase 2でドメイン層を構築してから、文字起こし・編集セクションの移行に戻る

### Phase 2: ドメイン層の確立（2週間）✅ 完了

#### 目標
- ✅ ビジネスエンティティの定義
- ✅ 値オブジェクトの実装
- ✅ ドメインルールの明確化

#### 完了したタスク
1. **ドメインエンティティ**
   - `TranscriptionResult` - 文字起こし結果（レガシー形式との相互変換対応）
   - `TranscriptionSegment` - セグメント（words/charsの正規化機能付き）
   - `Word` / `Char` - 単語/文字レベルのタイムスタンプ
   - `VideoSegment` - 動画セグメント（無音/有音、マージ機能）
   - `TextDifference` - テキスト差分

2. **値オブジェクト**
   - `TimeRange` - 時間範囲（マージ、交差、隣接判定機能）
   - `FilePath` - ファイルパス（検証、操作機能）
   - `Duration` - 継続時間（各種フォーマット変換）

3. **ドメインルール**
   - `DOMAIN_RULES.md` - ビジネスルールの文書化
   - 無音検出パラメータ、字幕設定、処理フローなど

4. **テストスイート**
   - 全エンティティ・値オブジェクトの単体テスト作成
   - レガシー形式との互換性テスト
   - 境界値テスト、不変性テスト

#### 主要エンティティ

```python
# domain/entities/transcription.py
from dataclasses import dataclass
from typing import List, Optional
from domain.value_objects.time_range import TimeRange

@dataclass
class TranscriptionSegment:
    """文字起こしセグメント"""
    id: str
    text: str
    time_range: TimeRange
    confidence: float
    words: Optional[List['Word']] = None

@dataclass
class TranscriptionResult:
    """文字起こし結果"""
    segments: List[TranscriptionSegment]
    language: str
    duration: float
    metadata: dict
```

### Phase 3: ユースケース層の実装（4週間）🚧 実装中

#### 拡張理由
- 並列文字起こし処理などの複雑なユースケースの実装
- Streamlit状態管理パターンの確立
- 包括的なテストスイートの作成

#### 目標
- ビジネスロジックをユースケースとして実装
- 外部依存を抽象化
- テスト可能な設計

#### 完了したタスク（Step 1/6）
1. **基本構造の作成** ✅
   - `UseCase`基底クラス（ジェネリック型対応）
   - `UseCaseError`と各種例外クラス
   - ロギングとエラーハンドリングの標準化
   - 包括的な単体テスト（9テストケース）

2. **ゲートウェイインターフェース定義** ✅
   - `ITranscriptionGateway` - 文字起こし機能
   - `ITextProcessorGateway` - テキスト処理
   - `IVideoProcessorGateway` - 動画処理
   - `IExportGateway`系 - 各種エクスポート
   - `IFileGateway` - ファイル操作

#### 完了したタスク（Step 2/6）
3. **文字起こしユースケース** ✅
   - `TranscribeVideoUseCase` - 通常の文字起こし実行
   - `LoadTranscriptionCacheUseCase` - キャッシュ読み込み
   - `ParallelTranscribeUseCase` - 並列文字起こし
   - 包括的な単体テスト（13テストケース）

#### 完了したタスク（Step 3/6）
4. **編集ユースケース** ✅
   - `FindTextDifferencesUseCase` - テキスト差分検出と時間範囲特定
   - `AdjustBoundariesUseCase` - 境界調整マーカーの解析と適用
   - 包括的な単体テスト（9テストケース）

#### 実装予定
- Step 4: 動画処理ユースケース
- Step 5: エクスポートユースケース
- Step 6: 統合とリファクタリング

#### ユースケース例

```python
# use_cases/transcription/transcribe_video.py
from typing import Protocol
from domain.entities.transcription import TranscriptionResult

class ITranscriptionGateway(Protocol):
    """文字起こしゲートウェイインターフェース"""
    def transcribe(self, video_path: str, options: dict) -> TranscriptionResult:
        ...

class TranscribeVideoUseCase:
    """動画文字起こしユースケース"""
    
    def __init__(self, gateway: ITranscriptionGateway):
        self.gateway = gateway
    
    def execute(self, video_path: str, model_size: str = "medium") -> TranscriptionResult:
        """ユースケースの実行"""
        # ビジネスルールの適用
        options = self._prepare_options(model_size)
        
        # ゲートウェイ経由で文字起こし実行
        result = self.gateway.transcribe(video_path, options)
        
        # 後処理
        return self._post_process(result)
```

### Phase 4: アダプター層の実装（2週間）

#### 目標
- コントローラーとプレゼンターの実装
- ゲートウェイインターフェースの定義
- 外部サービスの抽象化

#### コントローラー例

```python
# adapters/controllers/transcription_controller.py
from use_cases.transcription.transcribe_video import TranscribeVideoUseCase
from adapters.presenters.transcription_presenter import TranscriptionPresenter

class TranscriptionController:
    """文字起こしコントローラー"""
    
    def __init__(
        self,
        use_case: TranscribeVideoUseCase,
        presenter: TranscriptionPresenter
    ):
        self.use_case = use_case
        self.presenter = presenter
    
    def handle_transcription_request(self, video_path: str, options: dict):
        """文字起こしリクエストの処理"""
        try:
            # ユースケース実行
            result = self.use_case.execute(video_path, options.get("model_size"))
            
            # プレゼンターで表示用に変換
            return self.presenter.present_success(result)
            
        except Exception as e:
            return self.presenter.present_error(e)
```

### Phase 5: 既存コードの移行（3週間）

#### 目標
- 既存のcore/services層を新アーキテクチャに移行
- 後方互換性の維持
- 段階的な置き換え

#### 移行戦略
1. **インターフェースでラップ**
   ```python
   # 既存コードをインターフェース経由で使用
   class LegacyTranscriptionGateway:
       def __init__(self, legacy_transcriber):
           self.legacy = legacy_transcriber
       
       def transcribe(self, video_path: str, options: dict):
           # 既存のAPIを新しいインターフェースに適合
           return self.legacy.transcribe(video_path)
   ```

2. **段階的な置き換え**
   - 新機能は新アーキテクチャで実装
   - 既存機能は順次移行
   - テストで動作保証

### Phase 6: テストとドキュメント（1週間）

### Phase 7: Streamlit固有の最適化（追加フェーズ・2週間）

#### 目標
- Streamlit特有の課題への対応
- パフォーマンス最適化
- 最終統合テスト

#### タスク
1. **状態管理パターンの実装**
   ```python
   # adapters/state/streamlit_state_manager.py
   from typing import Any, Dict, Optional
   import streamlit as st
   from threading import Lock
   
   class StreamlitStateManager:
       """
       Streamlitのセッション状態を一元管理
       
       ライフサイクル:
       - リクエストごとに新しいインスタンスが生成される
       - st.session_stateへの直接アクセスを禁止し、このクラス経由でのみ状態を操作
       """
       
       _instance: Optional['StreamlitStateManager'] = None
       _lock = Lock()
       
       def __new__(cls):
           """リクエストスコープのシングルトン実装"""
           # Streamlitの再実行ごとに新しいインスタンスを作成
           if not hasattr(st, '_state_manager_initialized'):
               with cls._lock:
                   cls._instance = super().__new__(cls)
                   st._state_manager_initialized = True
           return cls._instance
       
       def __init__(self):
           if not hasattr(self, '_initialized'):
               self._initialize_state()
               self._initialized = True
       
       def _initialize_state(self):
           """初期状態の設定"""
           # 必須の状態を定義
           default_states = {
               'transcription_result': None,
               'cache_path': None,
               'is_processing': False,
               'edited_text': '',
               'time_ranges': [],
               'export_settings': {}
           }
           
           for key, default_value in default_states.items():
               if key not in st.session_state:
                   st.session_state[key] = default_value
       
       def get_transcription_state(self) -> TranscriptionState:
           """文字起こし状態を取得"""
           return TranscriptionState(
               result=st.session_state.get('transcription_result'),
               cache_path=st.session_state.get('cache_path'),
               is_processing=st.session_state.get('is_processing', False)
           )
       
       def update_transcription_state(self, state: TranscriptionState):
           """文字起こし状態を更新（バリデーション付き）"""
           if state.is_processing and st.session_state.get('is_processing', False):
               raise ValueError("既に処理中です")
           
           st.session_state.transcription_result = state.result
           st.session_state.cache_path = state.cache_path
           st.session_state.is_processing = state.is_processing
       
       def clear_all_state(self):
           """すべての状態をクリア（新規セッション開始時用）"""
           for key in list(st.session_state.keys()):
               del st.session_state[key]
           self._initialize_state()
       
       @property
       def debug_state(self) -> Dict[str, Any]:
           """デバッグ用：現在の状態をダンプ"""
           return {key: value for key, value in st.session_state.items()}
   ```
   
   #### 使用ルール
   - **禁止**: `st.session_state`への直接アクセス
   - **推奨**: すべての状態操作は`StreamlitStateManager`経由
   - **例外**: Streamlitウィジェットのkey引数は許可（内部的に必要なため）

2. **リアクティブ更新の制御**
   - `st.rerun()`の使用を最小限に
   - 状態変更の集約化
   - 更新タイミングの最適化

#### 目標
- 包括的なテストスイートの作成
- アーキテクチャドキュメントの整備
- 開発ガイドラインの策定

#### テスト戦略
```python
# tests/unit/use_cases/test_transcribe_video.py
import pytest
from unittest.mock import Mock
from use_cases.transcription.transcribe_video import TranscribeVideoUseCase

class TestTranscribeVideoUseCase:
    def test_successful_transcription(self):
        # Arrange
        mock_gateway = Mock()
        mock_gateway.transcribe.return_value = create_mock_result()
        use_case = TranscribeVideoUseCase(mock_gateway)
        
        # Act
        result = use_case.execute("test.mp4", "medium")
        
        # Assert
        assert result is not None
        assert len(result.segments) > 0
        mock_gateway.transcribe.assert_called_once()
```

## 移行戦略

### 基本原則

1. **既存機能を壊さない**
   - すべての変更は後方互換性を保つ
   - 段階的な切り替えを可能にする

2. **小さなステップ**
   - 1つのPRは1つの機能に限定
   - レビューとテストを容易にする

3. **継続的な動作確認**
   - 各フェーズ終了時に統合テスト
   - ユーザー受け入れテストの実施

### 並行稼働期間

```python
# 移行期間中の設定
class AppConfig:
    # 新アーキテクチャの機能フラグ
    USE_CLEAN_ARCHITECTURE = {
        "transcription": False,  # Phase 3で True に
        "editing": False,       # Phase 4で True に
        "export": False,        # Phase 5で True に
    }
```

### リファクタリング手順

1. **機能の特定**
   - リファクタリング対象の機能を明確化
   - 依存関係の分析

2. **テストの作成**
   - 現在の動作を保証するテストを作成
   - リファクタリング後も同じテストが通ることを確認

3. **インターフェースの定義**
   - 新しいアーキテクチャでのインターフェースを設計
   - 既存コードをラップ

4. **段階的な実装**
   - 新しい実装を作成
   - フィーチャーフラグで切り替え

5. **検証と切り替え**
   - A/Bテストの実施
   - 問題がなければ完全移行

## リスクと対策

### 技術的リスク

| リスク | 影響度 | 発生確率 | 対策 |
|--------|--------|----------|------|
| 既存機能の破壊 | 高 | 中 | 包括的なテストスイート、段階的移行、フィーチャーフラグ |
| パフォーマンス低下 | 中 | 中 | ベンチマークテスト、プロファイリング、キャッシング戦略 |
| 開発期間の延長 | 高 | 高 | バッファ期間の確保、MVP優先、段階的リリース |
| チーム学習コスト | 中 | 高 | ドキュメント整備、ペアプログラミング、サンプルコード |
| Streamlit統合の困難 | 高 | 高 | 専用アダプター層、状態管理パターン、プロトタイプ検証 |

### ビジネスリスク

| リスク | 影響度 | 発生確率 | 対策 |
|--------|--------|----------|------|
| 新機能開発の遅延 | 高 | 中 | 並行開発体制、優先度調整 |
| ユーザー影響 | 高 | 低 | 段階的リリース、ロールバック計画 |

## 成功指標

### 定量的指標

1. **コード品質**
   - main.py: 2,119行 → 100行以下
   - 平均ファイルサイズ: 200行以下
   - 循環的複雑度: 10以下
   - 型カバレッジ: 95%以上

2. **テストカバレッジ**
   - ドメイン層: 100%
   - ユースケース層: 90%以上
   - アダプター層: 80%以上
   - 全体: 85%以上

3. **パフォーマンス**
   - 起動時間: 3秒以内
   - メモリ使用量: 20%削減
   - 文字起こし処理時間: 現状維持

4. **開発効率**
   - 新機能追加時間: 50%削減
   - バグ修正時間: 60%削減
   - デプロイ頻度: 週2回以上

### 定性的指標

1. **開発効率**
   - 新機能追加時間の短縮
   - バグ修正時間の短縮
   - コードレビュー時間の短縮

2. **保守性**
   - 新規開発者のオンボーディング時間短縮
   - ドキュメントの充実度
   - コードの理解しやすさ

## 移行例：並列文字起こし処理

現在の実装（main.py内）から新アーキテクチャへの移行例：

### 現在の実装
```python
# main.py内の並列処理（簡略化）
if parallel_enabled:
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = []
        for segment in segments:
            future = executor.submit(process_segment, segment)
            futures.append(future)
```

### 新アーキテクチャでの実装
```python
# use_cases/transcription/parallel_transcribe.py
class ParallelTranscribeUseCase:
    def __init__(self, gateway: ITranscriptionGateway, config: ParallelConfig):
        self.gateway = gateway
        self.config = config
    
    def execute(self, video_path: str, options: dict) -> TranscriptionResult:
        segments = self._split_video(video_path)
        
        if self.config.parallel_enabled:
            return self._parallel_process(segments, options)
        else:
            return self._sequential_process(segments, options)
```

## ロールバック計画

### フィーチャーフラグによる段階的切り替え
```python
# config/feature_flags.py
FEATURE_FLAGS = {
    "use_clean_architecture": {
        "transcription": os.getenv("USE_CLEAN_TRANSCRIPTION", "false") == "true",
        "editing": os.getenv("USE_CLEAN_EDITING", "false") == "true",
        "export": os.getenv("USE_CLEAN_EXPORT", "false") == "true",
    }
}
```

### ロールバック手順
1. 環境変数でフィーチャーフラグを無効化
2. 旧実装に即座に切り替わる
3. 問題の調査と修正
4. 再度有効化してテスト

## 次のステップ

1. **承認と準備**
   - ステークホルダーへの説明と承認
   - 開発環境の準備
   - チームトレーニング
   - プロトタイプの作成

2. **Phase 1の開始**
   - ブランチの作成: `feature/clean-architecture-phase1`
   - 基本構造の実装
   - 最初のページ分割
   - Streamlit状態管理パターンの検証

3. **定期的なレビュー**
   - 週次進捗レビュー
   - 課題の早期発見と対応
   - 計画の柔軟な調整
   - ユーザーフィードバックの収集

## 参考資料

- [Clean Architecture by Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Implementing Clean Architecture in Python](https://github.com/topics/clean-architecture?l=python)
- [Domain-Driven Design by Eric Evans](https://www.domainlanguage.com/ddd/)

---

作成日: 2025-06-29
更新日: 2025-06-29
作成者: Claude AI & 開発チーム
バージョン: 2.1.0

## 更新履歴

### v2.0.0 (2025-06-29)
- 期間を6週間から15週間に延長
- Streamlit特有の課題セクションを追加
- Phase 7（Streamlit固有の最適化）を追加
- リスク評価を現実的に調整
- 具体的な移行例とロールバック計画を追加
- 成功指標を具体化

### v2.1.0 (2025-06-29)
- 期間に関する注意事項を追加（専任チーム前提、不確実性の高いフェーズへの言及）
- 依存性注入（DI）の方針を詳細化
  - Phase 1-3では手動組み立て（AppFactory）
  - Phase 4以降でDIコンテナライブラリ（dependency-injector）導入
- StreamlitStateManagerの詳細設計を追加
  - リクエストスコープのシングルトン実装
  - ライフサイクルの明確化
  - st.session_stateへの直接アクセス禁止ルール

### v2.2.0 (2025-06-29)
- Phase 2完了を記録
  - ドメインエンティティとテストの実装完了
  - レガシー形式との互換性確保
  - ドメインルールの文書化（DOMAIN_RULES.md）