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

# START.bat の作成（通常起動 - 高速版）
cat > release/START.bat <<EOF
@echo off
chcp 65001 >nul
echo Starting TextffCut v${VERSION}...
echo.

REM Set environment variables
set HOST_VIDEOS_PATH=%cd%\videos

REM ===========================================
REM Memory optimization settings
REM ===========================================
echo [Memory] Checking Docker Desktop memory settings...

REM Get memory allocated to Docker Desktop
for /f "tokens=3" %%i in ('docker system info 2^>nul ^| findstr "Total Memory"') do (
    set DOCKER_MEM_STR=%%i
    goto :gotdockermem
)
:gotdockermem

REM Convert GiB to GB
if defined DOCKER_MEM_STR (
    REM Remove GiB and get numeric value only (truncate decimal)
    set DOCKER_MEM_STR=%DOCKER_MEM_STR:GiB=%
    for /f "tokens=1 delims=." %%a in ("%DOCKER_MEM_STR%") do set DOCKER_MEM_GB=%%a
) else (
    REM If unable to get, estimate from PC physical memory
    for /f "tokens=2 delims==" %%i in ('wmic computersystem get TotalPhysicalMemory /value ^| findstr "="') do set TOTAL_MEM_BYTES=%%i
    set /a TOTAL_MEM_GB=%TOTAL_MEM_BYTES:~0,-9%+1
    REM Docker Desktop default is about half of physical memory
    set /a DOCKER_MEM_GB=%TOTAL_MEM_GB%/2
    echo    * Could not get Docker Desktop memory settings
    echo    Estimated from physical memory (%TOTAL_MEM_GB%GB): %DOCKER_MEM_GB%GB
)

echo    Docker Desktop allocated: %DOCKER_MEM_GB%GB

REM Calculate recommended value based on Docker Desktop allocated memory (80% baseline)
set /a RECOMMENDED_MEM=%DOCKER_MEM_GB%*80/100

REM Ensure minimum 1GB (safety for minimal environments)
if %RECOMMENDED_MEM% lss 1 (
    set RECOMMENDED_MEM=1
)

REM Check that recommended value doesn't exceed Docker allocation (just in case)
if %RECOMMENDED_MEM% gtr %DOCKER_MEM_GB% (
    set RECOMMENDED_MEM=%DOCKER_MEM_GB%
    echo    * Adjusted to %RECOMMENDED_MEM%GB to not exceed Docker Desktop allocation
)

echo    Allocated memory: %RECOMMENDED_MEM%GB
echo.

REM Generate docker-compose.override.yml
echo version: '3.8' > docker-compose.override.yml
echo services: >> docker-compose.override.yml
echo   textffcut: >> docker-compose.override.yml
echo     deploy: >> docker-compose.override.yml
echo       resources: >> docker-compose.override.yml
echo         limits: >> docker-compose.override.yml
echo           memory: %RECOMMENDED_MEM%g >> docker-compose.override.yml
echo     environment: >> docker-compose.override.yml
echo       - TEXTFFCUT_MEMORY_LIMIT=%RECOMMENDED_MEM%g >> docker-compose.override.yml

REM ===========================================
REM Check Docker Desktop
REM ===========================================
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Docker Desktop is not running.
    echo Please start Docker Desktop and try again.
    echo.
    echo Hint: Check Docker Desktop memory settings
    echo       Settings - Resources - Memory should be %RECOMMENDED_MEM%GB or more
    echo.
    pause
    exit /b 1
)

REM Create necessary folders
for %%f in (videos logs models) do (
    if not exist %%f (
        echo Creating %%f folder...
        mkdir %%f
    )
)

REM Check existing TextffCut container
docker ps --format "{{.Names}}" | findstr "^TextffCut$" >nul 2>&1
if %errorlevel% equ 0 (
    echo Existing TextffCut container is running.
    echo.
    echo ===========================================
    echo Startup Configuration
    echo ===========================================
    echo    URL: http://localhost:8501
    echo    Memory allocation: %RECOMMENDED_MEM%GB
    echo    Video folder: %cd%\videos
    echo.
    echo Opening http://localhost:8501 in browser...
    start http://localhost:8501
    echo.
    echo Already running, using existing container.
    echo Press Ctrl+C to stop.
    pause
    exit /b 0
)

