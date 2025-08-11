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
echo "TextffCut リリースビルド（メモリ最適化）"
echo "バージョン: v${VERSION}"
echo "=========================================="
echo ""

# VERSION.txtファイルを更新
echo "v${VERSION}" > VERSION.txt
echo "✅ VERSION.txt を更新しました"
echo ""

# 既存のリリースファイルをクリーンアップ
echo "既存のリリースファイルをクリーンアップしています..."
rm -f release/TextffCut_v${VERSION}.zip
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

# START.bat の作成（v7ベースのシンプル版）
cat > release/START.bat <<EOF
@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo Starting TextffCut v${VERSION}...
echo.

echo Checking Docker...
docker version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Docker Desktop not running
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)
echo Docker OK
echo.

echo Checking Docker Compose v2...
docker compose version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Docker Compose v2 not found. Checking v1...
    docker-compose version >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Docker Compose not found
        echo Please install Docker Desktop with Docker Compose
        pause
        exit /b 1
    )
    set COMPOSE_CMD=docker-compose
) else (
    echo Docker Compose v2 OK
    set COMPOSE_CMD=docker compose
)
echo.

echo Creating folders...
for %%f in (videos logs models prompts) do (
    if not exist %%f (
        mkdir %%f
        echo Created %%f folder
    )
)
echo.

echo Loading Docker image...
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Loading image (first time only)...
    docker load -i textffcut_v${VERSION}_docker.tar.gz
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to load Docker image
        echo Please check if textffcut_v${VERSION}_docker.tar.gz exists
        pause
        exit /b 1
    )
) else (
    echo Image already loaded
)
echo.

REM メモリ設定は削除（Docker Desktopに任せる）

REM ポート自動検出
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510

:find_port
netstat -an | findstr ":!PORT! " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    REM ポートが使用中
    set /a PORT=PORT+1
    if !PORT! gtr !MAX_PORT! (
        echo [ERROR] No available port found.
        pause
        exit /b 1
    )
    goto find_port
) else (
    REM ポートが空いている
)

if !PORT! neq !BASE_PORT! (
    echo [WARNING] Port !BASE_PORT! is in use, using port !PORT!
    
    REM docker-compose.override.ymlを作成（ポート設定のみ）
    (
        echo version: '3.8'
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
) else (
    REM ポートは変更不要なのでoverride.ymlは作成しない
)

echo Starting TextffCut...
echo URL: http://localhost:!PORT!
echo Videos folder: "%cd%\videos"
echo.

if not exist docker-compose-simple.yml (
    echo [ERROR] docker-compose-simple.yml not found
    echo Please make sure all files are extracted properly
    pause
    exit /b 1
)

echo Opening browser...
start http://localhost:!PORT!

if exist docker-compose.override.yml (
    %COMPOSE_CMD% -f docker-compose-simple.yml -f docker-compose.override.yml up
    del docker-compose.override.yml
) else (
    %COMPOSE_CMD% -f docker-compose-simple.yml up
)

pause
EOF

# 改行コードをCRLFに変換（Windows用）
if command -v unix2dos >/dev/null 2>&1; then
    unix2dos release/START.bat >/dev/null 2>&1
fi

# START_CLEAN.bat の作成（v7ベースのクリーン起動版）
cat > release/START_CLEAN.bat <<EOF
@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
echo TextffCut v${VERSION} Clean Start
echo.

echo Cleaning up existing containers and images...
echo.

REM Stop and remove TextffCut containers
echo Stopping containers...
for /f "tokens=*" %%i in ('docker ps -a --format "{{.Names}}" ^| findstr /i textffcut') do (
    echo - Stopping %%i
    docker stop %%i >nul 2>&1
    docker rm %%i >nul 2>&1
)

REM Check for Docker Compose v2
docker compose version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    docker-compose version >nul 2>&1
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Docker Compose not found
        echo Please install Docker Desktop with Docker Compose
        pause
        exit /b 1
    )
    set COMPOSE_CMD=docker-compose
) else (
    set COMPOSE_CMD=docker compose
)

REM Clean up with docker-compose
if exist docker-compose-simple.yml (
    %COMPOSE_CMD% -f docker-compose-simple.yml down >nul 2>&1
)

REM Remove all textffcut images
echo.
echo Removing all images...
for /f "tokens=*" %%i in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr /i textffcut') do (
    echo - Removing %%i
    docker rmi %%i >nul 2>&1
)

REM Remove volumes
echo.
echo Removing volumes...
for /f "tokens=*" %%i in ('docker volume ls --format "{{.Name}}" ^| findstr /i textffcut') do (
    echo - Removing %%i
    docker volume rm %%i >nul 2>&1
)

