# TextffCutの手動起動ガイド

自動起動スクリプトが失敗した場合に、手動でTextffCutを起動する方法を説明します。

## 📋 目次
1. [起動スクリプトが行っていること](#起動スクリプトが行っていること)
2. [手動での起動方法](#手動での起動方法)
3. [プラットフォーム別の操作](#プラットフォーム別の操作)
4. [よくあるエラーと対処法](#よくあるエラーと対処法)

## 起動スクリプトが行っていること

起動スクリプトは以下の処理を自動で行っています：

### 1. **Dockerの起動確認**
- Docker Desktop（Windows/Mac）またはDocker Engine（Linux）が起動しているかチェック
- 起動していない場合はエラーメッセージを表示

### 2. **使用可能なポートの検索**
- ポート8501が使用中かどうかを確認
- 使用中の場合は8502〜8510の範囲で空いているポートを探す
- 空いているポートが見つかったら、そのポートを使用

### 3. **必要なフォルダの作成**
- `videos`フォルダ（動画ファイル用）
- `logs`フォルダ（ログファイル用）
- `prompts`フォルダ（プロンプトファイル用）

### 4. **Dockerコンテナの起動**
- Dockerイメージのビルド
- コンテナの起動
- ブラウザでアクセスできるURLの表示

## 手動での起動方法

### 基本的な手順

1. **ターミナル/コマンドプロンプトを開く**
2. **TextffCutフォルダに移動**
3. **必要なフォルダを作成**
4. **Dockerコンテナを起動**

### 詳細な手順

#### 1. Dockerの起動確認

**Mac/Windows:**
```bash
docker --version
```

**Linux:**
```bash
sudo docker --version
```

エラーが出る場合は、Docker Desktop（Mac/Windows）またはDocker Engine（Linux）を起動してください。

#### 2. TextffCutフォルダに移動

**Mac/Linux:**
```bash
cd ~/Downloads/TextffCut
```

**Windows:**
```cmd
cd C:\Users\あなたのユーザー名\Downloads\TextffCut
```

（実際のパスに置き換えてください）

#### 3. 使用中のポートを確認

**Mac/Linux:**
```bash
lsof -i :8501
```

**Windows:**
```cmd
netstat -an | findstr :8501
```

何か表示される場合は、ポート8501が使用中です。

#### 4. 必要なフォルダの作成

**Mac/Linux:**
```bash
mkdir -p videos logs prompts
```

**Windows:**
```cmd
mkdir videos 2>nul
mkdir logs 2>nul
mkdir prompts 2>nul
```

#### 5. Dockerコンテナを起動

**通常の起動:**
```bash
docker compose up --build
```

**古いバージョンのDocker Composeの場合:**
```bash
docker-compose up --build
```

#### 6. ブラウザでアクセス
- http://localhost:8501 を開く
- もし「接続できません」と表示される場合は、少し待ってから再度アクセス

## プラットフォーム別の操作

### Mac環境での追加情報

#### Docker Desktop GUIからの起動
1. アプリケーションフォルダから「Docker」を起動
2. メニューバーのDockerアイコンが「Docker Desktop is running」と表示されるまで待つ
3. ターミナルを開いて上記の手順を実行

#### ポートを手動で変更する場合
1. テキストエディタで`docker-compose.yml`を開く
   ```bash
   open -e docker-compose.yml
   ```
2. ポート設定を変更（例：8502を使用）
   ```yaml
   ports:
     - "8502:8501"  # 左側の数字だけ変更
   ```
3. 保存して起動

### Windows環境での追加情報

#### Docker Desktop GUIからの起動
1. スタートメニューから「Docker Desktop」を起動
2. タスクバーのDockerアイコンが白くなるまで待つ
3. コマンドプロンプトまたはPowerShellで上記の手順を実行

#### メモ帳でポートを変更する場合
1. `docker-compose.yml`を右クリック→「プログラムから開く」→「メモ帳」
2. ポート設定を変更して保存

### Linux環境での追加情報

#### Dockerサービスの確認
```bash
sudo systemctl status docker
```

起動していない場合：
```bash
sudo systemctl start docker
```

#### 権限エラーの場合
```bash
sudo docker compose up --build
```

## よくあるエラーと対処法

### エラー1: 「docker: command not found」または「'docker' は認識されていません」
**原因**: Dockerがインストールされていない、またはPATHに追加されていない

**対処法**:
- **Mac**: Docker Desktopをインストール
- **Windows**: Docker Desktopをインストール後、PCを再起動
- **Linux**: Docker Engineをインストール

### エラー2: 「bind: address already in use」
**原因**: ポートが既に使用されている

**対処法**:

方法1: 別のポートを使用
```bash
# docker-compose.override.ymlを作成
cat > docker-compose.override.yml << EOF
services:
  textffcut:
    ports:
      - "8502:8501"
EOF

# 起動
docker compose up --build
```

方法2: 使用中のプロセスを確認して終了
- **Mac/Linux**: `lsof -i :8501` でプロセスを確認
- **Windows**: タスクマネージャーで該当プロセスを終了

### エラー3: 「Cannot connect to the Docker daemon」
**原因**: Dockerが起動していない

**対処法**:
- **Mac/Windows**: Docker Desktopを起動
- **Linux**: `sudo systemctl start docker`

### エラー4: ファイアウォールの問題
**症状**: コンテナは起動したが、ブラウザでアクセスできない

**対処法**:
1. `http://127.0.0.1:8501` でアクセスしてみる
2. ファイアウォール設定を確認
3. セキュリティソフトの設定を確認

## 🔍 高度なトラブルシューティング

### ログの確認
```bash
# コンテナのログを表示
docker compose logs

# リアルタイムでログを表示
docker compose logs -f
```

### コンテナの状態確認
```bash
# 実行中のコンテナを表示
docker ps

# すべてのコンテナを表示（停止中も含む）
docker ps -a
```

### クリーンな再起動
```bash
# すべてを停止・削除して再起動
docker compose down
docker compose up --build --force-recreate
```

### ポートの解放（強制）
**Mac/Linux:**
```bash
# プロセスIDを確認
lsof -ti:8501
# プロセスを終了（PIDを置き換えて実行）
kill -9 <PID>
```

**Windows (管理者権限で実行):**
```cmd
# プロセスIDを確認
netstat -aon | findstr :8501
# プロセスを終了（PIDを置き換えて実行）
taskkill /F /PID <PID>
```

## 📞 サポート

上記の方法で解決しない場合は、以下の情報を添えてサポートにお問い合わせください：
- OS情報（例：macOS 14.2、Windows 11 23H2、Ubuntu 22.04）
- Dockerのバージョン（`docker --version`の結果）
- 表示されたエラーメッセージの全文
- 実行したコマンドと結果