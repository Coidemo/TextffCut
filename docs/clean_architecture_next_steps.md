# Clean Architecture 次のステップ

## 現在の状況

### ✅ 完了したフェーズ（Phase 2-6）
- **ドメイン層**: エンティティ、値オブジェクト、ビジネスルール
- **ユースケース層**: 全ビジネスロジック実装（53テスト）
- **Gateway Adapter層**: 既存サービスのラッピング（51テスト）
- **DIコンテナ**: dependency-injectorによる依存性管理（14テスト）
- **Presentation層（MVP）**: VideoInput実装済み（23テスト）

**合計テスト数**: 141テスト ✅

### 🔄 実装中のフェーズ
なし（Phase 6まで完了）

## 次のステップ：Phase 7 既存コードの移行

### 優先順位1：TranscriptionのMVP実装

#### 1. ViewModel作成
```python
# presentation/view_models/transcription.py
@dataclass
class TranscriptionViewModel(BaseViewModel):
    is_processing: bool = False
    progress: float = 0.0
    status_message: str = ""
    model_size: str = "large-v3"
    use_api: bool = False
    transcription_result: Optional[TranscriptionResult] = None
    error_message: Optional[str] = None
```

#### 2. Presenter実装
```python
# presentation/presenters/transcription.py
class TranscriptionPresenter(BasePresenter[TranscriptionViewModel]):
    def start_transcription(self, video_path: Path):
        # ユースケースを呼び出し
        # 進捗更新
        # エラーハンドリング
```

#### 3. View実装
```python
# presentation/views/transcription.py
def show_transcription_controls(container) -> Optional[TranscriptionResult]:
    presenter = container.presentation.transcription_presenter()
    view = TranscriptionView(presenter)
    return view.render()
```

### 優先順位2：TextEditorのMVP実装

#### 主な課題
- 差分検出機能の統合
- タイムライン編集機能の移行
- リアルタイム更新の制御

### 優先順位3：ExportSettingsのMVP実装

#### 主な課題
- 複数のエクスポート形式対応
- 設定の永続化
- プレビュー機能

## 実装上の注意点

### 1. セッション状態の移行
```python
# 変更前
st.session_state.transcription_result = result

# 変更後
view_model.transcription_result = result
view_model.notify()  # オブザーバーに通知
```

### 2. エラーハンドリング
- Presenterで一元管理
- ViewModelにエラー状態を保持
- UIで適切に表示

### 3. テスト戦略
- 各ViewModelの単体テスト
- 各Presenterのビジネスロジックテスト
- 統合テスト（View + Presenter + UseCase）

## 期待される成果

### Phase 7完了時
- main.pyが100行以下に
- すべてのUIコンポーネントがMVP化
- テストカバレッジ85%以上

### 全体完了時
- 完全なClean Architecture実現
- 高い保守性とテスタビリティ
- 新機能追加が容易な構造

## リスクと対策

### リスク1：既存機能の破壊
**対策**: 
- 段階的な移行
- 十分なテスト
- フィーチャーフラグ

### リスク2：開発期間の延長
**対策**:
- MVPに集中
- 並行開発
- 定期的なレビュー

## 推奨アクション

1. **今すぐ**: TranscriptionViewModelの設計レビュー
2. **今週中**: TranscriptionのMVP実装完了
3. **来週**: TextEditorのMVP実装開始

---

作成日: 2025-06-29  
次回レビュー: 2025-07-06