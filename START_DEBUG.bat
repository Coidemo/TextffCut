@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 デバッグ版
echo.

REM 環境変数を設定
set HOST_VIDEOS_PATH=%cd%\videos

echo [1] Docker確認中...
docker version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Docker Desktopが起動していません
    pause
    exit /b 1
)
echo ✅ Docker Desktop: OK

echo.
echo [2] Docker Compose確認中...
docker compose version
if %errorlevel% neq 0 (
    echo ❌ Docker Composeが見つかりません
    echo.
    echo 古いdocker-composeを試します...
    docker-compose version
    if %errorlevel% neq 0 (
        echo ❌ docker-composeも見つかりません
        pause
        exit /b 1
    )
    echo ✅ docker-compose (旧版) を使用します
    set COMPOSE_CMD=docker-compose
) else (
    echo ✅ Docker Compose: OK
    set COMPOSE_CMD=docker compose
)

echo.
echo [3] 必要なフォルダを作成中...
for %%f in (videos logs models) do (
    if not exist %%f (
        echo 📁 %%f フォルダを作成
        mkdir %%f
    )
)

echo.
echo [4] Docker Composeファイルを確認中...
if exist docker-compose-simple.yml (
    echo ✅ docker-compose-simple.yml: 存在
) else (
    echo ❌ docker-compose-simple.yml: 見つかりません
    pause
    exit /b 1
)

echo.
echo [5] Dockerイメージを確認中...
docker images | findstr textffcut:0.9.7
if %errorlevel% neq 0 (
    echo ❌ Dockerイメージがロードされていません
    echo.
    if exist textffcut_v0.9.7_docker.tar.gz (
        echo 📦 イメージファイルを読み込み中...
        docker load -i textffcut_v0.9.7_docker.tar.gz
    ) else (
        echo ❌ textffcut_v0.9.7_docker.tar.gz が見つかりません
        pause
        exit /b 1
    )
)

echo.
echo [6] コンテナを起動します...
echo コマンド: %COMPOSE_CMD% -f docker-compose-simple.yml up
echo.

%COMPOSE_CMD% -f docker-compose-simple.yml up

pause