echo.
echo Cleanup complete!
echo.

REM Check Docker
echo Checking Docker...
docker version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Docker Desktop not running
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)
echo Docker OK
echo.

REM Create folders
echo Creating folders...
for %%f in (videos logs models prompts) do (
    if not exist %%f (
        mkdir %%f
        echo Created %%f folder
    )
)
echo.

REM Load fresh image
echo Loading Docker image...
if not exist textffcut_v${VERSION}_docker.tar.gz (
    echo [ERROR] Docker image file not found: textffcut_v${VERSION}_docker.tar.gz
    echo Please make sure the file exists in the current directory
    pause
    exit /b 1
)
docker load -i textffcut_v${VERSION}_docker.tar.gz
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to load Docker image
    pause
    exit /b 1
)
echo.

REM メモリ設定は削除（Docker Desktopに任せる）

REM ポート自動検出
set BASE_PORT=8501
set PORT=!BASE_PORT!
set MAX_PORT=8510

:find_port_clean
netstat -an | findstr ":!PORT! " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    REM ポートが使用中
    set /a PORT=PORT+1
    if !PORT! gtr !MAX_PORT! (
        echo [ERROR] No available port found.
        pause
        exit /b 1
    )
    goto find_port_clean
) else (
    REM ポートが空いている
)

if !PORT! neq !BASE_PORT! (
    echo [WARNING] Port !BASE_PORT! is in use, using port !PORT!
    
    REM docker-compose.override.ymlを作成（ポート設定のみ）
    (
        echo version: '3.8'
        echo services:
        echo   textffcut:
        echo     ports:
        echo       - "!PORT!:8501"
    ) > docker-compose.override.yml
) else (
    REM ポートは変更不要なのでoverride.ymlは作成しない
)

echo Starting TextffCut...
echo URL: http://localhost:!PORT!
echo Videos folder: "%cd%\videos"
echo.

if not exist docker-compose-simple.yml (
    echo [ERROR] docker-compose-simple.yml not found
    echo Please make sure all files are extracted properly
    pause
    exit /b 1
)

echo Opening browser...
start http://localhost:!PORT!

if exist docker-compose.override.yml (
    %COMPOSE_CMD% -f docker-compose-simple.yml -f docker-compose.override.yml up
    del docker-compose.override.yml
) else (
    %COMPOSE_CMD% -f docker-compose-simple.yml up
)

pause
EOF

# 改行コードをCRLFに変換（Windows用）
if command -v unix2dos >/dev/null 2>&1; then
    unix2dos release/START_CLEAN.bat >/dev/null 2>&1
fi

# START.command の作成（通常起動 - 高速版）
cat > release/START.command <<'EOF'
#!/bin/bash

echo "TextffCut v${VERSION} を起動します..."
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# 環境変数を設定
export HOST_VIDEOS_PATH="${SCRIPT_DIR}/videos"

# Docker Desktopが適切にメモリ管理を行うため、追加の設定は不要

# ===========================================
# Docker Desktop確認
# ===========================================
if ! docker version &>/dev/null; then
    echo "エラー: Docker Desktopが起動していません。"
    echo "Docker Desktopを起動してから、もう一度実行してください。"
    
    # Docker Desktopのメモリ設定アドバイス
    echo ""
    echo "💡 Docker Desktopのメモリ設定を確認してください："
    echo "   1. Docker Desktop → Settings → Resources"
    echo "   2. Memory の設定を確認"
    echo ""
    
    read -p "Enterキーを押して終了..."
    exit 1
fi

# 既存のTextffCutコンテナをチェック
RUNNING_CONTAINER=$(docker ps --format "{{.Names}}" | grep -E "^TextffCut$" || true)
if [ -n "$RUNNING_CONTAINER" ]; then
    echo "既存のTextffCutコンテナが起動中です。"
    echo ""
    echo "=== 起動設定 ==="
    echo "📍 URL: http://localhost:8501"
    echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    echo ""
    echo "既に起動しているため、そのまま使用します。"
    echo "終了するには Ctrl+C を押してください。"
    read -p "Enterキーを押して終了..."
    exit 0
fi

# 停止したコンテナがあるかチェック
STOPPED_CONTAINER=$(docker ps -a --format "{{.Names}}" | grep -E "^TextffCut$" || true)
if [ -n "$STOPPED_CONTAINER" ]; then
    echo "停止中のTextffCutコンテナを再起動しています..."
    docker start TextffCut
    echo ""
    echo "=== 起動設定 ==="
    echo "📍 URL: http://localhost:8501"
    echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    
    # ログを表示
    docker logs -f TextffCut
    read -p "Enterキーを押して終了..."
    exit 0
