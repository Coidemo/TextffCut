# TextffCut Docker ガイド

Docker版TextffCutの詳細な使用方法です。

## 🚀 クイックスタート

### 1. 前提条件
- Docker Desktop for Mac がインストールされていること
- 4GB以上のメモリをDockerに割り当てていること

### 2. 簡単起動

```bash
# リポジトリをクローン
git clone https://github.com/Coidemo/TextffCut.git
cd TextffCut

# Docker版を起動
./docker-run.sh start

# ブラウザで http://localhost:8501 にアクセス
```

## 📁 ディレクトリ構造

```
TextffCut/
├── videos/      # 動画ファイルを配置
├── output/      # 出力ファイルが保存される
├── logs/        # ログファイル
└── .env         # 環境設定（API設定など）
```

## 🎬 使い方

### 動画ファイルの配置
1. `videos/` フォルダに処理したい動画を配置
2. アプリ内のドロップダウンから選択

### API設定（オプション）
`.env` ファイルを編集：
```bash
TEXTFFCUT_USE_API=true
TEXTFFCUT_API_KEY=sk-your-openai-api-key
```

## 🛠️ Docker管理コマンド

### 基本操作
```bash
# 起動
./docker-run.sh start

# 停止
./docker-run.sh stop

# 再起動
./docker-run.sh restart

# ログ確認
./docker-run.sh logs

# 状態確認
./docker-run.sh status
```

### 高度な操作
```bash
# コンテナ内でシェルを起動
./docker-run.sh shell

# 完全クリーンアップ
./docker-run.sh clean
```

## 🔧 カスタマイズ

### ポート変更
`.env` ファイルで設定：
```bash
TEXTFFCUT_PORT=8502
```

### メモリ制限の調整
`docker-compose.yml` を編集：
```yaml
deploy:
  resources:
    limits:
      memory: 16G  # 必要に応じて増減
```

### ホームディレクトリアクセス
`docker-compose.yml` のコメントを解除：
```yaml
volumes:
  - ${HOME}:/host/home:ro
```

## 🚨 トラブルシューティング

### コンテナが起動しない
```bash
# Docker Desktopが起動しているか確認
docker --version

# ログを確認
./docker-run.sh logs
```

### メモリ不足エラー
Docker Desktop > Preferences > Resources でメモリを増やす

### ファイルアクセスエラー
```bash
# 権限を修正
chmod -R 755 videos output logs
```

## 🐳 Docker Compose 直接操作

ヘルパースクリプトを使わない場合：

```bash
# ビルドして起動
docker compose up -d --build

# 停止
docker compose down

# ログ確認（リアルタイム）
docker compose logs -f

# 再ビルド
docker compose build --no-cache
```

## 📊 パフォーマンス最適化

### ビルドキャッシュの活用
```bash
# キャッシュを使って高速ビルド
docker compose build --cache-from textffcut:latest
```

### ボリュームの最適化
大量の動画を処理する場合は、専用ボリュームの使用を推奨：
```yaml
volumes:
  - textffcut_videos:/app/videos
  - textffcut_output:/app/output
```

## 🔒 セキュリティ

- 非rootユーザーで実行
- 読み取り専用の設定ファイルマウント
- ネットワークの分離
- リソース制限の設定

## 🆘 サポート

問題が解決しない場合は、以下の情報を添えてIssueを作成してください：

1. `docker --version` の出力
2. `./docker-run.sh logs` の出力
3. エラーメッセージのスクリーンショット