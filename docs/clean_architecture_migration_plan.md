# TextffCut クリーンアーキテクチャ移行計画書

## 概要

TextffCutプロジェクトをクリーンアーキテクチャに段階的に移行する計画書です。

## 移行フェーズ

### Phase 1-6: 基盤構築（完了）
- DIコンテナの導入
- 基本的なレイヤー構造の確立
- ゲートウェイインターフェースの定義

### Phase 7: Transcription MVP（完了）
**実装内容**：
- TranscriptionViewModel: 文字起こし画面の状態管理
- TranscriptionPresenter: ビジネスロジックの実装
- TranscriptionView: Streamlit UIの実装
- TranscriptionGatewayAdapter: レガシーコードとの統合

**特記事項**：
- キャッシュ読み込みでレガシー形式を維持（一時対応）
- SessionManagerを通じた状態管理

### Phase 8: TextEditor MVP（完了）
**実装内容**：
- TextEditorViewModel: テキスト編集の状態管理
- TextEditorPresenter: テキスト処理ロジック
- TextEditorView: 編集UI（タイムライン編集含む）
- TextProcessorGatewayAdapter: 差分検出処理との統合

**特記事項**：
- モーダルダイアログをインライン表示に変更
- タイムライン編集機能を統合

### Phase 9: ExportSettings MVP（完了）
**実装内容**：
- ExportSettingsViewModel: エクスポート設定の状態管理
- ExportSettingsPresenter: エクスポート処理ロジック
- ExportSettingsView: 設定UI（無音削除、形式選択）
- 各種エクスポートゲートウェイアダプター:
  - VideoExportGatewayAdapter
  - FCPXMLExportGatewayAdapter
  - EDLExportGatewayAdapter
  - SRTExportGatewayAdapter

**特記事項**：
- main.pyの古いエクスポートコードを無効化
- プログレス表示の統合

### Phase 10: main.py統合（計画中）
**目標**：
- main.pyを完全にMVPパターンに移行
- レガシー形式からドメインエンティティへの完全移行
- SessionManagerの活用

**作業項目**：
1. MainPresenterの作成
2. VideoInputセクションのMVP化
3. レガシー形式依存の解消
4. エラーハンドリングの統一

### Phase 11: レガシーコード削除（計画中）
**目標**：
- 不要になったレガシーコードの削除
- インターフェースの整理
- パフォーマンス最適化

## 技術的負債と対応

### 1. レガシー形式とドメインエンティティの混在
**現状**：
- SessionManagerがレガシー形式を保存（一時対応）
- main.pyがレガシー形式に依存

**対応計画**：
- Phase 10でmain.pyをリファクタリング
- アダプター層でのみレガシー形式を扱う

### 2. 状態管理の複雑性
**現状**：
- st.session_stateとViewModelの二重管理
- SessionManagerによる抽象化

**対応計画**：
- ViewModelを単一の真実の源とする
- session_stateは表示制御のみに使用

### 3. エラーハンドリングの不統一
**現状**：
- 各層で異なるエラーハンドリング
- ユーザーへのエラー表示が不統一

**対応計画**：
- ErrorHandlerサービスの活用
- ドメイン例外の統一

## 移行の成果

### 達成したこと
1. **モジュール性の向上**
   - UIとビジネスロジックの分離
   - 各機能の独立性確保

2. **テスタビリティの改善**
   - Presenterのユニットテスト可能
   - モックを使用した統合テスト

3. **保守性の向上**
   - 明確な責任分離
   - 変更の影響範囲の限定

### 今後の課題
1. **パフォーマンス最適化**
   - 大容量ファイルの処理
   - メモリ使用量の削減

2. **ユーザビリティ向上**
   - エラーメッセージの改善
   - プログレス表示の統一

3. **拡張性の確保**
   - プラグイン機構の検討
   - 新しいエクスポート形式の追加

## まとめ

TextffCutのクリーンアーキテクチャ移行は順調に進んでいます。Phase 9まで完了し、主要な機能（文字起こし、テキスト編集、エクスポート）のMVP化が完了しました。

次のステップはmain.pyの完全な移行と、レガシーコードの段階的な削除です。これにより、保守性と拡張性に優れたアプリケーションアーキテクチャが実現されます。

最終更新日: 2025-01-01