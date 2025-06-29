# Phase 6: Presentation層の現状分析

## 現在のUI構造

### UIコンポーネントの分類

1. **メインUIコンポーネント** (`ui/components.py`)
   - `show_api_key_manager`: APIキー管理
   - `show_diff_viewer`: 差分表示
   - `show_export_settings`: エクスポート設定
   - `show_help`: ヘルプ表示
   - `show_progress`: 進捗表示
   - `show_red_highlight_modal`: ハイライトモーダル
   - `show_silence_settings`: 無音設定
   - `show_text_editor`: テキストエディター
   - `show_transcription_controls`: 文字起こしコントロール
   - `show_video_input`: 動画入力

2. **リカバリー関連** (`ui/recovery_components.py`)
   - `show_recovery_check`: リカバリーチェック
   - `show_recovery_history`: リカバリー履歴
   - `show_recovery_settings`: リカバリー設定
   - `show_recovery_status`: リカバリーステータス

3. **タイムライン関連**
   - `timeline_editor.py`: タイムラインエディター
   - `timeline_editor_simple.py`: シンプル版
   - `timeline_editor_static.py`: 静的版
   - `waveform_display.py`: 波形表示
   - `waveform_interaction.py`: 波形インタラクション

4. **スタイル関連**
   - `styles.py`: カスタムCSS
   - `dark_mode_styles.py`: ダークモード
   - `timeline_color_scheme.py`: カラースキーム

5. **ユーティリティ**
   - `file_upload.py`: ファイルアップロード
   - `session_state_adapter.py`: セッション状態アダプター
   - `keyboard_handler.py`: キーボードハンドラー

## 現在の問題点

1. **責務の混在**
   - UIコンポーネントがビジネスロジックを含んでいる
   - 直接サービスやコアモジュールにアクセスしている
   - 状態管理がStreamlitのセッション状態に強く依存

2. **テスタビリティ**
   - Streamlit依存のためユニットテストが困難
   - UIロジックとビジネスロジックが分離されていない

3. **再利用性**
   - 他のUIフレームワークへの移植が困難
   - コンポーネント間の依存関係が複雑

## Presentation層の設計方針

### 1. MVP (Model-View-Presenter) パターンの採用

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    View     │────▶│  Presenter  │────▶│  ViewModel  │
│ (Streamlit) │◀────│             │◀────│             │
└─────────────┘     └─────────────┘     └─────────────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                           │
                    ┌──────▼──────┐
                    │  Use Cases  │
                    └─────────────┘
```

### 2. 責務の分離

- **View**: Streamlit UI（表示のみ）
- **Presenter**: UIロジック、イベントハンドリング
- **ViewModel**: UI用のデータモデル
- **Use Case**: ビジネスロジック

### 3. 段階的な移行戦略

1. **Phase 6.1**: ViewModelの作成
   - 既存のセッション状態をViewModelに抽象化
   - データ変換ロジックの分離

2. **Phase 6.2**: Presenterの実装
   - UIイベントハンドリングの分離
   - Use Caseの呼び出し

3. **Phase 6.3**: Viewの簡素化
   - 既存UIコンポーネントのリファクタリング
   - 表示ロジックのみに限定

## 実装優先順位

1. **高優先度（最もよく使われる機能）**
   - 動画入力（`show_video_input`）
   - 文字起こしコントロール（`show_transcription_controls`）
   - テキストエディター（`show_text_editor`）
   - エクスポート設定（`show_export_settings`）

2. **中優先度**
   - 無音設定（`show_silence_settings`）
   - 差分表示（`show_diff_viewer`）
   - 進捗表示（`show_progress`）

3. **低優先度**
   - APIキー管理（`show_api_key_manager`）
   - ヘルプ表示（`show_help`）
   - リカバリー関連機能

## 技術的考慮事項

1. **Streamlit固有の制約**
   - リアクティブな更新メカニズム
   - セッション状態の管理
   - リロード時の状態保持

2. **DIコンテナとの統合**
   - PresenterとUse CaseをDIで注入
   - テスト時のモック注入

3. **型安全性**
   - ViewModelに型ヒントを追加
   - Presenter/View間のインターフェース定義