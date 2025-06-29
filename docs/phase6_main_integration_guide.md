# Phase 6: main.pyへのPresentation層統合ガイド

## 統合方針

既存のUIコンポーネントを段階的にPresentation層に移行します。

## 統合手順

### Step 1: 最小限の変更で動画入力を置き換え

#### 1. インポートの追加
```python
# main.pyの先頭に追加
from presentation.views.video_input import show_video_input as show_video_input_mvp
```

#### 2. 既存の関数を置き換え
```python
# 既存のshow_video_inputの呼び出しを置き換え
# 変更前:
video_path = show_video_input()

# 変更後:
container = get_container()  # 既に定義済み
video_path = show_video_input_mvp(container)
```

### Step 2: 段階的な移行

#### 現在の状態
```
ui/components.py
├── show_video_input()        → presentation/views/video_input.py ✅
├── show_transcription_controls() → 次の実装対象
├── show_text_editor()           → 次の実装対象
├── show_export_settings()       → 次の実装対象
└── その他のUI関数
```

#### 移行の利点

1. **テスタビリティ向上**
   - PresenterとViewModelは独立してテスト可能
   - モックを使用した単体テスト

2. **ビジネスロジックの分離**
   - UIロジックとビジネスロジックが明確に分離
   - 再利用性の向上

3. **状態管理の改善**
   - ViewModelによる一元的な状態管理
   - オブザーバーパターンによる変更通知

## 実装例: show_transcription_controls の移行

### 1. TranscriptionViewModel
```python
@dataclass
class TranscriptionViewModel(BaseViewModel):
    """文字起こしのViewModel"""
    is_processing: bool = False
    progress: float = 0.0
    status_message: str = ""
    model_size: str = "large-v3"
    use_api: bool = False
    estimated_cost: Optional[float] = None
    error_message: Optional[str] = None
```

### 2. TranscriptionPresenter
```python
class TranscriptionPresenter(BasePresenter[TranscriptionViewModel]):
    """文字起こしのPresenter"""
    
    @inject
    def __init__(
        self,
        view_model: TranscriptionViewModel,
        transcribe_use_case=Provide[ApplicationContainer.use_cases.transcribe_video]
    ):
        super().__init__(view_model)
        self.transcribe_use_case = transcribe_use_case
    
    def start_transcription(self, video_path: Path):
        """文字起こしを開始"""
        # ViewModelを更新
        self.view_model.is_processing = True
        self.view_model.progress = 0.0
        self.view_model.notify()
        
        # Use Caseを実行
        request = TranscribeVideoRequest(
            video_path=video_path,
            model_size=self.view_model.model_size,
            language="ja"
        )
        
        try:
            response = self.transcribe_use_case.execute(request)
            # 成功処理
        except Exception as e:
            self.handle_error(e, "文字起こし処理")
```

### 3. TranscriptionView
```python
def show_transcription_controls(container) -> Optional[TranscriptionResult]:
    """文字起こしコントロールを表示"""
    presenter = container.presentation.transcription_presenter()
    view = TranscriptionView(presenter)
    return view.render()
```

## 注意事項

1. **セッション状態の移行**
   - 既存のst.session_stateはViewModelに移行
   - 必要に応じてSessionStateManagerを使用

2. **後方互換性**
   - 既存の関数シグネチャは維持
   - 内部実装のみを変更

3. **エラーハンドリング**
   - Presenterで一元的に処理
   - ViewModelにエラー情報を設定

## テスト戦略

1. **単体テスト**
   ```python
   def test_video_input_presenter():
       # モックを使用してPresenterをテスト
       mock_gateway = Mock()
       view_model = VideoInputViewModel()
       presenter = VideoInputPresenter(view_model)
       presenter.file_gateway = mock_gateway
       
       # テストの実行
       presenter.refresh_video_list()
       
       # アサーション
       assert view_model.video_files == expected_files
   ```

2. **統合テスト**
   - 実際のStreamlitアプリでの動作確認
   - E2Eテストツールの使用を検討

## まとめ

Presentation層の導入により、以下が実現されます：

1. **保守性の向上**: ビジネスロジックとUIの分離
2. **テスタビリティの向上**: 独立したテストが可能
3. **再利用性の向上**: ViewModelとPresenterの再利用
4. **型安全性の向上**: 明確なインターフェース定義

段階的な移行により、リスクを最小限に抑えながら、アーキテクチャを改善できます。