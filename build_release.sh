#!/bin/bash

# TextffCut Docker版 リリースビルドスクリプト
# 使い方: ./build_release.sh [バージョン番号]
# バージョン番号を指定しない場合は、Gitタグから自動取得

set -e  # エラーが発生したら即座に終了

# スクリプトのディレクトリを基準に移動
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# バージョン番号の取得
if [ -n "$1" ]; then
    # 引数にvが付いている場合は削除
    VERSION=${1#v}
else
    # Gitから最新のタグを取得（タグがない場合は0.9.0をデフォルト）
    VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.9.0")
    # v接頭辞を削除
    VERSION=${VERSION#v}
fi

echo "=========================================="
echo "TextffCut リリースビルド"
echo "バージョン: v${VERSION}"
echo "=========================================="
echo ""

# VERSION.txtファイルを更新
echo "v${VERSION}" > VERSION.txt
echo "✅ VERSION.txt を更新しました"
echo ""

# 既存のリリースファイルをクリーンアップ
echo "既存のリリースファイルをクリーンアップしています..."
rm -f release/textffcut_v${VERSION}_docker_distribution.zip
rm -f release/textffcut_v${VERSION}_docker.tar.gz
echo "✅ クリーンアップ完了"
echo ""

# 1. Docker イメージのビルド
echo "1. Docker イメージをビルドしています..."
docker build -t textffcut:${VERSION} .
echo "✅ Docker イメージのビルド完了"
echo ""

# 2. releaseディレクトリの準備
echo "2. releaseディレクトリを準備しています..."
mkdir -p release
echo "✅ releaseディレクトリ準備完了"
echo ""

# 3. Docker イメージの保存
echo "3. Docker イメージを保存しています..."
docker save textffcut:${VERSION} | gzip > release/textffcut_v${VERSION}_docker.tar.gz
echo "✅ Docker イメージの保存完了"
echo ""

# 4. 配布用ファイルの作成
echo "4. 配布用ファイルを作成しています..."

# START.bat の作成
cat > release/START.bat <<EOF
@echo off
echo TextffCut v${VERSION} を起動します...
echo.

REM 環境変数を設定
set HOST_VIDEOS_PATH=%cd%\videos

REM Docker Desktopが起動しているか確認
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    pause
    exit /b 1
)

REM ポート8501を使用しているコンテナをチェック
docker ps --format "table {{.Names}}	{{.Ports}}" | findstr "8501" >nul 2>&1
if %errorlevel% equ 0 (
    echo 警告: ポート8501が既に使用されています。
    echo 既存のコンテナ:
    docker ps --format "table {{.Names}}	{{.Ports}}" | findstr "8501"
    echo.
    set /p REPLY=既存のコンテナを停止してから起動しますか？ (y/n): 
    if /i "%REPLY%"=="y" (
        REM ポート8501を使用しているコンテナを停止
        for /f "tokens=1" %%i in ('docker ps --format "{{.Names}}"') do (
            docker port %%i | findstr "8501" >nul 2>&1
            if %errorlevel% equ 0 (
                echo 停止中: %%i
                docker stop %%i
            )
        )
    ) else (
        echo 起動をキャンセルしました。
        pause
        exit /b 0
    )
)

REM videosフォルダがなければ作成
if not exist videos (
    echo videosフォルダを作成しています...
    mkdir videos
)

REM 既存のTextffCutコンテナを停止・削除
docker ps -a --format "{{.Names}}" | findstr "^TextffCut$" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存のTextffCutコンテナを停止・削除しています...
    docker stop TextffCut 2>nul
    docker rm TextffCut 2>nul
)

REM 古いバージョンのイメージを削除
echo 古いバージョンのイメージをクリーンアップしています...

REM まず古いバージョンのコンテナを全て削除
echo 古いバージョンのコンテナを削除しています...
for /f "tokens=1,2" %%a in ('docker ps -a --format "{{.Names}} {{.Image}}" ^| findstr "textffcut:" ^| findstr /v ":${VERSION}"') do (
    echo コンテナ削除中: %%a (%%b)
    docker rm -f %%a 2>nul
)

