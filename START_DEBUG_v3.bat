@echo off
chcp 65001 >nul
echo TextffCut v0.9.7 デバッグ版 v3
echo.

REM 現在のディレクトリを表示
echo [0] 現在のディレクトリ:
echo %cd%
echo.
echo ディレクトリ内容:
dir /b
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
echo 新版を試します: docker compose version
docker compose version
if %errorlevel% neq 0 (
    echo ❌ 新版のDocker Composeが見つかりません
    echo.
    echo 旧版を試します: docker-compose version
    docker-compose version
    if %errorlevel% neq 0 (
        echo ❌ docker-composeも見つかりません
        pause
        exit /b 1
    )
    echo ✅ docker-compose (旧版) を使用します
    set COMPOSE_CMD=docker-compose
) else (
    echo ✅ Docker Compose (新版) を使用します
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
        if %errorlevel% neq 0 (
            echo ❌ イメージの読み込みに失敗しました
            pause
            exit /b 1
        )
    ) else (
        echo ❌ textffcut_v0.9.7_docker.tar.gz が見つかりません
        pause
        exit /b 1
    )
) else (
    echo ✅ Dockerイメージ: OK
)

echo.
echo [6] 既存のコンテナを確認中...
docker ps -a --format "table {{.Names}}\t{{.Status}}" | findstr TextffCut
if %errorlevel% equ 0 (
    echo 既存のコンテナを停止・削除します...
    docker stop TextffCut >nul 2>&1
    docker rm TextffCut >nul 2>&1
)

echo.
echo [7] コンテナを起動します...
echo コマンド: %COMPOSE_CMD% -f docker-compose-simple.yml up
echo.

REM ここで一時停止して、設定を確認
echo 以下の設定で起動します:
echo - Docker Compose: %COMPOSE_CMD%
echo - 設定ファイル: docker-compose-simple.yml
echo - ホストボリューム: %HOST_VIDEOS_PATH%
echo.
echo 続行するには何かキーを押してください...
pause >nul

%COMPOSE_CMD% -f docker-compose-simple.yml up

echo.
echo 終了コード: %errorlevel%
pause