REM Check for stopped container
docker ps -a --format "{{.Names}}" | findstr "^TextffCut$" >nul 2>&1
if %errorlevel% equ 0 (
    echo Restarting stopped TextffCut container...
    docker start TextffCut
    echo.
    echo ===========================================
    echo Startup Configuration
    echo ===========================================
    echo    URL: http://localhost:8501
    echo    Memory allocation: %RECOMMENDED_MEM%GB
    echo    Video folder: %cd%\videos
    echo.
    echo Opening http://localhost:8501 in browser...
    start http://localhost:8501
    
    REM Show logs
    docker logs -f TextffCut
    pause
    exit /b 0
)

REM Load image (if not already loaded)
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% neq 0 (
    echo Loading Docker image (first time only)...
    docker load -i textffcut_v${VERSION}_docker.tar.gz
)

echo.
echo ===========================================
echo Startup Configuration
echo ===========================================
echo    URL: http://localhost:8501
echo    Memory allocation: %RECOMMENDED_MEM%GB
echo    Video folder: %cd%\videos
echo.

echo Starting application...
echo Opening http://localhost:8501 in browser...
start http://localhost:8501

REM Check Docker Compose version and start
docker compose version >nul 2>&1
if errorlevel 1 (
    REM Use old version
    docker-compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up
) else (
    REM Use new version
    docker compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up
)

REM Delete override file
del /f docker-compose.override.yml 2>nul

pause
EOF

# START_CLEAN.bat の作成（クリーン起動版）
cat > release/START_CLEAN.bat <<EOF
@echo off
chcp 65001 >nul
echo Starting TextffCut v${VERSION}...
echo.

REM Set environment variables
set HOST_VIDEOS_PATH=%cd%\videos

REM ===========================================
REM Cleanup existing TextffCut containers and images
REM ===========================================
echo [Cleanup] Removing existing TextffCut containers and images...

REM Stop and remove containers containing textffcut in name
echo    Stopping and removing containers...
for /f "tokens=*" %%i in ('docker ps -a --format "{{.Names}}" ^| findstr /i textffcut') do (
    echo    - %%i
    docker stop %%i >nul 2>&1
    docker rm %%i >nul 2>&1
)

REM Remove containers managed by docker-compose
if exist docker-compose-simple.yml (
    REM Check Docker Compose version
    docker compose version >nul 2>&1
    if errorlevel 1 (
        docker-compose -f docker-compose-simple.yml down >nul 2>&1
    ) else (
        docker compose -f docker-compose-simple.yml down >nul 2>&1
    )
)

REM Remove images containing textffcut in name (except current version)
echo    Removing images...
for /f "tokens=*" %%i in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr /i textffcut ^| findstr /v ":%VERSION%$"') do (
    echo    - %%i
    docker rmi %%i >nul 2>&1
)

REM Remove volumes
echo    Removing volumes...
for /f "tokens=*" %%i in ('docker volume ls --format "{{.Name}}" ^| findstr /i textffcut') do (
    echo    - %%i
    docker volume rm %%i >nul 2>&1
)

echo    Cleanup complete
echo.

REM ===========================================
REM Memory optimization settings
REM ===========================================
echo [Memory] Checking Docker Desktop memory settings...

REM Get memory allocated to Docker Desktop
for /f "tokens=3" %%i in ('docker system info 2^>nul ^| findstr "Total Memory"') do (
    set DOCKER_MEM_STR=%%i
    goto :gotdockermem
)
:gotdockermem

REM Convert GiB to GB
if defined DOCKER_MEM_STR (
    REM Remove GiB and get numeric value only (truncate decimal)
    set DOCKER_MEM_STR=%DOCKER_MEM_STR:GiB=%
    for /f "tokens=1 delims=." %%a in ("%DOCKER_MEM_STR%") do set DOCKER_MEM_GB=%%a
) else (
    REM If unable to get, estimate from PC physical memory
    for /f "tokens=2 delims==" %%i in ('wmic computersystem get TotalPhysicalMemory /value ^| findstr "="') do set TOTAL_MEM_BYTES=%%i
    set /a TOTAL_MEM_GB=%TOTAL_MEM_BYTES:~0,-9%+1
    REM Docker Desktop default is about half of physical memory
    set /a DOCKER_MEM_GB=%TOTAL_MEM_GB%/2
    echo    * Could not get Docker Desktop memory settings
    echo    Estimated from physical memory (%TOTAL_MEM_GB%GB): %DOCKER_MEM_GB%GB
)

