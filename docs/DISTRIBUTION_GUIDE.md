# TextffCut 配布ガイド

## 配布方法の比較

### 方法1: ソースコード配布（現在）
**メリット:**
- 配布ファイルが軽量（100KB）
- ライセンス管理が簡単

**デメリット:**
- 購入者のビルド環境により動作が異なる可能性
- 初回セットアップに時間がかかる

### 方法2: Docker Hub経由（推奨）
**メリット:**
- 完全に同一の環境を保証
- セットアップが簡単・高速
- プロフェッショナルな印象

**デメリット:**
- Docker Hubの有料プラン必要（プライベートイメージ）
- イメージサイズが大きい（3-4GB）

## Docker Hub配布の実装方法

### 1. プライベートリポジトリ作成
```bash
# Docker Hub でプライベートリポジトリを作成
# https://hub.docker.com/
# 料金: $7/月（5プライベートリポジトリ）
```

### 2. イメージのビルドとプッシュ
```bash
# タグ付けしてビルド
docker build -t textffcut/textffcut:v1.1.0 .
docker tag textffcut/textffcut:v1.1.0 textffcut/textffcut:latest

# Docker Hub にログイン
docker login

# プッシュ
docker push textffcut/textffcut:v1.1.0
docker push textffcut/textffcut:latest
```

### 3. 購入者への配布
```bash
# 購入者用の認証情報を提供
docker login -u [購入者用アカウント] -p [パスワード]

# イメージの取得
docker pull textffcut/textffcut:latest

# 実行
docker run -p 8501:8501 textffcut/textffcut:latest
```

## セキュリティ対策

### 1. アクセストークン管理
- 購入者ごとに個別のアクセストークン発行
- 有効期限の設定
- 定期的なトークンローテーション

### 2. イメージ内への情報埋め込み
```dockerfile
# ビルド時に購入者情報を埋め込む
ARG CUSTOMER_ID
ENV CUSTOMER_ID=${CUSTOMER_ID}
```

### 3. 利用状況の監視
- Docker Hub のダウンロード履歴確認
- 異常なアクセスパターンの検知

## ハイブリッド方式（バランス型）

### 初期配布
1. ソースコード（ZIP）配布
2. 公式ビルド済みイメージのSHA256ハッシュ提供
3. セルフビルドとの比較推奨

### docker-compose.yml の工夫
```yaml
services:
  app:
    # 公式イメージを優先的に使用
    image: textffcut/textffcut:v1.1.0
    # ローカルビルドはフォールバック
    build:
      context: .
      dockerfile: Dockerfile
```

## 推奨される配布フロー

1. **評価版**: ソースコード配布（機能制限付き）
2. **正規版**: Docker Hub 経由（フルサポート）
3. **エンタープライズ**: カスタムビルド + SLA

## まとめ

最も安全で確実な方法：
- **Docker Hub のプライベートリポジトリ**
- 月額$7のコストで、完全な環境統一を実現
- 購入者体験も向上（簡単・高速）