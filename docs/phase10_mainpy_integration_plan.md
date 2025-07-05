# Phase 10: main.py統合計画書

## 概要

TextffCutのmain.pyを完全にMVPパターンに移行し、クリーンアーキテクチャを完成させる計画です。

## 現状分析

### 現在のmain.pyの構造

1. **Streamlit設定とCSS** (行1-90)
   - ページ設定
   - カスタムCSS
   - ダークモード対応

2. **メイン関数** (行91-1000+)
   - DIコンテナ初期化
   - サイドバー（状態管理、設定）
   - メインコンテンツ
     - ファイル選択（MVP化済み）
     - 文字起こし（MVP化済み）
     - テキスト編集（MVP化済み）
     - エクスポート（MVP化済み）

### 課題

1. **レガシー形式への依存**
   - `transcription.get_full_text()`などレガシーメソッドの使用
   - SessionManagerがレガシー形式を保存（一時対応）

2. **直接的なUI実装**
   - サイドバーの実装がmain.pyに含まれている
   - エラーハンドリングの不統一

3. **状態管理の複雑性**
   - st.session_stateの直接操作
   - SessionManagerとの二重管理

## 移行戦略

### Step 1: MainPresenterの作成

**目的**: main.pyのビジネスロジックをPresenterに移動

**実装内容**:
```python
class MainPresenter:
    def __init__(
        self,
        video_input_presenter: VideoInputPresenter,
        transcription_presenter: TranscriptionPresenter,
        text_editor_presenter: TextEditorPresenter,
        export_settings_presenter: ExportSettingsPresenter,
        session_manager: SessionManager,
        error_handler: ErrorHandler
    ):
        # 各MVPのPresenterを統合管理
```

**責務**:
- ワークフロー管理
- 各MVP間の連携
- エラーハンドリングの統一

### Step 2: サイドバーのMVP化

**SidebarViewModel**:
- リカバリー状態
- プロセス管理
- 設定（無音検出、API設定など）

**SidebarPresenter**:
- 設定の保存/読み込み
- リカバリー処理
- ヘルプ表示

**SidebarView**:
- Streamlit UIの実装
- イベントハンドリング

### Step 3: レガシー形式の解消

**TranscriptionResultAdapter**:
```python
class TranscriptionResultAdapter:
    """ドメインエンティティをレガシー形式に適応させるアダプター"""
    
    def __init__(self, domain_result: domain.TranscriptionResult):
        self._domain_result = domain_result
    
    def get_full_text(self) -> str:
        """レガシーのget_full_textメソッドを提供"""
        # ドメインエンティティから全テキストを生成
        return self._generate_full_text_from_domain()
    
    @property
    def segments(self):
        """レガシー形式のセグメントを提供"""
        return self._convert_segments_to_legacy()
```

### Step 4: 統合とテスト

1. **段階的移行**
   - 新しいMainViewを作成
   - 既存のmain()関数と並行実行
   - 動作確認後に切り替え

2. **統合テスト**
   - エンドツーエンドテスト
   - 各MVP間の連携テスト
   - パフォーマンステスト

## 実装計画

### Phase 10.1: 基盤整備（1-2日）
- [ ] MainViewModelの設計と実装
- [ ] MainPresenterの基本実装
- [ ] TranscriptionResultAdapterの実装

### Phase 10.2: サイドバーMVP（2-3日）
- [ ] SidebarViewModelの実装
- [ ] SidebarPresenterの実装
- [ ] SidebarViewの実装
- [ ] 既存機能の移行

### Phase 10.3: 統合作業（2-3日）
- [ ] MainViewの実装
- [ ] 各MVP間の連携実装
- [ ] エラーハンドリングの統一
- [ ] SessionManagerの最適化

### Phase 10.4: テストと切り替え（1-2日）
- [ ] 統合テストの作成と実行
- [ ] パフォーマンス測定
- [ ] 本番環境への切り替え
- [ ] ドキュメント更新

## 期待される成果

1. **アーキテクチャの統一**
   - すべてのコンポーネントがMVPパターンに準拠
   - 明確な責任分離

2. **保守性の向上**
   - main.pyが薄くなり、理解しやすくなる
   - 変更の影響範囲が限定される

3. **テスタビリティ**
   - MainPresenterの単体テストが可能
   - 統合テストの実装が容易

4. **拡張性**
   - 新機能の追加が容易
   - プラグインアーキテクチャへの道筋

## リスクと対策

### リスク1: 大規模な変更による不具合
**対策**: 
- 段階的移行
- 並行実行期間の設定
- 十分なテスト

### リスク2: パフォーマンスの低下
**対策**:
- プロファイリングの実施
- 不要な再描画の削減
- キャッシュの最適化

### リスク3: ユーザー体験の変化
**対策**:
- UIの見た目は変更しない
- 動作の互換性を維持
- ユーザーテストの実施

## 成功基準

1. **機能的要件**
   - すべての既存機能が動作する
   - パフォーマンスの劣化がない
   - エラーハンドリングが改善される

2. **非機能的要件**
   - コードカバレッジ80%以上
   - main.pyが500行以下
   - 各クラスが単一責任原則に従う

## まとめ

Phase 10は、TextffCutのクリーンアーキテクチャ移行の最終段階です。main.pyの完全なMVP化により、保守性、拡張性、テスタビリティに優れたアプリケーションが完成します。

慎重な計画と段階的な実装により、リスクを最小限に抑えながら、大きな価値を提供できると考えています。

作成日: 2025-01-01