fi

# ポート自動検出機能
find_available_port() {
    local base_port=$1
    local port=$base_port
    local max_attempts=10
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if ! lsof -ti:$port > /dev/null 2>&1; then
            echo $port
            return 0
        fi
        port=$((port + 1))
        attempt=$((attempt + 1))
    done
    
    return 1
}

# 使用するポートを決定
PORT=$(find_available_port 8501)

if [ -z "$PORT" ]; then
    echo "❌ エラー: 利用可能なポートが見つかりませんでした。"
    echo "   他のアプリケーションを終了してから再度お試しください。"
    read -p "Enterキーを押して終了..."
    exit 1
fi

if [ "$PORT" != "8501" ]; then
    echo "⚠️  ポート8501が使用中のため、ポート$PORTを使用します。"
fi

# docker-compose.override.ymlを生成（ポート設定のみ）
if [ "$PORT" != "8501" ]; then
    # ポート変更が必要な場合のみ作成
    cat > docker-compose.override.yml <<OVERRIDE_EOF
version: '3.8'
services:
  textffcut:
    ports:
      - "$PORT:8501"
OVERRIDE_EOF
fi
# ポートがデフォルトの場合はoverride.ymlは不要

# 必要なフォルダを作成
for folder in videos logs models prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

# 現在のバージョンのイメージが存在するかチェック
if docker images | grep -q "textffcut.*${VERSION}"; then
    echo "既存のイメージ textffcut:${VERSION} を使用します。"
fi

# イメージをロード（まだロードされていない場合）
if ! docker images | grep -q "textffcut.*${VERSION}"; then
    echo "Dockerイメージをロードしています（初回のみ）..."
    docker load -i textffcut_v${VERSION}_docker.tar.gz
fi

echo ""
echo "=== 起動設定 ==="
echo "📍 URL: http://localhost:$PORT"
echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
echo ""

# メモリ警告は削除（Docker Desktopに任せる）

echo "アプリケーションを起動しています..."
echo "ブラウザで http://localhost:$PORT を開いています..."
open "http://localhost:$PORT"

# Docker Composeで起動
if [ -f docker-compose.override.yml ]; then
    # override.ymlがある場合（ポート変更時）
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose-simple.yml -f docker-compose.override.yml up
    else
        docker-compose -f docker-compose-simple.yml -f docker-compose.override.yml up
    fi
    rm -f docker-compose.override.yml
else
    # override.ymlがない場合（通常）
    if docker compose version &> /dev/null; then
        docker compose -f docker-compose-simple.yml up
    else
        docker-compose -f docker-compose-simple.yml up
    fi
fi

read -p "Enterキーを押して終了..."
EOF

# ${VERSION}を実際の値に置換
sed -i '' "s/\${VERSION}/${VERSION}/g" release/START.command

# (START_CLEAN.bat は既に作成済み)

# START_CLEAN.command の作成（Mac版クリーンスタート）
cat > release/START_CLEAN.command <<'EOF'
#!/bin/bash
# TextffCut クリーンスタート (Mac版)
# Dockerイメージを再読み込みして起動します

echo "=== TextffCut クリーンスタート (Mac) ==="
echo ""
echo "このスクリプトは以下を実行します:"
echo "- 既存のコンテナを停止"
echo "- Dockerイメージを削除して再読み込み"
echo "- 新しいコンテナを起動"
echo ""
echo "続行しますか？ (y/N): "
read -r response

if [[ ! "$response" =~ ^[Yy]$ ]]; then
    echo "キャンセルしました"
    exit 0
fi

# スクリプトの場所に移動
cd "$(dirname "$0")"

echo ""
echo "1. 既存のコンテナを停止しています..."
docker-compose down 2>/dev/null

echo ""
echo "2. 既存のイメージを削除しています..."
docker images | grep textffcut | awk '{print $3}' | xargs docker rmi -f 2>/dev/null || true

echo ""
echo "3. Dockerイメージを読み込んでいます..."
for file in textffcut_*.tar.gz; do
    if [ -f "$file" ]; then
        echo "   読み込み中: $file"
        docker load -i "$file"
    fi
done

echo ""
echo "4. コンテナを起動しています..."
docker-compose up -d

echo ""
echo "起動を確認中..."
sleep 5

# ヘルスチェック
if curl -s http://localhost:8501 > /dev/null; then
    echo "✅ クリーンスタート完了！"
    echo "🌐 ブラウザで http://localhost:8501 を開いています..."
    open http://localhost:8501
else
    echo "⚠️ アプリケーションの起動に時間がかかっています"
    echo "しばらくお待ちください..."
