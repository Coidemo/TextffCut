# TextffCut クリーンアーキテクチャ移行ガイド

## 概要

TextffCutを段階的にクリーンアーキテクチャへ移行しています。
移行期間中も既存の機能は完全に動作します。

## 使い方

### レガシーモード（デフォルト）
従来通りの使い方：
```bash
streamlit run main.py
```

### 新アーキテクチャモード（開発中）
```bash
streamlit run app.py
```

初回起動時はレガシーモードで動作します。
UIから新アーキテクチャモードに切り替えることができます。

## 移行状況

### Phase 1: 基盤整備（80%完了）
- [x] ディレクトリ構造の作成
- [x] app.pyとRouterの実装
- [x] セッション管理の抽象化（SessionManager）
- [x] 動画入力セクションの分離
- [x] エクスポートセクションの分離
- [ ] 文字起こしセクション（Phase 2後に実装）
- [ ] 編集セクション（Phase 2後に実装）

**重要な決定**: 文字起こし・編集セクションは相互依存が強いため、ドメイン層構築後に実装

### Phase 2: ドメイン層（100%完了）✅
- [x] エンティティの定義
  - TranscriptionResult, TranscriptionSegment, Word, Char
  - VideoSegment, TextDifference
- [x] 値オブジェクトの実装
  - TimeRange, FilePath, Duration
- [x] ドメインルールの文書化
- [x] 包括的なテストスイート

### Phase 3: ユースケース層
- [ ] ビジネスロジックの抽出
- [ ] インターフェースの定義

## 開発者向け情報

### ディレクトリ構造
```
TextffCut/
├── app.py              # 新しいエントリーポイント
├── main.py             # レガシーコード（保持）
├── domain/             # ドメイン層
│   ├── entities/       # エンティティ
│   └── value_objects/  # 値オブジェクト
├── use_cases/          # ユースケース層
│   ├── transcription/  # 文字起こし
│   ├── editing/        # 編集
│   └── export/         # エクスポート
├── adapters/           # アダプター層
│   ├── controllers/    # コントローラー
│   ├── presenters/     # プレゼンター
│   └── gateways/       # ゲートウェイ
└── infrastructure/     # インフラ層
    ├── ui/             # UI実装
    ├── persistence/    # 永続化
    └── external/       # 外部サービス
```

### テスト
移行の正確性を確認：
```bash
python test_app_migration.py
```