# Infrastructure Layer (インフラストラクチャ層)

最も外側の層で、具体的な実装の詳細を含みます。

## 特徴
- フレームワーク固有のコード
- 外部サービスとの実際の通信
- データの永続化
- UI の実装

## ディレクトリ構造

### ui/pages/
Streamlitの実際のページ実装
- `transcription_page.py` - 文字起こしページ
- `editing_page.py` - 編集ページ
- `export_page.py` - エクスポートページ

### ui/components/
再利用可能なUIコンポーネント
- 共通のウィジェット
- カスタムコンポーネント

### persistence/
データの永続化
- `file_repository.py` - ファイルの読み書き
- `cache_repository.py` - キャッシュ管理

### external/
外部サービスとの実際の通信
- `whisper_service.py` - WhisperXの実装
- `ffmpeg_service.py` - FFmpegの実装
- `openai_api_service.py` - OpenAI APIの実装

### di/
依存性注入の設定
- `container.py` - DIコンテナ定義
- `providers.py` - プロバイダー定義