fi

echo ""
echo "終了するにはEnterキーを押してください"
read
EOF

# 実行権限を付与
chmod +x release/START_CLEAN.command

# ${VERSION}を実際の値に置換
sed -i '' "s/\${VERSION}/${VERSION}/g" release/START.command

# docker-compose.yml の作成（配布用）
cat > release/docker-compose.yml <<EOF
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
      - ./transcriptions:/app/transcriptions
      - ./logs:/app/logs
    environment:
      - TZ=Asia/Tokyo
      - HOST_VIDEOS_PATH=\${HOST_VIDEOS_PATH}
EOF

# docker-compose-simple.yml の作成（配布用）
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
      - ./logs:/app/logs
      - ./models:/home/appuser/.cache
      - ./optimizer_profiles:/home/appuser/.textffcut
      - ./prompts:/app/prompts
    environment:
      - TZ=Asia/Tokyo
      - HOST_VIDEOS_PATH=\${HOST_VIDEOS_PATH}
EOF

# README.txt の作成
cat > release/README.txt <<'EOF'
=====================================
TextffCut
=====================================

動画の文字起こしと切り抜きを効率化するツールです。

【クイックスタート】

1. Docker Desktop を起動
   Docker Desktop がインストールされていない場合は、
   公式サイトからダウンロードしてください。
   https://www.docker.com/products/docker-desktop/

2. TextffCut を起動
   【通常起動（推奨）】
   - Windows: START.bat をダブルクリック
   - macOS: START.command をダブルクリック
   
   【クリーン起動】
   問題が発生した場合や、完全にリセットしたい場合：
   - Windows: START_CLEAN.bat をダブルクリック
   - macOS: START_CLEAN.command をダブルクリック
   ※ クリーン起動は既存のコンテナ・イメージを全て削除するため時間がかかります

3. 使い方
   (1) videos フォルダに動画ファイル（MP4）を入れる
   (2) ブラウザで自動的に開く画面で操作
   (3) 結果は videos フォルダ内に保存される

4. 終了方法
   ターミナル/コマンドプロンプトで Ctrl+C を押す

【トラブルシューティング】

問題が発生した場合:
   - Windows: START_CLEAN.bat をダブルクリック
   - macOS: START_CLEAN.command をダブルクリック
   （Dockerイメージを削除して再読み込みします）

【詳しい使い方】

スクリーンショット付きの詳しい説明は note をご覧ください：
https://note.com/coidemo


【動作環境】
- Docker Desktop 必須
- メモリ 8GB以上推奨（16GB推奨）
- 検証済み: macOS + MP4形式
EOF

# START_CLEAN.command の作成（クリーン起動版）
cat > release/START_CLEAN.command <<'EOF'
#!/bin/bash

echo "==========================================="
echo "TextffCut v${VERSION} クリーン起動"
echo "==========================================="
echo ""

# スクリプトの絶対パスを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# 環境変数を設定
export HOST_VIDEOS_PATH="${SCRIPT_DIR}/videos"

echo "🧹 既存のTextffCutコンテナとイメージをクリーンアップしています..."
echo ""

# textffcutという名前を含むコンテナを停止・削除
echo "▶ コンテナを停止・削除中..."
TEXTFFCUT_CONTAINERS=$(docker ps -a --filter "name=textffcut" --format "{{.Names}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_CONTAINERS" ]; then
    echo "$TEXTFFCUT_CONTAINERS" | while read container; do
        echo "  - $container を停止中..."
        docker stop "$container" >/dev/null 2>&1 || true
        echo "  - $container を削除中..."
        docker rm "$container" >/dev/null 2>&1 || true
    done
fi

# docker-composeで管理されているコンテナも削除
docker-compose -f docker-compose-simple.yml down >/dev/null 2>&1 || true

# textffcutという名前を含むイメージを削除
echo ""
echo "▶ イメージを削除中..."
TEXTFFCUT_IMAGES=$(docker images --filter "reference=*textffcut*" --format "{{.Repository}}:{{.Tag}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_IMAGES" ]; then
    echo "$TEXTFFCUT_IMAGES" | while read image; do
        echo "  - $image を削除中..."
        docker rmi "$image" >/dev/null 2>&1 || true
    done
fi

# ボリュームの削除
echo ""
echo "▶ ボリュームを削除中..."
TEXTFFCUT_VOLUMES=$(docker volume ls --filter "name=textffcut" --format "{{.Name}}" | grep -i textffcut || true)
if [ -n "$TEXTFFCUT_VOLUMES" ]; then
    echo "$TEXTFFCUT_VOLUMES" | while read volume; do
        echo "  - $volume を削除中..."
        docker volume rm "$volume" >/dev/null 2>&1 || true
    done