echo    Docker Desktop allocated: %DOCKER_MEM_GB%GB

REM Calculate recommended value based on Docker Desktop allocated memory (80% baseline)
set /a RECOMMENDED_MEM=%DOCKER_MEM_GB%*80/100

REM Ensure minimum 1GB (safety for minimal environments)
if %RECOMMENDED_MEM% lss 1 (
    set RECOMMENDED_MEM=1
)

REM Check that recommended value doesn't exceed Docker allocation (just in case)
if %RECOMMENDED_MEM% gtr %DOCKER_MEM_GB% (
    set RECOMMENDED_MEM=%DOCKER_MEM_GB%
    echo    * Adjusted to %RECOMMENDED_MEM%GB to not exceed Docker Desktop allocation
)

echo    Allocated memory: %RECOMMENDED_MEM%GB
echo.

REM Generate docker-compose.override.yml
echo version: '3.8' > docker-compose.override.yml
echo services: >> docker-compose.override.yml
echo   textffcut: >> docker-compose.override.yml
echo     deploy: >> docker-compose.override.yml
echo       resources: >> docker-compose.override.yml
echo         limits: >> docker-compose.override.yml
echo           memory: %RECOMMENDED_MEM%g >> docker-compose.override.yml
echo     environment: >> docker-compose.override.yml
echo       - TEXTFFCUT_MEMORY_LIMIT=%RECOMMENDED_MEM%g >> docker-compose.override.yml

REM ===========================================
REM Check Docker Desktop
REM ===========================================
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Docker Desktop is not running.
    echo Please start Docker Desktop and try again.
    echo.
    echo Hint: Check Docker Desktop memory settings
    echo       Settings - Resources - Memory should be %RECOMMENDED_MEM%GB or more
    echo.
    pause
    exit /b 1
)

REM Check if any container is using port 8501
docker ps --format "table {{.Names}}	{{.Ports}}" | findstr "8501" >nul 2>&1
if %errorlevel% equ 0 (
    echo Warning: Port 8501 is already in use.
    echo Existing containers:
    docker ps --format "table {{.Names}}	{{.Ports}}" | findstr "8501"
    echo.
    set /p REPLY=Stop existing containers and start? (y/n): 
    if /i "%REPLY%"=="y" (
        REM Stop containers using port 8501
        for /f "tokens=1" %%i in ('docker ps --format "{{.Names}}"') do (
            docker port %%i | findstr "8501" >nul 2>&1
            if %errorlevel% equ 0 (
                echo Stopping: %%i
                docker stop %%i
            )
        )
    ) else (
        echo Startup cancelled.
        pause
        exit /b 0
    )
)

REM Create necessary folders
for %%f in (videos logs models) do (
    if not exist %%f (
        echo Creating %%f folder...
        mkdir %%f
    )
)

REM Stop and remove existing TextffCut container
docker ps -a --format "{{.Names}}" | findstr "^TextffCut$" >nul 2>&1
if %errorlevel% equ 0 (
    echo Stopping and removing existing TextffCut container...
    docker stop TextffCut 2>nul
    docker rm TextffCut 2>nul
)

REM Check if current version image exists
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% equ 0 (
    echo Using existing image textffcut:${VERSION}.
) else (
    REM Remove old version images
    echo Cleaning up old version images...
    
    REM First remove all old version containers
    echo Removing old version containers...
    for /f "tokens=1,2" %%a in ('docker ps -a --format "{{.Names}} {{.Image}}" ^| findstr "textffcut:" ^| findstr /v ":${VERSION}"') do (
        echo Removing container: %%a (%%b)
        docker rm -f %%a 2>nul
    )
    
    REM Remove old version images (force removal)
    set OLD_IMAGES_FOUND=0
    for /f "tokens=*" %%a in ('docker images --format "{{.Repository}}:{{.Tag}}" ^| findstr "^textffcut:" ^| findstr /v ":${VERSION}$"') do (
        set OLD_IMAGES_FOUND=1
        echo Removing: %%a
        docker rmi -f %%a 2>nul
    )
    if %OLD_IMAGES_FOUND% equ 0 (
        echo No old images to remove.
    )
)

