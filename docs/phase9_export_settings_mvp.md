# Phase 9: ExportSettings MVP - 切り抜き処理セクション

## 概要
切り抜き処理（エクスポート）セクションをMVPパターンで実装し、クリーンアーキテクチャへの移行を完了させます。

## 実装対象
main.pyの以下の部分をMVP化：
- `show_export_settings()` 関数
- エクスポート処理のビジネスロジック
- 各種エクスポート形式（動画、FCPXML、EDL、SRT）の処理

## アーキテクチャ設計

### 1. ViewModel
```python
# presentation/view_models/export_settings.py
@dataclass
class ExportSettingsViewModel(BaseViewModel):
    """エクスポート設定のViewModel"""
    
    # 入力データ
    video_path: Optional[Path] = None
    transcription_result: Optional[Any] = None
    edited_text: Optional[str] = None
    time_ranges: Optional[List[TimeRange]] = None
    adjusted_time_ranges: Optional[List[TimeRange]] = None
    
    # 設定
    remove_silence: bool = False
    silence_threshold: float = -35.0
    min_silence_duration: float = 0.3
    silence_pad_start: float = 0.3
    silence_pad_end: float = 0.3
    
    # エクスポート形式
    export_format: str = "video"  # video, fcpxml, edl, srt
    include_srt: bool = False
    srt_max_line_length: int = 40
    srt_max_lines: int = 2
    
    # 処理状態
    is_processing: bool = False
    progress: float = 0.0
    status_message: str = ""
    
    # 結果
    export_results: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
```

### 2. Presenter
```python
# presentation/presenters/export_settings.py
class ExportSettingsPresenter(BasePresenter[ExportSettingsViewModel]):
    """エクスポート設定のPresenter"""
    
    def __init__(
        self,
        view_model: ExportSettingsViewModel,
        export_video_use_case: ExportVideoUseCase,
        export_fcpxml_use_case: ExportFCPXMLUseCase,
        export_edl_use_case: ExportEDLUseCase,
        export_srt_use_case: ExportSRTUseCase,
        session_manager: SessionManager
    ):
        super().__init__(view_model)
        self.export_video_use_case = export_video_use_case
        self.export_fcpxml_use_case = export_fcpxml_use_case
        self.export_edl_use_case = export_edl_use_case
        self.export_srt_use_case = export_srt_use_case
        self.session_manager = session_manager
```

### 3. View
```python
# presentation/views/export_settings.py
class ExportSettingsView:
    """エクスポート設定のView"""
    
    def render(self) -> None:
        """UIをレンダリング"""
        # 無音削除設定
        # エクスポート形式選択
        # 実行ボタン
        # 進捗表示
```

## 実装手順

1. **ViewModelの作成**
   - エクスポート設定の状態管理
   - プロパティとバリデーション

2. **Presenterの実装**
   - 各エクスポート形式のユースケース呼び出し
   - 進捗管理とエラーハンドリング

3. **Viewの実装**
   - Streamlit UIコンポーネント
   - イベントハンドリング

4. **DI設定の更新**
   - PresentationContainerにExportSettings関連を追加

5. **main.pyの統合**
   - show_export_settings()をExportSettingsViewに置き換え

## 期待される成果
- エクスポート処理がクリーンアーキテクチャに準拠
- テスト可能な設計
- UIとビジネスロジックの分離