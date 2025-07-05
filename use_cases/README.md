# Use Cases Layer (ユースケース層)

アプリケーション固有のビジネスルールを実装します。

## 特徴
- ドメイン層のみに依存
- 外部の実装詳細を知らない
- インターフェース（Protocol）を通じて外部と通信

## ディレクトリ構造

### transcription/
文字起こし関連のユースケース
- `TranscribeVideoUseCase` - 動画を文字起こしする
- `SplitTranscriptionUseCase` - 長時間動画を分割して処理

### editing/
編集関連のユースケース
- `FindDifferencesUseCase` - テキスト差分を検出
- `AdjustBoundariesUseCase` - 境界を調整

### export/
エクスポート関連のユースケース
- `ExportToFCPXMLUseCase` - FCPXMLにエクスポート
- `GenerateSRTUseCase` - SRT字幕を生成