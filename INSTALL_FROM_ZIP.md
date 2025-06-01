# TextffCut インストールガイド（ZIP版）

## 📦 パッケージ内容

ZIPファイルには以下が含まれています：
- ソースコード（Python）
- Docker設定ファイル
- ドキュメント
- 起動スクリプト

## 🚀 インストール方法

### 方法1: Docker版（推奨）

#### 前提条件
- Docker Desktop がインストールされていること

#### 手順
```bash
# 1. ZIPファイルを解凍
unzip TextffCut-v*.zip
cd TextffCut-v*

# 2. Docker版を起動
./scripts/docker-run.sh start

# 3. ブラウザで開く
# http://localhost:8501
```

初回起動時は、Dockerイメージのビルドに5-10分かかります。

### 方法2: ローカル版

#### 前提条件
- Python 3.9以上
- FFmpeg
- Git

#### 手順
```bash
# 1. ZIPファイルを解凍
unzip TextffCut-v*.zip
cd TextffCut-v*

# 2. 自動インストール
./scripts/install.sh

# 3. 起動
./scripts/start.sh
```

## 📁 使い方

1. `videos/` フォルダに動画を配置
2. ブラウザでアプリケーションを開く
3. 動画を選択して処理開始

## ⚖️ ライセンス

本ソフトウェアは購入者限定のライセンスです。
- ✅ 個人利用OK
- ❌ 商用利用不可
- ❌ 再配布禁止

詳細は `LICENSE` ファイルをご確認ください。

## 🆘 サポート

- 購入時に提供されたサポートメールアドレスまでご連絡ください
- GitHubアカウントをお持ちの方は、Issueでの報告も可能です

## 🔄 アップデート

新しいバージョンがリリースされた場合：
1. 購入時のダウンロードリンクから最新版を取得
2. 既存のフォルダに上書き（videosフォルダは除く）
3. Dockerイメージを再ビルド

---
TextffCut Team