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

# START.bat の作成（Windows版もメモリ最適化対応）
cat > release/START.bat <<EOF
@echo off
echo TextffCut v${VERSION} を起動します...
echo.

REM 環境変数を設定
set HOST_VIDEOS_PATH=%cd%\videos

REM ===========================================
REM メモリ最適化設定
REM ===========================================
echo [メモリ] システムメモリを確認しています...

REM Windowsでのメモリ取得（MB単位で取得してGB変換）
for /f "tokens=2 delims==" %%i in ('wmic computersystem get TotalPhysicalMemory /value ^| findstr "="') do set TOTAL_MEM_BYTES=%%i
set /a TOTAL_MEM_GB=%TOTAL_MEM_BYTES:~0,-9%+1

REM 利用可能メモリを取得
for /f "skip=1" %%i in ('wmic OS get FreePhysicalMemory') do (
    set FREE_MEM_KB=%%i
    goto :gotfreemem
)
:gotfreemem
set /a AVAILABLE_MEM_GB=%FREE_MEM_KB%/1048576

echo    総メモリ: %TOTAL_MEM_GB%GB
echo    利用可能: %AVAILABLE_MEM_GB%GB

REM 推奨メモリ設定を計算
if %TOTAL_MEM_GB% geq 32 (
    set RECOMMENDED_MEM=16
    set MIN_MEM=8
    set MEMORY_MODE=高性能
) else if %TOTAL_MEM_GB% geq 16 (
    set RECOMMENDED_MEM=12
    set MIN_MEM=6
    set MEMORY_MODE=バランス
) else if %TOTAL_MEM_GB% geq 12 (
    set RECOMMENDED_MEM=8
    set MIN_MEM=4
    set MEMORY_MODE=標準
) else if %TOTAL_MEM_GB% geq 8 (
    set RECOMMENDED_MEM=6
    set MIN_MEM=3
    set MEMORY_MODE=省メモリ
) else (
    set RECOMMENDED_MEM=4
    set MIN_MEM=2
    set MEMORY_MODE=最小
)

REM 利用可能メモリが推奨値より少ない場合は調整
if %AVAILABLE_MEM_GB% lss %RECOMMENDED_MEM% (
    set /a ADJUSTED_MEM=%AVAILABLE_MEM_GB%*70/100
    if %ADJUSTED_MEM% lss %MIN_MEM% (
        set RECOMMENDED_MEM=%MIN_MEM%
    ) else (
        set RECOMMENDED_MEM=%ADJUSTED_MEM%
    )
    echo    ※ 利用可能メモリが少ないため、%RECOMMENDED_MEM%GBに調整しました
)

echo    推奨設定: %MEMORY_MODE%モード (%RECOMMENDED_MEM%GB)
echo.

REM docker-compose.override.ymlを生成
echo version: '3.8' > docker-compose.override.yml
echo services: >> docker-compose.override.yml
echo   textffcut: >> docker-compose.override.yml
echo     deploy: >> docker-compose.override.yml
echo       resources: >> docker-compose.override.yml
echo         limits: >> docker-compose.override.yml
echo           memory: %RECOMMENDED_MEM%g >> docker-compose.override.yml
echo         reservations: >> docker-compose.override.yml
echo           memory: %MIN_MEM%g >> docker-compose.override.yml
echo     environment: >> docker-compose.override.yml
echo       - TEXTFFCUT_MEMORY_MODE=%MEMORY_MODE% >> docker-compose.override.yml
echo       - TEXTFFCUT_MEMORY_LIMIT=%RECOMMENDED_MEM%g >> docker-compose.override.yml

REM ===========================================
REM Docker Desktop確認
REM ===========================================
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo エラー: Docker Desktopが起動していません。
    echo Docker Desktopを起動してから、もう一度実行してください。
    echo.
    echo ヒント: Docker Desktopのメモリ設定を確認してください
    echo         Settings → Resources → Memory を %RECOMMENDED_MEM%GB 以上に設定
    echo.
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

REM 必要なフォルダを作成
for %%f in (videos logs) do (
    if not exist %%f (
        echo [フォルダ] %%f フォルダを作成しています...
        mkdir %%f
    )
)

REM 既存のTextffCutコンテナを停止・削除
docker ps -a --format "{{.Names}}" | findstr "^TextffCut$" >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存のTextffCutコンテナを停止・削除しています...
    docker stop TextffCut 2>nul
    docker rm TextffCut 2>nul
)

REM 現在のバージョンのイメージが存在するかチェック
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% equ 0 (
    echo 既存のイメージ textffcut:${VERSION} を使用します。
) else (
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
)

REM イメージをロード（まだロードされていない場合）
docker images | findstr textffcut:${VERSION} >nul 2>&1
if %errorlevel% neq 0 (
    echo Dockerイメージをロードしています（初回のみ）...
    docker load -i textffcut_v${VERSION}_docker.tar.gz
)

echo.
echo ===========================================
echo 起動設定
echo ===========================================
echo    URL: http://localhost:8501
echo    メモリ: %MEMORY_MODE%モード (%RECOMMENDED_MEM%GB)
echo    動画フォルダ: %cd%\videos
echo.

REM メモリ不足の警告
if %AVAILABLE_MEM_GB% lss 4 (
    echo ※※※ 警告 ※※※
    echo    利用可能メモリが4GB未満です
    echo    大きな動画の処理に失敗する可能性があります
    echo    他のアプリケーションを終了することを推奨します
    echo.
    echo    ヒント: 2時間以上の動画は12GB以上推奨
    echo.
)