REM Load image (if not already loaded)
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% neq 0 (
    echo Loading Docker image (first time only)...
    docker load -i textffcut_v${VERSION}_docker.tar.gz
)

echo.
echo ===========================================
echo Startup Configuration
echo ===========================================
echo    URL: http://localhost:8501
echo    Memory allocation: %RECOMMENDED_MEM%GB
echo    Video folder: %cd%\videos
echo.

REM Memory shortage warning
if %AVAILABLE_MEM_GB% lss 4 (
    echo *** WARNING ***
    echo    Available memory is less than 4GB
    echo    Processing large videos may fail
    echo    Recommend closing other applications
    echo.
    echo    Hint: Videos over 2 hours need 12GB+ memory
    echo.
)

echo Starting application...
echo Opening http://localhost:8501 in browser...
start http://localhost:8501

REM Check Docker Compose version and start
docker compose version >nul 2>&1
if errorlevel 1 (
    REM Use old version
    docker-compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up
) else (
    REM Use new version
    docker compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up
)

REM Delete override file
del /f docker-compose.override.yml 2>nul

pause
EOF

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

# ===========================================
# メモリ最適化設定
# ===========================================
echo "💾 Docker Desktopのメモリ設定を確認しています..."

# Docker Desktopに割り当てられたメモリを取得
DOCKER_MEM_BYTES=$(docker system info 2>/dev/null | grep "Total Memory" | awk '{print $3}' | sed 's/GiB//')
if [ -n "$DOCKER_MEM_BYTES" ]; then
    # GiBからGBに変換（小数点以下切り捨て）
    DOCKER_MEM_GB=$(echo "$DOCKER_MEM_BYTES" | awk '{print int($1)}')
else
    # 取得できない場合はMacの物理メモリから推定
    TOTAL_MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
    # Docker Desktopのデフォルトは物理メモリの半分程度
    DOCKER_MEM_GB=$(( TOTAL_MEM_GB / 2 ))
    echo "   ⚠️  Docker Desktopのメモリ設定を取得できませんでした"
    echo "   物理メモリ(${TOTAL_MEM_GB}GB)から推定: ${DOCKER_MEM_GB}GB"
fi

echo "   Docker Desktop割り当て: ${DOCKER_MEM_GB}GB"

# Docker Desktopの割り当てメモリに基づいて推奨値を計算（80%を基本）
RECOMMENDED_MEM=$(( DOCKER_MEM_GB * 80 / 100 ))

# 最低1GBは確保（極小環境用の安全策）
if [ $RECOMMENDED_MEM -lt 1 ]; then
    RECOMMENDED_MEM=1
fi

# 推奨値がDocker割り当てを超えないようにチェック（念のため）
if [ $RECOMMENDED_MEM -gt $DOCKER_MEM_GB ]; then
    RECOMMENDED_MEM=$DOCKER_MEM_GB
    echo "   ⚠️  Docker Desktop割り当てを超えないよう、${RECOMMENDED_MEM}GBに調整しました"
fi

echo "   割り当てメモリ: ${RECOMMENDED_MEM}GB"
echo ""

# docker-compose.override.ymlを生成（メモリ制限を追加）
cat > docker-compose.override.yml <<OVERRIDE_EOF
version: '3.8'
services:
  textffcut:
    deploy:
      resources:
        limits:
          memory: ${RECOMMENDED_MEM}g
    environment:
      - TEXTFFCUT_MEMORY_LIMIT=${RECOMMENDED_MEM}g
OVERRIDE_EOF

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
    echo "   2. Memory を ${RECOMMENDED_MEM}GB 以上に設定"
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
    echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
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
    echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
    echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
    echo ""
    echo "ブラウザで http://localhost:8501 を開いています..."
    open "http://localhost:8501"
    
    # ログを表示
    docker logs -f TextffCut
    read -p "Enterキーを押して終了..."
    exit 0
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
        if [[ "$CONTAINER_USING_PORT" == textffcut* ]] || [[ "$CONTAINER_USING_PORT" == "TextffCut" ]]; then
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

