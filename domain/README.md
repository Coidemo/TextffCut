# Domain Layer (ドメイン層)

最も内側の層で、ビジネスの核心部分を表現します。

## 特徴
- 外部に一切依存しない
- ビジネスルールとビジネスデータを含む
- フレームワークやライブラリから独立

## ディレクトリ構造

### entities/
ビジネスの中核概念を表現するエンティティ
- `TranscriptionResult` - 文字起こし結果
- `VideoSegment` - 動画の切り抜き部分
- `ExportProject` - エクスポートプロジェクト

### value_objects/
不変の値を表現する値オブジェクト
- `TimeRange` - 開始/終了時間
- `FilePath` - ファイルパス
- `AudioThreshold` - 音声閾値