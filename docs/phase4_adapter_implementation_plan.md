# Phase 4: アダプター層実装計画

## 概要

Phase 4では、既存のcore/services層をクリーンアーキテクチャのゲートウェイとして実装します。
既存機能を壊さないよう、慎重に既存コードをラップする形で進めます。

## 現状分析

### 既存構造

```
core/
├── transcription.py        # Transcriberクラス（ローカル/API統合）
├── transcription_api.py    # APITranscriberクラス
├── text_processor.py       # テキスト差分検出
├── video.py               # VideoProcessorクラス
├── export.py              # FCPXMLExporter, PremiereXMLExporter
├── srt_exporter.py        # SRTExporterクラス
└── ...

services/
├── transcription_service.py    # 文字起こしサービス
├── text_editing_service.py     # テキスト編集サービス
├── video_processing_service.py # 動画処理サービス
├── export_service.py          # エクスポートサービス
└── ...
```

### ゲートウェイインターフェースとのマッピング

| ゲートウェイインターフェース | 既存実装 | 備考 |
|---------------------------|---------|------|
| ITranscriptionGateway | core.transcription.Transcriber | ローカル/API統合 |
| ITextProcessorGateway | core.text_processor | 差分検出・境界調整 |
| IVideoProcessorGateway | core.video.VideoProcessor | 無音検出・セグメント抽出 |
| IExportGateway | core.export.FCPXMLExporter等 | 各種エクスポート |
| IFileGateway | 新規実装 | ファイル操作の抽象化 |

## 実装方針

### 1. 既存コードの保持

- **既存のcore/servicesは変更しない**
- 新しい`adapters/gateways/`ディレクトリにゲートウェイ実装を作成
- 既存クラスをコンポジションで包含

### 2. データ変換戦略

```python
# 例: TranscriptionGatewayAdapter
class TranscriptionGatewayAdapter:
    def __init__(self, legacy_transcriber: Transcriber):
        self._legacy = legacy_transcriber
    
    def transcribe(self, video_path: FilePath, ...) -> domain.TranscriptionResult:
        # 1. ドメイン型 → レガシー型
        legacy_path = str(video_path)
        
        # 2. レガシー処理実行
        legacy_result = self._legacy.transcribe(legacy_path, ...)
        
        # 3. レガシー型 → ドメイン型
        return self._convert_to_domain(legacy_result)
```

### 3. エラーハンドリング

- レガシーエラーをドメイン例外に変換
- スタックトレースの保持
- 後方互換性の維持

### 4. テスト戦略

各ゲートウェイアダプターに対して：
1. **単体テスト**: モックを使用した変換ロジックのテスト
2. **統合テスト**: 実際のレガシークラスとの統合テスト
3. **回帰テスト**: 既存機能が変わらないことの確認

## 実装順序

### Step 1: ディレクトリ構造の作成
```
adapters/
├── gateways/
│   ├── __init__.py
│   ├── transcription/
│   │   ├── __init__.py
│   │   └── transcription_gateway.py
│   ├── text_processing/
│   │   ├── __init__.py
│   │   └── text_processor_gateway.py
│   ├── video_processing/
│   │   ├── __init__.py
│   │   └── video_processor_gateway.py
│   ├── export/
│   │   ├── __init__.py
│   │   ├── fcpxml_gateway.py
│   │   └── srt_gateway.py
│   └── file/
│       ├── __init__.py
│       └── file_gateway.py
└── converters/
    ├── __init__.py
    ├── transcription_converter.py
    ├── text_converter.py
    └── video_converter.py
```

### Step 2: FileGateway実装（新規）
- ファイル操作の抽象化
- 一時ディレクトリ管理
- エラーハンドリング

### Step 3: TranscriptionGateway実装
1. Transcriberクラスのラップ
2. データ型変換（レガシー ↔ ドメイン）
3. キャッシュ機能の統合
4. APIモード対応

### Step 4: TextProcessorGateway実装
- text_processor.pyの機能をラップ
- 差分検出・境界調整の実装

### Step 5: VideoProcessorGateway実装
- VideoProcessorクラスのラップ
- 無音検出・セグメント抽出

### Step 6: ExportGateway実装
- FCPXML/SRTエクスポートの統合
- TimeMapperの実装

### Step 7: 統合テスト
- 全ゲートウェイの連携確認
- エンドツーエンドテスト

## リスクと対策

### リスク1: データ型の不整合
**対策**: 
- 詳細な変換テストの作成
- 型アノテーションの活用
- ランタイムバリデーション

### リスク2: パフォーマンス劣化
**対策**:
- 変換処理の最適化
- 不要なコピーの削減
- プロファイリングの実施

### リスク3: 既存機能の破壊
**対策**:
- 既存コードは変更しない
- 包括的な回帰テスト
- 段階的な移行

## 成功基準

1. **機能面**
   - 既存の全機能が正常に動作
   - ユースケースとの統合が完了

2. **品質面**
   - 各ゲートウェイのテストカバレッジ 90%以上
   - エラーハンドリングの網羅

3. **保守性**
   - 明確な責任分離
   - 将来の拡張が容易

## タイムライン

- Step 1-2: 1日（基盤準備）
- Step 3: 2日（最も複雑）
- Step 4-6: 各1日
- Step 7: 1日（統合テスト）

合計: 約7日

---

最終更新: 2025-06-29