# 必要なフォルダを作成
for folder in videos logs models; do
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
echo "💾 メモリ割り当て: ${RECOMMENDED_MEM}GB"
echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
echo ""

# メモリ不足の警告
if [ $RECOMMENDED_MEM -lt 4 ]; then
    echo "⚠️  警告: 割り当てメモリが4GB未満です"
    echo "   大きな動画の処理に失敗する可能性があります"
    echo "   Docker Desktopのメモリ設定を増やすか、他のアプリケーションを終了してください"
    echo ""
    echo "   ヒント: 2時間以上の動画は12GB以上推奨"
    echo ""
fi

echo "アプリケーションを起動しています..."
echo "ブラウザで http://localhost:$PORT を開いています..."
open "http://localhost:$PORT"

if [ -n "$TEXTFFCUT_PORT" ]; then
    # docker-compose.ymlを一時的に作成（ポート変更対応）
    sed "s/8501:8501/$TEXTFFCUT_PORT:8501/g" ./docker-compose-simple.yml > ./docker-compose-temp.yml
    
    # overrideファイルと一緒に起動
    docker-compose -f ./docker-compose-temp.yml -f ./docker-compose.override.yml up
    
    # 一時ファイルを削除
    rm -f ./docker-compose-temp.yml
    rm -f ./docker-compose.override.yml
else
    # overrideファイルと一緒に起動
    docker-compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up
    
    # overrideファイルを削除
    rm -f ./docker-compose.override.yml
fi

read -p "Enterキーを押して終了..."
EOF

# ${VERSION}を実際の値に置換
sed -i '' "s/\${VERSION}/${VERSION}/g" release/START.command

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
      - ./logs:/app/logs
      - ./models:/home/appuser/.cache
      - ./optimizer_profiles:/home/appuser/.textffcut
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
for folder in videos logs models; do
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

# 推奨メモリを計算
RECOMMENDED_MEM=$(( DOCKER_MEM_GB * 80 / 100 ))
if [ $RECOMMENDED_MEM -lt 1 ]; then
    RECOMMENDED_MEM=1
fi

echo "Docker Desktop割り当て: ${DOCKER_MEM_GB}GB"
echo "割り当てメモリ: ${RECOMMENDED_MEM}GB"

# docker-compose.override.ymlを生成
cat > docker-compose.override.yml <<OVERRIDE_EOF
version: '3.8'
services:
  textffcut:
    deploy:
      resources:
        limits:
          memory: ${RECOMMENDED_MEM}g
    environment:
      - TEXTFFCUT_MEMORY_LIMIT=${RECOMMENDED_MEM}g
OVERRIDE_EOF

echo ""
echo "🚀 TextffCut を起動しています..."

# Docker Composeで起動
docker-compose -f docker-compose-simple.yml -f docker-compose.override.yml up -d

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

echo "Done: Distribution files created successfully"
echo ""

# 5. Create ZIP file (folder name is TextffCut)
echo "5. Creating ZIP file..."
cd release

# Create TextffCut folder and place files
mkdir -p TextffCut
mv textffcut_v${VERSION}_docker.tar.gz TextffCut/
mv START.bat TextffCut/
mv START_CLEAN.bat TextffCut/
mv START.command TextffCut/
mv START_CLEAN.command TextffCut/
mv docker-compose-simple.yml TextffCut/
mv README.txt TextffCut/

# Create ZIP file
zip -r TextffCut_v${VERSION}.zip TextffCut

# Remove temporary folder (keep only ZIP file)
rm -rf TextffCut

echo "Done: ZIP file created successfully"
echo ""

# 6. Check file size
echo "=========================================="
echo "Build complete!"
echo "=========================================="
echo ""
echo "Generated file:"
ls -lh TextffCut_v${VERSION}.zip
echo ""
echo "Distribution file: release/TextffCut_v${VERSION}.zip"
echo ""
echo "[Key improvements]"
echo "- Added automatic memory optimization"
echo "- Recommended settings based on system memory"
echo "- Memory shortage warning display"
echo ""