echo アプリケーションを起動しています...
echo ブラウザで http://localhost:8501 を開いています...
start http://localhost:8501

REM overrideファイルと一緒に起動
docker-compose -f ./docker-compose-simple.yml -f ./docker-compose.override.yml up

REM overrideファイルを削除
del /f docker-compose.override.yml 2>nul

pause
EOF

# START.command の作成（メモリ最適化版）
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
echo "💾 システムメモリを確認しています..."

# macOSでのメモリ取得
TOTAL_MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
# 利用可能メモリを計算（ページ数 × ページサイズ）
FREE_PAGES=$(vm_stat | grep "Pages free" | awk '{print $3}' | sed 's/\.//')
INACTIVE_PAGES=$(vm_stat | grep "Pages inactive" | awk '{print $3}' | sed 's/\.//')
PURGEABLE_PAGES=$(vm_stat | grep "Pages purgeable" | awk '{print $3}' | sed 's/\.//')
AVAILABLE_PAGES=$((FREE_PAGES + INACTIVE_PAGES + PURGEABLE_PAGES))
AVAILABLE_MEM_GB=$(( AVAILABLE_PAGES * 4096 / 1024 / 1024 / 1024 ))

echo "   総メモリ: ${TOTAL_MEM_GB}GB"
echo "   利用可能: ${AVAILABLE_MEM_GB}GB"

# 推奨メモリ設定を計算（改訂版）
if [ $TOTAL_MEM_GB -ge 32 ]; then
    RECOMMENDED_MEM=16
    MIN_MEM=8
    MEMORY_MODE="高性能"
elif [ $TOTAL_MEM_GB -ge 16 ]; then
    RECOMMENDED_MEM=12
    MIN_MEM=6
    MEMORY_MODE="バランス"
elif [ $TOTAL_MEM_GB -ge 12 ]; then
    RECOMMENDED_MEM=8
    MIN_MEM=4
    MEMORY_MODE="標準"
elif [ $TOTAL_MEM_GB -ge 8 ]; then
    RECOMMENDED_MEM=6
    MIN_MEM=3
    MEMORY_MODE="省メモリ"
else
    RECOMMENDED_MEM=4
    MIN_MEM=2
    MEMORY_MODE="最小"
fi

# 利用可能メモリが推奨値より少ない場合は調整（70%を上限）
if [ $AVAILABLE_MEM_GB -lt $RECOMMENDED_MEM ]; then
    ADJUSTED_MEM=$(( AVAILABLE_MEM_GB * 70 / 100 ))
    if [ $ADJUSTED_MEM -lt $MIN_MEM ]; then
        RECOMMENDED_MEM=$MIN_MEM
    else
        RECOMMENDED_MEM=$ADJUSTED_MEM
    fi
    echo "   ⚠️  利用可能メモリが少ないため、${RECOMMENDED_MEM}GBに調整しました"
fi

echo "   推奨設定: ${MEMORY_MODE}モード (${RECOMMENDED_MEM}GB)"
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
        reservations:
          memory: ${MIN_MEM}g
    environment:
      - TEXTFFCUT_MEMORY_MODE=${MEMORY_MODE}
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
for folder in videos logs; do
    if [ ! -d "$folder" ]; then
        echo "📁 $folder フォルダを作成しています..."
        mkdir -p "$folder"
    fi
done

# 現在のバージョンのイメージが存在するかチェック
if docker images | grep -q "textffcut.*${VERSION}"; then
    echo "既存のイメージ textffcut:${VERSION} を使用します。"
else
    # 古いバージョンのイメージを削除
    echo "古いバージョンのイメージをクリーンアップしています..."
    
    # まず古いバージョンのコンテナを全て削除
    echo "古いバージョンのコンテナを削除しています..."
    docker ps -a --format "{{.Names}} {{.Image}}" | grep "textffcut:" | grep -v ":${VERSION}" | while read name image; do
        if [ -n "$name" ]; then
            echo "コンテナ削除中: $name ($image)"
            docker rm -f "$name" 2>/dev/null || true
        fi
    done
    
    # 古いバージョンのイメージを削除（強制削除）
    OLD_IMAGES=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^textffcut:" | grep -v ":${VERSION}$" || true)
    if [ -n "$OLD_IMAGES" ]; then
        echo "$OLD_IMAGES" | while read image; do
            if [ -n "$image" ]; then
                echo "削除中: $image"
                docker rmi -f "$image" 2>/dev/null || true
            fi
        done
    else
        echo "削除する古いイメージはありません。"
    fi
fi

# イメージをロード（まだロードされていない場合）
if ! docker images | grep -q "textffcut.*${VERSION}"; then
    echo "Dockerイメージをロードしています（初回のみ）..."
    docker load -i textffcut_v${VERSION}_docker.tar.gz
fi

echo ""
echo "=== 起動設定 ==="
echo "📍 URL: http://localhost:$PORT"
echo "💾 メモリ: ${MEMORY_MODE}モード (${RECOMMENDED_MEM}GB)"
echo "📁 動画フォルダ: ${SCRIPT_DIR}/videos"
echo ""

# メモリ不足の警告
if [ $AVAILABLE_MEM_GB -lt 4 ]; then
    echo "⚠️  警告: 利用可能メモリが4GB未満です"
    echo "   大きな動画の処理に失敗する可能性があります"
    echo "   他のアプリケーションを終了することを推奨します"
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
   - Windows: START.bat をダブルクリック
   - macOS: START.command をダブルクリック   

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