fi

echo ""
echo "✅ クリーンアップ完了！"
echo ""
echo "==========================================="
echo "TextffCut を起動しています..."
echo "==========================================="
echo ""

# Docker イメージをロード
if [ -f "textffcut_v${VERSION}_docker.tar.gz" ]; then
    echo "📦 Docker イメージを読み込んでいます..."
    echo "（初回は数分かかります）"
    docker load < textffcut_v${VERSION}_docker.tar.gz
    echo ""
else
    echo "❌ Docker イメージファイルが見つかりません。"
    echo "textffcut_v${VERSION}_docker.tar.gz が同じフォルダにあることを確認してください。"
    echo ""
    read -p "Enterキーを押して終了..."
    exit 1
fi

# 必要なフォルダを作成
for folder in videos logs models prompts; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

# システムメモリをチェック
MEMORY_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
echo "💻 システムメモリ: ${MEMORY_GB}GB"

# Docker Desktopに割り当てられたメモリを取得
DOCKER_MEM_BYTES=$(docker system info 2>/dev/null | grep "Total Memory" | awk '{print $3}' | sed 's/GiB//')
if [ -n "$DOCKER_MEM_BYTES" ]; then
    DOCKER_MEM_GB=$(echo "$DOCKER_MEM_BYTES" | awk '{print int($1)}')
else
    DOCKER_MEM_GB=$(( MEMORY_GB / 2 ))
fi

# 推奨メモリ（Docker Desktopの割り当て全体を使用）
RECOMMENDED_MEM=$DOCKER_MEM_GB
if [ $RECOMMENDED_MEM -lt 1 ]; then
    RECOMMENDED_MEM=1
fi

echo "Docker Desktop割り当て: ${DOCKER_MEM_GB}GB"
echo "割り当てメモリ: ${RECOMMENDED_MEM}GB"

# docker-compose.override.ymlは作成しない（メモリ制限は不要）

echo ""
echo "🚀 TextffCut を起動しています..."

# Docker Composeで起動
docker-compose -f docker-compose-simple.yml up -d

# 起動確認
echo ""
echo "⏳ 起動を確認しています..."
sleep 5

if docker ps | grep -q textffcut; then
    echo ""
    echo "✅ TextffCut が正常に起動しました！"
    echo ""
    echo "==========================================="
    echo "📌 アクセス方法"
    echo "==========================================="
    echo ""
    echo "ブラウザで以下のURLを開いてください："
    echo "http://localhost:8501"
    echo ""
    echo "動画ファイルは videos フォルダに入れてください。"
    echo ""
    echo "==========================================="
    echo ""
    
    # ブラウザを開く
    open "http://localhost:8501"
    
    echo "終了するには、このウィンドウを閉じてください。"
    echo "（TextffCutは引き続き実行されます）"
    echo ""
    echo "TextffCutを停止する場合は、Docker Desktop から"
    echo "textffcut コンテナを停止してください。"
else
    echo ""
    echo "❌ TextffCut の起動に失敗しました。"
    echo ""
    echo "Docker Desktop が正常に動作していることを確認してください。"
    echo ""
fi

# overrideファイルを削除
rm -f ./docker-compose.override.yml

read -p "Enterキーを押して終了..."
EOF

# ${VERSION}を実際の値に置換
sed -i '' "s/\${VERSION}/${VERSION}/g" release/START_CLEAN.command

# 実行権限を付与
chmod +x release/START.command
chmod +x release/START_CLEAN.command

echo "✅ 配布用ファイルの作成完了"
echo ""

# 5. ZIPファイルの作成（フォルダ名はTextffCut）
echo "5. ZIPファイルを作成しています..."
cd release

# TextffCutフォルダを作成してファイルを配置
mkdir -p TextffCut
mv textffcut_v${VERSION}_docker.tar.gz TextffCut/
mv START.bat TextffCut/
mv START_CLEAN.bat TextffCut/
mv START.command TextffCut/
mv START_CLEAN.command TextffCut/
mv docker-compose-simple.yml TextffCut/
mv README.txt TextffCut/


# ZIPファイルを作成
zip -r TextffCut_v${VERSION}.zip TextffCut

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
ls -lh TextffCut_v${VERSION}.zip
echo ""
echo "配布用ファイル: release/TextffCut_v${VERSION}.zip"
echo ""
echo "【主な改善点】"
echo "- メモリ自動最適化機能を追加"
echo "- システムメモリに応じた推奨設定"
echo "- メモリ不足時の警告表示"
echo ""