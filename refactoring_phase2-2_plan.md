# Phase 2-2: main.pyのサービス層分離 - 実装計画

## 分析結果サマリー

### 現状
- **ファイルサイズ**: 1,178行
- **主要機能**: 文字起こし、テキスト編集、動画処理、エクスポート
- **問題点**: UIとビジネスロジックの密結合、セッション状態への過度な依存

### リスク評価
- **高リスク**: セッション状態の複雑な相互依存
- **中リスク**: プログレスコールバックのUI依存
- **低リスク**: 純粋なビジネスロジック部分

## 段階的移行計画

### Stage 1: ユーティリティサービスの作成（低リスク）

#### 1.1 ConfigurationService
```python
# services/configuration_service.py
class ConfigurationService(BaseService):
    """アプリケーション設定の管理"""
    
    def calculate_api_cost(self, duration_minutes: float) -> ServiceResult:
        """API使用料金の計算"""
        pass
    
    def validate_model_settings(
        self, 
        model_size: str, 
        use_api: bool,
        available_memory: float
    ) -> ServiceResult:
        """モデル設定の検証"""
        pass
    
    def get_output_path(
        self,
        video_path: str,
        process_type: str,
        custom_output_dir: Optional[str]
    ) -> ServiceResult:
        """出力パスの生成"""
        pass
```

#### 1.2 SessionStateAdapter
```python
# ui/session_state_adapter.py
class SessionStateAdapter:
    """セッション状態とサービス層のアダプター"""
    
    def __init__(self, session_state):
        self.session_state = session_state
    
    def get_transcription_settings(self) -> WorkflowSettings:
        """セッション状態からワークフロー設定を生成"""
        pass
    
    def update_from_service_result(self, result: ServiceResult):
        """サービス結果をセッション状態に反映"""
        pass
```

### Stage 2: ビジネスロジックの分離（中リスク）

#### 2.1 文字起こし実行部分のリファクタリング
**現在のコード（509-686行）**を以下のように分離：

```python
# main.py（リファクタリング後）
def handle_transcription_execution():
    """文字起こし実行のUIハンドラー"""
    # UIの準備
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # サービスの準備
    workflow_service = WorkflowService(config)
    settings = SessionStateAdapter(st.session_state).get_transcription_settings()
    
    # プログレスコールバック
    def ui_progress_callback(progress: float, message: str):
        progress_bar.progress(progress)
        status_text.text(message)
    
    # サービス実行
    result = workflow_service.transcription_only_workflow(
        video_path=st.session_state.current_video_path,
        settings=settings,
        progress_callback=ui_progress_callback
    )
    
    # 結果の処理
    if result.success:
        st.session_state.transcription_result = result.data
        st.success("文字起こし完了！")
    else:
        st.error(f"エラー: {result.error}")
```

#### 2.2 差分計算・検証のリファクタリング
**現在のコード（757-876行）**を以下のように分離：

```python
# main.py（リファクタリング後）
def handle_text_processing():
    """テキスト処理のUIハンドラー"""
    # サービスの準備
    text_service = TextEditingService(config)
    
    # 差分計算
    diff_result = text_service.find_differences(
        original_segments=st.session_state.transcription_result.segments,
        edited_text=st.session_state.edited_text
    )
    
    if diff_result.success:
        st.session_state.current_diff = diff_result.data
        # UI表示は既存のshow_diff_viewer()を使用
        show_diff_viewer(diff_result.data, diff_result.metadata)
    else:
        st.error(f"差分検出エラー: {diff_result.error}")
```

### Stage 3: UIファサードの実装（高リスク）

#### 3.1 AppFacade
```python
# ui/app_facade.py
class AppFacade:
    """アプリケーション全体のファサード"""
    
    def __init__(self, config: Config):
        self.workflow_service = WorkflowService(config)
        self.config_service = ConfigurationService(config)
        self.session_adapter = None  # Streamlit実行時に設定
    
    def initialize_session(self, session_state):
        """セッション初期化"""
        self.session_adapter = SessionStateAdapter(session_state)
    
    def process_video_with_ui(
        self,
        video_path: str,
        progress_container,
        status_container
    ) -> bool:
        """動画処理の完全なワークフロー（UI付き）"""
        # UIコンテナを使った進捗表示
        # サービス層の呼び出し
        # 結果のセッション状態への反映
        pass
```

### Stage 4: main.pyの最終形

```python
# main.py（最終形）
def main():
    """メインアプリケーション（UI層のみ）"""
    # UIの初期化
    apply_dark_mode_styles()
    show_header()
    
    # ファサードの初期化
    app = AppFacade(config)
    app.initialize_session(st.session_state)
    
    # サイドバー
    with st.sidebar:
        show_settings(app.config_service)
    
    # メインコンテンツ
    video_path = show_video_input()
    if not video_path:
        return
    
    # タブ構成
    tab1, tab2, tab3 = st.tabs(["文字起こし", "編集", "エクスポート"])
    
    with tab1:
        handle_transcription_tab(app)
    
    with tab2:
        handle_editing_tab(app)
    
    with tab3:
        handle_export_tab(app)
```

## 実装順序と検証計画

### Phase 2-2-1: 準備とユーティリティ
1. ConfigurationServiceの実装
2. SessionStateAdapterの実装
3. 単体テストの作成

### Phase 2-2-2: 部分的な移行
1. 料金計算ロジックの移行
2. モデル検証ロジックの移行
3. 出力パス生成ロジックの移行
4. 動作確認（既存機能が正常に動作すること）

### Phase 2-2-3: 主要機能の移行
1. 文字起こし実行部分の移行
2. テキスト処理部分の移行
3. エクスポート処理の移行
4. 統合テスト

### Phase 2-2-4: UIファサードとクリーンアップ
1. AppFacadeの実装
2. main.pyの整理
3. 不要なインポートの削除
4. 最終動作確認

## 検証項目

### 機能テスト
- [ ] 文字起こし（API/ローカル両モード）
- [ ] キャッシュの読み書き
- [ ] テキスト編集と差分表示
- [ ] 無音削除
- [ ] 各種エクスポート形式
- [ ] エラーハンドリング

### 非機能テスト
- [ ] パフォーマンス（処理時間が増加していないこと）
- [ ] メモリ使用量（リークがないこと）
- [ ] UI応答性（フリーズしないこと）

## リスク軽減策

1. **バックアップ**: main.pyの元のバージョンを保持
2. **並行稼働**: 新旧コードを一時的に共存させる
3. **フィーチャーフラグ**: 新実装への切り替えを制御
4. **段階的ロールアウト**: 一部機能から順次移行

## 成功基準

1. **機能維持**: すべての既存機能が正常に動作
2. **コード品質**: main.pyが500行以下に削減
3. **保守性**: ビジネスロジックが独立してテスト可能
4. **拡張性**: 新機能追加が容易になる