REM 古いバージョンのイメージを削除（強制削除）
set OLD_IMAGES_FOUND=0
for /f "tokens=*" %%a in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr "^textffcut:" ^| findstr /v ":${VERSION}$"') do (
    set OLD_IMAGES_FOUND=1
    echo 削除中: %%a
    docker rmi -f %%a 2>nul
)
if %OLD_IMAGES_FOUND% equ 0 (
    echo 削除する古いイメージはありません。
)

REM イメージをロード（まだロードされていない場合）
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% neq 0 (
    echo Dockerイメージをロードしています（初回のみ）...
    docker load -i textffcut_v${VERSION}_docker.tar.gz
)

echo アプリケーションを起動しています...
echo.
echo ブラウザで http://localhost:8501 を開いています...
start http://localhost:8501

docker-compose -f ./docker-compose-simple.yml up

pause
EOF

# START.command の作成
cat > release/START.command <<EOF
#!/bin/bash

echo "TextffCut v${VERSION} を起動します..."
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "\$SCRIPT_DIR"

# デバッグ情報（後で削除予定）
# echo "スクリプトディレクトリ: \$SCRIPT_DIR"
# echo "現在のディレクトリ: \$(pwd)"

# 環境変数を設定
export HOST_VIDEOS_PATH="\${SCRIPT_DIR}/videos"

# Docker Desktopが起動しているか確認
if ! docker version &>/dev/null; then
    echo "エラー: Docker Desktopが起動していません。"
    echo "Docker Desktopを起動してから、もう一度実行してください。"
    read -p "Enterキーを押して終了..."
    exit 1
fi

# 既存のTextffCutコンテナをチェックして停止
EXISTING_CONTAINER=$(docker ps -a --format "{{.Names}}" | grep -E "^TextffCut$" || true)
if [ -n "$EXISTING_CONTAINER" ]; then
    echo "既存のTextffCutコンテナを停止・削除しています..."
    docker stop "$EXISTING_CONTAINER" 2>/dev/null || true
    docker rm "$EXISTING_CONTAINER" 2>/dev/null || true
fi

# ポート8501を使用しているプロセスをチェック
PORT=8501
if lsof -ti:$PORT > /dev/null 2>&1; then
    echo "警告: ポート$PORTが既に使用されています。"
    
    # Dockerコンテナが使用しているかチェック
    CONTAINER_USING_PORT=$(docker ps --format "{{.Names}}" | while read container; do
        if docker port "$container" 2>/dev/null | grep -q "$PORT"; then
            echo "$container"
            break
        fi
    done)
    
    if [ -n "$CONTAINER_USING_PORT" ]; then
        # TextffCutのコンテナかチェック
        if [[ "$CONTAINER_USING_PORT" == textffcut* ]]; then
            echo "既存のTextffCutコンテナ($CONTAINER_USING_PORT)が起動しています。"
            echo "自動的に停止して新しいコンテナを起動します..."
            docker stop "$CONTAINER_USING_PORT"
            docker rm "$CONTAINER_USING_PORT" 2>/dev/null
        else
            echo "別のDockerコンテナ($CONTAINER_USING_PORT)がポート$PORTを使用しています。"
            # 別のポートを探す
            for ALT_PORT in 8502 8503 8504 8505; do
                if ! lsof -ti:$ALT_PORT > /dev/null 2>&1; then
                    PORT=$ALT_PORT
                    echo "代替ポート$PORTを使用します。"
                    export TEXTFFCUT_PORT=$PORT
                    break
                fi
            done
        fi
    else
        echo "Docker以外のプロセスがポート$PORTを使用しています。"
        # 別のポートを探す
        for ALT_PORT in 8502 8503 8504 8505; do
            if ! lsof -ti:$ALT_PORT > /dev/null 2>&1; then
                PORT=$ALT_PORT
                echo "代替ポート$PORTを使用します。"
                export TEXTFFCUT_PORT=$PORT
                break
            fi
        done
    fi
fi

# videosフォルダがなければ作成
if [ ! -d "videos" ]; then
    echo "videosフォルダを作成しています..."
    mkdir -p videos
