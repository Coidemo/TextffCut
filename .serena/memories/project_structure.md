# プロジェクト構造

## ディレクトリ構成

### コアモジュール
```
core/                     # コア機能
├── transcription.py      # WhisperX文字起こし
├── transcription_api.py  # OpenAI API文字起こし
├── text_processor.py     # テキスト差分検出
├── video.py             # 動画処理・無音検出
├── export.py            # FCPXML/EDLエクスポート
├── error_handling.py    # エラーハンドリング
├── types.py             # 型定義
└── models.py            # データモデル
```

### クリーンアーキテクチャ層
```
domain/                  # ドメイン層（ビジネスロジック）
├── entities/           # エンティティ
├── value_objects/      # 値オブジェクト
├── use_cases/         # ユースケース
└── gateways/          # ゲートウェイインターフェース

application/            # アプリケーション層
└── use_cases/         # アプリケーション固有のユースケース

infrastructure/         # インフラ層
├── gateways/          # ゲートウェイ実装
└── repositories/      # リポジトリ実装

presentation/          # プレゼンテーション層
├── views/            # ビュー（Streamlit UI）
└── presenters/       # プレゼンター
```

### UI/サポート
```
ui/                    # UI関連
├── components.py      # Streamlitコンポーネント
└── file_upload.py     # ファイル入力処理

utils/                 # ユーティリティ
di/                   # 依存性注入
├── containers.py     # DIコンテナ定義
```

### 設定・スクリプト
```
config/               # 設定ファイル
scripts/              # ユーティリティスクリプト
tests/                # テストコード
├── unit/            # ユニットテスト
└── integration/     # 統合テスト
```

### ドキュメント
```
docs/                 # ドキュメント
├── api_schemas/      # API仕様
└── *.md             # 各種設計書
```

### Docker/CI
```
.github/              # GitHub Actions
docker-compose.yml    # Docker構成
Dockerfile           # Dockerイメージ定義
```

## エントリーポイント
- **main.py**: メインアプリケーション（Streamlit）
- **app.py**: 代替エントリーポイント
- **worker_*.py**: ワーカープロセス（並列処理用）

## 重要な設定ファイル
- **config.py**: アプリケーション設定
- **pyproject.toml**: Python開発ツール設定
- **requirements.txt**: 依存パッケージ
- **CLAUDE.md**: プロジェクト固有の指示
- **Makefile**: 開発コマンド集