fi

# 既存のTextffCutコンテナをチェックして停止
EXISTING_CONTAINER=\$(docker ps -a --format "{{.Names}}" | grep -E "^TextffCut\$" || true)
if [ -n "\$EXISTING_CONTAINER" ]; then
    echo "既存のTextffCutコンテナを停止・削除しています..."
    docker stop "\$EXISTING_CONTAINER" 2>/dev/null || true
    docker rm "\$EXISTING_CONTAINER" 2>/dev/null || true
fi

# 古いバージョンのイメージを削除
echo "古いバージョンのイメージをクリーンアップしています..."

# まず古いバージョンのコンテナを全て削除
echo "古いバージョンのコンテナを削除しています..."
docker ps -a --format "{{.Names}} {{.Image}}" | grep "textffcut:" | grep -v ":${VERSION}" | while read name image; do
    if [ -n "\$name" ]; then
        echo "コンテナ削除中: \$name (\$image)"
        docker rm -f "\$name" 2>/dev/null || true
    fi
done

# 古いバージョンのイメージを削除（強制削除）
OLD_IMAGES=\$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^textffcut:" | grep -v ":${VERSION}\$" || true)
if [ -n "\$OLD_IMAGES" ]; then
    echo "\$OLD_IMAGES" | while read image; do
        if [ -n "\$image" ]; then
            echo "削除中: \$image"
            docker rmi -f "\$image" 2>/dev/null || true
        fi
    done
else
    echo "削除する古いイメージはありません。"
fi

# イメージをロード（まだロードされていない場合）
if ! docker images | grep -q "textffcut.*${VERSION}"; then
    echo "Dockerイメージをロードしています（初回のみ）..."
    docker load -i textffcut_v${VERSION}_docker.tar.gz
fi

echo "アプリケーションを起動しています..."
if [ -n "$TEXTFFCUT_PORT" ]; then
    echo "URL: http://localhost:$TEXTFFCUT_PORT"
    echo ""
    echo "ブラウザで http://localhost:$TEXTFFCUT_PORT を開いています..."
    open "http://localhost:$TEXTFFCUT_PORT"
    # docker-compose.ymlを一時的に作成（ポート変更対応）
    sed "s/8501:8501/$TEXTFFCUT_PORT:8501/g" ./docker-compose-simple.yml > ./docker-compose-temp.yml
    docker-compose -f ./docker-compose-temp.yml up
    rm -f ./docker-compose-temp.yml
else
    echo "URL: http://localhost:8501"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    docker-compose -f ./docker-compose-simple.yml up
fi

read -p "Enterキーを押して終了..."
EOF

# docker-compose-simple.yml の作成
cat > release/docker-compose-simple.yml <<EOF
version: '3.8'

services:
  textffcut:
    image: textffcut:${VERSION}
    container_name: TextffCut
    restart: unless-stopped
    ports:
      - "8501:8501"
    volumes:
      - ./videos:/app/videos
    environment:
      - TZ=Asia/Tokyo
      - HOST_VIDEOS_PATH=\${HOST_VIDEOS_PATH}
EOF

# README_Docker.md の作成
cat > release/README_Docker.md <<'EOF'
# TextffCut セットアップガイド

📖 **詳しい使い方はこちら**: [TextffCut 完全ガイド（note）](https://note.com/YOUR_NOTE_URL)
- スクリーンショット付きの詳細な説明
- 動画での操作説明
- よくある質問と解決方法

## 必要なシステム要件

- **検証済み環境**: macOS 10.15以降
- **未検証**: Windows 10/11（Dockerの仕組み上動作するはずですが、検証していません）
- Docker Desktop がインストールされていること
- 8GB以上のメモリ（推奨: 16GB以上）
- 10GB以上の空きディスク容量

## セットアップ手順

### 1. Docker Desktop のインストール

まだインストールしていない場合は、以下からダウンロードしてインストールしてください：

- **Windows**: [Docker Desktop for Windows](https://docs.docker.com/desktop/install/windows-install/)
- **macOS**: [Docker Desktop for Mac](https://docs.docker.com/desktop/install/mac-install/)

### 2. Docker Desktop の起動

インストール後、Docker Desktop を起動してください。
タスクバー（Windows）またはメニューバー（macOS）にDockerアイコンが表示されます。

### 3. TextffCut の起動

#### Windows の場合
1. `START.bat` をダブルクリックします
2. 初回起動時は Docker イメージの読み込みに数分かかります
3. ブラウザが自動的に開き、`http://localhost:8501` でアプリケーションが表示されます

#### macOS の場合
1. `START.command` をダブルクリックします
   - 初回実行時に「開発元が未確認」の警告が出る場合は、Finderで右クリック→「開く」を選択
2. 初回起動時は Docker イメージの読み込みに数分かかります
3. ブラウザが自動的に開き、`http://localhost:8501` でアプリケーションが表示されます

## 使い方

1. **動画ファイルの配置**
   - 同じフォルダ内の `videos` フォルダに動画ファイルを配置します
   - **検証済み形式**: MP4
   - **未検証形式**: MOV, AVI, MKV（FFmpegが対応しているため動作するはずです）

2. **アプリケーションの利用**
   - ブラウザで `http://localhost:8501` にアクセス
   - 動画を選択して文字起こし・編集を行います

3. **出力ファイル**
   - 処理結果は `videos` フォルダ内に保存されます

## トラブルシューティング

### アプリケーションが起動しない
- Docker Desktop が起動していることを確認してください
- ポート 8501 が他のアプリケーションで使用されていないか確認してください

### メモリ不足エラー
- Docker Desktop の設定でメモリ割り当てを増やしてください
  - Docker Desktop → Settings → Resources → Memory

### 動画が表示されない
- 動画ファイルが `videos` フォルダに配置されているか確認してください
- ファイル名に日本語が含まれている場合、英数字に変更してみてください

## アプリケーションの停止

### 推奨される停止方法（簡単）
1. **ターミナル/コマンドプロンプトで `Ctrl+C` を押す**
   - これが最も簡単で確実な方法です
   - ターミナルに戻って `Ctrl+C` を押すだけで停止します

### その他の停止方法
2. **ターミナル/コマンドプロンプトウィンドウを閉じる**
   - ウィンドウを閉じても停止します
   - ただし、Dockerコンテナが残る場合があります

3. **Docker Desktop から停止**
   - Docker Desktop を開く
   - 「Containers」タブで `TextffCut` を探す
   - 停止ボタン（■）をクリック

### 💡 便利な使い方のヒント
- ブラウザタブは閉じても問題ありません（アプリは動作し続けます）
- 再度アクセスしたい場合は http://localhost:8501 を開いてください
- 作業が終わったら、必ずターミナルで `Ctrl+C` を押して停止してください

## サポート

問題が解決しない場合は、エラーメッセージと共にお問い合わせください。
EOF

# 実行権限を付与
chmod +x release/START.command

echo "✅ 配布用ファイルの作成完了"
echo ""

# 5. ZIPファイルの作成（フォルダ名はTextffCut）
echo "5. ZIPファイルを作成しています..."
cd release

# TextffCutフォルダを作成してファイルを配置
mkdir -p TextffCut
mv textffcut_v${VERSION}_docker.tar.gz TextffCut/
mv START.bat TextffCut/
mv START.command TextffCut/
mv docker-compose-simple.yml TextffCut/
mv README_Docker.md TextffCut/

# ZIPファイルを作成
zip -r textffcut_v${VERSION}_docker_distribution.zip TextffCut

# 一時フォルダを削除（ZIPファイルのみ残す）
rm -rf TextffCut

echo "✅ ZIPファイルの作成完了"
echo ""

# 6. ファイルサイズの確認
echo "=========================================="
echo "ビルド完了！"
echo "=========================================="
echo ""
echo "生成されたファイル:"
ls -lh textffcut_v${VERSION}_docker_distribution.zip
echo ""
echo "配布用ファイル: release/textffcut_v${VERSION}_docker_distribution.zip"
echo ""